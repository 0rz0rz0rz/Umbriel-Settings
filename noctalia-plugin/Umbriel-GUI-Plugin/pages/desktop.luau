-- User folders (user-dirs.dirs) and default applications (mimeapps.list), with a searchable app picker.
local kit = require("../ui/kit.luau")

local M = {}

local FOLDERS = {
  { "DESKTOP", "Desktop" }, { "DOCUMENTS", "Documents" }, { "DOWNLOAD", "Downloads" }, { "MUSIC", "Music" },
  { "PICTURES", "Pictures" }, { "VIDEOS", "Videos" }, { "TEMPLATES", "Templates" },
  { "PUBLICSHARE", "Public share" }, { "PROJECTS", "Projects" },
}
local ROLE_ORDER = { "Web browser", "Email client", "File manager", "Text editor", "Image viewer", "PDF viewer",
                     "Audio player", "Video player" }
local ROLE_GLYPHS = { ["Web browser"] = "world", ["Email client"] = "mail", ["File manager"] = "folder",
                      ["Text editor"] = "file-text", ["Image viewer"] = "photo", ["PDF viewer"] = "file-type-pdf",
                      ["Audio player"] = "music", ["Video player"] = "movie" }

local function loading(ctx, title)
  ctx.loadDesktop()
  local content = { ctx.desktopError and kit.notice(ctx.desktopError, "error", nil, "desktop-error")
                    or kit.empty("Loading…", "loader") }
  return { header = { kit.header(ctx, title) }, content = content }
end

local function appName(apps, id)
  if not id or id == "" then return nil end
  for _, app in ipairs(apps) do
    if app.id == id then return app.name end
  end
  return id
end

local function validFolder(value)
  if value == "" then return true end
  if not (string.sub(value, 1, 1) == "/" or value == "$HOME" or string.sub(value, 1, 6) == "$HOME/") then
    return false, "Use an absolute path or $HOME/…"
  end
  local rest = string.sub(value, 1, 5) == "$HOME" and string.sub(value, 6) or value
  if string.find(rest, '[$`"\\\r\n]') then return false, "The path contains unsupported characters." end
  return true
end

local function foldersPage(ctx)
  local store, view = ctx.store, ctx.view
  if not store.desktop then return loading(ctx, "User folders") end
  local dirs = store.desktop.userdirs
  local header = { kit.header(ctx, "User folders", "Where apps put downloads, documents, pictures… Folders are not created.") }
  local content = {}
  local keys = {}
  for _, item in ipairs(FOLDERS) do keys[item[1]] = item[2] end
  local list = {}
  for _, item in ipairs(FOLDERS) do table.insert(list, item) end
  for key in pairs(dirs.values) do
    if not keys[key] then table.insert(list, { key, string.sub(key, 1, 1) .. string.lower(string.sub(key, 2)) }) end
  end
  for _, item in ipairs(list) do
    local key, label = item[1], item[2]
    local value = dirs.values[key] or ""
    local ok, problem = validFolder(value)
    local badges = {}
    if value ~= (dirs.original[key] or "") then table.insert(badges, kit.badge("changed", "primary", "fb-" .. key)) end
    local rows = {
      ui.row({ gap = 6, align = "center" }, {
        ui.label({ text = label, fontSize = 13, fontWeight = "bold", flexGrow = 1 }),
        ui.row({ gap = 4 }, badges),
      }),
      ui.row({ gap = 6, align = "center" }, {
        ui.input({ key = "fold-" .. key .. "-" .. tostring(view.gen["fold-" .. key] or 0), value = value, flexGrow = 1,
                   controlSize = "sm", placeholder = "Not set",
                   onChange = function(text) dirs.values[key] = text; ctx.render() end }),
        ui.button({ text = "Browse…", glyph = "folder-open", controlSize = "sm", variant = "outline",
                    enabled = not view.browsing, onClick = function()
                      view.browsing = true
                      ctx.render()
                      ctx.helper.call("pick-folder", { start = value }, function(err, data)
                        view.browsing = false
                        if err then ctx.flash(err.error, "error")
                        elseif data.path then
                          dirs.values[key] = data.path
                          view.gen["fold-" .. key] = (view.gen["fold-" .. key] or 0) + 1
                        end
                        ctx.render()
                      end, { timeout = 60000 })
                    end }),
      }),
    }
    if not ok then table.insert(rows, kit.notice(problem, "error", nil, "fe-" .. key)) end
    table.insert(content, kit.card({ key = "folder-" .. key }, rows))
  end
  return { header = header, content = content }
