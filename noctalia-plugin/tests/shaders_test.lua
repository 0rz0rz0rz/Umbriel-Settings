-- Community shaders on the Effects page (pages/shaders.luau): browse on request, kinds, previews, Install and
-- Install & use as draft edits (one undo step), Remove, filter, offline mode, a close while downloading.
-- Usage: lua shaders_test.lua PLUGIN_DIR FIXTURE_DIR
local H = dofile((arg[0]:match("^(.*)/") or ".") .. "/harness.lua")
local entry = H.start("panel.luau")
local json, calls, replies, loaded, pluginDir = H.json, H.calls, H.replies, H.loaded, H.pluginDir
local flushReads, hasText, find, clickText, lastCall, screen = H.flushReads, H.hasText, H.find, H.clickText, H.lastCall, H.screen
local byKey = H.byKey

local CRT = "shaders/community/window/crt/effect.toml"
local rows = {
  { id = "window/crt", kind = "window", name = "CRT", description = "Scanlines and a curved screen.", author = "A",
    license = "MIT", tags = { "retro" }, include = CRT, settings = { ["effects.window"] = "window.crt" },
    presets = { "window.crt" }, installed = false },
  { id = "border/rainbow", kind = "border", name = "Rainbow", description = "A rainbow ring.", author = "B",
    license = "GPL-3.0-or-later", tags = { "colourful" }, include = "shaders/community/border/rainbow/effect.toml",
    settings = { ["effects.border"] = "rainbow" }, presets = { "rainbow", "rainbow-overlay" }, installed = false },
}
for index = 1, 30 do
  local id = string.format("window/w%02d", index)
  table.insert(rows, { id = id, kind = "window", name = string.format("W%02d", index), description = "Filler.",
                       author = "C", license = "MIT", tags = {}, include = "shaders/community/" .. id .. "/effect.toml",
                       settings = {}, presets = {}, installed = false })
end
rows[3].settings, rows[3].presets = { ["effects.window"] = "w01" }, { "w01" }  -- W01 can take over from CRT
local browsed = false  -- the cache holds the catalogue once Browse downloaded it
replies.shaders = function(request)
  browsed = browsed or request.refresh == true
  if not browsed then return true, json.encode({ loaded = false }) end
  return true, json.encode({ loaded = true, age = 7200, git = false, rows = rows })
end
replies["shader-previews"] = function(request)
  local paths = {}
  for _, id in ipairs(request.ids) do paths[id] = "/cache/" .. id:gsub("/", "--") .. ".png" end
  return true, json.encode({ paths = paths, failed = {} })
end
replies["shader-prepare"] = function(request)
  return true, json.encode({ id = request.id, include = "x", presets = {} })
end
local function count(command)
  local n = 0
  for _, call in ipairs(calls) do if call.command == command then n = n + 1 end end
  return n
end

entry.onOpen()
flushReads()
local store = loaded[pluginDir .. "/lib/store.luau"]
H.goHome()
clickText("Effects")
flushReads()

-- nothing downloads until asked; offline mode keeps it that way
assert(lastCall("shaders") and not lastCall("shaders").request.refresh, "only the cache is read")
assert(hasText("Browse community shaders") and count("shader-previews") == 0, screen())
H.settings["shell.offline_mode"] = true
entry.onConfigChanged()
assert(byKey("shaders-browse").props.enabled == false and hasText("Noctalia is in offline mode."), screen())
H.settings["shell.offline_mode"] = nil
entry.onConfigChanged()
byKey("shaders-browse").props.onClick()
flushReads()
assert(lastCall("shaders").request.refresh == true, "Browse downloads the catalogue")
assert(hasText("32 effects · fetched 2 h ago") and hasText("Window 31") and hasText("Border 1"), H.fullScreen())

