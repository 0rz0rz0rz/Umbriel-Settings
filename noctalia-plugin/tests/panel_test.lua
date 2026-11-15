-- Drives the Noctalia panel (panel.luau) through the main flows.
-- Usage: lua panel_test.lua PLUGIN_DIR FIXTURE_DIR   (fixtures come from the real helper, see test_panel.py)
local H = dofile((arg[0]:match("^(.*)/") or ".") .. "/harness.lua")
local entry = H.start("panel.luau")
local json, fixtures, files, calls, replies, loaded, pluginDir = H.json, H.fixtures, H.files, H.calls, H.replies, H.loaded, H.pluginDir
local flushReads, hasText, find, clickText, lastCall, screen = H.flushReads, H.hasText, H.find, H.clickText, H.lastCall, H.screen

-- ------------------------------------------------------------------ scenario
entry.onOpen()
flushReads()
assert(lastCall("meta") and lastCall("read") and lastCall("desktop"), "loads meta, config and desktop")
assert(hasText("Umbriel Settings"), "home header")
assert(hasText("Appearance") and hasText("Window rules") and hasText("Keybinds"), "page cards")

-- search finds a setting by its help text and opens the right group
local search = find("input", function(n) return tostring(n.props.key):match("^search:") end)
search.props.onChange("modifier")
flushReads()
assert(hasText("Mod key"), "search shows Mod key: " .. screen())
clickText("Mod key")
assert(hasText("General") and hasText("Session"), "opened General")
local select = find("select", function(n) return n.props.key == "f:general.mod_key:select" end)
local alt
for i, option in ipairs(select.props.options) do if option == "Alt" then alt = i - 1 end end
select.props.onChange(tostring(alt))
assert(hasText("1 unsaved change"), "save bar counts the edit")
assert(hasText("changed"), "row shows the changed badge")

-- the toggle of a bool field and undo
local toggle = find("toggle", function(n) return n.props.key == "f:general.show_cheatsheet:toggle" end)
toggle.props.onChange(tostring(not toggle.props.checked))
assert(hasText("2 unsaved changes"))
find("button", function(n) return n.props.key == "f:general.show_cheatsheet:undo" end).props.onClick()
assert(hasText("1 unsaved change"), "undo restores the loaded value")

-- review sends the change set and shows the readable summary
replies.preview = function(request)
  assert(request.changes.fields["general.mod_key"].value == "Alt", "preview gets the field change")
  return true, json.encode({ changed = true, summary = { { page = "General", label = "Mod key", old = "Super",
    new = "Alt", id = "general.mod_key" } }, sections = { { title = "[general]", diff = "-a\n+b\n" } },
    validation = { ran = true, valid = true, diagnostics = {} } })
end
clickText("Review & save")
flushReads()
assert(hasText("Review changes") and hasText("Umbriel accepts the new config."), "review page: " .. screen())
replies.save = function(request)
  assert(request.validate == true and request.changes.revision.config, "save request")
  return true, fixtures.saved
end
clickText("Save")
flushReads()
assert(lastCall("save"), "saved")
assert(not hasText("Review & save"), "no pending changes after saving: " .. screen())
assert(hasText("Saved."), "flash after save: " .. screen())

-- rejected configs are not written and the diagnostic links to the setting
entry.onKey("ctrl+f", true)
search = find("input", function(n) return tostring(n.props.key):match("^search:") end)
search.props.onChange("")
clickText("General")
select = find("select", function(n) return n.props.key == "f:general.mod_key:select" end)
select.props.onChange("0")
replies.preview = function()
  return true, json.encode({ changed = true, summary = {}, sections = {},
    validation = { ran = true, valid = false, diagnostics = { { severity = "error", message = "bad mod key",
      field = "general.mod_key" } } } })
end
entry.onKey("ctrl+s", true)
flushReads()
assert(hasText("Saving is disabled until Umbriel accepts the config, or turn off the check."), screen())
clickText("Go to setting")
assert(hasText("General"), "jumped to the setting")

