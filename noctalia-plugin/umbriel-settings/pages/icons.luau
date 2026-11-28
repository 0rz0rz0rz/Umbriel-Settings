--!nonstrict
-- Icon theme (Desktop page, route `icons`): the installed icon themes (helper `icon-themes`) with six of their
-- icons each. Picking one is a desktop edit (store part "icons"): desktop-save writes it into GNOME settings and
-- the GTK, Qt and KDE files that exist. The trash button queues deleting a theme in the home folder (part
-- "iconRemovals"); never the theme picked, one it builds on, or a system theme.
local kit = require("../ui/kit.luau")
local cursor = require("../ui/cursor.luau")

local M = {}

local ICON = 32  -- px per icon; the files are 48 px or scalable, so they stay sharp on HiDPI
local COUNT = 6  -- icons per theme (`icon_themes.ICONS`)
local FILTER_FROM = 12  -- themes before the list gets a filter box

-- Asks for the themes: once per panel open and after a save (ctx.clearPickerBusy / ctx.savingDone mark the list
-- `stale`), with Refresh, and again while the helper's time ran out before every icon was found. The old rows
-- stay on screen until the answer.
local function load(ctx)
  local view = ctx.view
  if view.iconLoading then return end
  view.iconLoading = true
  ctx.helper.call("icon-themes", {}, function(err, data)
    view.iconLoading = false
    if err then
      view.iconThemes = { error = err.error, rows = {}, byName = {}, complete = true }
    else
      local rows, byName, removable = type(data.themes) == "table" and data.themes or {}, {}, {}
      for _, row in ipairs(rows) do
        byName[row.name] = row
        if row.removable then removable[row.name] = true end
      end
      ctx.store.forgetIconRemovals(removable)  -- queued deletions of themes already gone
      view.iconThemes = { rows = rows, byName = byName, complete = data.complete ~= false }
    end
    ctx.render()
  end)
end

local function themes(ctx)
  local view = ctx.view
  local state = view.iconThemes
  if not view.iconLoading and (state == nil or state.stale or not state.complete) then load(ctx) end
  return view.iconThemes
end

-- `name` and every theme it inherits: deleting one of them would break the theme in use.
local function chain(byName, name)
  local found, todo = {}, { name }
  while #todo > 0 do
    local current = table.remove(todo)
    if current ~= "" and not found[current] then
      found[current] = true
      local row = byName[current]
      for _, parent in ipairs(row and row.inherits or {}) do table.insert(todo, parent) end
    end
  end
  return found
end

local function trash(ctx, row, current, protected, key)
  local removals = ctx.store.desktop.icons.removals
  local name = row.name
  local queued = removals[name] == true
  local tooltip, enabled = nil, false
  if queued then
    tooltip, enabled = "Keep " .. name, true
  elseif row.system then
    tooltip = name .. " came with your system: remove its package to delete it"
  elseif row.cursors then
    tooltip = name .. " also holds a cursor theme: delete it under Input → Cursor"
  elseif name == current then
    tooltip = "Pick another theme to delete " .. name
  elseif protected[name] then
    tooltip = "The theme you picked builds on " .. name
  else
    tooltip, enabled = "Delete " .. name .. " from your home folder when you save", true
  end
  return kit.iconButton(queued and "arrow-back-up" or "trash", tooltip, function()
    if queued then ctx.store.setDesktop("iconRemovals", name, nil) else ctx.store.setDesktop("iconRemovals", name, true) end
    ctx.render()
  end, enabled, key)
end

local function themeRow(ctx, row, index, current, protected)
  local icons = ctx.store.desktop.icons
  local chosen = row.name == current
  local queued = icons.removals[row.name] == true
  local strip = {}
  for slot = 1, COUNT do
    local path = type(row.icons) == "table" and row.icons[slot] or nil
    if type(path) == "string" and path ~= "" then
      table.insert(strip, ui.image({ key = "icon-" .. index .. "-" .. slot, path = path, width = ICON, height = ICON,
                                     fit = "contain" }))
    else
      table.insert(strip, ui.column({ key = "icon-" .. index .. "-" .. slot, width = ICON, height = ICON }, {}))
    end
  end
  local text = { ui.label({ text = row.label or row.name, fontSize = kit.FONT.body, maxLines = 1,
                            fontWeight = chosen and "bold" or nil }) }
  if row.label and row.label ~= row.name then
    table.insert(text, kit.muted(row.name, { fontSize = kit.FONT.caption, maxLines = 1 }))
  end
  local children = {
    ui.row({ key = "icons-strip-" .. index, gap = 6, align = "center" }, strip),
    ui.column({ gap = 0, flexGrow = 1 }, text),
  }
  if queued then table.insert(children, kit.badge("Deleted on save", "tertiary", "icons-badge-" .. index))
  elseif chosen and current ~= icons.original then
    table.insert(children, kit.badge("unsaved", "primary", "icons-badge-" .. index))
  end
  if chosen then table.insert(children, ui.glyph({ name = "check", size = kit.GLYPH.body, color = "primary" })) end
  local pick = ui.row({ key = "icons-pick-" .. index, gap = 12, align = "center", paddingH = 8, paddingV = 6,
                        radius = kit.RADIUS.sm, flexGrow = 1, fill = chosen and "primary/0.12" or nil,
                        tooltip = "Use " .. (row.label or row.name) .. " (written when you save)",
                        onClick = function()
                          ctx.store.group(function()  -- picking a theme queued for deletion keeps it
                            if queued then ctx.store.setDesktop("iconRemovals", row.name, nil) end
                            ctx.store.setDesktop("icons", "theme", row.name)
                          end)
                          ctx.render()
                        end }, children)
  return ui.row({ key = "icons-row-" .. index, gap = 4, align = "center" },
                { pick, trash(ctx, row, current, protected, "icons-rm-" .. index) })
