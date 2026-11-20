-- Drives the standalone app's layout (app.luau) through the main flows with the same mocked API.
-- Usage: lua app_test.lua PLUGIN_DIR FIXTURE_DIR
local H = dofile((arg[0]:match("^(.*)/") or ".") .. "/harness.lua")
H.env.LC_NUMERIC = "de_DE.UTF-8"  -- numbers follow the numeric locale
local entry = H.start("app.luau", { initialConfig = "/configs/other.toml", validateDefault = false })
local json, replies, loaded, pluginDir = H.json, H.replies, H.loaded, H.pluginDir
local flushReads, hasText, find, clickText, lastCall, screen = H.flushReads, H.hasText, H.find, H.clickText, H.lastCall, H.screen

local function exists(kind, key)
  local node = H.byKey(key)
  return node ~= nil and node.kind == kind
end

entry.onOpen()
flushReads()
-- --config is read without being remembered as the saved choice
local read = lastCall("read")
assert(read and read.request.config == "/configs/other.toml", "initial config from APP")
assert(not lastCall("set-config"), "the command-line config is not remembered")

-- sidebar navigation, no close button, Home title
assert(exists("column", "sidebar"), "sidebar: " .. screen())
-- the app scales radii in CSS (--radius-scale), so its Luau tokens stay at the base values
H.settings["shell.corner_radius_scale"] = 2
entry.onFrameTick()
assert(H.byKey("sidebar").props.radius == 12, "the app doesn't scale radii in Luau")
H.settings["shell.corner_radius_scale"] = nil
assert(not exists("button", "close"), "the app has no close button")
assert(hasText("Home") and hasText("Appearance") and hasText("Window rules"), screen())

-- the sidebar search shows results on Home; results open pages as roots (no back button)
local search = H.input("^search:")
search.props.onChange("modifier")
flushReads()
assert(hasText("Mod key"), "search results: " .. screen())
clickText("Mod key")
assert(hasText("Session"), "General opened")
assert(not exists("button", "back"), "pages opened from the sidebar are roots")

-- editing shows an unsaved badge next to the page in the sidebar
local select = find("select", function(n) return n.props.key == "f:general.mod_key:select" end)
select.props.onChange("1")
assert(exists("row", "navb-General"), "sidebar badge for General: " .. screen())

-- German numeric locale: decimal comma shown, both separators accepted, dot stored
clickText("Appearance")
assert(not hasText("Opacity while dragging"), "groups start collapsed in the app")
clickText("Windows")
local opacity = find("input", function(n) return tostring(n.props.key):match("drag_opacity:num:") end)
assert(opacity.props.value == "" or not tostring(opacity.props.value):find("%."), "no dot shown: " .. tostring(opacity.props.value))
opacity.props.onChange("0,6")
local store0 = loaded[pluginDir .. "/lib/store.luau"]
assert(store0.fieldChanges["appearance.drag_opacity"].value == 0.6, "comma parsed")

-- drill-down inside a page still has back
clickText("Window rules")
clickText("Add")
assert(exists("button", "back"), "entry page has back")
find("button", function(n) return n.props.key == "back" end).props.onClick()
assert(exists("row", "filter-Window rules-box"), "back to the rule list")

-- --no-validate: the review starts with validation off
replies.preview = function(request)
  assert(request.validate == false, "validation follows APP.validateDefault")
  return true, json.encode({ changed = true, summary = {}, sections = {}, validation = { ran = false } })
end
entry.onKey("ctrl+s", true)
flushReads()
assert(hasText("Review changes"), screen())
assert(lastCall("preview"), "preview requested")

