-- Drives the panel through state that outlives one screen: drafts, discarded input text, reopening
-- while a request is running, and inputs that are reused between entries.
-- Usage: lua state_test.lua PLUGIN_DIR FIXTURE_DIR
local H = dofile((arg[0]:match("^(.*)/") or ".") .. "/harness.lua")
local entry = H.start("panel.luau")
local json, fixtures, files, calls, replies, loaded, pluginDir = H.json, H.fixtures, H.files, H.calls, H.replies, H.loaded, H.pluginDir
local flushReads, hasText, find, clickText, lastCall, screen = H.flushReads, H.hasText, H.find, H.clickText, H.lastCall, H.screen

local input, goHome = H.input, H.goHome
local function countCalls(command)
  local count = 0
  for _, call in ipairs(calls) do if call.command == command then count = count + 1 end end
  return count
end

-- a draft from last time: an edit that was saved in the meantime is not an unsaved change any more
local state = json.decode(fixtures.state)
files["/data/draft.json"] = json.encode({ path = state.path, revision = state.revision, fields = {
  ["general.mod_key"] = { value = state.fields["general.mod_key"] },
  ["appearance.border_width"] = { value = 9 },
} })
entry.onOpen()
flushReads()
local store = loaded[pluginDir .. "/lib/store.luau"]
assert(store.fieldChanges["general.mod_key"] == nil, "a drafted value equal to the file is dropped")
assert(store.fieldChanges["appearance.border_width"].value == 9, "the real edit is restored")
assert(hasText("Restored 1 unsaved change(s) from last time."), screen())
assert(hasText("1 unsaved change"), "one pending change: " .. screen())

-- Previous/Next reuse the page: each entry needs its own inputs, or the last entry's typed text stays
clickText("Window rules")
clickText("Add")
clickText("Open placement")
local second = input("^e:window_rule:2:.*width")
second.props.onChange("640")
find("button", function(n) return n.props.key == "prev" end).props.onClick()
assert(hasText("Window rules · 1 of 2"), screen())
local first = input("^e:window_rule:1:.*width")
assert(first.props.key ~= second.props.key, "entries share an input key: " .. first.props.key)

