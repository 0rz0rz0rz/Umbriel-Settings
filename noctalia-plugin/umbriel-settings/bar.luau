local pending = 0

local function display()
  local value = noctalia.getConfig and noctalia.getConfig("display")
  if value == "icon_text" or value == "text" then return value end
  return "icon"
end

local ICONS = {
  ["settings"] = true,
  ["settings-2"] = true,
  ["settings-cog"] = true,
  ["adjustments-horizontal"] = true,
  ["adjustments-cog"] = true,
  ["tool"] = true,
  ["tools"] = true,
  ["moon"] = true,
  ["moon-stars"] = true,
  ["moon-2"] = true,
  ["home-cog"] = true,
}

local function icon()
  local value = noctalia.getConfig and noctalia.getConfig("icon")
  return ICONS[value] and value or "moon-stars"
end

local function refresh()
  barWidget.setTooltip(pending > 0 and ("Umbriel Settings: " .. pending .. " unsaved change(s)")
    or "Open Umbriel Settings")
  local mode = display()
  if barWidget.isVertical and barWidget.isVertical() then mode = "icon" end
  local children = {}
  if mode ~= "text" then table.insert(children, ui.glyph({ name = icon() })) end
  if mode ~= "icon" then table.insert(children, ui.label({ text = "Umbriel Settings" })) end
  -- The dot is always laid out and only hidden: a widget that changes width moves the bar's layout and the
  -- panel anchored to it, which then animates on every unsaved/saved flip (e.g. a slider dragged across its
  -- saved value).
  table.insert(children, ui.label({ key = "dot", text = "•", color = "primary", opacity = pending > 0 and 1 or 0 }))
  barWidget.render(ui.row({ gap = 6, align = "center" }, children))
end

function update()
  refresh()
end

function onClick()
  noctalia.togglePanel("0rz0rz0rz/umbriel-settings:folders")
end

if noctalia.state and noctalia.state.watch then
  noctalia.state.watch("umbriel.pending", function(value)
    pending = tonumber(value) or 0
    refresh()
  end)
end

refresh()
