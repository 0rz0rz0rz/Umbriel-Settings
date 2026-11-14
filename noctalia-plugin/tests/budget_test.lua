-- Visits every page and group of the Noctalia panel on a large config and fails when one callback
-- uses more than Noctalia's 25 ms CPU budget (three overruns disable the plugin).
-- Usage: lua budget_test.lua PLUGIN_DIR FIXTURE_DIR   (fixtures from test_panel.py's large config)
local H = dofile((arg[0]:match("^(.*)/") or ".") .. "/harness.lua")
local entry = H.start("panel.luau")
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
H.checkBudget("budget", 0.025)
print("budget ok")
