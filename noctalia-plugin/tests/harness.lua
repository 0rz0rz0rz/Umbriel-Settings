-- Mocked Noctalia API shared by panel_test.lua and app_test.lua (plain Lua, fixtures from the real helper).
-- H.start(entryFile, appOptions) loads an entry script; the returned table exposes the helpers.
local pluginDir, fixtureDir = arg[1], arg[2]
local H = { env = {}, clock = 1000 }  -- clock: what noctalia.nowMs() returns; tests advance it

-- ------------------------------------------------------------------ JSON
local json = {}
local function encodeString(s)
  return '"' .. s:gsub('[%c"\\]', function(c)
    local map = { ['"'] = '\\"', ["\\"] = "\\\\", ["\n"] = "\\n", ["\r"] = "\\r", ["\t"] = "\\t" }
    return map[c] or string.format("\\u%04x", c:byte())
  end) .. '"'
end
function json.encode(value)
  local kind = type(value)
  if kind == "nil" then return "null" end
  if kind == "boolean" then return tostring(value) end
  if kind == "number" then
    if math.type(value) == "integer" then return tostring(value) end
    return string.format("%.17g", value)
  end
  if kind == "string" then return encodeString(value) end
  local count = 0
  for _ in pairs(value) do count = count + 1 end
  if count == #value then
    local parts = {}
    for _, item in ipairs(value) do table.insert(parts, json.encode(item)) end
    return "[" .. table.concat(parts, ",") .. "]"
  end
  local keys = {}
  for key in pairs(value) do table.insert(keys, tostring(key)) end
  table.sort(keys)
  local parts = {}
  for _, key in ipairs(keys) do table.insert(parts, encodeString(key) .. ":" .. json.encode(value[key])) end
  return "{" .. table.concat(parts, ",") .. "}"
end
function json.decode(text)
  local pos = 1
  local function ws() pos = text:find("[^ \t\r\n]", pos) or #text + 1 end
  local value
  local function str()
    local out, i = {}, pos + 1
    while true do
      local c = text:sub(i, i)
      if c == '"' then pos = i + 1; return table.concat(out) end
      if c == "\\" then
        local e = text:sub(i + 1, i + 1)
        if e == "u" then
          table.insert(out, utf8.char(tonumber(text:sub(i + 2, i + 5), 16)))
          i = i + 6
        else
          table.insert(out, ({ n = "\n", r = "\r", t = "\t", b = "\b", f = "\f" })[e] or e)
          i = i + 2
        end
      else
        table.insert(out, c)
        i = i + 1
      end
    end
  end
  function value()
    ws()
    local c = text:sub(pos, pos)
    if c == "{" then
      local result = {}
      pos = pos + 1; ws()
      if text:sub(pos, pos) == "}" then pos = pos + 1; return result end
      while true do
        ws(); local key = str(); ws(); pos = pos + 1
        result[key] = value(); ws()
        local sep = text:sub(pos, pos); pos = pos + 1
        if sep == "}" then return result end
      end
    elseif c == "[" then
      local result = {}
      pos = pos + 1; ws()
      if text:sub(pos, pos) == "]" then pos = pos + 1; return result end
      while true do
        table.insert(result, value()); ws()
        local sep = text:sub(pos, pos); pos = pos + 1
        if sep == "]" then return result end
      end
    elseif c == '"' then return str()
    elseif text:sub(pos, pos + 3) == "true" then pos = pos + 4; return true
    elseif text:sub(pos, pos + 4) == "false" then pos = pos + 5; return false
    elseif text:sub(pos, pos + 3) == "null" then pos = pos + 4; return nil
    else
      local number = text:match("^-?%d+%.?%d*[eE]?[-+]?%d*", pos)
      pos = pos + #number
      return math.tointeger(tonumber(number)) or tonumber(number)
    end
  end
  local ok, result = pcall(value)
  if not ok then return nil, result end
  return result
end

local function readFile(path)
  local handle = io.open(path, "rb")
  if not handle then return nil end
  local data = handle:read("a")
  handle:close()
  return data
end

local fixtures = {}
for _, name in ipairs({ "meta", "search", "state", "desktop", "saved" }) do
  fixtures[name] = assert(readFile(fixtureDir .. "/" .. name .. ".json"), name)
