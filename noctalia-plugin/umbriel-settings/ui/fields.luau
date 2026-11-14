-- One settings row per field: label, help, default, a compact control, and undo/reset buttons.
local kit = require("./kit.luau")

local M = {}

M.EDITOR_WIDTH = 320

-- Numbers follow the system's numeric locale (LC_ALL > LC_NUMERIC > LANG): "0,75" in German.
-- The config file always stores a dot; only display and typing change.
local COMMA_LANGUAGES = {
  de = true, fr = true, es = true, it = true, nl = true, pt = true, ru = true, pl = true, cs = true, sk = true,
  sv = true, da = true, nb = true, nn = true, no = true, fi = true, tr = true, uk = true, hu = true, ro = true,
  hr = true, sl = true, el = true, bg = true, lt = true, lv = true, et = true, id = true, vi = true, be = true,
}
local decimalPoint = nil
function M.decimalPoint()
  if decimalPoint == nil then
    local value = ""
    for _, name in ipairs({ "LC_ALL", "LC_NUMERIC", "LANG" }) do
      local found = noctalia.getenv(name)
      if found and found ~= "" then value = found; break end
    end
    decimalPoint = COMMA_LANGUAGES[string.lower(string.match(value, "^(%a+)") or "")] and "," or "."
  end
  return decimalPoint
end

-- A number as text with the locale's decimal separator.
function M.number(value)
  if type(value) ~= "number" then return tostring(value) end
  local text
  if value == math.floor(value) and math.abs(value) < 1e15 then text = string.format("%d", math.floor(value))
  else text = string.format("%g", value) end
  if M.decimalPoint() ~= "." then text = (string.gsub(text, "%.", M.decimalPoint())) end
  return text
end

-- Parse typed text; both "0,75" and "0.75" are accepted.
function M.parseNumber(text)
  text = noctalia.string.trim(text or "")
  if text == "" then return nil end
  return tonumber((string.gsub(text, ",", ".")))
end

function M.format(field, value)
  if value == nil then return "not set" end
  local kind = field.kind
  if kind == "bool" then return value and "on" or "off" end
  if type(value) == "number" then return M.number(value) end
  if type(value) == "table" then
    if kind == "table" then
      local parts = {}
      for _, key in ipairs(field.keys or {}) do
        if value[key] ~= nil then table.insert(parts, key .. " " .. M.number(value[key])) end
      end
      return table.concat(parts, ", ")
    end
    local parts = {}
    for _, item in ipairs(value) do table.insert(parts, tostring(item)) end
    return #parts > 0 and table.concat(parts, ", ") or "empty"
  end
  local text = tostring(value)
  if text == "" then return "empty" end
  return text
end

local function indexOf(list, value)
  for index, item in ipairs(list or {}) do
    if item == value then return index end
  end
  return nil
end

local function parseNumber(text, integer)
  local number = M.parseNumber(text)
  if number == nil then return nil end
  if integer then
    if number ~= math.floor(number) then return nil end
  end
  return number
end

local function clamp(field, number)
  if field.min ~= nil and number < field.min then return nil end
  if field.max ~= nil and number > field.max then return nil end
  return number
end

-- Rule fields have no default: an absent key means "match anything" or "leave unchanged".
local function unsetLabel(field)
  return string.sub(field.path, 1, 6) == "match." and "Any" or "Not set"
end

local function hasDefault(field) return field.default ~= nil end

-- view: per-panel UI state (open pickers, help, input generations).
local function gen(view, key) return tostring(view.gen[key] or 0) end
local function bump(view, key) view.gen[key] = (view.gen[key] or 0) + 1 end

local function numberControl(ctx, spec, effective)
  local field, view, key = spec.field, ctx.view, spec.key
  local integer = field.kind == "int"
  local controls = {}
  local hasRange = field.min ~= nil and field.max ~= nil and field.max - field.min <= 100000
  if hasRange then
    local step = integer and 1 or ((field.max - field.min) <= 2 and 0.01 or (field.max - field.min) <= 20 and 0.05 or 0.5)
    table.insert(controls, ui.slider({
      key = key .. ":slider", min = field.min, max = field.max, step = step,
      value = effective or field.initial or field.min,
      flexGrow = 1, controlSize = "sm",
      onChange = function(text)
        local number = tonumber(text)
        if number == nil then return end
        if integer then number = math.floor(number + 0.5) end
        spec.onSet(number)
        bump(view, key)
        ctx.renderSoon()
      end,
    }))
  end
  table.insert(controls, ui.input({
    key = key .. ":num:" .. gen(view, key), value = effective ~= nil and M.format(field, effective) or "",
    width = hasRange and 84 or nil, flexGrow = hasRange and nil or 1, controlSize = "sm",
    placeholder = (effective == nil and field.initial ~= nil) and ("e.g. " .. M.format(field, field.initial))
      or field.min ~= nil and (M.number(field.min) .. " – " .. M.number(field.max)) or "number",
    onChange = function(text)
      local number = parseNumber(text, integer)
      if number ~= nil and clamp(field, number) ~= nil then
        view.invalid[key] = nil
        spec.onSet(number)
      else
        view.invalid[key] = noctalia.string.trim(text) == "" and nil
          or (integer and "Enter a whole number" or "Enter a number")
            .. (field.min ~= nil and (" between " .. M.number(field.min) .. " and " .. M.number(field.max)) or "")
      end
      ctx.render()
    end,
  }))
  return controls
