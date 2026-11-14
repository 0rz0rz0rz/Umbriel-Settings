local toggles = {}
local glyph, label, tooltip
local watchers = {}
barWidget = {
  setGlyph = function(value) glyph = value end,
  setText = function(value) label = value end,
  setTooltip = function(value) tooltip = value end,
}
noctalia = {
  togglePanel = function(value) table.insert(toggles, value) end,
  state = { watch = function(key, fn) watchers[key] = fn end },
}

assert(loadfile(arg[1]))()
assert(glyph == "settings" and label == "Umbriel-GUI" and tooltip ~= "")
watchers["umbriel.pending"](3)
assert(label == "Umbriel-GUI •" and tooltip:find("3 unsaved"), tooltip)
watchers["umbriel.pending"](0)
assert(label == "Umbriel-GUI")
onClick()
onClick()
assert(#toggles == 2)
assert(toggles[1] == "umbriel-settings/Umbriel-GUI-Plugin:folders" and toggles[2] == toggles[1])
