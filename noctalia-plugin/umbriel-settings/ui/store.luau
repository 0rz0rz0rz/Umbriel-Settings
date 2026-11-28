--!nonstrict
-- A Pling store page (gnome-look.org, store.kde.org), shared by the cursor store (pages/cursors.luau) and the
-- icon store (pages/iconstore.luau): sort chips, a search, rows with a preview (click for a large one), author,
-- score, downloads. Nothing goes on the network until the user presses Browse (never in Noctalia's offline
-- mode). Rows come a store page (about 10) at a time, the next page when the page is scrolled to the bottom (or
-- **Show more**), 60 at most. What a row offers comes from the page's `spec`:
--   stateKey (view field), prefix (node keys), command (helper listing), title, subtitle, header (extra header
--   buttons), introTitle, intro, browseText, offlineNote, hint (muted line under the search, optional),
--   fresh() (extra state fields), onRow(s, row) (each row received), prepare(ctx, s) (once per render, its
--   result is passed on), rowParts(ctx, s, row, prepared) → badges, actions.
local kit = require("./kit.luau")

local M = {}

local SORTS = { { "popular", "Most downloaded" }, { "rated", "Top rated" }, { "new", "Newest" }, { "name", "A–Z" } }
local CAP = 60  -- rows at most: one render stays inside Noctalia's 25 ms
local NEAR_BOTTOM = 160  -- px from the end of the page that load the next page
local PREVIEW_W, PREVIEW_H = 176, 108  -- the store's small previews are 280×171
local LARGE_W, LARGE_H = 560, 393  -- and the large ones 770×540

function M.offline(ctx)
  if ctx.isApp or type(noctalia.getSetting) ~= "function" then return false end
  return noctalia.getSetting("shell.offline_mode") == true
end

function M.list(value) return type(value) == "table" and value or {} end
local list = M.list

function M.state(ctx, spec)
  local view = ctx.view
  if not view[spec.stateKey] then
    local s = { rows = {}, seen = {}, previews = {}, requested = {}, failed = {}, sort = "popular", search = "",
                page = 0, errors = {} }
    for key, value in pairs(spec.fresh and spec.fresh() or {}) do s[key] = value end
    view[spec.stateKey] = s
  end
  return view[spec.stateKey]
end

-- Asks for one store page: `more` appends the next one, else the list starts again (sort or search changed).
local function load(ctx, spec, more)
  local s = M.state(ctx, spec)
  if s.loading then return end
  if not more then s.rows, s.seen, s.page, s.done, s.grewAt = {}, {}, 0, false, nil end
  s.loading, s.error, s.browsed = true, nil, true
  local page = more and (s.page + 1) or 0
  ctx.helper.call(spec.command, { sort = s.sort, search = s.search, page = page, offline = M.offline(ctx) },
    function(err, data)
      s.loading = false
      if err then
        s.error = err.error
      else
        s.page, s.total = page, data.total
        local added = 0
        for _, row in ipairs(list(data.rows)) do
          if not s.seen[row.id] then  -- the store's pages may shift while scrolling: each item once
            s.seen[row.id] = true
            table.insert(s.rows, row)
            added = added + 1
          end
          if spec.onRow then spec.onRow(s, row) end
        end
        -- the store filters on its side: an empty page (or one with only repeats) is the end
        s.done = #list(data.rows) == 0 or (more and added == 0)
      end
      ctx.render()
    end)
end

-- Previews of the shown rows that aren't cached yet, one request at a time, each row once (a failed request
-- un-marks them, so a later render asks again).
local function requestPreviews(ctx, s, rows, large)
  if s.previewBusy then return end
  local items, ids = {}, {}
  for _, row in ipairs(rows) do
    local key = large and ("L" .. row.id) or tostring(row.id)
    local url = large and row.large or row.preview
    if url and not s.previews[key] and not s.requested[key] then
      s.requested[key] = true
      items[key] = url
      table.insert(ids, key)
    end
  end
  if #ids == 0 then return end
  s.previewBusy = true
  ctx.helper.call("cursor-store-previews", { items = items, offline = M.offline(ctx) }, function(err, data)
    s.previewBusy = false
    if err then
      for _, key in ipairs(ids) do s.requested[key] = nil end
    else
      for key, path in pairs(list(data.paths)) do s.previews[key] = path end
      for _, key in ipairs(list(data.failed)) do s.failed[key] = true end
    end
    ctx.render()
  end)
