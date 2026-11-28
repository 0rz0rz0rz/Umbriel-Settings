--!nonstrict
-- Community shaders on the Effects page: Noctalia's community-umbriel-shaders catalogue by kind, with previews.
-- **Use** downloads into the private cache only, then adds the include and the effect's settings (its global
-- selector, or an animation's events) to the draft; **Install** only adds the include, so the effect can be picked
-- per window rule, output or pool. The reviewed save copies the files next to the config, and a later save that no
-- longer includes them removes them. Using an effect drops the effect of its kind it took over from (once nothing
-- names it any more), so saving deletes the old one; **Remove all** drops every effect of the shown kind. Rows come 12 at first, then 6 more each time the
-- page is scrolled to the bottom (or **Show 6 more**). Nothing goes on the network until the user asks (never in
-- offline mode).
local kit = require("../ui/kit.luau")

local M = {}

local INCLUDE, OPTIONAL = "include.files", "include.optional.files"
local KINDS = { { "window", "Window" }, { "border", "Border" }, { "screen", "Screen" }, { "cursor", "Cursor" },
                { "animation", "Animation" } }
-- What Use and Install mean for each kind, for people new to shaders (a line under the kinds, button tooltips).
local HINTS = {
  window = { use = "Use it for every window", where = "for single apps under Window rules",
             line = "Use turns an effect on for every window. Install only adds it, so you can pick it for single "
               .. "apps under Window rules." },
  border = { use = "Use it for every window border", where = "for single apps under Window rules",
             line = "Use turns a border effect on for every window. Install only adds it, so you can pick it for "
               .. "single apps under Window rules." },
  screen = { use = "Use it for the whole screen", where = "for one display under Outputs",
             line = "Use turns a screen effect on for every display. Install only adds it, so you can pick it for "
               .. "one display under Outputs." },
  cursor = { use = "Use it for the mouse pointer", where = "in an effect pool",
             line = "Use turns a cursor effect on. Install only adds it, so you can pick it later or in an effect "
               .. "pool." },
  animation = { use = "Use it for the animations it was made for", where = "for single animations under Animation",
                line = "Use turns an animation effect on for the events it was made for (opening windows, "
                  .. "switching workspaces, …); effects for different events work side by side. Install only adds "
                  .. "it, so you can pick it under Animation." },
}
local FIRST, STEP = 12, 6  -- rows shown at first, rows added per scroll to the bottom or "Show more"
local CAP = 72  -- at most (the largest kind has 67): one render stays inside Noctalia's 25 ms
local NEAR_BOTTOM = 160  -- px from the end of the page that load more
-- The catalogue's previews are 3:2 (animations 16:10): shown whole (contain), never cropped, since a border
-- effect is only at the edge. A click opens the large one under the row.
local PREVIEW_W, PREVIEW_H = 144, 96
local LARGE_W, LARGE_H = 480, 320

local function offline(ctx)
  if ctx.isApp or type(noctalia.getSetting) ~= "function" then return false end
  return noctalia.getSetting("shell.offline_mode") == true
end

local function list(value) return type(value) == "table" and value or {} end

local function has(entries, include)
  for _, entry in ipairs(entries) do
    if entry == include or entry == "./" .. include then return true end
  end
  return false
end

-- Whether the draft (or, with `saved`, the file) includes the effect.
local function included(store, row, saved)
  for _, fid in ipairs({ INCLUDE, OPTIONAL }) do
    local value
    if saved then value = store.state.fields[fid] else value = store.value(fid) end
    if has(list(value), row.include) then return true end
  end
  return false
end

-- Whether every setting the effect turns on already has its value in the draft.
local function applied(store, row)
  for key, value in pairs(row.settings or {}) do
    if store.meta.fields[key] and store.value(key) ~= value then return false end
  end
  return true
end

local function presetSet(row)
  local set = {}
  for _, name in ipairs(row.presets or {}) do set[name] = true end
  return set
end

-- The draft's string values, once per edit: exact values, plus those that may quote names (pool `choose` arrays).
local stringsCache = {}
local function draftStrings(store)
  if stringsCache.serial == store.serial and stringsCache.state == store.state then return stringsCache end
  local exact, quoted = {}, {}
  local function add(value)
    if type(value) ~= "string" then return end
    exact[value] = true
    if string.find(value, '"', 1, true) then table.insert(quoted, value) end
  end
  for fid in pairs(store.meta.fields) do add((store.value(fid))) end
  for _, items in pairs(store.entries or {}) do
    for _, item in ipairs(items) do
      for _, value in pairs(item.values or {}) do add(value) end
    end
  end
  stringsCache = { serial = store.serial, state = store.state, exact = exact, quoted = quoted }
  return stringsCache