-- rule editor: add an entry, name it, and record the operations
entry.onKey("ctrl+f", true)
clickText("Window rules")
clickText("Add")
local label = find("input", function(n) return tostring(n.props.key):match("^label%-window_rule") end)
label.props.onChange("Browser")
label.props.onChange("Browsers")
assert(hasText("Window rules · 2 of 2") or hasText("Window rules · 1 of 1"), screen())
local store = loaded[pluginDir .. "/lib/store.luau"]
local ops = {}
for _, op in ipairs(store.entryOps) do table.insert(ops, op.op) end
assert(table.concat(ops, ",") == "add,label", "typing coalesces label edits: " .. table.concat(ops, ","))

-- keybinds: change a shortcut with the modifier chips
entry.onKey("ctrl+f", true)
clickText("Keybinds")
local first = store.keybinds.rows[1]
clickText(first.key)
find("button", function(n) return n.props.key == "mod-Shift" end).props.onClick()
assert(store.keybinds.rows[1].key:find("Shift"), "Shift added: " .. store.keybinds.rows[1].key)
assert(store.keybindsDirty)

-- helper errors are shown, not swallowed
replies.backups = function() return false, "disk on fire" end
entry.onKey("ctrl+f", true)
clickText("Backups")
assert(hasText("disk on fire"), "error shown: " .. screen())

-- title-bar follow state (background follows the KDE header color at D7)
local titlebarState = { noctalia = true, palette = true, old_include = "titlebar.toml", fields = {
  background = { source = "kde_header", role = "surface_container", alpha = "D7", color = "#202020D7" } } }
replies.titlebar = function() return true, json.encode(titlebarState) end
replies["kde-colors"] = function() return true, json.encode({ available = true,
  colors = { ["colors.title_bar.background"] = "#303030", ["colors.title_bar.background_unfocused"] = "#101010" },
  backgrounds = { ["colors.title_bar.background"] = "#202020", ["colors.title_bar.background_unfocused"] = "#101010" } }) end
replies["titlebar-follow"] = function(request)
  if request.source then
    titlebarState.fields[request.field] = { source = request.source, role = "surface", alpha = "FF", color = "#101010FF" }
  else
    titlebarState.fields[request.field] = nil
  end
  return true, json.encode(titlebarState)
end