end

local function colorControl(ctx, spec, effective)
  local key, view = spec.key, ctx.view
  local value = type(effective) == "string" and effective or "#000000FF"
  local controls = {
    ui.box({ width = 34, height = 22, radius = 6, fill = value, border = "outline_variant", borderWidth = 1,
             onClick = function()
               view.openColor = view.openColor ~= key and key or nil
               ctx.render()
             end, tooltip = "Pick a color" }),
    ui.input({ key = key .. ":hex:" .. gen(view, key), value = effective or "", width = 120, controlSize = "sm",
               placeholder = "#RRGGBBAA",
               onChange = function(text)
                 text = noctalia.string.trim(text)
                 if string.match(text, "^#%x%x%x%x%x%x$") or string.match(text, "^#%x%x%x%x%x%x%x%x$") then
                   view.invalid[key] = nil
                   spec.onSet(string.upper(text))
                 else
                   view.invalid[key] = text ~= "" and "Use #RRGGBB or #RRGGBBAA" or nil
                 end
                 ctx.render()
               end }),
  }
  for _, source in ipairs(spec.kdeColors or {}) do
    table.insert(controls, ui.button({
      key = key .. ":kde:" .. source.label, text = source.label, controlSize = "sm", variant = "ghost",
      tooltip = "Use " .. source.hex .. " from " .. source.tooltip,
      onClick = function()
        local alpha = string.len(value) == 9 and string.sub(value, 8, 9) or "FF"
        spec.onSet(string.sub(source.hex, 1, 7) .. alpha)
        bump(view, key)
        ctx.render()
      end,
    }))
  end
  return controls
end

local function choiceControl(ctx, spec, effective)
  local field, key, view = spec.field, spec.key, ctx.view
  local choices = field.choices or {}
  local options, offset = {}, 0
  local unsettable = spec.onUnset ~= nil and not hasDefault(field)
  if unsettable then table.insert(options, unsetLabel(field)); offset = 1 end
  for _, choice in ipairs(choices) do table.insert(options, choice) end
  local index = indexOf(choices, effective)
  local custom = field.kind == "combo" and (view.custom[key] or (effective ~= nil and index == nil))
  if field.kind == "combo" then table.insert(options, "Custom…") end
  local selected
  if custom then selected = #options
  elseif index then selected = index + offset
  else selected = 1 end
  local controls = { ui.select({
    key = key .. ":select", options = options, selectedIndex = selected - 1, flexGrow = 1, controlSize = "sm",
    onChange = function(text)
      local chosen = (tonumber(text) or 0) + 1
      if field.kind == "combo" and chosen == #options then
        view.custom[key] = true
      elseif unsettable and chosen == 1 then
        view.custom[key] = nil
        spec.onUnset()
      else
        view.custom[key] = nil
        spec.onSet(choices[chosen - offset])
      end
      ctx.render()
    end,
  }) }
  if custom then
    table.insert(controls, ui.input({
      key = key .. ":custom:" .. gen(view, key), value = (index == nil and effective) or "", flexGrow = 1,
      controlSize = "sm", placeholder = "Custom value", focus = true,
      onChange = function(text) spec.onSet(text); ctx.render() end,
    }))
  end
  return controls
end

