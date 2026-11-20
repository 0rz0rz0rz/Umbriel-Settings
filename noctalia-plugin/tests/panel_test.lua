-- Drives the Noctalia panel (panel.luau) through the main flows.
-- Usage: lua panel_test.lua PLUGIN_DIR FIXTURE_DIR   (fixtures come from the real helper, see test_panel.py)
local H = dofile((arg[0]:match("^(.*)/") or ".") .. "/harness.lua")
local entry = H.start("panel.luau")
local json, fixtures, files, calls, replies, loaded, pluginDir = H.json, H.fixtures, H.files, H.calls, H.replies, H.loaded, H.pluginDir
local flushReads, hasText, find, clickText, lastCall, screen = H.flushReads, H.hasText, H.find, H.clickText, H.lastCall, H.screen

-- ------------------------------------------------------------------ scenario
replies.outputs = function()
  return true, json.encode({ outputs = { { name = "HDMI-A-1", config_name = "Acme 2", modes = {} } } })
end
entry.onOpen()
flushReads()
assert(lastCall("meta") and lastCall("read") and lastCall("desktop"), "loads meta, config and desktop")
assert(hasText("Umbriel Settings"), "home header")
assert(hasText("Appearance") and hasText("Window rules") and hasText("Keybinds"), "page cards")

-- the clear button empties the search box (a new, empty input) and is disabled while there is nothing to clear
local function searchInput() return H.input("^search:") end
local function clearButton() return find("button", function(n) return n.props.key == "search-clear" end) end
assert(clearButton().props.enabled == false, "nothing to clear yet")
local typed = searchInput()
typed.props.onChange("modifier")
flushReads()
assert(hasText("Mod key") and clearButton().props.enabled, "results and an enabled clear button: " .. screen())
clearButton().props.onClick()
assert(searchInput().props.key ~= typed.props.key and (searchInput().props.value or "") == "", "the box is emptied")
assert(not hasText("Mod key") and clearButton().props.enabled == false, "results gone: " .. screen())

-- search finds a setting by its help text and opens the right group
local search = H.input("^search:")
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
assert(hasText("unsaved"), "row shows the unsaved badge")
assert(hasText("Default Super"), "the status line names the default: " .. screen())
local byKey = H.byKey
local function overrideBadge() return byKey("f:general.mod_key:override") end
assert(overrideBadge() and hasText("Override"), "an overridden key shows the Override badge")

-- the toggle of a bool field and undo
local toggle = find("toggle", function(n) return n.props.key == "f:general.show_cheatsheet:toggle" end)
toggle.props.onChange(tostring(not toggle.props.checked))
assert(hasText("2 unsaved changes"))
find("button", function(n) return n.props.key == "f:general.show_cheatsheet:undo" end).props.onClick()
assert(hasText("1 unsaved change"), "undo restores the loaded value")