-- smoke: every page and every group renders (covers every field kind's row)
local function goHome()
  entry.onKey("ctrl+f", true)
  find("input", function(n) return tostring(n.props.key):match("^search:") end).props.onChange("")
end
local names = {}
for name in pairs(store.meta.pages) do table.insert(names, name) end
table.sort(names)
for _, name in ipairs(names) do
  goHome()
  clickText(name)
  local page = store.meta.pages[name]
  for _, group in ipairs(page.groups or {}) do clickText(group.title) end
end

-- color rows open an inline picker; number rows take typed values
goHome()
clickText("Colors")
find("box", function(n) return n.props.onClick ~= nil end).props.onClick()
local picker = find("colorPicker", function() return true end)
picker.props.onChangeEnd("#112233ff")
flushReads()  -- a picked color stops following; deliver that answer
assert(lastCall("titlebar-follow").request.source == nil, "picking a color stops following")
if not hasText("Background unfocused") then clickText("Title bar") end
local function opacitySlider(id)
  return find("slider", function(n) return n.props.key == "f:" .. id .. ":opacity-slider" end, "opacity slider for " .. id)
end
assert(opacitySlider("colors.title_bar.background").props.value == 1, "the picked #112233FF is fully opaque")
opacitySlider("colors.title_bar.background").props.onChange("0.5")
assert(store.fieldChanges["colors.title_bar.background"].value == "#11223380", "0.5 is alpha 80, color kept")
opacitySlider("colors.title_bar.background_unfocused").props.onChange("0.84")
assert(store.fieldChanges["colors.title_bar.background_unfocused"].value == "#1A1A1FD6", "0.84 rounds to D6")
flushReads()  -- runs the frame tick that renderSoon waits for
assert(hasText("0.84 · D6"), "value and hex shown: " .. screen())

-- title-bar backgrounds can follow Noctalia's palette instead of a fixed color
store.revertField("colors.title_bar.background")
store.revertField("colors.title_bar.background_unfocused")
goHome()
clickText("Colors")
if not hasText("Background unfocused") then clickText("Title bar") end
find("button", function(n) return n.props.key == "f:colors.title_bar.background:kde:KDE header" end).props.onClick()
flushReads()
assert(hasText("Follows Noctalia · KDE header"), "follow state shown: " .. screen())
opacitySlider("colors.title_bar.background").props.onChange("0.5")
local followCall = lastCall("titlebar-follow")
assert(followCall.request.field == "background" and followCall.request.source == "kde_header"
       and followCall.request.opacity == 0.5, "slider changes the followed opacity")
assert(store.fieldChanges["colors.title_bar.background"].value == "#101010FF", "the followed color is queued for review")
store.setField("include.optional.files", { "effect.toml", "titlebar.toml", "noctalia.toml" })
find("button", function(n) return n.props.key == "f:colors.title_bar.background_unfocused:kde:KDE" end).props.onClick()
followCall = lastCall("titlebar-follow")
assert(followCall.request.field == "background_unfocused" and followCall.request.source == "kde", "KDE button follows")
flushReads()
assert(store.fieldChanges["colors.title_bar.background_unfocused"].value == "#101010FF", "KDE color queued")
local includes = store.fieldChanges["include.optional.files"].value
assert(#includes == 2 and includes[2] == "noctalia.toml", "the old titlebar.toml include is removed")
assert(hasText("Follows Noctalia · KDE"), screen())
-- typing a fixed color stops following
local hex = find("input", function(n) return tostring(n.props.key):match("^f:colors%.title_bar%.background_unfocused:hex") end)
hex.props.onChange("#123456FF")
followCall = lastCall("titlebar-follow")
assert(followCall.request.field == "background_unfocused" and followCall.request.source == nil, "a fixed color stops following")
store.revertField("include.optional.files")
goHome()
clickText("Appearance")
clickText("Windows")
local number = find("input", function(n) return tostring(n.props.key):match("^f:appearance%.border_width:num") end)
number.props.onChange("abc")
assert(hasText("Enter a whole number between 0 and 100"), screen())
number.props.onChange("4")
assert(store.fieldChanges["appearance.border_width"].value == 4)

-- rule detail with every group, and the output inspector
goHome()
clickText("Window rules")
clickText("1. firefox (app id)")
for _, group in ipairs(store.meta.editors.window_rule.groups) do clickText(group.title) end
-- unset table fields: clearing a box is not an error, typing fills the other parts from the hints
clickText("Open placement")
local width = find("input", function(n) return tostring(n.props.key):match("default_floating_size_px:width:") end)
width.props.onChange("12")
width.props.onChange("")
assert(not hasText("width: enter a number"), "empty box is not an error")
width.props.onChange("abc")
assert(hasText("width: enter a number"), "non-number is an error")
width.props.onChange("900")
local sized = store.entryOps[#store.entryOps]
assert(sized.field == "default_floating_size_px" and sized.value.width == 900 and sized.value.height == 600,
  "other parts come from the hints")
-- optional booleans without a default are three-way: Any / On / Off
clickText(store.meta.editors.window_rule.groups[1].title)
local any = find("button", function(n) return tostring(n.props.key):match("match%.is_focused:tri:1$") end)
assert(any.props.text == "Any" and any.props.selected, "unset match bool shows Any")
find("button", function(n) return tostring(n.props.key):match("match%.is_focused:tri:3$") end).props.onClick()
local op = store.entryOps[#store.entryOps]
assert(op.op == "set" and op.field == "match.is_focused" and op.value == false, "Off sets false")
find("button", function(n) return tostring(n.props.key):match("match%.is_focused:tri:1$") end).props.onClick()
assert(store.entryOps[#store.entryOps].op == "unset", "Any unsets")
replies.outputs = function()
  return true, json.encode({ outputs = { { name = "DP-1", config_name = "Acme 1", description = "Acme (DP-1)",
    modes = { { width = 2560, height = 1440, refresh_mhz = 164999, current = true },
              { width = 1920, height = 1080, refresh_mhz = 60000, preferred = true } } } } })
end
goHome()
clickText("Outputs")
clickText("Inspect connected outputs")
clickText("Use for this output")
local last = store.entryOps[#store.entryOps]
assert(last.editor == "output" and last.field == "mode" and last.value == "2560x1440@164.999", last.value)

-- maps: edit a row in place
goHome()
clickText("Environment")
find("button", function(n) return n.props.tooltip == "Edit" end).props.onClick()
clickText("Apply")
assert(store.mapOps[#store.mapOps].name == "QT_QPA_PLATFORM")

-- desktop pages and the app picker
goHome()
clickText("User folders")
goHome()
clickText("Default apps")
-- the picker resolves only a few icons per callback (Noctalia's CPU budget) and fills in the rest later
for i = 1, 20 do
  table.insert(store.desktop.apps.apps, { id = "fake" .. i .. ".desktop", name = "Fake app " .. i })
end
local iconCalls = 0
local appIconPath = noctalia.appIconPath
noctalia.appIconPath = function() iconCalls = iconCalls + 1; return nil end
find("row", function(n) return n.props.key == "role-Web browser" end).props.onClick()
assert(hasText("Choose an app"), screen())
assert(iconCalls > 0 and iconCalls <= 6, "icon lookups in one callback: " .. iconCalls)
for _ = 1, 10 do flushReads() end
local afterFrames = iconCalls
assert(afterFrames >= 20, "remaining icons resolved on later frames: " .. afterFrames)
flushReads()
assert(iconCalls == afterFrames, "icons are cached")
-- slow lookups stop once the render's icon time budget is spent (always at least one per render)
local fakeNow = 0
noctalia.nowMs = function() return fakeNow end
noctalia.appIconPath = function() iconCalls = iconCalls + 1; fakeNow = fakeNow + 10; return nil end
for i = 1, 10 do table.insert(store.desktop.apps.apps, { id = "slow" .. i .. ".desktop", name = "Fake app slow " .. i }) end
iconCalls = 0
find("input", function(n) return n.props.key == "app-search" end).props.onChange("slow")
assert(iconCalls == 1, "slow icon lookups in one callback: " .. iconCalls)
noctalia.nowMs = nil
noctalia.appIconPath = appIconPath
find("input", function(n) return n.props.key == "app-search" end).props.onChange("")
find("input", function(n) return n.props.key == "app-id" end).props.onChange("firefox.desktop")
clickText("Use")
assert(store.desktop.apps.roles["Web browser"] == "firefox.desktop")

-- backups list and comparison, and about
replies.backups = function() return true, json.encode({ backups = {
  { path = "/b/config.toml.1.bak", name = "config.toml.1.bak", time = "2026-11-14 10:00:00", size = 2048 } } }) end
replies["backup-diff"] = function() return true, json.encode({ diff = "-x\n+y\n" }) end
goHome()
clickText("Backups")
clickText("Compare")
assert(find("markdown", function(n) return n.props.text:find("```diff", 1, true) end))
clickText("Select all")
assert(hasText("Delete 1 backup") and hasText("Clear selection"), "select all marks every backup")
replies["delete-backups"] = function(request)
  return true, json.encode({ deleted = { "config.toml.1.bak" }, errors = {}, backups = { backups = {} } })
end
clickText("Delete 1 backup")
assert(lastCall("delete-backups").request.snapshots[1] == "/b/config.toml.1.bak", "marked backup deleted")
assert(hasText("No backups yet."), "list refreshed after delete")
goHome()
replies.about = function() return true, json.encode({ editor = "kate", palette = { noctalia = true } }) end
replies["set-editor"] = function(request) return true, json.encode({ editor = request.editor }) end
clickText("About")
assert(hasText("Every option of this version has a setting here.") or screen():find("not part of this version: `animation", 1, true),
       "schema coverage: " .. screen())
local editorInput = find("input", function(n) return tostring(n.props.key):match("^editor:") end)
assert(editorInput.props.value == "kate", "saved editor shown")
editorInput.props.onChange("code --new-window")
clickText("Save")
assert(lastCall("set-editor").request.editor == "code --new-window", "editor saved")
assert(not hasText("Set up palette template"), "palette template is app-only")

-- closing keeps a draft of unsaved edits for the next start
entry.onClose()
assert(files["/data/draft.json"], "draft written on close")
local draft = json.decode(files["/data/draft.json"])
assert(draft.fields["general.mod_key"] and draft.keybinds, "draft holds field and keybind edits")

-- leftover request/response files are cleaned up
for path in pairs(files) do assert(not path:match("%.req%.json$"), "request file left behind: " .. path) end
H.checkBudget("panel", 0.025)
print("panel ok")
