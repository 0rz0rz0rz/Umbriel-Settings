-- Noctalia panel: the shared shell in a single column (home with search, drill-down pages).
local shell = require("./lib/shell.luau")

local function layout(_, parts)
  local children = {}
  for _, child in ipairs(parts.header) do table.insert(children, child) end
  for _, child in ipairs(parts.notices) do table.insert(children, child) end
  table.insert(children, parts.content)
  if parts.saveBar then table.insert(children, parts.saveBar) end
  return ui.column({ gap = 10, flexGrow = 1, padding = 4 }, children)
end

local _, handlers = shell.create(layout, {})

function onOpen() handlers.onOpen() end
function onClose() handlers.onClose() end
function onFrameTick() handlers.onFrameTick() end
function onKey(chord, pressed) handlers.onKey(chord, pressed) end
function onMenu(action, context) handlers.onMenu(action, context) end
function onDrop(payload, value) handlers.onDrop(payload, value) end
