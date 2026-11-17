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
  local function walk(node, visit)
    if visit(node) then return node end
    for _, child in ipairs(node.children or {}) do
      local found = walk(child, visit)
      if found then return found end
    end
  end
  local node = walk(H.tree(), function(n)
    return n.props.onClick and texts(n):find(pattern, 1, true) ~= nil
  end)
  if node then node.props.onClick(); flushReads() end
  return node ~= nil
end

local function search(text)
  entry.onKey("ctrl+f", true)
  find("input", function(n) return tostring(n.props.key):match("^search:") end).props.onChange(text)
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
H.checkBudget("budget " .. layout, 0.025)
print("budget ok")
