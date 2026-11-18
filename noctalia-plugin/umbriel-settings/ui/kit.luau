-- Shared building blocks: page header, cards, badges, notices and empty states.
local M = {}

M.MUTED = "on_surface_variant"

function M.label(text, props)
  props = props or {}
  props.text = text
  props.fontSize = props.fontSize or 13
  return ui.label(props)
end

function M.muted(text, props)
  props = props or {}
  props.color = props.color or M.MUTED
  props.fontSize = props.fontSize or 12
  return M.label(text, props)
end

local function titleLabel(text, size)
  return ui.label({ text = text, fontSize = size or 18, fontWeight = "bold" })
end

-- A small rounded tag such as "3 changed" or "restart".
function M.badge(text, color, key)
  return ui.row({ key = key, paddingH = 8, paddingV = 2, radius = 10, fill = (color or "primary") .. "/0.18",
                  align = "center" }, {
    ui.label({ text = text, fontSize = 11, color = color or "primary", fontWeight = "bold" }),
  })
end

-- Noctalia's settings badge for a key that differs from the default.
function M.overrideBadge(key)
  return ui.row({ key = key, paddingH = 8, paddingV = 2, radius = 6, fill = "primary_container", align = "center",
                  tooltip = "Set in your config; differs from Umbriel's default" }, {
    ui.label({ text = "Override", fontSize = 11, color = "on_primary_container", fontWeight = "bold" }),
  })
end

-- Cards carry a thin outline so they stand out from the page; their padding is that much smaller to keep the height.
M.CARD_BORDER, M.CARD_BORDER_WIDTH = "outline_variant", 1

function M.card(props, children)
  props.fill = props.fill or "surface_container"
  props.border, props.borderWidth = props.border or M.CARD_BORDER, props.borderWidth or M.CARD_BORDER_WIDTH
  props.radius = props.radius or 12
  props.padding = props.padding or 12
  props.gap = props.gap or 8
  return ui.column(props, children)
end

function M.fileSize(bytes) return string.format("%.1f KB", bytes / 1024) end

-- A settings row: label on the left, its control on the right.
function M.optionRow(key, label, control, tooltip)
  return ui.row({ key = key, gap = 8, align = "center", tooltip = tooltip }, {
    ui.label({ text = label, fontSize = 13, flexGrow = 1 }),
    control,
  })
end

-- A button that asks once: the first click arms it (destructive "Click again to …"), the second runs `action`.
-- props: key (also what view.confirm holds while armed), text, armedText, glyph, controlSize, enabled, and
-- `check`, which can refuse before arming. Navigation disarms it (the shell clears view.confirm).
function M.confirmButton(ctx, props, action)
  local view = ctx.view
  local armed = view.confirm == props.key
  return ui.button({ key = props.key, text = armed and props.armedText or props.text, glyph = props.glyph,
                     variant = armed and "destructive" or "outline", controlSize = props.controlSize,
                     enabled = props.enabled, onClick = function()
                       if props.check and not props.check() then return end
                       if view.confirm ~= props.key then view.confirm = props.key; ctx.render(); return end
                       view.confirm = nil
                       action()
                     end })
end

-- Header: back button, breadcrumb title, then right-side actions.
function M.header(ctx, title, subtitle, actions)
  local left = {}
  if ctx.canGoBack() then
    table.insert(left, ui.button({ key = "back", glyph = "arrow-left", variant = "ghost", tooltip = "Back (Alt+Left)",
                                   onClick = function() ctx.back() end }))
  end
  local titles = { titleLabel(title) }
  if subtitle and subtitle ~= "" then table.insert(titles, M.muted(subtitle, { maxLines = 2 })) end
  table.insert(left, ui.column({ gap = 0, flexGrow = 1 }, titles))
  for _, action in ipairs(actions or {}) do table.insert(left, action) end
  if not ctx.isApp then
    table.insert(left, ui.button({ key = "close", glyph = "x", variant = "ghost", tooltip = "Close (Esc)",
                                   onClick = function() panel.close() end }))
  end
  return ui.row({ key = "header", gap = 8, align = "center" }, left)