end

local function preview(ctx, spec, s, row)
  local key = spec.prefix .. "-img-" .. row.id
  local path = s.previews[tostring(row.id)]
  if path then
    local open = s.large == row.id
    return ui.image({ key = key, path = path, width = PREVIEW_W, height = PREVIEW_H, fit = "contain",
                      radius = kit.RADIUS.sm, tooltip = open and "Hide the large preview" or "Show a large preview",
                      onClick = function()
                        s.large = (not open) and row.id or nil
                        ctx.render()
                      end })
  end
  return ui.column({ key = key, width = PREVIEW_W, height = PREVIEW_H, radius = kit.RADIUS.sm,
                     fill = "surface_container_high", align = "center", justify = "center" }, {
    ui.glyph({ name = s.failed[tostring(row.id)] and "photo-off" or "photo", size = kit.GLYPH.large,
               color = kit.MUTED }),
  })
end

local function count(number)
  if number >= 1000000 then return string.format("%.1fM", number / 1000000) end
  if number >= 1000 then return string.format("%.0fk", number / 1000) end
  return tostring(number)
end

local function rowNode(ctx, spec, s, row, prepared)
  local prefix = spec.prefix
  local badges, actions = spec.rowParts(ctx, s, row, prepared)
  local title = { ui.label({ text = row.name, fontSize = kit.FONT.item, fontWeight = "bold", maxLines = 1 }) }
  for _, badge in ipairs(badges or {}) do table.insert(title, badge) end
  local details = {}
  if row.author ~= "" then table.insert(details, row.author) end
  table.insert(details, "★ " .. tostring(row.score) .. "%")
  table.insert(details, count(row.downloads or 0) .. " downloads")
  if row.updated ~= "" then table.insert(details, "updated " .. row.updated) end
  local body = {
    ui.row({ key = prefix .. "-title-" .. row.id, gap = 6, align = "center" }, title),
    kit.muted(row.summary or "", { maxLines = 2 }),
    kit.muted(table.concat(details, " · "), { fontSize = kit.FONT.caption, maxLines = 1 }),
  }
  if s.errors[row.id] then
    table.insert(body, kit.notice(s.errors[row.id], "error", nil, prefix .. "-error-" .. row.id))
  end
  return kit.rowCard({ key = prefix .. "-" .. row.id, padding = 8, gap = 12, align = "center" }, {
    preview(ctx, spec, s, row),
    ui.column({ gap = 2, flexGrow = 1 }, body),
    ui.column({ key = prefix .. "-actions-" .. row.id, gap = 4, align = "end" }, actions or {}),
  })
end

local function search(ctx, spec, s, text)
  s.search = noctalia.string.trim(text or "")
  load(ctx, spec, false)
  ctx.render()
end