end

local function appsPage(ctx)
  local store, view = ctx.store, ctx.view
  if not store.desktop then return loading(ctx, "Default apps") end
  local apps = store.desktop.apps
  local header = { kit.header(ctx, "Default apps", "Which app opens links and files. Other fallbacks are kept.", {
    ui.button({ glyph = "refresh", variant = "ghost", tooltip = "Rescan installed apps",
                onClick = function()
                  if store.desktopChanges() then ctx.flash("Save or discard desktop changes before rescanning.", "warning")
                  else ctx.loadDesktop(true) end
                end }),
  }) }
  local content = { kit.section("Common roles") }
  for _, role in ipairs(ROLE_ORDER) do
    local value = apps.roles[role] or ""
    local subtitle = value == "<multiple>" and "Different apps for different file types"
      or (value ~= "" and (appName(apps.apps, value) .. "  ·  " .. value)) or "Not set"
    local badges = {}
    if value ~= (apps.originalRoles[role] or "") then table.insert(badges, kit.badge("changed", "primary", "rb-" .. role)) end
    local icon = value ~= "" and value ~= "<multiple>" and noctalia.appIconPath and noctalia.appIconPath(
      string.gsub(value, "%.desktop$", ""), 32)
    table.insert(content, kit.navRow({ key = "role-" .. role, image = icon or nil, glyph = ROLE_GLYPHS[role],
      title = role, subtitle = subtitle, badges = badges, onClick = function()
        ctx.go({ name = "appPicker", kind = "role", target = role })
      end }))
  end
  table.insert(content, kit.section("Other file types"))
  table.insert(content, ui.input({ key = "mime-filter", value = view.mimeFilter or "", controlSize = "sm",
                                   placeholder = "Filter file types or apps",
                                   onChange = function(text) view.mimeFilter = text; ctx.render() end }))
  local addKey = "mime-add-" .. tostring(view.gen.mimeAdd or 0)
  local function addMime(mime)
    mime = noctalia.string.trim(mime or "")
    for _, managed in ipairs(apps.roleMimes or {}) do
      if string.lower(managed) == string.lower(mime) then
        ctx.flash("That type is set through a common role above.", "warning"); return
      end
    end
    if apps.mimes[mime] == nil then apps.mimes[mime] = "" end
    view.gen.mimeAdd = (view.gen.mimeAdd or 0) + 1
    ctx.go({ name = "appPicker", kind = "mime", target = mime })
  end
  table.insert(content, ui.row({ key = "mime-add", gap = 6, align = "center" }, {
    ui.input({ key = addKey, value = "", flexGrow = 1, controlSize = "sm",
               placeholder = "Add a MIME type (text/markdown) or extension (.md)",
               onChange = function(text) view.mimeDraft = text end }),
    ui.button({ text = "Add", glyph = "plus", controlSize = "sm", variant = "outline", onClick = function()
      local text = noctalia.string.trim(view.mimeDraft or "")
      if text == "" then return end
      if string.find(text, "/", 1, true) then addMime(text); return end
      ctx.helper.call("extension", { extension = text }, function(err, data)
        if err then ctx.flash(err.error, "warning") else addMime(data.mime) end
      end)
    end }),
  }))
  local filter = string.lower(noctalia.string.trim(view.mimeFilter or ""))
  local names = {}
  for mime in pairs(apps.mimes) do table.insert(names, mime) end
  table.sort(names)
  local listStart = #content + 1
  local shown = 0
  for _, mime in ipairs(names) do
    local value = apps.mimes[mime]
    if shown < 50 and (filter == "" or string.find(string.lower(mime .. " " .. value), filter, 1, true)) then
      shown = shown + 1
      table.insert(content, ui.row({ key = "mime-" .. mime, gap = 6, align = "center", paddingH = 12, paddingV = 6,
                                     radius = 10, fill = "surface_container" }, {
        ui.column({ gap = 2, flexGrow = 1 }, {
          ui.label({ text = mime, fontSize = 13 }),
          kit.muted(value ~= "" and (appName(apps.apps, value) .. "  ·  " .. value) or "Removed when you save"),
        }),
        ui.button({ text = "Change", controlSize = "sm", variant = "outline",
                    onClick = function() ctx.go({ name = "appPicker", kind = "mime", target = mime }) end }),
        ui.button({ glyph = "trash", variant = "ghost", controlSize = "sm", tooltip = "Remove this association",
                    enabled = value ~= "", onClick = function() apps.mimes[mime] = ""; ctx.render() end }),
      }))
    end
  end
  if shown == 50 then table.insert(content, listStart, kit.muted("Showing 50 file types; filter to find others.")) end
  return { header = header, content = content }
