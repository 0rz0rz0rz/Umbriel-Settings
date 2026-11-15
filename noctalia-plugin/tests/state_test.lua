-- Drives the panel through state that outlives one screen: drafts, discarded input text, reopening
-- while a request is running, and inputs that are reused between entries.
-- Usage: lua state_test.lua PLUGIN_DIR FIXTURE_DIR
local H = dofile((arg[0]:match("^(.*)/") or ".") .. "/harness.lua")
local entry = H.start("panel.luau")
local json, fixtures, files, calls, replies, loaded, pluginDir = H.json, H.fixtures, H.files, H.calls, H.replies, H.loaded, H.pluginDir
local flushReads, hasText, find, clickText, lastCall, screen = H.flushReads, H.hasText, H.find, H.clickText, H.lastCall, H.screen

local function input(pattern)
  return find("input", function(n) return tostring(n.props.key):match(pattern) end, "no input " .. pattern)
end
local function goHome()
  entry.onKey("ctrl+f", true)
  input("^search:").props.onChange("")
end
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
entry.onOpen()
flushReads()
assert(countCalls("outputs") == 1, "outputs requested again after reopening")
assert(hasText("no compositor socket") and not hasText("Umbriel reported no outputs."), "the error is shown: " .. screen())
replies.outputs = function()
  return true, json.encode({ outputs = { { name = "DP-7", description = "Test monitor", modes = {} } } })
end
clickText("Try again")
assert(hasText("DP-7"), "outputs listed after a retry: " .. screen())

-- duplicating a keybind shows the copy's empty shortcut, not the original's
goHome()
clickText("Keybinds")
clickText(store.keybinds.rows[1].key)
local keyInput = input("^kb%-key%-")
assert(keyInput.props.value ~= "", "the original shows its key")
clickText("Duplicate")
local copyInput = input("^kb%-key%-")
assert(copyInput.props.key ~= keyInput.props.key and copyInput.props.value == "",
       "the copy shows “" .. tostring(copyInput.props.value) .. "” under key " .. copyInput.props.key)

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

H.checkBudget("state", 0.025)
print("state ok")
