local pending = 0

local function display()
  local value = noctalia.getConfig and noctalia.getConfig("display")
  if value == "icon" or value == "text" then return value end
  return "icon_text"
end

local function refresh()
  barWidget.setTooltip(pending > 0 and ("Umbriel Settings: " .. pending .. " unsaved change(s)")
    or "Open Umbriel Settings")
  local mode = display()
  if barWidget.isVertical and barWidget.isVertical() then mode = "icon" end
  local children = {}
  if mode ~= "text" then table.insert(children, ui.glyph({ name = "settings" })) end
  if mode ~= "icon" then
    table.insert(children, ui.label({ text = pending > 0 and "Umbriel-GUI •" or "Umbriel-GUI" }))
  elseif pending > 0 then
    table.insert(children, ui.label({ text = "•", color = "primary" }))
  end
  barWidget.render(ui.row({ gap = 6, align = "center" }, children))
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