-- Reset asks to confirm like Noctalia; an edit in between cancels the confirmation
local function resetButton() return byKey("f:general.mod_key:reset") end
assert(resetButton().props.text == "Reset" and resetButton().props.variant == "ghost", "Reset is a ghost button")
resetButton().props.onClick()
assert(resetButton().props.text == "Confirm Reset" and resetButton().props.variant == "destructive", "asks first")
assert(overrideBadge(), "the first click keeps the key")
toggle = find("toggle", function(n) return n.props.key == "f:general.show_cheatsheet:toggle" end)
toggle.props.onChange(tostring(not toggle.props.checked))
assert(resetButton().props.text == "Reset", "another edit cancels the confirmation")
find("button", function(n) return n.props.key == "f:general.show_cheatsheet:undo" end).props.onClick()
resetButton().props.onClick()
resetButton().props.onClick()
assert(not overrideBadge() and not resetButton(), "confirmed reset removes the key: " .. screen())
clickText("Undo")
assert(overrideBadge() and hasText("1 unsaved change"), "undo brings the override back: " .. screen())

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
-- the save bar stays (so the page height and its scrollbar don't change with every edit), quiet and disabled
assert(hasText("No unsaved changes"), "no pending changes after saving: " .. screen())
assert(find("button", function(n) return n.props.text == "Review & save" end).props.enabled == false,
       "nothing to review")
assert(hasText("Saved."), "flash after save: " .. screen())

-- rejected configs are not written and the diagnostic links to the setting
entry.onKey("ctrl+f", true)
search = H.input("^search:")
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
-- undo puts the name box back too (a new key: inputs are uncontrolled)
local labelKey = label.props.key
entry.onKey("ctrl+z", true)
label = find("input", function(n) return tostring(n.props.key):match("^label%-window_rule") end)
assert(label.props.key ~= labelKey and label.props.value == "", "the name box shows the undone name")
label.props.onChange("Browsers")

-- an armed "Click again to delete" is disarmed by leaving the page (and by Ctrl+F)
local function deleteButton() return find("button", function(n) return tostring(n.props.key):match("^delete%-window_rule%-") end) end
deleteButton().props.onClick()
assert(hasText("Click again to delete"), "first click arms the delete: " .. screen())
entry.onKey("alt+Left", true)
clickText("2. Browsers")
assert(not hasText("Click again to delete"), "navigation disarms it: " .. screen())
deleteButton().props.onClick()
entry.onKey("ctrl+f", true)
clickText("Window rules")
clickText("2. Browsers")
assert(not hasText("Click again to delete"), "Ctrl+F disarms it: " .. screen())

-- keybinds: change a shortcut with the modifier chips
entry.onKey("ctrl+f", true)
clickText("Keybinds")
local first = store.keybinds.rows[1]
H.clickShortcut(first.key)
find("button", function(n) return n.props.key == "mod-Shift" end).props.onClick()
assert(store.keybinds.rows[1].key:find("Shift"), "Shift added: " .. store.keybinds.rows[1].key)
assert(store.keybindsDirty)

-- keybinds: reorder shortcuts and groups by drag and drop, and with the buttons
local walk = H.walk
local function order()
  local keys = {}
  for _, row in ipairs(store.keybinds.rows) do table.insert(keys, row.key .. "@" .. (row.group or "")) end
  return table.concat(store.keybinds.groups, ",") .. " / " .. table.concat(keys, ",")
end
local function newGroup(name)
  find("input", function(n) return tostring(n.props.key):match("^grp%-new%-") end).props.onSubmit(name)
end
local launcher, closer = store.keybinds.rows[1].key, store.keybinds.rows[2].key
entry.onKey("alt+Left", true)
newGroup("Apps")
newGroup("Windows")
assert(order() == "Apps,Windows / " .. launcher .. "@," .. closer .. "@", order())
assert(hasText("Ungrouped  ·  2") and hasText("Apps  ·  0"), "empty groups stay as drop targets: " .. screen())
H.drag("kbgrip-2", "kbgap-1")  -- before the first row of its group
assert(order() == "Apps,Windows / " .. closer .. "@," .. launcher .. "@", order())
H.drag("kbgrip-1", "kbgroup-2-Windows")  -- onto a group: appended to it
H.drag("kbgrip-2", "kbgroup-1-Apps")
assert(order() == "Apps,Windows / " .. launcher .. "@Apps," .. closer .. "@Windows", "rows follow the groups: " .. order())
local beforeGroupMove = order()
H.drag("kbggrip-2", "kbggap-1-Apps")  -- a whole group before another one; its rows move with it
assert(order() == "Windows,Apps / " .. closer .. "@Windows," .. launcher .. "@Apps", order())
H.drag("kbggrip-1", "kbggap-1-Windows")  -- onto its own gap: nothing to record
entry.onKey("ctrl+z", true)
assert(order() == beforeGroupMove, "one drag is one undo step: " .. order())
entry.onDrop("r|1|no-such-shortcut", "g|0|")  -- the list changed since the drag began
entry.onDrop("g|2|Windows", "r|1|" .. launcher)  -- a group only lands on groups
assert(order() == beforeGroupMove, "stale or mismatched drops are ignored: " .. order())
-- the buttons: group order, and a shortcut's place within its group
find("button", function(n) return n.props.key == "grp-down-1" end).props.onClick()
assert(table.concat(store.keybinds.groups, ",") == "Windows,Apps", order())
find("button", function(n) return n.props.key == "grp-up-2" end).props.onClick()
H.drag("kbgrip-2", "kbgroup-1-Apps")
assert(order() == "Apps,Windows / " .. launcher .. "@Apps," .. closer .. "@Apps", order())
H.clickShortcut(closer)
assert(find("button", function(n) return n.props.key == "kb-down" end).props.enabled == false, "last in its group")
find("button", function(n) return n.props.key == "kb-up" end).props.onClick()
assert(store.keybinds.rows[1].key == closer and hasText(closer), "moved up and still on its page: " .. order())
entry.onKey("alt+Left", true)
-- locked shortcuts have no grip; a filter turns sorting off
store.keybinds.rows[1].locked = true
find("input", function(n) return n.props.key == "kb-filter" end).props.onChange("")
assert(not walk(H.tree(), function(n) return n.props.key == "kbgrip-1" end) and
       walk(H.tree(), function(n) return n.props.key == "kbgrip-2" end), "only unlocked rows drag")
store.keybinds.rows[1].locked = nil
find("input", function(n) return n.props.key == "kb-filter" end).props.onChange("super")
assert(not walk(H.tree(), function(n) return n.kind == "dragSource" or n.kind == "dropZone" end)
       and hasText("Clear the filter to reorder shortcuts and groups."), screen())
find("input", function(n) return n.props.key == "kb-filter" end).props.onChange("")

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
local goHome = H.goHome
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
  return find("slider", function(n) return tostring(n.props.key):find("f:" .. id .. ":opacity-slider:", 1, true) == 1 end,
              "opacity slider for " .. id)
end
assert(opacitySlider("colors.title_bar.background").props.value == 1, "the picked #112233FF is fully opaque")
-- dragging previews the value and stores it on release
local dragged = opacitySlider("colors.title_bar.background")
dragged.props.onChange("0.6")
flushReads()
assert(hasText("0.60 · 99") and store.fieldChanges["colors.title_bar.background"].value == "#112233FF",
       "previewed, not stored yet: " .. screen())
dragged.props.onChange("0.5")
dragged.props.onDragEnd()
assert(store.fieldChanges["colors.title_bar.background"].value == "#11223380", "0.5 is alpha 80, color kept")
H.slide(opacitySlider("colors.title_bar.background_unfocused"), 0.84)
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
H.slide(opacitySlider("colors.title_bar.background"), 0.5)
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

-- rule detail with every group
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
-- rule matches picked from open windows and layers
replies.windows = function()
  return true, json.encode({ windows = {
    { app_id = "firefox", title = "Docs", count = 2, pattern = "^firefox$", title_pattern = "^Docs$" },
    { app_id = "org.gajim.Gajim", title = "Gajim", count = 1, pattern = "^org\\.gajim\\.Gajim$",
      title_pattern = "^Gajim$" } } })
end
goHome()
clickText("Window rules")
clickText("Add")
local ruleIndex = #store.entryItems("window_rule")
clickText("Pick from open windows")
assert(hasText("firefox · 2 windows") and hasText("org.gajim.Gajim"), screen())
H.input("^live%-filter:").props.onChange("gajim")
assert(not hasText("firefox · 2 windows"), "the filter hides other windows: " .. screen())
local appSteps = #store.history
clickText("App and title")
assert(#store.history == appSteps + 1, "app id and title are one undo step")
local item = store.entryItems("window_rule")[ruleIndex]
assert(item.values["match.app_id"] == "^org\\.gajim\\.Gajim$" and item.values["match.title"] == "^Gajim$",
  "app id and title set: " .. tostring(item.values["match.app_id"]))
assert(hasText("Pick from open windows") and hasText("The rule now matches “org.gajim.Gajim”."), screen())
replies.windows = function() return false, "Umbriel is not running" end
clickText("Pick from open windows")
assert(hasText("Umbriel is not running") and hasText("Try again"), screen())
replies.layers = function()
  return true, json.encode({ layers = { { namespace = "noctalia-bar", layer = "top", outputs = { "DP-1" },
                                          pattern = "^noctalia-bar$" } } })
end
goHome()
clickText("Layer rules")
clickText("Add")
clickText("Pick from open layers")
assert(hasText("top · DP-1"), screen())
clickText("Match")
local layerRule = store.entryItems("layer_rule")[#store.entryItems("layer_rule")]
assert(layerRule.values["match.namespace"] == "^noctalia-bar$", "namespace set")

-- curve and effect choices include the config's own named curves and presets
store.meta.fields["animation.windows_in.curve"].names_from = "curve"
local effectField = store.meta.fields["animation.windows_in.effect"]
effectField.kind, effectField.choices, effectField.names_from, effectField.default = "combo", { "" }, "effect", ""
store.mapSet("beziers", "soft", "[0.05, 0.9, 0.1, 1.0]")
store.entryOp("effect_preset", { op = "add", name = "glow" })
goHome()
clickText("Animation")
clickText("Windows opening")
local function options(fid)
  return table.concat(find("select", function(n) return n.props.key == "f:" .. fid .. ":select" end).props.options, ",")
end
assert(options("animation.windows_in.curve"):find(",soft,Custom…$"), options("animation.windows_in.curve"))
assert(options("animation.windows_in.effect") == "None,glow,Custom…", options("animation.windows_in.effect"))
find("select", function(n) return n.props.key == "f:animation.windows_in.effect:select" end).props.onChange("1")
assert(store.value("animation.windows_in.effect") == "glow", "picked the preset")

-- the keyboard layout picker writes layouts, aligned variants and options
replies.xkb = function()
  return true, json.encode({ current = "German",
    layouts = { { name = "us", desc = "English (US)" }, { name = "de", desc = "German" } },
    variants = { de = { { name = "nodeadkeys", desc = "German (no dead keys)" } } },
    options = { { name = "caps", desc = "Caps Lock behavior",
                  items = { { name = "caps:escape", desc = "Make Caps Lock an additional Esc" } } } } })
end
goHome()
clickText("Input")
clickText("Keyboard")
clickText("Choose…")
assert(hasText("Active now: German"), screen())
local function addFrom(query, inputKey, rowKey)
  H.input("^" .. inputKey .. ":").props.onChange(query)
  H.walk(H.byKey(rowKey), function(n) return n.kind == "button" end).props.onClick()
end
local xkbSteps = #store.history
addFrom("german", "xkb%-layout%-q", "xkb-add-de")
assert(#store.history == xkbSteps + 1, "adding a layout is one undo step")
find("select", function(n) return n.props.key == "xkb-variant-1-de" end).props.onChange("1")
addFrom("us", "xkb%-layout%-q", "xkb-add-us")
assert(store.value("input.keyboard.layout") == "de,us" and store.value("input.keyboard.variant") == "nodeadkeys,",
  tostring(store.value("input.keyboard.variant")))
find("button", function(n) return n.props.key == "xkb-up-2" end).props.onClick()
assert(store.value("input.keyboard.layout") == "us,de" and store.value("input.keyboard.variant") == ",nodeadkeys")
addFrom("caps", "xkb%-option%-q", "xkb-opt-caps:escape")
assert(store.value("input.keyboard.options") == "caps:escape")
find("button", function(n) return n.props.key == "xkb-opt-off-caps:escape" end).props.onClick()
find("button", function(n) return n.props.key == "xkb-remove-2" end).props.onClick()
assert(store.value("input.keyboard.variant") == nil and store.value("input.keyboard.options") == nil,
  "an empty list unsets the key")

-- Run now: two clicks send the action; blocked actions can't be run
goHome()
clickText("Keybinds")
H.clickShortcut(launcher)
local run = function() return find("button", function(n) return n.props.key == "kb-run" end) end
assert(run().props.enabled, "spawn kitty may run")
run().props.onClick()
assert(not lastCall("run-action") and hasText("Click again to run"), "the first click only arms it")
run().props.onClick()
assert(lastCall("run-action").request.action == "spawn kitty", "sent the action")
entry.onKey("alt+Left", true)
H.clickShortcut(closer)
assert(not run().props.enabled and run().props.tooltip:find("close"), "window-close is blocked")

-- output settings offer the config's outputs and the connected ones
store.entryOp("output", { op = "add", name = "DP-1" })
goHome()
clickText("General")
clickText("XWayland")
local outputOptions = table.concat(find("select", function(n)
  return n.props.key == "f:general.xwayland_primary_output:select" end).props.options, ",")
assert(outputOptions:find("DP-1", 1, true) and outputOptions:find("HDMI-A-1,Acme 2", 1, true)
       and outputOptions:find("Custom…$"), outputOptions)

-- the first argument of an action is offered from the config's names
goHome()
clickText("Keybinds")
H.clickShortcut(launcher)
local function argSelect() return find("select", function(n) return n.props.key == "kb-arg-select" end) end
local function pickArg(choice)
  for i, option in ipairs(argSelect().props.options) do
    if option == choice then argSelect().props.onChange(tostring(i - 1)); return end
  end
  error("no argument choice " .. choice .. ": " .. table.concat(argSelect().props.options, ","))
end
local function launcherAction()
  for _, row in ipairs(store.keybinds.rows) do if row.key == launcher then return row.action end end
end
H.input("^kb%-action%-").props.onChange("effect-border-set")
assert(table.concat(argSelect().props.options, ",") == "Choose name…,off,glow", "presets plus off")
pickArg("glow")
assert(launcherAction() == "effect-border-set glow" and H.input("^kb%-action%-").props.value ==
       "effect-border-set glow", "the argument is filled in and shown")
-- presets from include files are offered too; a name defined nowhere is still shown as the choice
store.state.included = { effect_preset = { "pulse" } }
H.input("^kb%-action%-").props.onChange("effect-border-set mystery")
local argOptions = table.concat(argSelect().props.options, ",")
assert(argOptions == "Choose name…,off,glow,pulse,mystery (not defined here)", argOptions)
assert(argSelect().props.selectedIndex == 4, "the typed name stays selected")
H.input("^kb%-action%-").props.onChange("workspace-move-to-output DP-1 --output HDMI-A-1")
pickArg("HDMI-A-1")
assert(launcherAction() == "workspace-move-to-output HDMI-A-1 --output HDMI-A-1",
  "replaces only the first argument: " .. launcherAction())
H.input("^kb%-action%-").props.onChange("spawn kitty")
assert(not H.byKey("kb-arg"), "no picker for a command line")

-- Browse… in the panel (it stays above every window): a file browser page of its own (helper `list-dir`)
local listings = {}
replies["list-dir"] = function(request)
  table.insert(listings, request)
  if request.path == "/nope" then return false, "/nope is not a folder." end
  local path = request.path or "/usr/share/umbriel"
  if path == "/usr/share/umbriel/effects" then
    return true, json.encode({ path = path, parent = "/usr/share/umbriel", folders = {},
                               files = { "glow.toml", "pulse.toml" } })
  end
  return true, json.encode({ path = path, parent = "/usr/share", folders = { "effects" }, files = { "config.toml" } })
end
replies["pick-file"] = function(request)
  assert(request.chosen, "the panel sends the file it chose")
  return true, json.encode({ path = request.relative and "shaders/glow.frag" or request.chosen })
end
goHome()
clickText("General")
clickText("Includes")
byKey("f:include.files:browse").props.onClick()
flushReads()
assert(listings[1].filter[2] == "*.toml" and listings[1].config and not listings[1].path, "opens where a chooser would")
assert(byKey("folder-effects") and byKey("file-config.toml"), screen())
byKey("folder-effects").props.onClick()
flushReads()
assert(listings[#listings].path == "/usr/share/umbriel/effects")
H.input("^files%-search%-").props.onChange("pul")
assert(not byKey("file-glow.toml") and byKey("file-pulse.toml"), "the filter narrows the folder")
H.input("^files%-path%-").props.onSubmit("/nope")
flushReads()
assert(hasText("/nope is not a folder.") and byKey("file-pulse.toml"), "a wrong path keeps the folder shown")
byKey("file-pulse.toml").props.onClick()
flushReads()
local includes = store.value("include.files")
assert(includes[#includes] == "/usr/share/umbriel/effects/pulse.toml", "appended to the list")
byKey("f:include.files:browse").props.onClick()
flushReads()
byKey("back").props.onClick()
assert(#store.value("include.files") == #includes, "going back changes nothing")
-- autostart: Browse… lists the installed apps like the default apps; the app's command is appended
table.insert(store.desktop.apps.apps, 1, { id = "aaa-term.desktop", name = "AAA Term" })
replies["app-command"] = function(request) return true, json.encode({ command = "aaa-term --login" }) end
goHome()
clickText("General")
clickText("Session")
byKey("f:general.autostart:browse").props.onClick()
assert(hasText("Choose an app"), screen())
byKey("app-aaa-term.desktop").props.onClick()
flushReads()
assert(lastCall("app-command").request.id == "aaa-term.desktop")
local autostart = store.value("general.autostart")
assert(autostart[#autostart] == "aaa-term --login", "the app's command is appended")
assert(byKey("f:general.autostart:browse"), "back on the form")
-- …or any program: the file browser takes the app list's place, so choosing returns to the form
byKey("f:general.autostart:browse").props.onClick()
clickText("Browse files…")
flushReads()
byKey("file-config.toml").props.onClick()
flushReads()
assert(lastCall("pick-file").request.command == true, "autostart asks for a command")
autostart = store.value("general.autostart")
assert(autostart[#autostart] == "/usr/share/umbriel/config.toml" and byKey("f:general.autostart:browse"), screen())
-- on a text setting, the chosen path replaces the box's text (a new key: inputs are uncontrolled)
goHome()
clickText("Effects")
clickText("glow")
clickText("Preset")  -- groups start closed
local function shaderInput()
  return find("input", function(n) return tostring(n.props.key):match("shader:text:") ~= nil end)
end
local shaderKey = shaderInput().props.key
find("button", function(n) return tostring(n.props.key):match("shader:browse$") ~= nil end).props.onClick()
flushReads()
byKey("file-config.toml").props.onClick()
flushReads()
assert(shaderInput().props.key ~= shaderKey and shaderInput().props.value == "shaders/glow.frag", "the box shows the path")
-- user folders: folders only, then "Use this folder"
replies["pick-folder"] = function(request) return true, json.encode({ path = "$HOME/" .. request.chosen:match("[^/]+$") }) end
goHome()
clickText("User folders")
find("button", function(n) return n.props.text == "Browse…" end).props.onClick()
flushReads()
assert(listings[#listings].folders == true, "only folders")
byKey("folder-effects").props.onClick()
flushReads()
clickText("Use this folder")
flushReads()
assert(lastCall("pick-folder").request.chosen == "/usr/share/umbriel/effects")
local changedDir = false
for _, value in pairs(store.desktop.userdirs.values) do if value == "$HOME/effects" then changedDir = true end end
assert(changedDir, "the folder is set")
store.undo()

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
local fakeNow, nowMs = 0, noctalia.nowMs
noctalia.nowMs = function() return fakeNow end
noctalia.appIconPath = function() iconCalls = iconCalls + 1; fakeNow = fakeNow + 10; return nil end
for i = 1, 10 do table.insert(store.desktop.apps.apps, { id = "slow" .. i .. ".desktop", name = "Fake app slow " .. i }) end
iconCalls = 0
find("input", function(n) return n.props.key == "app-search" end).props.onChange("slow")
assert(iconCalls == 1, "slow icon lookups in one callback: " .. iconCalls)
noctalia.nowMs = nowMs
noctalia.appIconPath = appIconPath
find("input", function(n) return n.props.key == "app-search" end).props.onChange("")
find("input", function(n) return n.props.key == "app-id-role-Web browser" end).props.onChange("firefox.desktop")
clickText("Use")
assert(store.desktop.apps.roles["Web browser"] == "firefox.desktop")
-- an ID typed for one target is not offered to the next one
find("row", function(n) return n.props.key == "role-Web browser" end).props.onClick()
find("input", function(n) return n.props.key == "app-id-role-Web browser" end).props.onChange("typed.desktop")
find("button", function(n) return n.props.tooltip == "Back" or n.props.key == "back" end, "back button").props.onClick()
local otherRole
for role in pairs(store.desktop.apps.roles) do if role ~= "Web browser" then otherRole = role end end
local before = store.desktop.apps.roles[otherRole]
find("row", function(n) return n.props.key == "role-" .. otherRole end).props.onClick()
clickText("Use")
assert(store.desktop.apps.roles[otherRole] == before, otherRole .. " got the ID typed for the web browser")

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

-- number sliders: a drag shows its value in the box and stores it on release
local store = loaded[pluginDir .. "/lib/store.luau"]
entry.onKey("ctrl+f", true)
clickText("Appearance")
if not hasText("Border width") then clickText("Windows") end
local function widthSlider()
  return find("slider", function(n) return tostring(n.props.key):find("f:appearance.border_width:slider:", 1, true) == 1 end)
end
local function widthBox()
  return find("input", function(n) return tostring(n.props.key):find("f:appearance.border_width:num:", 1, true) == 1 end)
end
local width = store.value("appearance.border_width")
local drag = widthSlider()
drag.props.onChange("7")
flushReads()
assert(widthBox().props.value == "7" and store.value("appearance.border_width") == width, "previewed in the box")
drag.props.onDragEnd()
assert(store.value("appearance.border_width") == 7, "stored on release")
-- typing into the box moves the slider; Noctalia reports that move, which must not replace the box being typed in
local box = widthBox()
box.props.onChange("8")
flushReads()
assert(widthBox().props.key == box.props.key, "the box keeps its key (and focus) while typing")
assert(store.value("appearance.border_width") == 8, "typed value stored")
box.props.onChange("12")
flushReads()
assert(widthBox().props.key == box.props.key and store.value("appearance.border_width") == 12, "typing goes on")
store.setField("appearance.border_width", width)

-- Customized settings lists values that differ from Umbriel's defaults and opens them
store.setField("appearance.border_width", 9)
entry.onKey("ctrl+f", true)
clickText("Customized")
assert(hasText("Customized settings") and hasText("Border width"), screen())
assert(not hasText("Show keybind cheatsheet at start"), "a value equal to its default is not customized: " .. screen())
clickText("Border width")
assert(hasText("Appearance") and find("input", function(n) return tostring(n.props.key):match("^f:appearance%.border_width") end),
       "the setting's page opens at the setting: " .. screen())

-- a special value (-1 = automatic) has its own switch: on writes it, off goes back to a number
goHome()
clickText("Appearance")
clickText("Title bar")
local fid = "appearance.title_bar.button_size"
local function chip()
  return find("button", function(n) return n.props.key == "f:" .. fid .. ":special" end, "no Automatic switch")
end
assert(chip().props.text == "Automatic", "the switch is named after the special value")
assert(store.meta.fields[fid].label == "Button size", "the note left the label")
find("input", function(n) return tostring(n.props.key):match("^f:appearance%.title_bar%.button_size:num") end)
  .props.onChange("5")
assert(store.value(fid) == 5 and not chip().props.selected, "a number is set")
local number = store.value(fid)
chip().props.onClick()
assert(store.value(fid) == -1 and chip().props.selected, "on writes -1")
chip().props.onClick()
assert(store.value(fid) == number, "off brings the last number back")

-- closing keeps a draft of unsaved edits for the next start
entry.onClose()
assert(files["/data/draft.json"], "draft written on close")
local draft = json.decode(files["/data/draft.json"])
assert(draft.fields["general.mod_key"] and draft.keybinds, "draft holds field and keybind edits")

-- leftover request/response files are cleaned up
for path in pairs(files) do assert(not path:match("%.req%.json$"), "request file left behind: " .. path) end
H.checkBudget("panel", 0.025)
print("panel ok")
