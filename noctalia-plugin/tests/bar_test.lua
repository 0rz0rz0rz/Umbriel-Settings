local toggles = {}
local tooltip, rendered
local watchers = {}
local config = {}
local vertical = false
ui = {
  glyph = function(props) return { kind = "glyph", props = props } end,
  label = function(props) return { kind = "label", props = props } end,
  row = function(props, children) return { kind = "row", props = props, children = children } end,
}
barWidget = {
  setTooltip = function(value) tooltip = value end,
  render = function(node) rendered = node end,
  isVertical = function() return vertical end,
}
local helperRuns = {}
noctalia = {
  togglePanel = function(value) table.insert(toggles, value) end,
  getConfig = function(key) return config[key] end,
  state = { watch = function(key, fn) watchers[key] = fn end },
  -- what lib/helper.luau needs to start a helper (onExit)
  pluginDir = function() return "/plugin" end,
  pluginDataDir = function() return "/data" end,
  mkdirAll = function() return true end,
  writeFile = function() return true end,
  json = { encode = function() return "{}" end },
  runAsync = function(argv) table.insert(helperRuns, argv[4]); return true end,
}

-- Noctalia's require: relative to the requiring file
local barDir = arg[1]:match("^(.*)/") or "."
local loaded = {}
local function makeRequire(dir)
  return function(path)
    local full = dir .. "/" .. path:gsub("^%./", "")
    if not loaded[full] then
      local chunk = assert(loadfile(full, "t", setmetatable({ require = makeRequire(full:match("^(.*)/")) },
                                                           { __index = _G })))
      loaded[full] = chunk()
    end
    return loaded[full]
  end
end
require = makeRequire(barDir)

-- Returns whether the expected glyph shows, the text label (if any) and whether unsaved edits are marked
-- (the icon tinted, or the text when there is no icon).
local function shown(expected)
  local glyph, text, tinted = false, nil, false
  for _, child in ipairs(rendered.children) do
    if child.kind == "glyph" then
      glyph = child.props.name == (expected or "moon-stars")
      tinted = child.props.color == "primary"
    elseif child.kind == "label" then
      text = child.props.text
      if child.props.color == "primary" then tinted = true end
    end
  end
  return glyph, text, tinted
end

assert(loadfile(arg[1]))()
local glyph, text, marked = shown()
assert(glyph and text == nil and not marked and tooltip ~= "", "default shows only the icon")
local idle = #rendered.children

watchers["umbriel.pending"](3)
glyph, text, marked = shown()
assert(glyph and text == nil and marked and tooltip:find("3 unsaved"), "unsaved edits tint the icon: " .. tooltip)
assert(#rendered.children == idle, "unsaved edits don't add or remove widget parts")

config.display = "icon_text"
update()
glyph, text, marked = shown()
assert(glyph and text == "Umbriel Settings" and marked, "icon and text")
watchers["umbriel.pending"](0)
glyph, text, marked = shown()
assert(glyph and text == "Umbriel Settings" and not marked, "icon and text without unsaved edits")

config.display = "text"
update()
glyph, text, marked = shown()
assert(not glyph and text == "Umbriel Settings" and not marked, "text only")
watchers["umbriel.pending"](1)
glyph, text, marked = shown()
assert(text == "Umbriel Settings" and marked, "text only: unsaved edits tint the text")
assert(#rendered.children == 1, "no extra parts")
watchers["umbriel.pending"](0)

vertical = true
update()
glyph, text = shown()
assert(glyph and text == nil, "a vertical bar shows only the icon")
vertical = false

config.display = "bogus"
update()
glyph, text = shown()
assert(glyph and text == nil, "unknown values fall back to icon only")

config.icon = "tools"
update()
glyph = shown("tools")
assert(glyph, "the chosen icon is drawn")

-- disabling or uninstalling the plugin stops title bars following Noctalia (community shaders stay); a reload or
-- shutdown doesn't
onExit(0, "reload")
onExit(15, "shutdown")
assert(#helperRuns == 0, "nothing on reload or shutdown")
onExit(0, "disable")
onExit(0, "uninstall")
assert(#helperRuns == 2 and helperRuns[1] == "titlebar-cleanup" and helperRuns[2] == "titlebar-cleanup",
       "titlebar-cleanup on disable and uninstall")
config.icon = "not-a-glyph"
update()
glyph = shown()
assert(glyph, "an unknown icon falls back to moon-stars")

onClick()
onClick()
assert(#toggles == 2)
assert(toggles[1] == "0rz0rz0rz/umbriel-settings:main" and toggles[2] == toggles[1])