end

-- Whether any value in the draft names one of `presets`: page fields, list entries (rules, outputs, presets) and
-- pool `choose` arrays.
local function referenced(store, presets)
  local strings = draftStrings(store)
  for name in pairs(presets) do
    if strings.exact[name] then return true end
    for _, value in ipairs(strings.quoted) do
      if string.find(value, '"' .. name .. '"', 1, true) then return true end
    end
  end
  return false
end

local function applySettings(ctx, row)
  local store, skipped = ctx.store, {}
  for key, value in pairs(row.settings or {}) do
    if store.meta.fields[key] then store.setField(key, value) else table.insert(skipped, key) end
  end
  if #skipped > 0 then
    table.sort(skipped)
    ctx.flash(row.name .. " also wants " .. table.concat(skipped, ", ") .. ", which this page can't set.", "warning")
  end
end

local function state(ctx) return ctx.view.shaders end

local function dropInclude(store, row)
  for _, fid in ipairs({ INCLUDE, OPTIONAL }) do
    local before, kept = list(store.value(fid)), {}
    for _, entry in ipairs(before) do
      if entry ~= row.include and entry ~= "./" .. row.include then table.insert(kept, entry) end
    end
    if #kept ~= #before then store.setField(fid, kept) end
  end
end

-- Drops the include and every selector set to one of its presets (a save then removes the files).
local function removeRow(store, row)
  local presets = presetSet(row)
  dropInclude(store, row)
  for key, value in pairs(row.settings or {}) do
    if type(value) == "string" and presets[value] and store.value(key) == value then store.unsetField(key) end
  end
end

-- Applies the effect's settings (call inside store.group); effects of its kind that were in use before and no
-- longer are lose their include, so the save removes their files (one only installed for a rule stays). Returns
-- their names.
local function use(ctx, row)
  local store, before = ctx.store, {}
  for _, other in ipairs(state(ctx).rows) do
    if other.id ~= row.id and other.kind == row.kind and included(store, other)
       and referenced(store, presetSet(other)) then
      table.insert(before, other)
    end
  end
  applySettings(ctx, row)
  local replaced = {}
  for _, other in ipairs(before) do
    if not referenced(store, presetSet(other)) then
      dropInclude(store, other)
      table.insert(replaced, other.name)
    end
  end
  return replaced
end

local function tellReplaced(ctx, replaced)
  if #replaced > 0 then
    ctx.flash("Replaced " .. table.concat(replaced, ", ") .. "; saving removes its files.", "info")
  end
end

-- The presets each include entry defines, for the effect choices (lib/choices.luau).
local function publishPresets(ctx, rows)
  local presets = {}
  for _, row in ipairs(rows) do presets[row.include] = row.presets or {} end
  ctx.store.shaderPresets = presets
end

local function load(ctx, refresh)
  local s = state(ctx)
  s.loading, s.error, s.stateSeen = true, nil, ctx.store.state
  ctx.helper.call("shaders", { config = ctx.store.state.path, refresh = refresh, offline = offline(ctx) },
    function(err, data)
      s.loading = false
      if err then
        s.error = err.error
      else
        s.loaded, s.rows, s.age, s.stale, s.git = data.loaded == true, list(data.rows), data.age, data.error, data.git
        if refresh then s.previews, s.requested, s.failed = {}, {}, {} end
        publishPresets(ctx, s.rows)
      end
      ctx.render()
    end)
end

-- Use (`andUse`) or Install: the include (downloaded into the cache first unless the draft has it), with Use also
-- the settings; one undo step.
local function addShader(ctx, row, andUse)
  local store, s = ctx.store, state(ctx)
  local function apply()
    local replaced = {}
    store.group(function()
      if not included(store, row) then
        local entries = {}
        for _, entry in ipairs(list(store.value(INCLUDE))) do table.insert(entries, entry) end
        table.insert(entries, row.include)
        store.setField(INCLUDE, entries)
      end
      if andUse then replaced = use(ctx, row) end
    end)
    tellReplaced(ctx, replaced)
    ctx.render()
  end
  if included(store, row) then apply(); return end
  s.busy[row.id] = true
  ctx.helper.call("shader-prepare", { id = row.id, offline = offline(ctx) }, function(err)
    s.busy[row.id] = nil
    if err then ctx.flash(err.error, "warning"); ctx.render(); return end
    apply()
  end)
  ctx.render()
