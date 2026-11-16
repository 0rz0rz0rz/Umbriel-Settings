-- Drives the standalone app's layout (app.luau) through the main flows with the same mocked API.
-- Usage: lua app_test.lua PLUGIN_DIR FIXTURE_DIR
local H = dofile((arg[0]:match("^(.*)/") or ".") .. "/harness.lua")
H.env.LC_NUMERIC = "de_DE.UTF-8"  -- numbers follow the numeric locale
local entry = H.start("app.luau", { initialConfig = "/configs/other.toml", validateDefault = false })
local json, replies, loaded, pluginDir = H.json, H.replies, H.loaded, H.pluginDir
local flushReads, hasText, find, clickText, lastCall, screen = H.flushReads, H.hasText, H.find, H.clickText, H.lastCall, H.screen

local function exists(kind, key)
  local found = false
  local function walk(node)
    if node.kind == kind and node.props.key == key then found = true end
    for _, child in ipairs(node.children or {}) do walk(child) end
  end
  walk(H.tree())
  return found
end

entry.onOpen()
flushReads()
-- --config is read without being remembered as the saved choice
local read = lastCall("read")
assert(read and read.request.config == "/configs/other.toml", "initial config from APP")
assert(not lastCall("set-config"), "the command-line config is not remembered")

-- sidebar navigation, no close button, Home title
assert(exists("column", "sidebar"), "sidebar: " .. screen())
assert(not exists("button", "close"), "the app has no close button")
assert(hasText("Home") and hasText("Appearance") and hasText("Window rules"), screen())

-- the sidebar search shows results on Home; results open pages as roots (no back button)
local search = find("input", function(n) return tostring(n.props.key):match("^search:") end)
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
assert(exists("input", "filter-Window rules"), "back to the rule list")

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
assert(screen():find("next theme change", 1, true), "status after setup: " .. screen())

-- Escape clears the search first, then leaves a drill-down, then a root page goes Home
find("input", function(n) return tostring(n.props.key):match("^search:") end).props.onChange("blur")
flushReads()
assert(hasText("Appearance › Blur"), "search results also show from a page above Home: " .. screen())
entry.onKey("Escape", true)
local cleared = find("input", function(n) return tostring(n.props.key):match("^search:") end)
assert(cleared.props.value == "", "the search is cleared: " .. tostring(cleared.props.value))
clickText("Window rules")
clickText("Add")
entry.onKey("Escape", true)
assert(exists("input", "filter-Window rules") and not exists("button", "back"), "back to the rule list")
entry.onKey("Escape", true)
assert(exists("row", "tools"), "Home after Escape on a root page: " .. screen())
H.checkBudget("app", 0.025)
print("app ok")
