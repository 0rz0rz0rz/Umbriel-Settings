-- Standalone app entry (not listed in plugin.toml): the shared shell with a left sidebar.
-- The host defines the global APP = { isApp = true, appVersion, initialConfig, validateDefault, rebuildDefault }.
local shell = require("./lib/shell.luau")
local sidebar = require("./ui/sidebar.luau")

local options = APP or { isApp = true }
options.isApp = true

local function layout(ctx, parts)
  local page = {}
  for _, child in ipairs(parts.header) do table.insert(page, child) end
  for _, child in ipairs(parts.notices) do table.insert(page, child) end
  table.insert(page, parts.content)
  if parts.saveBar then table.insert(page, parts.saveBar) end
  return ui.row({ gap = 12, flexGrow = 1, padding = 8 }, {
    sidebar.render(ctx),
    ui.column({ key = "page", gap = 10, flexGrow = 1 }, page),
  })
end

local _, handlers = shell.create(layout, options)

function onOpen() handlers.onOpen() end
function onClose() handlers.onClose() end
function onFrameTick() handlers.onFrameTick() end
function onKey(chord, pressed) handlers.onKey(chord, pressed) end
function onMenu(action, context) handlers.onMenu(action, context) end
function onExternalChange() handlers.onExternalChange() end