-- Discard replaces the text of inputs, also of those that were only typed into
goHome()
clickText("Appearance")
if not pcall(input, "^f:appearance%.border_width:num") then clickText("Windows") end
local number = input("^f:appearance%.border_width:num")
assert(number.props.value == "9", "the restored edit is shown: " .. tostring(number.props.value))
number.props.onChange("4")
clickText("Discard")
assert(next(store.fieldChanges) == nil and #store.entryOps == 0, "everything discarded")
local fresh = input("^f:appearance%.border_width:num")
assert(fresh.props.key ~= number.props.key, "the input keeps its key, so it keeps the discarded text")
assert(fresh.props.value ~= "4" and fresh.props.value ~= "9", "discarded value still shown: " .. fresh.props.value)

-- closing while a request runs drops its answer; the page must ask again instead of waiting forever
goHome()
clickText("Outputs")
local runAsync = noctalia.runAsync
noctalia.runAsync = function(argv, callback)
  if argv[4] == "outputs" then return true end  -- never answers
  return runAsync(argv, callback)
end
clickText("Inspect connected outputs")
assert(hasText("Asking Umbriel for outputs…"), screen())
noctalia.runAsync = runAsync
entry.onClose()
replies.outputs = function() return false, "no compositor socket" end
local outputCalls = countCalls("outputs")  -- earlier ones include the output names for output settings
entry.onOpen()
flushReads()
assert(countCalls("outputs") == outputCalls + 1, "outputs requested again after reopening")
assert(hasText("no compositor socket") and not hasText("Umbriel reported no outputs."), "the error is shown: " .. screen())
replies.outputs = function()
  return true, json.encode({ outputs = { { name = "DP-7", description = "Test monitor", modes = {} } } })
end
clickText("Try again")
assert(hasText("DP-7"), "outputs listed after a retry: " .. screen())

-- duplicating a keybind shows the copy's empty shortcut, not the original's
goHome()
clickText("Keybinds")
H.clickShortcut(store.keybinds.rows[1].key)
local keyInput = input("^kb%-key%-")
assert(keyInput.props.value ~= "", "the original shows its key")
clickText("Duplicate")
local copyInput = input("^kb%-key%-")
assert(copyInput.props.key ~= keyInput.props.key and copyInput.props.value == "",
       "the copy shows “" .. tostring(copyInput.props.value) .. "” under key " .. copyInput.props.key)

-- Undo: repeated edits of one value are one step; entry and keybind edits are replayed from the file
goHome()
store.discardAll()
store.setField("appearance.border_width", 5)
store.setField("appearance.border_width", 6)
store.setField("general.mod_key", "Alt")
entry.onKey("ctrl+z", true)
assert(store.fieldChanges["general.mod_key"] == nil and store.fieldChanges["appearance.border_width"].value == 6,
       "the newest edit is undone first")
entry.onKey("ctrl+z", true)
assert(next(store.fieldChanges) == nil, "edits of one field undo as one step")
local rules = #store.entryItems("window_rule")
store.entryOp("window_rule", { op = "add" })
store.entryOp("window_rule", { op = "label", index = rules, text = "A" })
store.entryOp("window_rule", { op = "label", index = rules, text = "Ab" })
entry.onKey("ctrl+z", true)
assert(#store.entryItems("window_rule") == rules + 1 and store.entryItems("window_rule")[rules + 1].label == ""
       and #store.entryOps == 1, "typing a label undoes as one step")
entry.onKey("ctrl+z", true)
assert(#store.entryItems("window_rule") == rules and #store.entryOps == 0, "the added rule is gone")
clickText("Keybinds")
local firstKey = store.keybinds.rows[1].key
H.clickShortcut(firstKey)
input("^kb%-key%-").props.onChange("F12")
input("^kb%-key%-").props.onChange("F11")
assert(store.keybindsDirty and store.keybinds.rows[1].key ~= firstKey, "the shortcut was edited")
clickText("Undo")
assert(store.keybinds.rows[1].key == firstKey and not store.keybindsDirty, "typing a shortcut undoes as one step")
assert(input("^kb%-key%-").props.value ~= "F11", "the input shows the restored shortcut")
entry.onKey("ctrl+z", true)
assert(hasText("Nothing to undo."), screen())

-- a successful save removes a draft that still held the saved edits
goHome()
store.setField("general.mod_key", "Alt")
files["/data/draft.json"] = "{}"
replies.preview = function()
  return true, json.encode({ changed = true, summary = {}, sections = {},
                             validation = { ran = true, valid = true, diagnostics = {} } })
end
replies.save = function() return true, fixtures.saved end
entry.onKey("ctrl+s", true)
flushReads()
clickText("Save")
flushReads()
assert(hasText("Saved."), screen())
assert(files["/data/draft.json"] == nil, "the stale draft is gone after saving")

-- an edit made while a save runs stays pending afterwards (the save only clears what it wrote)
goHome()
store.discardAll()
store.setField("appearance.border_width", 11)
local held
local plainRunAsync = noctalia.runAsync
noctalia.runAsync = function(argv, callback)
  if argv[4] == "save" then held = function() plainRunAsync(argv, callback) end; return true end
  return plainRunAsync(argv, callback)
end
entry.onKey("ctrl+s", true)
flushReads()
clickText("Save")
assert(held, "the save started")
store.setField("appearance.border_width", 7)
noctalia.runAsync = plainRunAsync
held()
flushReads()
assert(store.fieldChanges["appearance.border_width"] and store.fieldChanges["appearance.border_width"].value == 7,
       "the edit made while saving survived")
assert(hasText("Saved. Edits made while saving are still unsaved."), screen())
store.discardAll()

-- a draft for another config is parked, not deleted, and comes back when that config opens
files["/data/draft.json"] = json.encode({ path = "/other/config.toml", revision = {},
                                          fields = { ["appearance.border_width"] = { value = 3 } } })
local drafts = loaded[pluginDir .. "/lib/drafts.luau"]
local note = drafts.restore()
assert(note and note:find("/other/config.toml", 1, true), tostring(note))
assert(files["/data/draft-other-config.json"] and next(store.fieldChanges) == nil, "parked, not applied")
local ownPath = store.state.path
store.state.path = "/other/config.toml"
assert(drafts.restoreParked() == "Restored 1 unsaved change(s) from last time.", "parked edits restored")
assert(store.fieldChanges["appearance.border_width"].value == 3 and files["/data/draft-other-config.json"] == nil)
store.state.path = ownPath
store.discardAll()

-- a desktop part that saved keeps its new revision when the other part fails; undo can't revert saved values
goHome()
store.setDesktop("userdirs", "MUSIC", "/tmp/music-test")
store.setDesktop("roles", "Web browser", "test-browser.desktop")
replies["desktop-save"] = function()
  return true, json.encode({ userdirs = { values = {}, revision = "saved-rev" },
                             errors = { apps = "Default applications changed externally." } })
end
entry.onKey("ctrl+s", true)
flushReads()
clickText("Save")
flushReads()
local pending = store.desktopChanges()
assert(store.desktop.userdirs.revision == "saved-rev" and pending and not pending.userdirs and pending.apps,
       "only the failed part stays pending")
assert(hasText("Desktop settings were not saved: Default applications changed externally."), screen())
replies["desktop-save"] = nil
store.discardAll()
goHome()
store.setDesktop("userdirs", "MUSIC", "/tmp/music-test-2")
entry.onKey("ctrl+s", true)
flushReads()
clickText("Save")
flushReads()
assert(not store.canUndo(), "no undo step after a desktop-only save")

H.checkBudget("state", 0.025)
print("state ok")