end

function M.render(ctx)
  local store, view = ctx.store, ctx.view
  if not store.desktop then
    ctx.loadDesktop()
    return { header = { kit.header(ctx, "Icon theme") },
             content = { ctx.desktopError and kit.notice(ctx.desktopError, "error", nil, "desktop-error")
                         or kit.loading() } }
  end
  local icons = store.desktop.icons
  local state = themes(ctx)
  local header = { kit.header(ctx, "Icon theme", "The icons GTK, Qt and KDE apps show", {
    ui.button({ key = "icons-folder", text = "Browse folder", glyph = "folder-open", controlSize = "sm",
                variant = "outline", tooltip = "Open the folder you can put icon themes into",
                onClick = function() cursor.openFolder(ctx) end }),
    kit.iconButton("refresh", "Look for newly installed themes", function()
      if view.iconThemes and view.iconThemes.error then view.iconThemes = nil end
      load(ctx)
    end, not view.iconLoading, "icons-refresh"),
  }) }
  local content = {}
  if icons.error then
    table.insert(content, kit.notice("The icon theme settings could not be read: " .. icons.error, "error", nil,
                                     "icons-read-error"))
  end
  if state and state.error then
    local notice, retry = kit.retryNotice("icons-list", "The icon themes could not be listed: " .. state.error,
                                          function() view.iconThemes = nil; load(ctx) end)
    table.insert(content, notice)
    table.insert(content, retry)
  end
  local where = #icons.targets > 0 and table.concat(icons.targets, ", ") or "the GTK 3 settings"
  table.insert(content, kit.muted("Saving writes it to " .. where .. ". Running apps may need a restart; delete "
    .. "themes from your home folder with the trash button.", { key = "icons-note", maxLines = 3 }))
  if state == nil then
    table.insert(content, kit.loading("Looking for icon themes…"))
    return { header = header, content = content }
  end
  local rows, current = state.rows, icons.theme or ""
  if current ~= "" and not state.byName[current] and not state.error then
    table.insert(content, kit.notice("Apps are set to " .. current .. ", which isn't installed: they fall back to "
      .. "another theme.", "warning", nil, "icons-missing"))
  end
  local query = ""
  if #rows > FILTER_FROM then
    table.insert(content, kit.filterBox(ctx, "iconFilter", { placeholder = "Filter themes" }))
    query = kit.filterText(ctx, "iconFilter")
  end
  local protected = chain(state.byName, current)
  local shown, matching = 0, 0
  for index, row in ipairs(rows) do
    if query == "" or kit.contains(row.name, query) or kit.contains(row.label or "", query) then
      matching = matching + 1
      if shown < kit.LIST_CAP then
        shown = shown + 1
        table.insert(content, themeRow(ctx, row, index, current, protected))
      end
    end
  end
  if matching > shown then
    table.insert(content, kit.muted((matching - shown) .. " more: filter to find them", { key = "icons-more" }))
  elseif #rows > 0 and matching == 0 then
    table.insert(content, kit.muted("No theme matches the filter.", { key = "icons-none" }))
  elseif #rows == 0 and not state.error then
    table.insert(content, kit.muted("No icon themes found.", { key = "icons-empty" }))
  end
  table.insert(content, ui.row({ key = "icons-store-row", paddingV = 6 }, {
    ui.button({ key = "icons-store", text = "Browse icon themes…", glyph = "download", variant = "primary",
                controlSize = "sm", tooltip = "Browse the Pling store's icon themes", onClick = function()
                  if view.iconThemes then view.iconThemes.stale = true end  -- back here: one may be extracted
                  ctx.go({ name = "iconStore" })
                end }),
  }))
  return { header = header, content = content }
end

return M