end

local function remove(ctx, rows)
  ctx.store.group(function()
    for _, row in ipairs(rows) do removeRow(ctx.store, row) end
  end)
  ctx.render()
end

local function age(seconds)
  seconds = tonumber(seconds) or 0
  if seconds < 90 then return "just now" end
  if seconds < 5400 then return tostring(math.floor(seconds / 60 + 0.5)) .. " min ago" end
  if seconds < 129600 then return tostring(math.floor(seconds / 3600 + 0.5)) .. " h ago" end
  return kit.plural(math.floor(seconds / 86400 + 0.5), "day") .. " ago"
end

local function matches(row, filter)
  if filter == "" then return true end
  if kit.contains(row.name, filter) or kit.contains(row.id, filter) or kit.contains(row.description or "", filter)
     or kit.contains(row.author or "", filter) then return true end
  for _, tag in ipairs(row.tags or {}) do
    if kit.contains(tag, filter) then return true end
  end
  return false
end

-- Asks for the previews of the shown rows that aren't cached yet, one request at a time, each row once.
local function requestPreviews(ctx, rows)
  local s = state(ctx)
  if s.previewBusy then return end
  local ids = {}
  for _, row in ipairs(rows) do
    if not s.previews[row.id] and not s.requested[row.id] then
      s.requested[row.id] = true
      table.insert(ids, row.id)
    end
  end
  if #ids == 0 then return end
  s.previewBusy = true
  ctx.helper.call("shader-previews", { ids = ids, offline = offline(ctx) }, function(err, data)
    s.previewBusy = false
    if err then  -- not answered (refused, timed out): these rows ask again on a later render
      for _, id in ipairs(ids) do s.requested[id] = nil end
    else
      for id, path in pairs(list(data.paths)) do s.previews[id] = path end
      for _, id in ipairs(list(data.failed)) do s.failed[id] = true end
    end
    ctx.render()
  end)
end

local function preview(ctx, s, row)
  local path = s.previews[row.id]
  if path then
    local open = s.large == row.id
    return ui.image({ key = "shader-img-" .. row.id, path = path, width = PREVIEW_W, height = PREVIEW_H,
                      fit = "contain", radius = kit.RADIUS.sm,
                      tooltip = open and "Hide the large preview" or "Show a large preview",
                      onClick = function()
                        s.large = (not open) and row.id or nil
                        ctx.render()
                      end })
  end
  return ui.column({ key = "shader-img-" .. row.id, width = PREVIEW_W, height = PREVIEW_H, radius = kit.RADIUS.sm,
                     fill = "surface_container_high", align = "center", justify = "center" }, {
    ui.glyph({ name = s.failed[row.id] and "photo-off" or "photo", size = kit.GLYPH.large, color = kit.MUTED }),
  })
end