function M.render(ctx, spec)
  local s, view, prefix = M.state(ctx, spec), ctx.view, spec.prefix
  local draftKey = prefix .. "Draft"
  local isOffline = M.offline(ctx)
  local header = { kit.header(ctx, spec.title, spec.subtitle, spec.header and spec.header(ctx) or nil) }
  local content = {}
  if not s.browsed then
    table.insert(content, kit.card({ key = prefix .. "-intro" }, {
      kit.label(spec.introTitle, { fontWeight = "bold" }),
      kit.muted(spec.intro, { maxLines = 8 }),
      ui.row({ key = prefix .. "-browse-row" }, {
        ui.button({ key = prefix .. "-browse", text = spec.browseText, glyph = "download", variant = "primary",
                    controlSize = "sm", enabled = not isOffline,
                    onClick = function() load(ctx, spec, false); ctx.render() end }),
      }),
    }))
    if isOffline then
      table.insert(content, kit.notice("Noctalia is in offline mode, so the store isn't asked.", "info", nil,
                                       prefix .. "-offline"))
    end
    return { header = header, content = content }
  end
  local chips = {}
  for _, sort in ipairs(SORTS) do
    local selected = s.sort == sort[1]
    table.insert(chips, ui.button({ key = prefix .. "-sort-" .. sort[1], text = sort[2], controlSize = "sm",
                                    selected = selected, variant = selected and "primary" or "outline",
                                    enabled = not isOffline, onClick = function()
                                      if s.sort == sort[1] then return end
                                      s.sort = sort[1]
                                      load(ctx, spec, false)
                                      ctx.render()
                                    end }))
  end
  table.insert(content, ui.row({ key = prefix .. "-sorts", gap = 6, align = "center" }, chips))
  table.insert(content, ui.row({ key = prefix .. "-search-row", gap = 6, align = "center" }, {
    ui.input({ key = prefix .. "-search:" .. ctx.gen(prefix .. "-search"), value = s.search, flexGrow = 1,
               controlSize = "sm", placeholder = "Search the store (Enter)",
               onChange = function(text) view[draftKey] = text end,
               onSubmit = function(text) search(ctx, spec, s, text) end }),
    ui.button({ key = prefix .. "-search", text = "Search", glyph = "search", controlSize = "sm", variant = "outline",
                enabled = not isOffline and not s.loading,
                onClick = function() search(ctx, spec, s, view[draftKey] or s.search) end }),
    kit.iconButton("eraser", "Clear the search", function()
      view[draftKey] = nil
      ctx.bump(prefix .. "-search")
      search(ctx, spec, s, "")
    end, s.search ~= "", prefix .. "-search-clear"),
  }))
  if spec.hint then table.insert(content, kit.muted(spec.hint, { key = prefix .. "-hint", maxLines = 2 })) end
  if isOffline then
    table.insert(content, kit.notice(spec.offlineNote or "Noctalia is in offline mode: the store isn't asked.",
                                     "info", nil, prefix .. "-offline"))
  end
  if s.error then
    local notice, retry = kit.retryNotice(prefix, s.error,
                                          function() load(ctx, spec, #s.rows > 0); ctx.render() end)
    table.insert(content, notice)
    table.insert(content, retry)
  end
  local shown = {}
  for index = 1, math.min(#s.rows, CAP) do table.insert(shown, s.rows[index]) end
  local prepared = spec.prepare and spec.prepare(ctx, s) or nil
  for _, row in ipairs(shown) do
    table.insert(content, rowNode(ctx, spec, s, row, prepared))
    if s.large == row.id then
      local path = s.previews["L" .. row.id]
      if path then
        table.insert(content, ui.row({ key = prefix .. "-large-row-" .. row.id, justify = "center" }, {
          ui.image({ key = prefix .. "-large-" .. row.id, path = path, width = LARGE_W, height = LARGE_H,
                     fit = "contain", radius = kit.RADIUS.md, tooltip = "Hide the large preview",
                     onClick = function() s.large = nil; ctx.render() end }),
        }))
      else
        requestPreviews(ctx, s, { row }, true)
      end
    end
  end
  if s.loading then table.insert(content, kit.loading("Asking the store…")) end
  if not s.loading and #s.rows == 0 and not s.error then
    table.insert(content, kit.muted("Nothing found.", { key = prefix .. "-none" }))
  end
  s.canGrow = not s.done and not s.loading and not s.error and #s.rows > 0 and #s.rows < CAP
  if s.canGrow then  -- scrolling to the bottom does the same; the button is the non-pointer way
    table.insert(content, ui.row({ key = prefix .. "-more-row" }, {
      ui.button({ key = prefix .. "-more", text = "Show more", variant = "ghost", controlSize = "sm",
                  onClick = function() load(ctx, spec, true); ctx.render() end }),
    }))
  elseif #s.rows >= CAP then
    table.insert(content, kit.muted("Search to find others.", { key = prefix .. "-capped" }))
  end
  requestPreviews(ctx, s, shown, false)
  return { header = header, content = content, onScroll = M.onScroll(ctx, spec) }
end

-- The page scroll's onScroll (offset, maxOffset as strings): near the bottom, the next store page; once per
-- growth of the page, since Noctalia may report several positions before the render that adds rows.
function M.onScroll(ctx, spec)
  local s = ctx.view[spec.stateKey]
  if not (s and s.canGrow) then return nil end
  return function(offset, maxOffset)
    offset, maxOffset = tonumber(offset) or 0, tonumber(maxOffset) or 0
    if maxOffset <= 0 or maxOffset - offset > NEAR_BOTTOM or s.grewAt == maxOffset or not s.canGrow then return end
    s.grewAt = maxOffset
    load(ctx, spec, true)
    ctx.render()
  end
end

-- Busy flags an answer dropped by a panel close never clears (ctx.clearPickerBusy).
function M.clearBusy(s)
  if not s then return end
  s.loading, s.previewBusy, s.downloading = false, false, nil
  s.requested = {}
end

return M
