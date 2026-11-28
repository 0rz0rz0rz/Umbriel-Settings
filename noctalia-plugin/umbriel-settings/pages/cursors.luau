--!nonstrict
-- Cursor themes from the Pling store, route `cursorStore` (the page itself: ui/store.luau): Download → Use. A
-- download lands in the private cache only; **Use** picks the theme like any edit, and the reviewed save copies
-- it into the icon folder. Badges, Use and the trash button follow the Theme list (`cursor.themes`).
local kit = require("../ui/kit.luau")
local cursor = require("../ui/cursor.luau")
local storePage = require("../ui/store.luau")

local M = {}

local THEME = "input.cursor.theme"
local list, offline = storePage.list, storePage.offline
local SPEC

-- One download at a time (it can take a while, and Noctalia runs only a few helper commands at once).
local function download(ctx, row, file)
  local s = storePage.state(ctx, SPEC)
  if s.downloading then return end
  s.downloading, s.errors[row.id] = row.id, nil
  ctx.render()
  ctx.helper.call("cursor-store-download", { id = row.id, file = file.file, offline = offline(ctx) },
    function(err, data)
      s.downloading = nil
      if err then
        s.errors[row.id] = err.error
      else
        s.themes[row.id .. ":" .. file.file] = list(data.themes)
        if ctx.view.cursorThemes then ctx.view.cursorThemes.stale = true end  -- asked again: it's listed now
      end
      ctx.render()
    end)
end

local function use(ctx, theme)
  ctx.store.group(function()  -- using a theme queued for removal keeps it
    if ctx.store.cursorRemovals[theme] then ctx.store.removeCursorTheme(theme, true) end
    ctx.store.setField(THEME, theme)
  end)
  ctx.flash("Picked " .. theme .. ". It's copied into ~/.local/share/icons/ when you save.", "info")
  ctx.render()
end

local function present(s, key, byName)
  local themes = s.themes[key]
  if not themes or not byName then return themes end
  local kept = {}
  for _, theme in ipairs(themes) do
    if byName[theme] then table.insert(kept, theme) end
  end
  if #kept == 0 then s.themes[key] = nil; return nil end
  return kept
end

local function rowParts(ctx, s, row, byName)
  local current = ctx.store.value(THEME)
  local files = list(row.files)
  local chosen = files[s.files[row.id] or 1] or files[1]
  local themes = chosen and present(s, row.id .. ":" .. chosen.file, byName) or nil
  local badges, actions = {}, {}
  local installed = {}
  for _, theme in ipairs(list(row.installed)) do installed[theme] = true end
  if themes then
    local inUse, first = false, byName and byName[themes[1]]
    for _, theme in ipairs(themes) do inUse = inUse or theme == current end
    local isInstalled = (first and not first.downloaded) or (not first and installed[themes[1]])
    table.insert(badges, kit.badge(inUse and "In use" or (isInstalled and "Installed" or "Downloaded"),
                                   inUse and "primary" or "secondary", "cstore-badge-" .. row.id))
  end
  if #files > 1 then  -- some items offer many variants: one select, one button
    local names = {}
    for _, file in ipairs(files) do table.insert(names, file.name .. " (" .. kit.fileSize((file.size or 0) * 1024) .. ")") end
    table.insert(actions, ui.select({ key = "cstore-file-" .. row.id, options = names, controlSize = "sm", width = 220,
                                      selectedIndex = (s.files[row.id] or 1) - 1, onChange = function(index)
                                        s.files[row.id] = (tonumber(index) or 0) + 1
                                        ctx.render()
                                      end }))
  end
  if themes and #themes > 0 then
    for index, theme in ipairs(themes) do
      if index > 4 then break end
      local inUse = theme == current
      local buttons = { ui.button({ key = "cstore-use-" .. row.id .. "-" .. index,
                                    -- several themes in one archive (light, dark, …): say which one is in use
                                    text = inUse and (#themes > 1 and (theme .. " in use") or "In use")
                                      or ("Use " .. theme), glyph = "check",
                                    variant = inUse and "outline" or "primary", controlSize = "sm",
                                    enabled = not inUse, onClick = function() use(ctx, theme) end }) }
      local known = byName and byName[theme]
      if known and (known.removable or known.system) then
        table.insert(buttons, cursor.removeButton(ctx, known, current, "cstore-rm-" .. row.id .. "-" .. index))
      end
      table.insert(actions, ui.row({ key = "cstore-theme-" .. row.id .. "-" .. index, gap = 4, align = "center" },
                                   buttons))
    end
  elseif chosen then
    local busy = s.downloading == row.id
    table.insert(actions, ui.button({ key = "cstore-dl-" .. row.id, text = busy and "Downloading…" or "Download",
                                      glyph = busy and "loader" or "download", variant = "outline", controlSize = "sm",
                                      enabled = s.downloading == nil and not offline(ctx),
                                      tooltip = "Download " .. chosen.name .. " (" .. kit.fileSize((chosen.size or 0) * 1024)
                                        .. ") into the private cache",
                                      onClick = function() download(ctx, row, chosen) end }))
  end
  return badges, actions
end

SPEC = {
  stateKey = "cursorStore", prefix = "cstore", command = "cursor-store",
  title = "Cursor themes", subtitle = "Community uploads from the Pling store (gnome-look.org, store.kde.org)",
  header = function(ctx)
    return { ui.button({ key = "cstore-folder", text = "Browse folder", glyph = "folder-open", controlSize = "sm",
                         variant = "outline", tooltip = "Open the folder cursor themes are installed into",
                         onClick = function() cursor.openFolder(ctx) end }) }
  end,
  introTitle = "Browse cursor themes", browseText = "Browse cursor themes",
  intro = "About 1200 X11 cursor themes people uploaded to the Pling store, the one KDE's \"Get New "
    .. "Cursors\" uses. Uploads aren't reviewed by anyone: a download is checked against the store's "
    .. "checksum, only the cursor images and index.theme are kept, and nothing from it is run. It goes into "
    .. "a private folder; the theme is copied into ~/.local/share/icons/ only when you save with it picked. "
    .. "The list, previews and downloads come from api.pling.com, images.pling.com and files.pling.com once "
    .. "you ask.",
  offlineNote = "Noctalia is in offline mode: nothing is downloaded.",
  fresh = function() return { files = {}, themes = {} } end,
  onRow = function(s, row)
    for _, file in ipairs(list(row.files)) do
      if #list(file.themes) > 0 then s.themes[row.id .. ":" .. file.file] = file.themes end
    end
  end,
  prepare = function(ctx)
    local onDisk = cursor.themes(ctx)  -- asked when stale (after a save): what is still on this computer
    return onDisk and not onDisk.error and not onDisk.stale and not ctx.view.cursorLoading and onDisk.byName or nil
  end,
  rowParts = rowParts,
}

function M.render(ctx) return storePage.render(ctx, SPEC) end
function M.onScroll(ctx) return storePage.onScroll(ctx, SPEC) end

return M