-- Three-way switch for optional booleans without a default (the app's tri-state).
local function triControl(ctx, spec)
  local field, key = spec.field, spec.key
  local current = spec.set and (spec.value and 2 or 3) or 1
  local controls = {}
  for index, label in ipairs({ unsetLabel(field), "On", "Off" }) do
    table.insert(controls, ui.button({
      key = key .. ":tri:" .. index, text = label, controlSize = "sm", flexGrow = 1, selected = current == index,
      variant = current == index and "primary" or "outline",
      onClick = function()
        if index == 1 then spec.onUnset() else spec.onSet(index == 2) end
        ctx.render()
      end,
    }))
  end
  return controls
end

local function textControl(ctx, spec, effective, placeholder)
  local key = spec.key
  return { ui.input({
    key = key .. ":text:" .. gen(ctx.view, key), value = effective ~= nil and tostring(effective) or "",
    flexGrow = 1, controlSize = "sm", placeholder = placeholder,
    onChange = function(text) spec.onSet(text); ctx.render() end,
  }) }
end

local function tableControl(ctx, spec, effective)
  local field, key = spec.field, spec.key
  local defaults = type(field.default) == "table" and field.default
    or type(field.initial) == "table" and field.initial or {}
  -- Unset tables show the starting values as hints; typing one part fills the others from them.
  local current = (spec.set and type(effective) == "table") and effective or nil
  local controls = {}
  for _, sub in ipairs(field.keys or {}) do
    local numeric = type(defaults[sub]) == "number"
    table.insert(controls, ui.column({ key = key .. ":" .. sub, gap = 2, flexGrow = 1 }, {
      kit.muted(sub, { fontSize = 10 }),
      ui.input({
        key = key .. ":" .. sub .. ":" .. gen(ctx.view, key), controlSize = "sm",
        value = (current and current[sub] ~= nil) and M.number(current[sub]) or "",
        placeholder = defaults[sub] ~= nil and M.number(defaults[sub]) or "",
        onChange = function(text)
          local next = {}
          for _, other in ipairs(field.keys) do
            if current and current[other] ~= nil then next[other] = current[other] else next[other] = defaults[other] end
          end
          local trimmed = noctalia.string.trim(text)
          if trimmed == "" then
            -- an emptied box is not an error: unset stays unset, a set value falls back to the hint
            ctx.view.invalid[key] = nil
            if not current then ctx.render(); return end
            next[sub] = defaults[sub]
          elseif numeric then
            local number = M.parseNumber(trimmed)
            if number == nil then ctx.view.invalid[key] = sub .. ": enter a number"; ctx.render(); return end
            next[sub] = number
          else
            next[sub] = text
          end
          ctx.view.invalid[key] = nil
          spec.onSet(next)
          ctx.render()
        end,
      }),
    }))
  end
  return controls
end

-- Lists get one row per item below the label.
local function listRows(ctx, spec, effective)
  local key, view = spec.key, ctx.view
  local items = type(effective) == "table" and effective or {}
  local rows = {}
  for index, item in ipairs(items) do
    table.insert(rows, ui.row({ key = key .. ":item:" .. index, gap = 6, align = "center" }, {
      ui.input({ key = key .. ":item:" .. index .. ":" .. gen(view, key), value = tostring(item), flexGrow = 1,
                 controlSize = "sm",
                 onChange = function(text)
                   local next = {}
                   for i, old in ipairs(items) do next[i] = old end
                   next[index] = text
                   spec.onSet(next)
                   ctx.render()
                 end }),
      ui.button({ glyph = "arrow-up", variant = "ghost", controlSize = "sm", enabled = index > 1, tooltip = "Move up",
                  onClick = function()
                    local next = {}
                    for i, old in ipairs(items) do next[i] = old end
                    next[index], next[index - 1] = next[index - 1], next[index]
                    spec.onSet(next); bump(view, key); ctx.render()
                  end }),
      ui.button({ glyph = "trash", variant = "ghost", controlSize = "sm", tooltip = "Remove",
                  onClick = function()
                    local next = {}
                    for i, old in ipairs(items) do if i ~= index then table.insert(next, old) end end
                    spec.onSet(next); bump(view, key); ctx.render()
                  end }),
    }))
  end
  table.insert(rows, ui.row({ key = key .. ":add", gap = 6 }, {
    ui.button({ text = "Add", glyph = "plus", controlSize = "sm", variant = "outline",
                onClick = function()
                  local next = {}
                  for i, old in ipairs(items) do next[i] = old end
                  table.insert(next, "")
                  spec.onSet(next); bump(view, key); ctx.render()
                end }),
  }))
  return rows
end

-- spec: key, field, value, set, changed, onSet(v), onUnset() or nil, onRevert() or nil, diagnostic, kdeColors
function M.row(ctx, spec)
  local field, view, key = spec.field, ctx.view, spec.key
  local effective = spec.value
  if not spec.set then effective = field.default end
  local kind = field.kind
  local controls, below = {}, nil
  if kind == "bool" and spec.onUnset and not hasDefault(field) then
    controls = triControl(ctx, spec)
  elseif kind == "bool" then
    controls = { ui.toggle({ key = key .. ":toggle", checked = effective == true,
                             onChange = function(text) spec.onSet(text == "true"); ctx.render() end }) }
  elseif kind == "int" or kind == "float" then
    controls = numberControl(ctx, spec, effective)
  elseif kind == "color" then
    controls = colorControl(ctx, spec, effective)
  elseif kind == "choice" or kind == "combo" then
    controls = choiceControl(ctx, spec, effective)
  elseif kind == "table" then
    controls = tableControl(ctx, spec, effective)
  elseif kind == "list" or kind == "command_list" then
    below = listRows(ctx, spec, spec.set and spec.value or nil)
  else
    local hint = field.default ~= nil and field.default or field.initial
    local placeholder = field.placeholder or (hint ~= nil and M.format(field, hint) or "")
    if placeholder == "empty" or placeholder == "not set" then placeholder = "" end
    if kind == "raw" then placeholder = "TOML value" .. (placeholder ~= "" and (", e.g. " .. placeholder) or "") end
    controls = textControl(ctx, spec, spec.set and spec.value or nil, placeholder)
  end

  local badges = {}
  if spec.changed then table.insert(badges, kit.badge("changed", "primary", key .. ":b1")) end
  if field.restart then table.insert(badges, kit.badge("restart", "tertiary", key .. ":b2")) end
  local labelRow = { ui.label({ text = field.label, fontSize = 13, maxLines = 2, flexGrow = 1 }) }
  for _, badge in ipairs(badges) do table.insert(labelRow, badge) end
  local status
  local defaultText = hasDefault(field) and M.format(field, field.default) or nil
  if defaultText == "empty" then defaultText = nil end
  if defaultText then
    status = (spec.set and "Default " or "Not set · uses default ") .. defaultText
  elseif spec.set then
    status = "Set"
  else
    status = unsetLabel(field) == "Any" and "Not set · matches anything" or "Not set"
  end

  local actions = {}
  if spec.onRevert then
    table.insert(actions, ui.button({ key = key .. ":undo", glyph = "arrow-back-up", variant = "ghost", controlSize = "sm",
      tooltip = "Undo this change", onClick = function() spec.onRevert(); bump(view, key); ctx.render() end }))
  end
  if spec.onUnset and spec.set then
    table.insert(actions, ui.button({ key = key .. ":reset", glyph = "eraser", variant = "ghost", controlSize = "sm",
      tooltip = "Remove the key and use the default", onClick = function()
        spec.onUnset(); bump(view, key); view.custom[key] = nil; ctx.render()
      end }))
  end
  table.insert(actions, ui.button({ key = key .. ":help", glyph = "info-circle", variant = "ghost", controlSize = "sm",
    tooltip = "Show help", selected = view.help[key] == true,
    onClick = function() view.help[key] = not view.help[key] or nil; ctx.render() end }))

  local children = {
    ui.row({ key = key .. ":main", gap = 12, align = "center" }, {
      ui.column({ gap = 2, flexGrow = 1, tooltip = field.help }, {
        ui.row({ gap = 6, align = "center" }, labelRow),
        kit.muted(status, { maxLines = 1 }),
      }),
      ui.row({ width = M.EDITOR_WIDTH, gap = 6, align = "center", opacity = spec.set and 1 or 0.75 }, controls),
      ui.row({ width = 96, gap = 0, justify = "end", align = "center" }, actions),
    }),
  }
  if below then
    table.insert(children, ui.column({ key = key .. ":list", gap = 4, paddingH = 8 }, below))
  end
  if view.openColor == key and kind == "color" then
    table.insert(children, ui.row({ key = key .. ":picker", justify = "end" }, {
      ui.colorPicker({ key = key .. ":cp", value = type(effective) == "string" and effective or "#000000FF",
                       alpha = true, inputs = "hex", width = 300, swatches = ctx.swatches(),
                       onChangeEnd = function(color) spec.onSet(string.upper(color)); bump(view, key); ctx.render() end }),
    }))
  end
  if view.help[key] then
    table.insert(children, ui.column({ key = key .. ":helptext", gap = 2, padding = 8, radius = 8,
                                       fill = "surface_container_high" }, {
      ui.label({ text = field.help or "", fontSize = 12, maxLines = 12 }),
      kit.muted("Config key: " .. field.path, { fontSize = 11 }),
    }))
  end
  local problem = view.invalid[key] or spec.diagnostic
  if problem then table.insert(children, kit.notice(problem, "error", nil, key .. ":problem")) end
  return ui.column({ key = key, gap = 4, paddingV = 6, paddingH = 4 }, children)
end

return M