local function rowNode(ctx, row)
  local store, s = ctx.store, state(ctx)
  local inDraft, inSaved = included(store, row), included(store, row, true)
  local badges = { ui.label({ text = row.name, fontSize = kit.FONT.item, fontWeight = "bold", maxLines = 1 }) }
  if inDraft and inSaved and row.installed then
    table.insert(badges, kit.badge("Installed", "primary"))
  elseif inDraft then
    table.insert(badges, kit.badge("Installs on save", "tertiary"))
  elseif inSaved then
    table.insert(badges, kit.badge("Removed on save", "error"))
  elseif row.installed then
    table.insert(badges, kit.badge("On disk", "secondary"))
  end
  if inDraft and not applied(store, row) and referenced(store, presetSet(row)) then
    table.insert(badges, kit.badge("Picked in your settings", "primary"))
  end
  if row.license ~= "MIT" and row.license ~= "" then table.insert(badges, kit.badge(row.license, "tertiary")) end
  local details = {}
  if row.author ~= "" then table.insert(details, row.author) end
  if row.license == "MIT" then table.insert(details, "MIT") end
  if #(row.tags or {}) > 0 then table.insert(details, table.concat(row.tags, ", ")) end
  local busy = s.busy[row.id] == true
  local buttons
  if busy then
    buttons = { ui.button({ key = "shader-busy-" .. row.id, text = "Downloading…", glyph = "loader", variant = "outline",
                            controlSize = "sm", enabled = false }) }
  else
    local hint = HINTS[row.kind] or HINTS.window
    local inUse = inDraft and applied(store, row)
    buttons = { ui.button({ key = "shader-use-" .. row.id, text = inUse and "In use" or "Use", glyph = "check",
                            variant = inUse and "outline" or "primary", controlSize = "sm", enabled = not inUse,
                            tooltip = not inUse and hint.use or nil,
                            onClick = function() addShader(ctx, row, true) end }) }
    if inDraft then
      table.insert(buttons, ui.button({ key = "shader-remove-" .. row.id, text = "Remove", glyph = "trash",
                                        variant = "ghost", controlSize = "sm",
                                        tooltip = "Take it out of the config; saving deletes its files",
                                        onClick = function() remove(ctx, { row }) end }))
    else
      table.insert(buttons, ui.button({ key = "shader-install-" .. row.id, text = "Install", glyph = "download",
                                        variant = "outline", controlSize = "sm",
                                        tooltip = "Only add it, to pick it " .. hint.where,
                                        onClick = function() addShader(ctx, row, false) end }))
    end
  end
  return kit.rowCard({ key = "shader-" .. row.id, padding = 8, gap = 12, align = "center" }, {
    preview(ctx, s, row),
    ui.column({ gap = 2, flexGrow = 1 }, {
      ui.row({ gap = 6, align = "center" }, badges),
      kit.muted(row.description or "", { maxLines = 2 }),
      kit.muted(table.concat(details, " · "), { fontSize = kit.FONT.caption, maxLines = 1 }),
    }),
    ui.column({ gap = 4, align = "end" }, buttons),
  })
end

