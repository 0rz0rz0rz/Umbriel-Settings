--!nonstrict
-- Cursor theme dropdown (meta `picker = "cursor"`): the installed themes, each with a strip of its shapes drawn
-- by helper `cursor-themes` (cached PNGs), "Umbriel default", Refresh, where to get more, and a
-- trash button per theme (deleted by the save; never the one in use or Umbriel's default).
local kit = require("./kit.luau")

local M = {}

local STRIP_W, STRIP_H = 240, 30  -- 8 shapes at 30 px; the PNGs are drawn at twice that for HiDPI
local ARROW = 22
local FILTER_FROM = 12  -- themes before the list gets a filter box

M.HELP = "Store uploads aren't reviewed: only cursor images and `index.theme` are kept, nothing is run. A picked "
  .. "theme is copied into `~/.local/share/icons/` on save; you can also extract themes there or install them as "
  .. "packages. The trash button deletes a theme on save (not the one in use or Umbriel's default). Running apps may "
  .. "keep the old cursor until they restart."

-- Asks for the themes and their previews: on each panel open and after a save (ctx.clearPickerBusy marks them
-- `stale`), each time the list opens and with Refresh (themes added or deleted meanwhile), and again while the
-- helper's time ran out before every preview was drawn. The old rows stay on screen until the answer.
local function load(ctx)
  local view = ctx.view
  if view.cursorLoading then return end
  view.cursorLoading = true
  ctx.helper.call("cursor-themes", {}, function(err, data)
    view.cursorLoading = false
    if err then
      view.cursorThemes = { error = err.error, rows = {}, byName = {}, complete = true }
    else
      local rows, byName, removable = type(data.themes) == "table" and data.themes or {}, {}, {}
      for _, row in ipairs(rows) do
        byName[row.name] = row
        if row.removable then removable[row.name] = true end
      end
      ctx.store.forgetCursorRemovals(removable)  -- queued removals of themes already gone
      view.cursorThemes = { rows = rows, byName = byName, complete = data.complete ~= false }
    end
    ctx.render()
  end)
end

local function themes(ctx)
  local view = ctx.view
  local state = view.cursorThemes
  if not view.cursorLoading and (state == nil or state.stale or (not state.complete and view.openCursor)) then
    load(ctx)
  end
  return view.cursorThemes
end
M.themes = themes  -- the store page's badges and trash buttons come from the same list

local function current(effective)
  if effective == nil or effective == "" then return nil end
  return tostring(effective)
end

local function close(ctx, key)
  if ctx.view.openCursor == key then ctx.view.openCursor = nil end
end

-- The closed dropdown: the current theme's arrow and name; a click opens the list under the row.
function M.control(ctx, spec, effective)
  local view, key = ctx.view, spec.key
  local state, name = themes(ctx), current(effective)
  local row = name and state and state.byName[name] or nil
  local open = view.openCursor == key
  local children = {}
  if row and row.arrow then
    table.insert(children, ui.image({ key = key .. ":arrow", path = row.arrow, width = ARROW, height = ARROW,
                                      fit = "contain" }))
  end
  table.insert(children, ui.label({ text = name or "Umbriel default", fontSize = kit.FONT.body, flexGrow = 1,
                                    maxLines = 1 }))
  table.insert(children, ui.glyph({ name = open and "chevron-up" or "chevron-down", size = kit.GLYPH.body,
                                    color = kit.MUTED }))
  return { ui.row({ key = key .. ":cursor", flexGrow = 1, height = 32, gap = 8, align = "center", paddingH = 10,
                    radius = kit.RADIUS.md, border = kit.CARD_BORDER, borderWidth = kit.CARD_BORDER_WIDTH,
                    fill = open and "surface_container_high" or "surface_container",
                    tooltip = open and "Close the theme list" or "Choose a cursor theme", onClick = function()
                      view.openCursor = (not open) and key or nil
                      if not open and view.cursorThemes and not view.cursorThemes.error then load(ctx) end
                      ctx.render()
                    end }, children) }
end

local function choice(ctx, key, props, chosen, onChoose)
  local children = {}
  if props.preview then
    table.insert(children, ui.image({ key = props.key .. "-img", path = props.preview, width = STRIP_W,
                                      height = STRIP_H, fit = "contain" }))
  elseif props.placeholder then  -- "" keeps the names in line
    table.insert(children, ui.row({ width = STRIP_W, height = STRIP_H, align = "center" },
                                  { kit.muted(props.placeholder, { fontSize = kit.FONT.caption, maxLines = 1 }) }))
  end
  table.insert(children, ui.label({ text = props.text, fontSize = kit.FONT.body, flexGrow = 1, maxLines = 1,
                                    fontWeight = chosen and "bold" or nil }))
  if props.badge then table.insert(children, kit.badge(props.badge, "tertiary", props.key .. "-badge")) end
  if chosen then table.insert(children, ui.glyph({ name = "check", size = kit.GLYPH.body, color = "primary" })) end
  return ui.row({ key = props.key, gap = 12, align = "center", paddingH = 8, paddingV = 4, radius = kit.RADIUS.sm,
                  flexGrow = 1, fill = chosen and "primary/0.12" or nil, tooltip = props.tooltip, onClick = function()
                    close(ctx, key)
                    onChoose()
                    ctx.render()
                  end }, children)
end

-- The open list, under the field's row.
function M.dropdown(ctx, spec, effective)
  local view, key = ctx.view, spec.key
  local state, name = themes(ctx), current(effective)
  local content = {}
  local refresh = kit.iconButton("refresh", "Look for newly installed themes", function()
    if view.cursorThemes and view.cursorThemes.error then view.cursorThemes = nil end
    load(ctx)
  end, not view.cursorLoading, key .. ":cursor-refresh")
  if state and state.error then
    local notice, retry = kit.retryNotice(key .. ":cursor", "The cursor themes could not be read: " .. state.error,
                                          function() view.cursorThemes = nil; load(ctx) end)
    table.insert(content, notice)
    table.insert(content, retry)
  end
  local rows = state and state.rows or {}
  local filterKey = "cursorFilter"
  local query = kit.filterText(ctx, filterKey)
  local folderButton = kit.iconButton("folder-open", "Open the cursor theme folder", function()
    M.openFolder(ctx)
  end, true, key .. ":cursor-folder")
  local top = { folderButton, refresh }
  if #rows > FILTER_FROM then
    table.insert(top, 1, kit.filterBox(ctx, filterKey, { placeholder = "Filter themes", flexGrow = 1 }))
  else
    table.insert(top, 1, kit.muted(#rows > 0 and kit.plural(#rows, "installed theme") or "", { flexGrow = 1 }))
  end
  table.insert(content, ui.row({ key = key .. ":cursor-top", gap = 8, align = "center" }, top))
  if state == nil then table.insert(content, kit.loading("Looking for cursor themes…")) end
  if query == "" then
    table.insert(content, choice(ctx, key, { key = key .. ":cursor-default", text = "Umbriel default",
                                             placeholder = "",
                                             tooltip = "Leave the theme to Umbriel" }, name == nil, function()
      if spec.onUnset then spec.onUnset() else spec.onSet("") end
    end))
  end
  local shown, matching = 0, 0
  for index, row in ipairs(rows) do
    if query == "" or kit.contains(row.name, query) then
      matching = matching + 1
      if shown < kit.LIST_CAP then
        shown = shown + 1
        local removing = ctx.store.cursorRemovals[row.name] == true
        local removed = (row.ours or row.downloaded) and "Removed on save" or "Deleted on save"
        local node = choice(ctx, key, {
          key = key .. ":cursor-" .. index, text = row.name, preview = row.preview,
          placeholder = row.preview == nil and (state.complete and "No preview" or "Drawing…") or nil,
          tooltip = row.downloaded and ("Use " .. row.name .. " (copied into your icon folder when you save)")
            or ("Use " .. row.name),
          badge = (removing and removed) or (row.downloaded and "Installs on save") or nil,
        }, row.name == name, function()
              ctx.store.group(function()  -- picking a theme queued for removal keeps it
            if removing then ctx.store.removeCursorTheme(row.name, true) end
            spec.onSet(row.name)
          end)
        end)
        if row.removable or row.system then  -- next to the row, not inside it (a click there picks the theme)
          node = ui.row({ key = key .. ":cursor-wrap-" .. index, gap = 4, align = "center" },
                        { node, M.removeButton(ctx, row, name, key .. ":cursor-rm-" .. index) })
        end
        table.insert(content, node)
      end
    end
  end
  if matching > shown then
    table.insert(content, kit.muted((matching - shown) .. " more: filter to find them", { key = key .. ":cursor-more" }))
  elseif state and #rows > 0 and matching == 0 then
    table.insert(content, kit.muted("No theme matches the filter.", { key = key .. ":cursor-none" }))
  end
  table.insert(content, ui.row({ key = key .. ":cursor-store-row", paddingH = 8, paddingV = 6 }, {
    ui.button({ key = key .. ":cursor-store", text = "Browse cursor themes…", glyph = "download", variant = "primary",
                controlSize = "sm", tooltip = "Browse the Pling store's cursor themes", onClick = function()
                  close(ctx, key)
                  ctx.go({ name = "cursorStore" })
                end }),
  }))
  table.insert(content, ui.markdown({ key = key .. ":cursor-help", text = M.HELP }))
  return kit.card({ key = key .. ":cursor-list", padding = 8, gap = 4, radius = kit.RADIUS.md }, content)
end

-- Opens the folder themes are installed into (helper `open-cursor-folder`: xdg-open, so the file manager).
function M.openFolder(ctx)
  ctx.helper.call("open-cursor-folder", {}, function(err, data)
    if err then
      ctx.flash(err.error, "warning")
    else
      ctx.flash("Opened " .. tostring(data.folder or "the cursor theme folder") .. ".", "info")
    end
    ctx.render()
  end)
end

-- Remove (queued: the next save deletes the theme) or Keep (unqueue) for a `cursor-themes` row; disabled, with the
-- reason as tooltip, for the theme in use, Umbriel's default and themes only the system has.
function M.removeButton(ctx, row, current, key)
  local theme = row.name
  local queued = ctx.store.cursorRemovals[theme] == true
  local tooltip, enabled = nil, false
  if queued then
    tooltip, enabled = "Keep " .. theme, true
  elseif row.system then
    tooltip = theme .. " came with your system: remove its package to delete it"
  elseif theme == current then
    tooltip = "Pick another theme to remove " .. theme
  elseif row.protected then
    tooltip = theme .. " is Umbriel's default cursor theme"
  elseif row.ours then
    tooltip, enabled = "Remove " .. theme .. " from your icon folder when you save", true
  elseif row.downloaded then
    tooltip, enabled = "Delete the download of " .. theme .. " when you save", true
  else
    tooltip, enabled = "Delete " .. theme .. " from your home folder when you save", true
  end
  return kit.iconButton(queued and "arrow-back-up" or "trash", tooltip, function()
    ctx.store.removeCursorTheme(theme, queued)
    ctx.render()
  end, enabled, key)
end


return M