-- a change on disk re-reads the config
local before = #H.calls
entry.onExternalChange()
flushReads()
assert(#H.calls > before and H.calls[#H.calls].command == "read", "external change reloads")

-- Home from the sidebar clears the search
clickText("Home")
assert(hasText("BASICS") or hasText("Basics"), "home cards: " .. screen())
local store = loaded[pluginDir .. "/lib/store.luau"]
assert(store.fieldChanges["general.mod_key"], "edits survive navigation")
-- About: the palette template can be set up from the app
replies.about = function() return true, json.encode({ editor = "", palette = { noctalia = true } }) end
replies["palette-template"] = function() return true, json.encode({ palette = {
  noctalia = true, template = true, entry = true, palette = false } }) end
clickText("About")
clickText("Set up palette template")
assert(lastCall("palette-template"), "template set up")
assert(H.fullScreen():find("next theme change", 1, true), "status after setup: " .. screen())

-- Escape clears the search first, then leaves a drill-down, then a root page goes Home
H.input("^search:").props.onChange("blur")
flushReads()
assert(hasText("Appearance › Blur"), "search results also show from a page above Home: " .. screen())
entry.onKey("Escape", true)
local cleared = H.input("^search:")
assert(cleared.props.value == "", "the search is cleared: " .. tostring(cleared.props.value))
clickText("Window rules")
clickText("Add")
entry.onKey("Escape", true)
assert(exists("row", "filter-Window rules-box") and not exists("button", "back"), "back to the rule list")
entry.onKey("Escape", true)
assert(exists("column", "home-config"), "Home after Escape on a root page: " .. screen())
-- the app's Home is a dashboard (the sidebar lists the pages); the sidebar's tools sit on top of Home
assert(hasText("Customized settings") and hasText("Recent backups") and not exists("row", "tools"), screen())
assert(lastCall("backups"), "recent backups are asked for")
clickText("Backups")
assert(hasText("A copy is taken before every save and restore; the newest 10 are kept"), screen())
entry.onKey("Escape", true)
assert(exists("column", "home-config"), "Escape from a sidebar tool goes Home: " .. screen())

-- the sidebar's Keybinds page sorts by drag and drop through the app's own onDrop global
clickText("Keybinds")
local kb = loaded[pluginDir .. "/lib/store.luau"].keybinds
local second = kb.rows[2].key
H.drag("kbgrip-2", "kbgap-1")
assert(kb.rows[1].key == second, "dragged before the first shortcut")
-- autostart in the app: Browse files… on the app list opens the same file browser as the panel, then the form
local store = loaded[pluginDir .. "/lib/store.luau"]
clickText("General")
if not H.byKey("f:general.autostart:browse") then clickText("Session") end
H.byKey("f:general.autostart:browse").props.onClick()
assert(hasText("Choose an app"), screen())
replies["list-dir"] = function()
  return true, json.encode({ path = "/opt", parent = "/", folders = {}, files = { "my tool" } })
end
replies["pick-file"] = function(request)
  assert(request.command and request.chosen == "/opt/my tool", "the browser's file, as a command")
  return true, json.encode({ path = "'/opt/my tool'" })
end
clickText("Browse files…")
flushReads()
H.byKey("file-my tool").props.onClick()
flushReads()
local autostart = store.value("general.autostart")
assert(autostart[#autostart] == "'/opt/my tool'" and H.byKey("f:general.autostart:browse"), screen())
-- the app records a shortcut from a key press (the panel gets only its capture_keys); Esc cancels
clickText("Keybinds")
local recordKey = store.keybinds.rows[1].key
H.clickShortcut(recordKey)
clickText("Record…")
H.byKey("kb-recorder").props.onKeyRecord("")
assert(not H.byKey("kb-recorder") and store.keybinds.rows[1].key == recordKey, "Esc leaves the shortcut")
clickText("Record…")
H.byKey("kb-recorder").props.onKeyRecord("Super+Shift+K")
assert(store.keybinds.rows[1].key == "Super+Shift+K" and not H.byKey("kb-recorder"), "recorded")
assert(H.input("^kb%-key%-").props.value == "K", "the key box shows the recorded key")
store.undo()
H.checkBudget("app", 0.025)
print("app ok")
