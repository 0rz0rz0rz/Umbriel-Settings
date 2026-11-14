local pending = 0

local function refresh()
  barWidget.setGlyph("settings")
  barWidget.setText(pending > 0 and "Umbriel-GUI •" or "Umbriel-GUI")
  barWidget.setTooltip(pending > 0 and ("Umbriel Settings: " .. pending .. " unsaved change(s)")
    or "Open Umbriel Settings")
end

function update()
  refresh()
end

function onClick()
  noctalia.togglePanel("umbriel-settings/Umbriel-GUI-Plugin:folders")
end

if noctalia.state and noctalia.state.watch then
  noctalia.state.watch("umbriel.pending", function(value)
    pending = tonumber(value) or 0
    refresh()
  end)
end

refresh()
