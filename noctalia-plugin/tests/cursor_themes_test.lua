-- The cursor theme dropdown (ui/cursor.luau): previews from helper cursor-themes, asked on each open of the list
-- and after a save (old rows shown meanwhile), pick, default, no custom name, the trash button (queue, Keep, undo,
-- change set; disabled for the theme in use, Umbriel's default and system themes), its Browse cursor themes… row.
-- Usage: lua cursor_themes_test.lua PLUGIN_DIR FIXTURE_DIR
local H = dofile((arg[0]:match("^(.*)/") or ".") .. "/harness.lua")
local entry = H.start("panel.luau")
local json, replies, loaded, pluginDir = H.json, H.replies, H.loaded, H.pluginDir
local flushReads, hasText, clickText, lastCall, screen = H.flushReads, H.hasText, H.clickText, H.lastCall, H.screen

entry.onOpen()
flushReads()
local store = loaded[pluginDir .. "/lib/store.luau"]
-- cursor theme dropdown: previews from helper cursor-themes, asked once per open; pick, default
local cursorRows = {}
for index = 1, 45 do
  table.insert(cursorRows, { name = string.format("Theme%02d", index), preview = "/data/cursor-previews/t" .. index
    .. "-strip.png", arrow = "/data/cursor-previews/t" .. index .. "-arrow.png" })
end
cursorRows[45].preview, cursorRows[45].arrow = nil, nil  -- none of the shapes
replies["cursor-themes"] = function() return true, json.encode({ themes = cursorRows, complete = true }) end
local function cursorCalls()
  local count = 0
  for _, call in ipairs(H.calls) do if call.command == "cursor-themes" then count = count + 1 end end
  return count
end
local THEME = "input.cursor.theme"
entry.onClose()  -- an earlier visit asked already: a reopen asks again
entry.onOpen()
flushReads()
local callsBefore = cursorCalls()
H.goHome()
clickText("Input")
clickText("Cursor")
flushReads()
local dropdown = H.byKey("f:" .. THEME .. ":cursor")
assert(dropdown and dropdown.props.onClick, "the theme is a dropdown: " .. screen())
assert(cursorCalls() == callsBefore + 1, "asked once: " .. cursorCalls() - callsBefore)
dropdown.props.onClick()
assert(H.byKey("f:" .. THEME .. ":cursor-list"), "the list opens under the row")
assert(H.byKey("f:" .. THEME .. ":cursor-1-img").props.path == "/data/cursor-previews/t1-strip.png", "a preview strip")
assert(H.byKey("f:" .. THEME .. ":cursor-40") and not H.byKey("f:" .. THEME .. ":cursor-41"), "40 rows at most")
assert(H.fullScreen():find("5 more: filter to find them", 1, true), screen())
assert(H.fullScreen():find("~/.local/share/icons/", 1, true), "where to put themes")
H.input("^cursorFilter:").props.onChange("theme45")
assert(H.byKey("f:" .. THEME .. ":cursor-45") and H.fullScreen():find("No preview", 1, true), screen())
H.byKey("cursorFilter-clear").props.onClick()
H.byKey("f:" .. THEME .. ":cursor-3").props.onClick()
assert(store.fieldChanges[THEME].value == "Theme03", "picked")
assert(not H.byKey("f:" .. THEME .. ":cursor-list"), "a pick closes the list")
assert(H.byKey("f:" .. THEME .. ":arrow").props.path == "/data/cursor-previews/t3-arrow.png", "its arrow shows")
assert(cursorCalls() == callsBefore + 2, "opening the list asked again (deleted themes go), the pick didn't")
H.byKey("f:" .. THEME .. ":cursor").props.onClick()
local customBox = false
H.walk(H.tree(), function(node)
  local key = node.props and node.props.key
  if type(key) == "string" and key:find(THEME .. ":custom", 1, true) then customBox = true end
end)
assert(not H.byKey("f:" .. THEME .. ":cursor-custom") and not customBox, "no custom name box")
assert(H.byKey("f:" .. THEME .. ":cursor-store").props.variant == "primary", "Browse is a primary button")
H.byKey("f:" .. THEME .. ":cursor-default").props.onClick()
assert(store.fieldChanges[THEME] == nil or store.fieldChanges[THEME].unset, "back to Umbriel's default")
H.byKey("f:" .. THEME .. ":cursor").props.onClick()
entry.onKey("alt+Left", true)
assert(not H.byKey("f:" .. THEME .. ":cursor-list"), "leaving the page closes the list")
entry.onClose()
entry.onOpen()
flushReads()
H.goHome()
clickText("Input")
clickText("Cursor")
flushReads()
assert(cursorCalls() == callsBefore + 2, "asked again after reopening (themes may have been installed)")
-- the trash button: queued (undoable), sent with the save; disabled for the theme in use, Umbriel's default and
-- themes only the system has
cursorRows[2].ours, cursorRows[2].removable = true, true
cursorRows[4].removable = true  -- in the home folder, not installed by this app
cursorRows[5].system = true
cursorRows[6].removable, cursorRows[6].protected = true, true  -- `default` inherits it
local ownName = cursorRows[2].name
entry.onClose()
entry.onOpen()
flushReads()
H.goHome()
clickText("Input")
if not H.byKey("f:" .. THEME .. ":cursor") then clickText("Cursor") end
flushReads()
H.byKey("f:" .. THEME .. ":cursor").props.onClick()
local rm = H.byKey("f:" .. THEME .. ":cursor-rm-2")
assert(rm and rm.props.enabled and not H.byKey("f:" .. THEME .. ":cursor-rm-3"), "only removable ones: " .. screen())
local function trash(index) return H.byKey("f:" .. THEME .. ":cursor-rm-" .. index).props end
assert(trash(4).enabled and trash(4).tooltip == "Delete Theme04 from your home folder when you save", trash(4).tooltip)
assert(trash(5).enabled == false and trash(5).tooltip:find("came with your system", 1, true), "system themes")
assert(trash(6).enabled == false and trash(6).tooltip == "Theme06 is Umbriel's default cursor theme", "the default")
trash(4).onClick()
assert(store.cursorRemovals.Theme04 and H.fullScreen():find("Deleted on save", 1, true), "queued: " .. screen())
trash(4).onClick()
assert(store.cursorRemovals.Theme04 == nil, "kept again")
local before = store.pendingCount()
rm.props.onClick()
assert(store.cursorRemovals[ownName] and store.pendingCount() == before + 1, "queued")
assert(H.byKey("f:" .. THEME .. ":cursor-2-badge") and H.byKey("f:" .. THEME .. ":cursor-rm-2").props.tooltip
       == "Keep " .. ownName, "badge and Keep")
local sent = store.changeSet().cursor_remove
assert(sent and sent[1] == ownName, "sent with the save")
entry.onKey("ctrl+z", true)
assert(store.cursorRemovals[ownName] == nil, "undone")
H.byKey("f:" .. THEME .. ":cursor-rm-2").props.onClick()  -- the list stays open
H.byKey("f:" .. THEME .. ":cursor-2").props.onClick()  -- picking it keeps it, in one step
assert(store.cursorRemovals[ownName] == nil and store.fieldChanges[THEME].value == ownName, "picked and kept")
H.byKey("f:" .. THEME .. ":cursor").props.onClick()
assert(H.byKey("f:" .. THEME .. ":cursor-rm-2").props.enabled == false, "the theme in use can't be removed")
entry.onKey("ctrl+z", true)
assert(store.fieldChanges[THEME] == nil or store.fieldChanges[THEME].value ~= ownName, "one undo step")
assert(store.cursorRemovals[ownName], "the undo brought the queued removal back")
store.discardAll()
assert(next(store.cursorRemovals) == nil, "discard drops it")
-- a queued removal of a theme that is gone meanwhile (an earlier save removed it) is dropped when the list loads
store.removeCursorTheme("Gone-Theme")
entry.onClose()
entry.onOpen()
flushReads()
H.goHome()
clickText("Input")
if not H.byKey("f:" .. THEME .. ":cursor") then clickText("Cursor") end
flushReads()
assert(store.cursorRemovals["Gone-Theme"] == nil and store.cursorRemovals[ownName] == nil, "dropped")
H.byKey("f:" .. THEME .. ":cursor").props.onClick()
replies["open-cursor-folder"] = function() return true, json.encode({ folder = "/home/u/.local/share/icons" }) end
H.byKey("f:" .. THEME .. ":cursor-folder").props.onClick()
flushReads()
assert(lastCall("open-cursor-folder") and H.fullScreen():find("Opened /home/u/.local/share/icons.", 1, true), screen())
H.byKey("f:" .. THEME .. ":cursor").props.onClick()  -- close the list again

-- opening the list asks again, showing the old rows until the answer: a theme deleted by hand goes, no reopen needed
table.remove(cursorRows, 7)  -- Theme07, deleted in the file manager
H.hold("cursor-themes")
H.byKey("f:" .. THEME .. ":cursor").props.onClick()
assert(H.fullScreen():find("Theme07", 1, true) and not hasText("Looking for cursor themes…"), "old rows meanwhile")
H.release("cursor-themes", true)
flushReads()
assert(H.byKey("f:" .. THEME .. ":cursor-list") and not H.fullScreen():find("Theme07", 1, true), screen())
H.byKey("f:" .. THEME .. ":cursor").props.onClick()

-- the dropdown's last row opens the cursor store page (nothing is asked before Browse)
if not H.byKey("f:" .. THEME .. ":cursor") then clickText("Cursor") end
flushReads()
H.byKey("f:" .. THEME .. ":cursor").props.onClick()
H.byKey("f:" .. THEME .. ":cursor-store").props.onClick()
assert(hasText("Cursor themes") and H.byKey("cstore-browse") and not lastCall("cursor-store"), screen())
entry.onKey("alt+Left", true)
store.discardAll()

H.checkBudget("cursor themes", 0.025)
print("cursor themes ok")
