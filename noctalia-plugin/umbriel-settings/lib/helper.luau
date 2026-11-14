-- Runs umbriel_settings.py with JSON request/response files (helper output and argv are size-limited).
local M = {}

local counter = 0
M.generation = 0
M.running = 0

local function fail(cb, message, code)
  cb({ error = message, code = code or "error" }, nil)
end

local function cleanup(...)
  for _, path in ipairs({ ... }) do
    if path and noctalia.fileExists(path) then noctalia.removeFile(path) end
  end
end

-- Calls cb(err, data); err is { error = text, code = text } or nil. Callbacks from a previous panel
-- session are dropped unless opts.always is set (used to report saves that finish after closing).
function M.call(command, request, cb, opts)
  opts = opts or {}
  local pluginDir = noctalia.pluginDir()
  local dataDir, dirError = noctalia.pluginDataDir()
  if not pluginDir or not dataDir then
    fail(cb, "Could not locate the plugin directories: " .. tostring(dirError or "unknown error"))
    return false
  end
  local runDir = dataDir .. "/run"
  local made, mkdirError = noctalia.mkdirAll(runDir)
  if not made then
    fail(cb, "Could not create " .. runDir .. ": " .. tostring(mkdirError))
    return false
  end
  counter = counter + 1
  local base = runDir .. "/" .. command .. "-" .. tostring(counter)
  local requestPath, responsePath = base .. ".req.json", base .. ".res.json"
  local encoded, encodeError = noctalia.json.encode(request or {})
  if not encoded then
    fail(cb, "Could not encode the request: " .. tostring(encodeError))
    return false
  end
  local written, writeError = noctalia.writeFile(requestPath, encoded)
  if not written then
    fail(cb, "Could not write the request: " .. tostring(writeError))
    return false
  end
  local generation = M.generation
  M.running = M.running + 1
  local argv = { "python3", "-B", pluginDir .. "/umbriel_settings.py", command,
                 "--request", requestPath, "--response", responsePath }
  local accepted = noctalia.runAsync(argv, function(result)
    M.running = M.running - 1
    local stale = generation ~= M.generation and not opts.always
    local function finish(err, data)
      cleanup(requestPath, responsePath)
      if not stale then cb(err, data) end
    end
    if result.timedOut then
      finish({ error = "The helper timed out.", code = "timeout" })
      return
    end
    if result.stdoutTruncated then
      finish({ error = "The helper's reply was cut off." })
      return
    end
    local status = noctalia.json.decode(result.stdout or "")
    if type(status) ~= "table" then
      local detail = result.stderr ~= "" and result.stderr or ("exit status " .. tostring(result.exitCode))
      if result.exitCode == 127 or string.find(detail, "No such file", 1, true) then
        finish({ error = "python3 was not found. Install Python 3.", code = "missing_python" })
      else
        finish({ error = "The helper failed: " .. detail })
      end
      return
    end
    if not status.ok then
      finish({ error = tostring(status.error or "Unknown helper error"), code = status.code or "error" })
      return
    end
    local queued = noctalia.readFileAsync(responsePath, function(contents, readError)
      if not contents then
        finish({ error = "Could not read the helper's reply: " .. tostring(readError) })
        return
      end
      local data, decodeError = noctalia.json.decode(contents)
      if data == nil then
        finish({ error = "The helper's reply is not valid JSON: " .. tostring(decodeError) })
        return
      end
      finish(nil, data)
    end)
    if not queued then finish({ error = "Too many files are being read; try again." }) end
  end, opts.timeout)
  if not accepted then
    M.running = M.running - 1
    cleanup(requestPath)
    fail(cb, "Could not start python3. Install Python 3 and try again.", "missing_python")
    return false
  end
  return true
end

-- Reads a JSON file in its own callback so large documents are decoded apart from rendering.
function M.readJson(path, cb)
  local generation = M.generation
  local queued = noctalia.readFileAsync(path, function(contents, readError)
    if generation ~= M.generation then return end
    if not contents then
      cb({ error = "Could not read " .. path .. ": " .. tostring(readError) })
      return
    end
    local data, decodeError = noctalia.json.decode(contents)
    if data == nil then
      cb({ error = "Invalid JSON in " .. path .. ": " .. tostring(decodeError) })
      return
    end
    cb(nil, data)
  end)
  if not queued then cb({ error = "Too many files are being read; try again." }) end
end

return M
