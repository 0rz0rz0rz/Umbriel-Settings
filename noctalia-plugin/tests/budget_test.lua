-- Visits every page and group of the Noctalia panel (or the app layout) on a large config and fails when one
-- callback uses more than Noctalia's 25 ms CPU budget (three overruns disable the plugin).
-- Usage: lua budget_test.lua PLUGIN_DIR FIXTURE_DIR [panel|app]   (fixtures from test_panel.py's large config)
local H = dofile((arg[0]:match("^(.*)/") or ".") .. "/harness.lua")
local layout = arg[3] or "panel"
local entry = H.start(layout .. ".luau", layout == "app" and {} or nil)
local meta = H.json.decode(H.fixtures.meta)
local flushReads, find, texts = H.flushReads, H.find, H.texts

-- Clicks the first clickable node whose text contains `pattern` (plain); returns whether one was found.
local function click(pattern)
  local node = H.walk(H.tree(), function(n)
    return n.props.onClick and texts(n):find(pattern, 1, true) ~= nil
  end)
  if node then node.props.onClick(); flushReads() end
  return node ~= nil
end

local function search(text)
  entry.onKey("ctrl+f", true)
  H.input("^search:").props.onChange(text)
  flushReads()
end

entry.onOpen()
flushReads()
search("a")  -- the widest search result list
local visited = 0
for _, section in ipairs(meta.nav) do
  for _, title in ipairs(section.pages) do
    search("")
    assert(click(title), "page card " .. title .. "\nScreen: " .. H.screen())
    visited = visited + 1
    local page = meta.pages[title]
    if page.kind == "form" then
      for _, group in ipairs(page.groups) do click(group.title) end
    elseif page.kind == "entries" then
      click("budget-entry-150")
    end
  end
end
assert(visited >= 20, "visited " .. visited .. " pages")

-- the customized view walks every field; undo of a typed shortcut restores the large keybind list
search("")
assert(click("Customized"), "Customized button\nScreen: " .. H.screen())
search("")
assert(click("Keybinds"), "Keybinds card")
local store = H.loaded[H.pluginDir .. "/lib/store.luau"]
-- the full list with a grip and a drop gap per shortcut; a drop reorders and redraws all of it
local last = store.keybinds.rows[#store.keybinds.rows].key
H.drag("kbgrip-" .. #store.keybinds.rows, "kbgap-1")
assert(store.keybinds.rows[1].key == last, "dropped first")
entry.onKey("ctrl+z", true)
-- shortcuts show as key caps in sections; filtering opens the section that holds the first one
find("input", function(n) return n.props.key == "kb-filter" end).props.onChange(store.keybinds.rows[1].key)
find("row", function(n) return tostring(n.props.key):match("^kb%-1%-") and n.props.onClick end).props.onClick()
local keyInput = function() return find("input", function(n) return tostring(n.props.key):match("^kb%-key%-") end) end
keyInput().props.onChange("F12")
keyInput().props.onChange("F11")
entry.onKey("ctrl+z", true)
assert(not store.keybindsDirty, "undone")
-- the keyboard layout picker with XKB-sized lists (100 layouts, 500 variants, 200 options), searching each
local layouts, variants, options = {}, {}, {}
for i = 1, 100 do
  local name = "l" .. i
  table.insert(layouts, { name = name, desc = "Layout number " .. i })
  variants[name] = {}
  for j = 1, 5 do table.insert(variants[name], { name = "v" .. j, desc = "Variant " .. j .. " of layout " .. i }) end
end
for g = 1, 20 do
  local group = { name = "g" .. g, desc = "Option group " .. g, items = {} }
  for j = 1, 10 do table.insert(group.items, { name = "g" .. g .. ":o" .. j, desc = "Option " .. j }) end
  table.insert(options, group)
end
H.replies.xkb = function()
  return true, H.json.encode({ layouts = layouts, variants = variants, options = options, current = "Layout number 1" })
end
search("")
assert(click("Input"), "Input card")
click("Keyboard")
assert(click("Choose…"), "Choose button\nScreen: " .. H.screen())
for i = 1, 4 do
  H.input("^xkb%-layout%-q:").props.onChange("layout")
  H.walk(H.byKey("xkb-add-l" .. i), function(n) return n.kind == "button" end).props.onClick()
end
H.input("^xkb%-option%-q:").props.onChange("o")
-- open windows: many of them, filtered as the user types
local windows = {}
for i = 1, 300 do
  table.insert(windows, { app_id = "app" .. i, title = "Window " .. i, count = 1, pattern = "^app" .. i .. "$",
                          title_pattern = "^Window " .. i .. "$" })
end
H.replies.windows = function() return true, H.json.encode({ windows = windows }) end
search("")
assert(click("Window rules"), "Window rules card")
click("budget-entry-150")
assert(click("Pick from open windows"), "picker button\nScreen: " .. H.screen())
H.input("^live%-filter:").props.onChange("app1")
-- six connected displays with many modes next to the 50 output entries: drop, Move, a detail page's dropdowns
local outputs = {}
for i = 0, 5 do
  local modes = {}
  for m = 1, 35 do
    table.insert(modes, { width = 3840 - m * 40, height = 2160 - m * 20, refresh_mhz = 60000 + m * 1000,
                          current = m == 1, preferred = m == 2 })
  end
  table.insert(outputs, { name = "BUDGET-" .. i, config_name = "Budget monitor " .. i, scale = 1, enabled = true,
    transform = "normal", logical_size = { width = 3800, height = 2140 }, position = { x = i * 3800, y = 0 },
    modes = modes })
end
H.replies.outputs = function() return true, H.json.encode({ outputs = outputs }) end
entry.onClose()
entry.onOpen()
flushReads()
search("")
assert(click("Outputs"), "Outputs card")
assert(H.byKey("display-BUDGET-5"), "display tiles\nScreen: " .. H.screen())
H.drag("display-BUDGET-5", "display-above-BUDGET-0")
H.byKey("display-star-BUDGET-3").props.onClick()
flushReads()
H.byKey("display-BUDGET-1").props.onClick()
flushReads()
if not H.walk(H.tree(), function(n) return tostring(n.props.key):match(":resolution$") end) then click("Basics") end
find("select", function(n) return tostring(n.props.key):match(":resolution$") end).props.onChange("3")
flushReads()
H.checkBudget("budget " .. layout, 0.025)
print("budget ok")
