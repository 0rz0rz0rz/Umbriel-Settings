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
noctalia = {
  togglePanel = function(value) table.insert(toggles, value) end,
  getConfig = function(key) return config[key] end,
  state = { watch = function(key, fn) watchers[key] = fn end },
}

local function shown()
  local glyph, text = false, nil
  for _, child in ipairs(rendered.children) do
    if child.kind == "glyph" then glyph = child.props.name == "settings" end
    if child.kind == "label" then text = child.props.text end
  end
  return glyph, text
end

assert(loadfile(arg[1]))()
local glyph, text = shown()
assert(glyph and text == "Umbriel-GUI" and tooltip ~= "", "default shows icon and text")

watchers["umbriel.pending"](3)
glyph, text = shown()
assert(text == "Umbriel-GUI •" and tooltip:find("3 unsaved"), tooltip)

config.display = "icon"
update()
glyph, text = shown()
assert(glyph and text == "•", "icon only keeps the unsaved dot")
watchers["umbriel.pending"](0)
glyph, text = shown()
assert(glyph and text == nil, "icon only")

config.display = "text"
update()
glyph, text = shown()
assert(not glyph and text == "Umbriel-GUI", "text only")

vertical = true
update()
glyph, text = shown()
assert(glyph and text == nil, "a vertical bar shows only the icon")
vertical = false

config.display = "bogus"
update()
glyph, text = shown()
assert(glyph and text == "Umbriel-GUI", "unknown values fall back to icon and text")

onClick()
onClick()
assert(#toggles == 2)
assert(toggles[1] == "umbriel-settings/Umbriel-GUI-Plugin:folders" and toggles[2] == toggles[1])