end

-- Notice strip for errors, warnings and info; `onDismiss` adds a close button.
function M.notice(text, kind, onDismiss, key)
  local color = kind == "error" and "error" or kind == "warning" and "tertiary" or "primary"
  local glyph = kind == "error" and "alert-circle" or kind == "warning" and "alert-triangle" or "info-circle"
  local children = {
    ui.glyph({ name = glyph, size = 16, color = color }),
    ui.label({ text = text, fontSize = 12, flexGrow = 1, maxLines = 6 }),
  }
  if onDismiss then
    table.insert(children, ui.button({ glyph = "x", variant = "ghost", controlSize = "sm", tooltip = "Dismiss",
                                       onClick = onDismiss }))
  end
  return ui.row({ key = key or ("notice-" .. text), gap = 8, align = "center", padding = 10, radius = 10,
                  fill = color .. "/0.12" }, children)
end

function M.empty(text, glyph)
  return ui.column({ key = "empty", align = "center", gap = 8, paddingV = 32 }, {
    ui.glyph({ name = glyph or "mood-empty", size = 32, color = M.MUTED }),
    M.muted(text, { fontSize = 13, textAlign = "center" }),
  })
end

-- A clickable list row: glyph, title, subtitle, trailing badges and a chevron.
function M.navRow(props)
  local text = { ui.label({ text = props.title, fontSize = 14, fontWeight = props.bold and "bold" or nil,
                            maxLines = 1 }) }
  if props.subtitle and props.subtitle ~= "" then
    table.insert(text, M.muted(props.subtitle, { maxLines = props.subtitleLines or 1 }))
  end
  local children = { props.leading }
  if props.image then
    table.insert(children, ui.image({ path = props.image, width = 24, height = 24, fit = "contain" }))
  elseif props.glyph then
    table.insert(children, ui.glyph({ name = props.glyph, size = 20, color = "primary" }))
  end
  table.insert(children, ui.column({ gap = 2, flexGrow = 1 }, text))
  for _, badge in ipairs(props.badges or {}) do table.insert(children, badge) end
  table.insert(children, ui.glyph({ name = props.trailing or "chevron-right", size = 16, color = M.MUTED }))
  return ui.row({ key = props.key, gap = 12, align = "center", paddingH = 12, paddingV = 6, radius = 10,
                  border = M.CARD_BORDER, borderWidth = M.CARD_BORDER_WIDTH, fill = props.fill or "surface_container",
                  tooltip = props.tooltip, onClick = props.onClick },
                children)
end

-- The global search box with a clear button. The button stays laid out (disabled while the box is empty) so
-- the box keeps its width; clearing replaces the input (inputs are uncontrolled) and keeps the focus there.
function M.searchBox(ctx, props)
  local view = ctx.view
  props.key = "search:" .. ctx.gen("search")
  props.value = view.query
  props.focus = true
  props.flexGrow = 1
  return ui.row({ key = "search-box", gap = 4, align = "center" }, {
    ui.input(props),
    ui.button({ key = "search-clear", glyph = "eraser", variant = "ghost", controlSize = props.controlSize,
                tooltip = "Clear search", enabled = (view.query or "") ~= "", onClick = function()
                  ctx.clearSearch()
                  ctx.render()
                end }),
  })
end

-- Section heading in its own case: string.upper is byte-wise and would leave "Bézier" as "BéZIER".
function M.section(text, key)
  return ui.label({ key = key or ("section-" .. text), text = text, fontSize = 12,
                    fontWeight = "bold", color = M.MUTED })
end

-- plural(3, "entry", "entries"); the plural form defaults to word .. "s".
function M.plural(count, word, many)
  return tostring(count) .. " " .. (count == 1 and word or (many or (word .. "s")))
end

return M
