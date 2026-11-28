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

-- a downloaded community shader catalogue as large as Noctalia's (183 effects) on the Effects page
local shaderRows, kinds = {}, { "window", "border", "screen", "cursor", "animation" }
for index = 1, 183 do  -- the largest kind at the page's cap (72 rows)
  local kind = index > 111 and "animation" or kinds[index % 4 + 1]
  local id = kind .. "/effect-" .. index
  table.insert(shaderRows, { id = id, kind = kind, name = "Effect " .. index, author = "Someone",
                             description = string.rep("A long description of a shader. ", 8), license = "MIT",
                             tags = { "retro", "glow", "fire" }, include = "shaders/community/" .. id .. "/effect.toml",
                             settings = { ["effects.window"] = "e" .. index, ["animation.enabled"] = true },
                             presets = { "e" .. index }, installed = index % 3 == 0 })
end
H.replies.shaders = function() return true, H.json.encode({ loaded = true, age = 60, rows = shaderRows }) end

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
search("")
-- every animation effect included in the draft: the kind chips and rows check which ones settings name
local includes = {}
for index = 112, 183 do table.insert(includes, shaderRows[index].include) end
H.loaded[H.pluginDir .. "/lib/store.luau"].setField("include.files", includes)
assert(click("Effects"), "community shaders\nScreen: " .. H.screen())
H.byKey("shaders-kind-animation").props.onClick()
flushReads()
for _ = 1, 12 do  -- scrolled to the bottom again and again: every animation effect (the largest kind)
  local scroll = find("scroll", function(n) return tostring(n.props.key):match("^content%-") ~= nil end)
  if not scroll.props.onScroll then break end
  scroll.props.onScroll("9000", tostring(9000 + _))
  flushReads()
end
assert(H.byKey("shader-animation/effect-183") and not H.byKey("shaders-more"), "all 72 animation effects shown")

-- the cursor theme dropdown with 200 installed themes (40 rows shown, each with its trash button), filtered, a pick
local cursorRows = {}
for index = 1, 200 do
  table.insert(cursorRows, { name = "Cursor theme " .. index, preview = "/p/" .. index .. "-strip.png",
                             arrow = "/p/" .. index .. "-arrow.png", removable = index % 5 ~= 0,
                             system = index % 5 == 0 })
end
H.replies["cursor-themes"] = function() return true, H.json.encode({ themes = cursorRows, complete = true }) end
entry.onClose()
entry.onOpen()
flushReads()
search("")
assert(click("Input"), "Input page\nScreen: " .. H.screen())
if not H.byKey("f:input.cursor.theme:cursor") then click("Cursor") end
flushReads()
H.byKey("f:input.cursor.theme:cursor").props.onClick()
assert(H.byKey("f:input.cursor.theme:cursor-40"), "the theme list is open\nScreen: " .. H.screen())
H.input("^cursorFilter:").props.onChange("1")
H.byKey("f:input.cursor.theme:cursor-100").props.onClick()

-- the Icon theme page with 200 themes (40 rows shown), six icons and a trash button each, filtered, a pick
local iconRows = {}
for index = 1, 200 do
  local icons = {}
  for slot = 1, 6 do table.insert(icons, "/i/" .. index .. "/" .. slot .. ".svg") end
  table.insert(iconRows, { name = "Icons " .. index, label = "Icon theme " .. index, inherits = { "Icons 1" },
                           icons = icons, removable = index % 4 ~= 0, system = index % 4 == 0, cursors = false })
end
H.replies["icon-themes"] = function() return true, H.json.encode({ themes = iconRows, complete = true }) end
search("")
assert(click("Icon theme"), "Icon theme page\nScreen: " .. H.screen())
flushReads()
assert(H.byKey("icons-row-40") and not H.byKey("icons-row-41"), "40 rows\nScreen: " .. H.screen())
H.input("^iconFilter:").props.onChange("1")
H.byKey("icons-pick-100").props.onClick()