end

-- ------------------------------------------------------------------ callback timing
-- Noctalia stops a plugin after repeated callbacks over 25 ms of CPU. Every callback the UI hands to the
-- mocked API is timed; nested callbacks (the mock runs helper replies synchronously) are subtracted from
-- the outer one, so each entry measures what Noctalia would see as one callback.
local timing = { max = 0, name = "none", count = 0, stack = {} }
local function timed(name, fn)
  return function(...)
    local frame = { start = os.clock(), nested = 0 }
    table.insert(timing.stack, frame)
    local results = table.pack(pcall(fn, ...))
    table.remove(timing.stack)
    local total = os.clock() - frame.start
    local own = total - frame.nested
    local parent = timing.stack[#timing.stack]
    if parent then parent.nested = parent.nested + total end
    timing.count = timing.count + 1
    if own > timing.max then timing.max, timing.name = own, name end
    if not results[1] then error(results[2], 0) end
    return table.unpack(results, 2, results.n)
  end
end
-- Mocked API functions that are native in Noctalia (JSON): their time is not charged to the caller.
local function native(fn)
  return function(...)
    local start = os.clock()
    local results = table.pack(fn(...))
    local parent = timing.stack[#timing.stack]
    if parent then parent.nested = parent.nested + (os.clock() - start) end
    return table.unpack(results, 1, results.n)
  end
end

-- ------------------------------------------------------------------ mocks
local tree
local files = {}
local calls = {}        -- helper commands in order: { command, request }
local replies = {}      -- command -> function(request) -> ok, data or error text
local reads = {}        -- pending readFileAsync callbacks
local notifications = {}
local frameTick = false

ui = {}
for _, kind in ipairs({ "column", "row", "scroll", "label", "input", "button", "select", "separator", "toggle",
                        "slider", "colorPicker", "glyph", "box", "spacer", "markdown", "image" }) do
  ui[kind] = function(props, children)
    assert(type(props) == "table", "ui." .. kind .. " needs props")
    for key, value in pairs(props) do
      if type(value) == "function" and key:match("^on") then
        props[key] = timed(kind .. "." .. key .. " " .. tostring(props.key or props.text or ""), value)
      end
    end
    return { kind = kind, props = props, children = children or {} }
  end
end
panel = {
  render = function(value) tree = value end,
  close = function() end,
  setNeedsFrameTick = function(value) frameTick = value end,
  openContextMenu = function() return true end,
}

noctalia = {
  pluginDir = function() return pluginDir end,
  pluginDataDir = function() return "/data" end,
  mkdirAll = function() return true end,
  writeFile = function(path, content) files[path] = content; return true end,
  readFile = function(path) return files[path] end,
  fileExists = function(path) return files[path] ~= nil end,
  removeFile = function(path) files[path] = nil; return true end,
  notify = function(_, body) table.insert(notifications, body) end,
  getColor = function() return "#336699" end,
  nowMs = function() return H.clock end,
  getenv = function(name) return H.env[name] end,
  fuzzyScore = function(query, text) return text:lower():find(query:lower(), 1, true) and 10 or 1 end,
  appIconPath = function() return nil end,
  json = { encode = native(json.encode), decode = native(json.decode) },
  string = { trim = function(value) return (value:gsub("^%s+", ""):gsub("%s+$", "")) end },
  state = { set = function() end },
  readFileAsync = function(path, callback)
    table.insert(reads, { path = path, callback = timed("readFileAsync " .. path, callback) })
    return true
  end,
  runAsync = function(argv, callback)
    assert(argv[1] == "python3" and argv[3] == pluginDir .. "/umbriel_settings.py", "helper argv")
    assert(string.match(argv[2], "^%-Xpycache_prefix=.+/pycache$"), "bytecode goes to the data dir")
    local command, requestPath, responsePath = argv[4], argv[6], argv[8]
    local request = json.decode(files[requestPath])
    table.insert(calls, { command = command, request = request })
    local reply = replies[command] or function() return true, "{}" end
    local ok, data = reply(request)
    if ok then files[responsePath] = data end
    timed("runAsync " .. command, callback)({ exitCode = 0, stdout = ok and '{"ok":true}' or json.encode({ ok = false, error = data }),
               stderr = "", timedOut = false })
    return true
  end,
}

-- Lexical relative require with a private global environment per module, like Noctalia.
local loaded = {}
local function makeRequire(dir)
  return function(path)
    assert(path:match("^%.%.?/.*%.luau$"), "relative .luau require: " .. path)
    local full = dir .. "/" .. path
    repeat local before = full; full = full:gsub("/%./", "/") until full == before
    repeat local before = full; full = full:gsub("/[^/]+/%.%./", "/", 1) until full == before
    if loaded[full] == nil then
      local env = setmetatable({}, { __index = _G })
      env.require = makeRequire(full:match("^(.*)/[^/]+$"))
      loaded[full] = assert(loadfile(full, "t", env))()
    end
    return loaded[full]
  end
end
local entry = setmetatable({}, { __index = _G })
entry.require = makeRequire(pluginDir)
function H.start(name, app)
  entry.APP = app
  assert(loadfile(pluginDir .. "/" .. name, "t", entry))()
  for _, global in ipairs({ "onOpen", "onClose", "onFrameTick", "onKey", "onMenu", "onExternalChange" }) do
    if type(rawget(entry, global)) == "function" then entry[global] = timed(global, rawget(entry, global)) end
  end
  return entry
end

replies.meta = function() return true, json.encode({ meta = "/data/cache/meta.json", search = "/data/cache/search.json" }) end
replies.read = function() return true, fixtures.state end
replies.desktop = function() return true, fixtures.desktop end

-- Completes queued async reads; fixture paths map to fixture files, other paths to written files.
local function flushReads()
  while #reads > 0 do
    local item = table.remove(reads, 1)
    local content = files[item.path]
    if item.path == "/data/cache/meta.json" then content = fixtures.meta end
    if item.path == "/data/cache/search.json" then content = fixtures.search end
    if content then item.callback(content, nil) else item.callback(nil, "missing " .. item.path) end
  end
  if frameTick then entry.onFrameTick(16) end
end

-- ------------------------------------------------------------------ tree helpers
local function walk(node, visit)
  if visit(node) then return node end
  for _, child in ipairs(node.children or {}) do
    local found = walk(child, visit)
    if found then return found end
  end
end
local function texts(node)
  local out = {}
  walk(node, function(n) if n.props.text then table.insert(out, n.props.text) end end)
  return table.concat(out, " | ")
end
local function hasText(text)
  return walk(tree, function(n) return n.props.text == text end) ~= nil
end
local function find(kind, predicate, message)
  local node = walk(tree, function(n) return n.kind == kind and predicate(n) end)
  assert(node, (message or ("no " .. kind)) .. "\nScreen: " .. texts(tree))
  return node
end
local function clickText(text)
  local node = walk(tree, function(n)
    return n.props.onClick and walk(n, function(c) return c.props.text == text end) ~= nil
  end)
  assert(node, "nothing clickable shows " .. text .. "\nScreen: " .. texts(tree))
  node.props.onClick()
  flushReads()
end
local function lastCall(command)
  for i = #calls, 1, -1 do if calls[i].command == command then return calls[i] end end
end

local function screen() return texts(tree) end

H.json, H.fixtures, H.files, H.calls, H.replies, H.loaded, H.pluginDir = json, fixtures, files, calls, replies, loaded, pluginDir
H.flushReads, H.texts, H.hasText, H.find, H.clickText, H.lastCall, H.screen =
  flushReads, texts, hasText, find, clickText, lastCall, screen
H.tree = function() return tree end
-- Moves a slider like the pointer does (press, drag, release later); `wheel` = a mouse-wheel notch, which Noctalia
-- reports as one change and an immediate drag end.
function H.slide(node, value, wheel)
  node.props.onChange(tostring(value))
  if not wheel then H.clock = H.clock + 150 end
  node.props.onDragEnd()
end
H.timing = timing
-- Prints the slowest callback; fails when it exceeds `limit` seconds of CPU.
function H.checkBudget(label, limit)
  print(string.format("%s: %d callbacks, slowest %.1f ms (%s)", label, timing.count, timing.max * 1000, timing.name))
  assert(timing.max <= limit, string.format("%s over the %.0f ms callback budget: %.1f ms in %s",
    label, limit * 1000, timing.max * 1000, timing.name))
end
return H
