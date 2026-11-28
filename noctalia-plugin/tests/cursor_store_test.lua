-- The cursor theme store page (pages/cursors.luau): nothing asked before Browse, sorts and search ask once, the next
-- store page on scrolling (duplicates dropped), previews once per row, Download → Use (one undo step), a file
-- select for items with many archives, offline mode, a close mid-download.
-- Usage: lua cursor_store_test.lua PLUGIN_DIR FIXTURE_DIR
local H = dofile((arg[0]:match("^(.*)/") or ".") .. "/harness.lua")
local entry = H.start("panel.luau")
local json, replies, loaded, pluginDir = H.json, H.replies, H.loaded, H.pluginDir
local flushReads, hasText, clickText, lastCall, screen = H.flushReads, H.hasText, H.clickText, H.lastCall, H.screen
local byKey = H.byKey
local THEME = "input.cursor.theme"

local function calls(command)
  local found = {}
  for _, call in ipairs(H.calls) do if call.command == command then table.insert(found, call.request) end end
  return found
end

local function row(id, files)
  return { id = id, name = "Theme " .. id, author = "maker", score = 88, downloads = 4200, updated = "2025-05-05",
           summary = "Nice cursors.", page = "https://www.pling.com/p/" .. id,
           preview = "https://images.pling.com/cache/280x171-2/" .. id .. ".png",
           large = "https://images.pling.com/cache/770x540-4/" .. id .. ".png",
           files = files or { { file = 1, name = "t" .. id .. ".tar.xz", size = 300, themes = {} } }, installed = {} }
end

replies["cursor-store"] = function(request)
  local rows = {}
  if request.search == "nothing" then return true, json.encode({ rows = {}, total = 0, page = 0 }) end
  local first = request.page * 10
  for index = 1, 10 do table.insert(rows, row(first + index)) end
  if request.page == 1 then rows[1] = row(10) end  -- the store's pages shifted: item 10 again
  if request.page == 0 then
    rows[2] = row(2, { { file = 1, name = "light.tar.gz", size = 100, themes = {} },
                       { file = 2, name = "dark.tar.gz", size = 120, themes = {} } })
  end
  return true, json.encode({ rows = rows, total = 1247, page = request.page })
end
replies["cursor-store-previews"] = function(request)
  local paths = {}
  for key in pairs(request.items) do paths[key] = "/data/cursor-store/" .. key .. ".png" end
  return true, json.encode({ paths = paths, failed = {} })
end

-- the Theme list (helper cursor-themes): what downloads, saves and the file manager left on this computer
local onDisk = {}
replies["cursor-themes"] = function() return true, json.encode({ themes = onDisk, complete = true }) end