-- The section's rows below the presets and pools; `filter` is the page filter (lower-cased).
function M.content(ctx, filter)
  local view = ctx.view
  if not view.shaders then
    view.shaders = { rows = {}, previews = {}, requested = {}, failed = {}, busy = {}, kind = "window", shown = FIRST }
    load(ctx, false)  -- the cache only
  end
  local s = state(ctx)
  -- a save or reload put files next to the config or took them away: read which are there again (the cache)
  if s.loaded and not s.loading and s.stateSeen ~= ctx.store.state then load(ctx, false) end
  local nodes = { ui.separator({ key = "shaders-rule", thickness = 1, opacity = 0.5 }) }
  local isOffline = offline(ctx)
  if not s.loaded then
    local text = "Ready-made window, border, screen, cursor and animation effects from Noctalia's "
      .. "community-umbriel-shaders repository. The catalogue and previews come from raw.githubusercontent.com "
      .. "once you ask; installed files go to shaders/community next to the config when you save."
    table.insert(nodes, kit.card({ key = "shaders-intro" }, {
      kit.label("Community shaders", { fontWeight = "bold" }),
      kit.muted(text, { maxLines = 4 }),
      ui.row({ key = "shaders-browse-row" }, {
        ui.button({ key = "shaders-browse", text = s.loading and "Loading…" or "Browse community shaders",
                    glyph = "download", variant = "primary", controlSize = "sm",
                    enabled = not s.loading and not isOffline, onClick = function() load(ctx, true); ctx.render() end }),
      }),
    }))
    if isOffline then table.insert(nodes, kit.notice("Noctalia is in offline mode.", "info", nil, "shaders-offline")) end
    if s.error then table.insert(nodes, kit.notice(s.error, "error", nil, "shaders-error")) end
    return nodes
  end
  local counts = {}
  for _, row in ipairs(s.rows) do counts[row.kind] = (counts[row.kind] or 0) + 1 end
  local subtitle = kit.plural(#s.rows, "effect") .. " · fetched " .. age(s.age)
  table.insert(nodes, ui.row({ key = "shaders-head", gap = 8, align = "center" }, {
    ui.column({ gap = 0, flexGrow = 1 }, { kit.section("Community shaders", "shaders-title"), kit.muted(subtitle) }),
    kit.iconButton(s.loading and "loader" or "refresh", "Download the catalogue again", function()
      load(ctx, true); ctx.render()
    end, not s.loading and not isOffline, "shaders-refresh"),
  }))
  if s.stale then
    table.insert(nodes, kit.notice("Showing the cached catalogue: " .. s.stale, "warning", nil, "shaders-stale"))
  end
  if s.error then table.insert(nodes, kit.notice(s.error, "error", nil, "shaders-error")) end
  if s.git then
    table.insert(nodes, kit.notice("shaders/community is a git checkout: Use only adds the include, so update "
      .. "the checkout with git for effects it doesn't have yet.", "info", nil, "shaders-git"))
  end
  -- kinds with an effect in use (included and named by a setting) get a check and its name as the tooltip
  local inUse = {}
  for _, row in ipairs(s.rows) do
    if included(ctx.store, row) and referenced(ctx.store, presetSet(row)) then
      inUse[row.kind] = inUse[row.kind] or {}
      table.insert(inUse[row.kind], row.name)
    end
  end
  local chips = {}
  for _, kind in ipairs(KINDS) do
    local selected, used = s.kind == kind[1], inUse[kind[1]]
    table.insert(chips, ui.button({ key = "shaders-kind-" .. kind[1], controlSize = "sm", selected = selected,
                                    text = kind[2] .. " " .. tostring(counts[kind[1]] or 0),
                                    glyph = used and "circle-check" or nil,
                                    tooltip = used and ("In use: " .. table.concat(used, ", ")) or nil,
                                    variant = selected and "primary" or "outline", onClick = function()
                                      s.kind, s.shown, s.grewAt = kind[1], FIRST, nil
                                      ctx.render()
                                    end }))
  end
  local ofKind = {}
  for _, row in ipairs(s.rows) do
    if row.kind == s.kind and included(ctx.store, row) then table.insert(ofKind, row) end
  end
  table.insert(chips, ui.spacer({ flexGrow = 1 }))
  table.insert(chips, kit.confirmButton(ctx, {
    key = "shaders-remove-all", text = "Remove all", glyph = "trash", controlSize = "sm", enabled = #ofKind > 0,
    armedText = "Click again to remove " .. kit.plural(#ofKind, "effect"),
    tooltip = "Remove every community effect of this kind from the config (saving removes the files)",
  }, function() remove(ctx, ofKind) end))
  table.insert(nodes, ui.row({ key = "shaders-kinds", gap = 6, align = "center" }, chips))
  table.insert(nodes, kit.muted((HINTS[s.kind] or HINTS.window).line, { key = "shaders-hint", maxLines = 3 }))
  local matching = {}
  for _, row in ipairs(s.rows) do
    if row.kind == s.kind and matches(row, filter) then table.insert(matching, row) end
  end
  local shown = {}
  for index = 1, math.min(#matching, s.shown, CAP) do table.insert(shown, matching[index]) end
  for _, row in ipairs(shown) do
    table.insert(nodes, rowNode(ctx, row))
    if s.large == row.id and s.previews[row.id] then
      table.insert(nodes, ui.row({ key = "shader-large-row-" .. row.id, justify = "center" }, {
        ui.image({ key = "shader-large-" .. row.id, path = s.previews[row.id], width = LARGE_W, height = LARGE_H,
                   fit = "contain", radius = kit.RADIUS.md, tooltip = "Hide the large preview",
                   onClick = function() s.large = nil; ctx.render() end }),
      }))
    end
  end
  if #matching == 0 then table.insert(nodes, kit.muted("No matches.", { key = "shaders-none" })) end
  local more = #matching - #shown
  s.canGrow = more > 0 and #shown < CAP
  if s.canGrow then  -- scrolling to the bottom does the same; the button is the non-pointer way
    table.insert(nodes, ui.row({ key = "shaders-more-row" }, {
      ui.button({ key = "shaders-more", text = "Show " .. tostring(math.min(more, STEP)) .. " more", variant = "ghost",
                  controlSize = "sm", onClick = function() s.shown = s.shown + STEP; ctx.render() end }),
    }))
  elseif more > 0 then
    table.insert(nodes, kit.muted(tostring(more) .. " more: filter by name or tag to find them.",
                                  { key = "shaders-capped" }))
  end
  requestPreviews(ctx, shown)
  return nodes
end

-- The page scroll's onScroll (offset, maxOffset as strings): near the bottom, 6 more rows; once per growth of the
-- page, since Noctalia may report several positions before the render that adds them.
function M.onScroll(ctx)
  local s = ctx.view.shaders
  if not (s and s.loaded and s.canGrow) then return nil end
  return function(offset, maxOffset)
    offset, maxOffset = tonumber(offset) or 0, tonumber(maxOffset) or 0
    if maxOffset <= 0 or maxOffset - offset > NEAR_BOTTOM or s.grewAt == maxOffset or not s.canGrow then return end
    s.grewAt = maxOffset
    s.shown = s.shown + STEP
    ctx.render()
  end
end

return M
