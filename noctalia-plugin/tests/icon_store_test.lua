-- The icon store page (pages/iconstore.luau on ui/store.luau): from the Icon theme page's button, nothing asked
-- before Browse, a sort and a search, the next store page on scrolling, Open page by item number (no download),
-- offline mode, a close mid-request.
-- Usage: lua icon_store_test.lua PLUGIN_DIR FIXTURE_DIR
local H = dofile((arg[0]:match("^(.*)/") or ".") .. "/harness.lua")
local entry = H.start("panel.luau")
local json, replies, fixtures = H.json, H.replies, H.fixtures
local flushReads, hasText, clickText, lastCall, screen = H.flushReads, H.hasText, H.clickText, H.lastCall, H.screen
local byKey = H.byKey

local function calls(command)
  local found = {}
  for _, call in ipairs(H.calls) do if call.command == command then table.insert(found, call.request) end end
  return found
end

local desktop = json.decode(fixtures.desktop)
desktop.icons = { theme = "Base", revision = "r1", targets = { "GTK 3" } }
replies.desktop = function() return true, json.encode(desktop) end
replies["icon-themes"] = function()
  return true, json.encode({ themes = { { name = "Base", label = "Base", inherits = {}, icons = {}, removable = false,
                                          system = true, cursors = false } }, complete = true })
end
replies["icon-store"] = function(request)
  local rows = {}
  if request.search == "nothing" then return true, json.encode({ rows = {}, total = 0, page = 0 }) end
  for index = 1, 10 do
    local id = request.page * 10 + index
    table.insert(rows, { id = id, name = "Icons " .. id, author = "maker", score = 90, downloads = 12000,
                         updated = "2025-01-01", summary = "Pretty icons.", files = {},
                         page = "https://www.pling.com/p/" .. id,
                         preview = "https://images.pling.com/cache/280x171-4/" .. id .. ".png" })
  end
  return true, json.encode({ rows = rows, total = 1265, page = request.page })
end
replies["cursor-store-previews"] = function(request)
  local paths = {}
  for key in pairs(request.items) do paths[key] = "/data/cursor-store/" .. key .. ".png" end
  return true, json.encode({ paths = paths, failed = {} })
end
replies["open-store-page"] = function(request)
  return true, json.encode({ url = "https://www.pling.com/p/" .. request.id .. "/" })
end

entry.onOpen()
flushReads()
clickText("Icon theme")
flushReads()
assert(byKey("icons-store") and byKey("icons-store").props.variant == "primary", screen())
byKey("icons-store").props.onClick()
assert(hasText("Icon themes") and byKey("istore-browse") and #calls("icon-store") == 0, "nothing before Browse")
assert(H.fullScreen():find("Nothing is downloaded here", 1, true), screen())

byKey("istore-browse").props.onClick()
flushReads()
assert(#calls("icon-store") == 1 and byKey("istore-1") and byKey("istore-10"), screen())
flushReads()
assert(byKey("istore-img-1").props.path == "/data/cursor-store/1.png", "previews like the cursor store")
assert(not byKey("cstore-1") and not byKey("istore-dl-1"), "no download here")

-- Open page goes by the item's number
byKey("istore-open-3").props.onClick()
flushReads()
assert(lastCall("open-store-page").request.id == 3, "by number")
assert(H.fullScreen():find("Opened the page of Icons 3 in your browser.", 1, true), screen())
replies["open-store-page"] = function() return false, "xdg-open was not found.", "missing_editor" end
byKey("istore-open-3").props.onClick()
flushReads()
assert(H.fullScreen():find("xdg-open was not found.", 1, true), screen())

-- a sort and a search start again; scrolling to the bottom brings the next page
byKey("istore-sort-new").props.onClick()
flushReads()
assert(calls("icon-store")[2].sort == "new" and calls("icon-store")[2].page == 0)
H.input("^istore%-search:").props.onSubmit("nothing")
flushReads()
assert(hasText("Nothing found."), screen())
byKey("istore-search-clear").props.onClick()
flushReads()
local node = H.find("scroll", function(n) return tostring(n.props.key):match("^content%-") ~= nil end)
node.props.onScroll("1990", "2000")
flushReads()
local last = calls("icon-store")
assert(last[#last].page == 1 and byKey("istore-20"), "next page: " .. screen())

-- a close mid-request leaves nothing busy; offline mode asks nothing
H.hold("icon-store")
byKey("istore-sort-rated").props.onClick()
entry.onClose()
H.release("icon-store", true)
entry.onOpen()
flushReads()
assert(byKey("istore-sort-name") and byKey("istore-search").props.enabled, "not stuck: " .. screen())
H.settings["shell.offline_mode"] = true
entry.onClose()
entry.onOpen()
flushReads()
assert(byKey("istore-search").props.enabled == false and H.fullScreen():find("offline mode", 1, true), screen())
H.settings["shell.offline_mode"] = nil

-- back on the Icon theme page, the list is read again (a theme may have been extracted meanwhile)
local before = #calls("icon-themes")
entry.onKey("alt+Left", true)
flushReads()
assert(#calls("icon-themes") > before and byKey("icons-row-1"), "asked again: " .. screen())

H.checkBudget("icon store", 0.025)
print("icon store ok")