-- the cursor store page with 60 rows (6 store pages), each with a preview and many files for one item
local storePage = 0
H.replies["cursor-store"] = function(request)
  local rows = {}
  for index = 1, 10 do
    local id = request.page * 10 + index
    local files = { { file = 1, name = "theme-" .. id .. ".tar.xz", size = 400, themes = {} } }
    if index == 1 then
      for extra = 2, 19 do table.insert(files, { file = extra, name = "variant-" .. extra .. ".tar.gz", size = 300, themes = {} }) end
    end
    table.insert(rows, { id = id, name = "Cursor " .. id, author = "someone", score = 80, downloads = 123456,
                         updated = "2026-01-01", summary = string.rep("A cursor theme. ", 20),
                         page = "https://www.pling.com/p/" .. id, preview = "https://images.pling.com/s/" .. id .. ".png",
                         large = "https://images.pling.com/l/" .. id .. ".png", files = files, installed = {} })
  end
  storePage = request.page
  return true, H.json.encode({ rows = rows, total = 1247, page = request.page })
end
H.replies["cursor-store-previews"] = function(request)
  local paths = {}
  for key in pairs(request.items) do paths[key] = "/p/" .. key .. ".png" end
  return true, H.json.encode({ paths = paths, failed = {} })
end
entry.onKey("alt+Left", true)
H.goHome()
search("")
assert(click("Input"), "Input page\nScreen: " .. H.screen())
if not H.byKey("f:input.cursor.theme:cursor") then click("Cursor") end
flushReads()
H.byKey("f:input.cursor.theme:cursor").props.onClick()
H.byKey("f:input.cursor.theme:cursor-store").props.onClick()
H.byKey("cstore-browse").props.onClick()
flushReads()
for _ = 1, 8 do
  local scroll = find("scroll", function(n) return tostring(n.props.key):match("^content%-") ~= nil end)
  if not scroll.props.onScroll then break end
  scroll.props.onScroll("9000", tostring(9000 + storePage))
  flushReads()
end
assert(H.byKey("cstore-60") and not H.byKey("cstore-more"), "60 store rows\nScreen: " .. H.screen())
H.byKey("cstore-img-1").props.onClick()
flushReads()

-- the icon store page with 60 rows, each with a preview and Open page
local iconPage = 0
H.replies["icon-store"] = function(request)
  local rows = {}
  for index = 1, 10 do
    local id = 5000 + request.page * 10 + index
    table.insert(rows, { id = id, name = "Icons " .. id, author = "someone", score = 80, downloads = 123456,
                         updated = "2026-01-01", summary = string.rep("An icon theme. ", 20), files = {},
                         page = "https://www.pling.com/p/" .. id, preview = "https://images.pling.com/s/" .. id .. ".png",
                         large = "https://images.pling.com/l/" .. id .. ".png" })
  end
  iconPage = request.page
  return true, H.json.encode({ rows = rows, total = 1265, page = request.page })
end
search("")
assert(click("Icon theme"), "Icon theme page\nScreen: " .. H.screen())
flushReads()
H.byKey("icons-store").props.onClick()
H.byKey("istore-browse").props.onClick()
flushReads()
for _ = 1, 8 do
  local scroll = find("scroll", function(n) return tostring(n.props.key):match("^content%-") ~= nil end)
  if not scroll.props.onScroll then break end
  scroll.props.onScroll("9000", tostring(9000 + iconPage))
  flushReads()
end
assert(H.byKey("istore-5060") and not H.byKey("istore-more"), "60 icon store rows\nScreen: " .. H.screen())

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
H.input("^kbFilter:").props.onChange(store.keybinds.rows[1].key)
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
H.input("^liveFilter:").props.onChange("app1")
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
-- the panel's own file browser on a folder at the helper's 2000-entry cap, filtered as the user types
if layout == "panel" then
  local programs = {}
  for i = 1, 1990 do table.insert(programs, "program-" .. i) end
  H.replies["list-dir"] = function()
    return true, H.json.encode({ path = "/usr/bin", parent = "/usr", folders = { "lib" }, files = programs })
  end
  search("")
  assert(click("General"), "General card")
  if not H.byKey("f:include.files:browse") then click("Includes") end  -- still open from the page sweep
  local browse = H.byKey("f:include.files:browse")
  assert(browse, "Includes Browse…\nScreen: " .. H.screen())
  browse.props.onClick()
  flushReads()
  assert(H.byKey("file-program-1"), "file rows\nScreen: " .. H.screen())
  H.input("^fileQuery:").props.onChange("program-19")
  flushReads()
end
H.checkBudget("budget " .. layout, 0.025)
print("budget ok")
