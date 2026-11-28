-- The Icon theme page (pages/icons.luau): themes from helper icon-themes with their icons, pick (undo), the trash
-- button (queue, Keep, disabled for the theme in use, one it builds on, system themes and ones holding cursors),
-- Review rows, the save (desktop-save `icons`, the list asked again), and the draft keeping the edits.
-- Usage: lua icons_test.lua PLUGIN_DIR FIXTURE_DIR
local H = dofile((arg[0]:match("^(.*)/") or ".") .. "/harness.lua")
local entry = H.start("panel.luau")
local json, replies, fixtures, files, loaded, pluginDir = H.json, H.replies, H.fixtures, H.files, H.loaded, H.pluginDir
local flushReads, hasText, clickText, lastCall, screen = H.flushReads, H.hasText, H.clickText, H.lastCall, H.screen
local byKey = H.byKey

local desktop = json.decode(fixtures.desktop)
desktop.icons = { theme = "Base", revision = "r1", targets = { "GNOME settings", "GTK 3" } }
replies.desktop = function() return true, json.encode(desktop) end
local function row(name, extra)
  local result = { name = name, label = name, inherits = {}, removable = true, system = false, cursors = false,
                   icons = { "/i/" .. name .. "/folder.png", "/i/" .. name .. "/home.svg" } }
  for key, value in pairs(extra or {}) do result[key] = value end
  return result
end
local themes = { row("Base"), row("Fancy", { label = "Fancy Icons", inherits = { "Base" } }), row("Old"),
                 row("Sys", { removable = false, system = true }), row("Both", { removable = false, cursors = true }) }
replies["icon-themes"] = function() return true, json.encode({ themes = themes, complete = true }) end
local function listCalls()
  local count = 0
  for _, call in ipairs(H.calls) do if call.command == "icon-themes" then count = count + 1 end end
  return count
end

entry.onOpen()
flushReads()
local store = loaded[pluginDir .. "/lib/store.luau"]
clickText("Icon theme")
flushReads()
assert(hasText("Icon theme") and byKey("icons-row-1"), screen())
assert(byKey("icon-1-1").props.path == "/i/Base/folder.png", "the theme's own icons")
assert(H.fullScreen():find("Saving writes it to GNOME settings, GTK 3.", 1, true), "where it goes")
assert(hasText("Fancy Icons") and hasText("Fancy"), "label and folder name")
local function trash(index) return byKey("icons-rm-" .. index).props end
assert(trash(1).enabled == false and trash(1).tooltip == "Pick another theme to delete Base", "in use")
assert(trash(4).enabled == false and trash(4).tooltip:find("came with your system", 1, true), "system")
assert(trash(5).enabled == false and trash(5).tooltip:find("cursor theme", 1, true), "holds cursors")

-- picking one: an edit (undoable); the theme it builds on can't be deleted then
byKey("icons-pick-2").props.onClick()
assert(store.desktopChanges().icons.theme == "Fancy" and store.pendingCount() == 1, "picked")
assert(byKey("icons-badge-2") and trash(1).enabled == false and trash(1).tooltip == "The theme you picked builds on Base",
       "Base protected: " .. tostring(trash(1).tooltip))
entry.onKey("ctrl+z", true)
assert(store.desktopChanges() == nil, "undone")
byKey("icons-pick-2").props.onClick()

-- the trash button queues the deletion; Keep takes it back; picking a queued theme keeps it
assert(trash(3).enabled and trash(3).tooltip == "Delete Old from your home folder when you save")
trash(3).onClick()
assert(store.desktopChanges().icons.remove[1] == "Old" and H.fullScreen():find("Deleted on save", 1, true), screen())
trash(3).onClick()
assert(store.desktopChanges().icons.remove == nil, "kept")
trash(3).onClick()

-- the draft keeps both edits
entry.onClose()
local draft = json.decode(files["/data/draft.json"])
assert(draft.desktop.icons.theme == "Fancy" and draft.desktop.icons.removals.Old, "drafted")
entry.onOpen()
flushReads()

-- Review lists them; the save sends the icons part and asks for the list again
H.goHome()
clickText("Icon theme")
flushReads()
entry.onKey("ctrl+s", true)
flushReads()
assert(hasText("Icon theme:  Fancy") and hasText("Icon theme Old:  deleted for good"), screen())
local before = listCalls()
replies["desktop-save"] = function(request)
  assert(request.icons.revision == "r1" and request.icons.theme == "Fancy" and request.icons.remove[1] == "Old")
  desktop.icons = { theme = "Fancy", revision = "r2", targets = { "GNOME settings", "GTK 3" } }
  table.remove(themes, 3)  -- Old is gone
  return true, json.encode({ icons = { revision = "r2", warnings = {} } })
end
clickText("Save")
flushReads()
assert(store.desktopChanges() == nil and H.fullScreen():find("Desktop settings saved", 1, true), screen())
H.goHome()
clickText("Icon theme")
flushReads()
assert(listCalls() > before and not hasText("Old"), "asked again: Old gone: " .. screen())
assert(byKey("icons-pick-2") and H.fullScreen():find("Fancy Icons", 1, true), screen())

H.checkBudget("icons", 0.025)
print("icons ok")