entry.onOpen()
flushReads()
local store = loaded[pluginDir .. "/lib/store.luau"]
local shell = loaded[pluginDir .. "/lib/shell.luau"]
-- open the page from the Theme dropdown
clickText("Input")
if not byKey("f:" .. THEME .. ":cursor") then clickText("Cursor") end
flushReads()
byKey("f:" .. THEME .. ":cursor").props.onClick()
byKey("f:" .. THEME .. ":cursor-store").props.onClick()
assert(hasText("Cursor themes") and byKey("cstore-browse"), screen())
assert(#calls("cursor-store") == 0, "nothing asked before Browse")
byKey("cstore-folder").props.onClick()
assert(lastCall("open-cursor-folder"), "Browse folder opens the theme folder")

byKey("cstore-browse").props.onClick()
flushReads()
assert(#calls("cursor-store") == 1 and calls("cursor-store")[1].sort == "popular" and calls("cursor-store")[1].page == 0)
assert(byKey("cstore-1") and byKey("cstore-10"), screen())
assert(#calls("cursor-store-previews") == 1, "one preview request for the shown rows")
flushReads()
assert(byKey("cstore-img-1").props.path == "/data/cursor-store/1.png", "the preview shows")
assert(#calls("cursor-store-previews") == 1, "previews are asked once per row")

-- a sort chip and a search ask once each and start the list again
byKey("cstore-sort-rated").props.onClick()
flushReads()
assert(calls("cursor-store")[2].sort == "rated" and calls("cursor-store")[2].page == 0)
byKey("cstore-sort-rated").props.onClick()
assert(#calls("cursor-store") == 2, "the selected sort asks nothing")
H.input("^cstore%-search:").props.onChange("bib")
assert(#calls("cursor-store") == 2, "typing asks nothing")
H.input("^cstore%-search:").props.onSubmit("bibata")
flushReads()
assert(#calls("cursor-store") == 3 and calls("cursor-store")[3].search == "bibata")
H.input("^cstore%-search:").props.onSubmit("nothing")
flushReads()
assert(hasText("Nothing found."), screen())
byKey("cstore-search-clear").props.onClick()
flushReads()
assert(calls("cursor-store")[5].search == "")

-- scrolling to the bottom loads the next store page once; a repeated item is shown once
local function scroll(maxOffset)
  local node = H.find("scroll", function(n) return tostring(n.props.key):match("^content%-") ~= nil end)
  if node.props.onScroll then node.props.onScroll(tostring(maxOffset - 10), tostring(maxOffset)) end
end
scroll(2000)
scroll(2000)
flushReads()
assert(#calls("cursor-store") == 6 and calls("cursor-store")[6].page == 1, "next page once per growth")
assert(byKey("cstore-20") and not byKey("cstore-21"), "page 1 brought 11–20 (10 again, once)")
local tens = 0
H.walk(H.tree(), function(n) if n.props.key == "cstore-10" then tens = tens + 1 end end)
assert(tens == 1, "item 10 once: " .. tens)

-- a large preview on click (fetched on demand)
byKey("cstore-img-1").props.onClick()
flushReads()
assert(byKey("cstore-large-1"), "the large preview: " .. screen())

-- many archives: a select picks which one Download takes
byKey("cstore-file-2").props.onChange("1")
H.hold("cursor-store-download")
byKey("cstore-dl-2").props.onClick()
assert(byKey("cstore-dl-2").props.text == "Downloading…" and byKey("cstore-dl-3").props.enabled == false,
       "busy, one download at a time")
assert(lastCall("cursor-store-download").request.file == 2, "the chosen archive")
-- a close mid-download clears the busy state; the answer of the closed panel is dropped
entry.onClose()
H.release("cursor-store-download", true)
entry.onOpen()
flushReads()
assert(byKey("cstore-dl-2") and byKey("cstore-dl-2").props.enabled, "not stuck busy: " .. screen())

replies["cursor-store-download"] = function(request)
  onDisk = { { name = "Theme-" .. request.id .. "-dark", downloaded = true, removable = true } }
  return true, json.encode({ themes = { "Theme-" .. request.id .. "-dark" } })
end
byKey("cstore-dl-2").props.onClick()
flushReads()
assert(byKey("cstore-badge-2") and byKey("cstore-use-2-1"), "downloaded: Use: " .. screen())
local steps = #store.history
byKey("cstore-use-2-1").props.onClick()
assert(store.fieldChanges[THEME].value == "Theme-2-dark", "picked")
assert(#store.history == steps + 1, "one undo step")
assert(byKey("cstore-use-2-1").props.text == "In use", screen())
entry.onKey("ctrl+z", true)
assert(store.fieldChanges[THEME] == nil, "undone")

-- its trash button queues the removal; once the save deleted it, the row offers Download again, without a reopen
assert(byKey("cstore-rm-2-1").props.tooltip == "Delete the download of Theme-2-dark when you save", screen())
byKey("cstore-rm-2-1").props.onClick()
assert(store.cursorRemovals["Theme-2-dark"], "queued")
replies.preview = function()
  return true, json.encode({ changed = true, summary = {}, sections = {},
                             validation = { ran = true, valid = true, diagnostics = {} } })
end
replies.save = function() onDisk = {}; return true, H.fixtures.saved end
entry.onKey("ctrl+s", true)
flushReads()
clickText("Save")
flushReads()
assert(hasText("Saved.") and next(store.cursorRemovals) == nil, screen())
assert(byKey("cstore-dl-2") and not byKey("cstore-badge-2") and not byKey("cstore-use-2-1"),
       "deleted: Download again: " .. screen())

-- a failed download says why on its row
replies["cursor-store-download"] = function() return false, "t3.tar.xz has no X11 cursor theme." end
byKey("cstore-dl-3").props.onClick()
flushReads()
assert(H.fullScreen():find("has no X11 cursor theme", 1, true), screen())

-- offline mode: nothing is asked
H.settings["shell.offline_mode"] = true
entry.onClose()
entry.onOpen()
flushReads()
assert(byKey("cstore-dl-4").props.enabled == false and H.fullScreen():find("offline mode", 1, true), screen())
assert(byKey("cstore-search").props.enabled == false)
H.settings["shell.offline_mode"] = nil

H.checkBudget("cursor store", 0.025)
assert(shell)
print("cursor store ok")