-- a page of rows, their previews in one request; scrolling to the bottom adds 6, once per growth of the page
assert(byKey("shader-window/crt") and byKey("shader-window/w11") and not byKey("shader-window/w12"), screen())
assert(#lastCall("shader-previews").request.ids == 12, "previews for the shown rows only")
assert(byKey("shader-img-window/crt").kind == "image", "the preview is drawn")
local previewCalls = count("shader-previews")
entry.onConfigChanged()
assert(count("shader-previews") == previewCalls, "each row's preview is asked for once")
local thumb = byKey("shader-img-window/crt").props
assert(thumb.fit == "contain" and thumb.width / thumb.height == 1.5, "3:2 like the previews, never cropped")
thumb.onClick()
assert(byKey("shader-large-window/crt") and byKey("shader-large-window/crt").props.width == 480, "a large preview")
byKey("shader-large-window/crt").props.onClick()
assert(not byKey("shader-large-window/crt"), "a click hides it")

-- a save (a new snapshot) reads which effects are next to the config again, once
local reads = count("shaders")
rows[1].installed = true
store.state = setmetatable({}, { __index = store.state })
entry.onConfigChanged()
assert(count("shaders") == reads + 1 and not lastCall("shaders").request.refresh, "re-read from the cache")
entry.onConfigChanged()
assert(count("shaders") == reads + 1, "only once per snapshot")
rows[1].installed = false
local function pageScroll()
  return find("scroll", function(n) return tostring(n.props.key):match("^content%-") ~= nil end)
end
pageScroll().props.onScroll("100", "900")
assert(not byKey("shader-window/w12"), "far from the bottom: nothing more")
pageScroll().props.onScroll("850", "900")
assert(byKey("shader-window/w17") and not byKey("shader-window/w18"), "6 more at the bottom")
assert(#lastCall("shader-previews").request.ids == 6, "previews for the new rows")
local stale = pageScroll().props.onScroll
stale("890", "900")  -- a position Noctalia reported before the render that added the rows
assert(not byKey("shader-window/w18"), "once per growth")
pageScroll().props.onScroll("1400", "1450")
assert(byKey("shader-window/w23"), "the grown page loads more again")
clickText("Show 6 more")
assert(byKey("shader-window/w29"), "the button does the same")
clickText("Show 1 more")  -- all 31 now: no more button, no scroll handler
assert(not byKey("shaders-more") and pageScroll().props.onScroll == nil, screen())

-- Install only adds the effect (to pick it per window rule): no selector; picking it marks it and its kind
assert(byKey("shader-install-window/crt") and byKey("shader-use-window/crt").props.text == "Use", screen())
assert(hasText("Use turns an effect on for every window. Install only adds it, so you can pick it for single "
  .. "apps under Window rules."), "the kind's hint")
assert(byKey("shader-install-window/crt").props.tooltip == "Only add it, to pick it for single apps under Window rules")
assert(byKey("shaders-kind-window").props.glyph == nil, "nothing in use yet")
byKey("shader-install-window/crt").props.onClick()
flushReads()
assert(store.value("include.files")[1] == CRT and store.value("effects.window") == nil, "added, not selected")
assert(byKey("shader-use-window/crt").props.text == "Use" and not byKey("shader-install-window/crt"), screen())
assert(byKey("shaders-kind-window").props.glyph == nil and not hasText("Picked in your settings"), "not used yet")
store.setField("animation.windows_in.effect", "window.crt")
entry.onConfigChanged()
assert(hasText("Picked in your settings") and byKey("shaders-kind-window").props.glyph == "circle-check", screen())
store.undo()
store.undo()
entry.onConfigChanged()

-- Use downloads, then the include and the effect's selector as one undo step; the preset becomes a choice, and
-- the kind is marked as in use
byKey("shader-use-window/crt").props.onClick()
flushReads()
assert(lastCall("shader-prepare").request.id == "window/crt", "downloaded into the cache first")
local includes = store.value("include.files")
assert(includes[#includes] == CRT and store.value("effects.window") == "window.crt", "draft edits")
assert(hasText("Installs on save") and byKey("shader-remove-window/crt"), H.fullScreen())
assert(byKey("shader-use-window/crt").props.text == "In use", "used")
local chip = byKey("shaders-kind-window")
assert(chip.props.glyph == "circle-check" and chip.props.tooltip == "In use: CRT", "the kind shows it is in use")
assert(byKey("shaders-kind-border").props.glyph == nil, "only that kind")
local effectChoices = store.namedChoices("effect", { "" })
local listed = false
for _, name in ipairs(effectChoices) do listed = listed or name == "window.crt" end
assert(listed, "the preset is offered before the save")
store.undo()
assert(#(store.value("include.files") or {}) == 0 and store.value("effects.window") ~= "window.crt", "one step")
store.redo()

-- Remove drops the include and the selector naming its preset
entry.onConfigChanged()
byKey("shader-remove-window/crt").props.onClick()
assert(#store.value("include.files") == 0 and store.value("effects.window") == nil, "removed from the draft")
assert(byKey("shader-use-window/crt").props.text == "Use" and byKey("shaders-kind-window").props.glyph == nil, screen())
assert(byKey("shader-install-window/crt"), "Install is back once removed")

-- using another effect of the kind replaces the old one (one undo step), unless something still names its preset
local function included(id)
  for _, entry in ipairs(store.value("include.files") or {}) do
    if entry == "shaders/community/" .. id .. "/effect.toml" then return true end
  end
  return false
end
byKey("shader-use-window/crt").props.onClick()
flushReads()
byKey("shader-use-window/w01").props.onClick()
flushReads()
assert(included("window/w01") and not included("window/crt") and store.value("effects.window") == "w01", "replaced")
assert(H.fullScreen():find("Replaced CRT; saving removes its files.", 1, true), H.fullScreen())
store.undo()
assert(included("window/crt") and not included("window/w01") and store.value("effects.window") == "window.crt",
       "undone in one step")
store.setField("animation.windows_in.effect", "window.crt")
entry.onConfigChanged()  -- renders the undone state
byKey("shader-use-window/w01").props.onClick()
flushReads()
assert(included("window/crt") and included("window/w01"), "still named by an animation: kept")
assert(byKey("shaders-kind-window").props.tooltip == "In use: CRT, W01", "both in use")
byKey("shader-install-window/w02").props.onClick()
flushReads()
byKey("shader-use-window/crt").props.onClick()
assert(included("window/w02"), "installed for a rule, never used: not replaced")

-- Remove all (click twice) drops every effect of the shown kind
byKey("shaders-remove-all").props.onClick()
assert(included("window/crt"), "the first click only arms it")
byKey("shaders-remove-all").props.onClick()
assert(#store.value("include.files") == 0 and store.value("effects.window") == nil, "all removed")
assert(byKey("shaders-remove-all").props.enabled == false, "nothing left to remove")
store.unsetField("animation.windows_in.effect")

-- a failed download changes nothing
replies["shader-prepare"] = function() return false, "Could not download x: offline" end
byKey("shader-use-window/crt").props.onClick()
flushReads()
assert(#store.value("include.files") == 0, "no include without the files")
replies["shader-prepare"] = function(request) return true, json.encode({ id = request.id, presets = {} }) end

-- kinds and the page filter
clickText("Border 1")
assert(byKey("shader-border/rainbow") and not byKey("shader-window/crt") and hasText("GPL-3.0-or-later"), screen())
clickText("Window 31")
assert(byKey("shader-window/w11") and not byKey("shader-window/w12"), "a kind starts with 12 rows again")
H.input("^filter%-Effects:").props.onChange("scanlines")
assert(byKey("shader-window/crt") and not byKey("shader-window/w01"), "filtered by description")
H.input("^filter%-Effects:").props.onChange("")

-- a close mid-download drops the answer: the row is usable again after reopening
H.hold("shader-prepare")
byKey("shader-use-window/crt").props.onClick()
assert(byKey("shader-busy-window/crt"), "busy while downloading")
entry.onClose()
entry.onOpen()
flushReads()
H.goHome()
clickText("Effects")
assert(byKey("shader-use-window/crt") and not byKey("shader-busy-window/crt"), screen())
H.release("shader-prepare", true)

H.checkBudget("shaders", 0.025)
print("shaders ok")