end

local function pickerPage(ctx, route)
  local store, view = ctx.store, ctx.view
  if not store.desktop then return loading(ctx, "Choose an app") end
  local apps = store.desktop.apps
  local current = route.kind == "role" and apps.roles[route.target] or apps.mimes[route.target]
  local header = { kit.header(ctx, "Choose an app", route.target),
    ui.input({ key = "app-search", value = view.appQuery or "", focus = true, placeholder = "Search installed apps",
               onChange = function(text) view.appQuery = text; ctx.render() end }) }
  local function choose(id)
    if route.kind == "role" then apps.roles[route.target] = id else apps.mimes[route.target] = id end
    view.appQuery = ""
    ctx.back()
  end
  local query = string.lower(noctalia.string.trim(view.appQuery or ""))
  local content = {}
  local shown = 0
  for _, app in ipairs(apps.apps) do
    if shown < 40 and (query == "" or string.find(string.lower(app.name .. " " .. app.id), query, 1, true)) then
      shown = shown + 1
      local icon = noctalia.appIconPath and noctalia.appIconPath(string.gsub(app.id, "%.desktop$", ""), 32)
      table.insert(content, kit.navRow({ key = "app-" .. app.id, image = icon or nil, glyph = "apps",
        title = app.name, subtitle = app.id, trailing = app.id == current and "check" or "chevron-right",
        fill = app.id == current and "primary_container" or nil, onClick = function() choose(app.id) end }))
    end
  end
  if shown == 40 then table.insert(content, kit.muted("Type to find more apps.")) end
  if shown == 0 then table.insert(content, kit.empty("No installed app matches.", "apps")) end
  table.insert(content, kit.section("Or enter a desktop file ID"))
  table.insert(content, ui.row({ key = "app-manual", gap = 6 }, {
    ui.input({ key = "app-id", value = current ~= "<multiple>" and current or "", flexGrow = 1, controlSize = "sm",
               placeholder = "e.g. org.gnome.Nautilus.desktop", onChange = function(text) view.appManual = text end,
               onSubmit = function(text) choose(noctalia.string.trim(text)) end }),
    ui.button({ text = "Use", controlSize = "sm", variant = "outline",
                onClick = function() choose(noctalia.string.trim(view.appManual or current or "")) end }),
  }))
  return { header = header, content = content }
end

function M.render(ctx, route)
  if route.name == "folders" then return foldersPage(ctx) end
  if route.name == "appPicker" then return pickerPage(ctx, route) end
  return appsPage(ctx)
end

return M
