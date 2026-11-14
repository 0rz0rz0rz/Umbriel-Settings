-- The loaded config snapshot plus every unsaved edit, and the change set sent to the helper on save.
local M = {}

M.meta = nil         -- pages, groups, fields, editors, actions (from `meta`)
M.searchIndex = nil  -- { { id, lowercased text } } loaded on first search
M.state = nil        -- last `read` snapshot
M.fieldChanges = {}  -- field id -> { value = v } or { unset = true }
M.entries = {}       -- editor id -> working copy of entry items
M.entryOps = {}      -- ordered entry operations, replayed by the helper
M.maps = {}          -- map editor id -> working { name, text } rows
M.mapOps = {}
M.keybinds = nil     -- working { rows, groups }
M.keybindsDirty = false
M.desktop = nil      -- { userdirs = {...}, apps = {...} }
M.rebuild = nil      -- nil follows the file (banners present), else true/false

local function deepCopy(value)
  if type(value) ~= "table" then return value end
  local result = {}
  for key, item in pairs(value) do result[key] = deepCopy(item) end
  return result
end
M.deepCopy = deepCopy

local function equal(a, b)
  if type(a) ~= type(b) then
    -- an absent table value and an empty one are the same to TOML lists
    if type(a) == "table" and b == nil then return next(a) == nil end
    if type(b) == "table" and a == nil then return next(b) == nil end
    return false
  end
  if type(a) ~= "table" then return a == b end
  for key, item in pairs(a) do
    if not equal(item, b[key]) then return false end
  end
  for key in pairs(b) do
    if a[key] == nil then return false end
  end
  return true
end
M.equal = equal

local function normalizeColor(value)
  if type(value) ~= "string" or not string.match(value, "^#%x+$") then return nil end
  if #value == 7 then return string.upper(value) .. "FF" end
  if #value == 9 then return string.upper(value) end
  return nil
end
M.normalizeColor = normalizeColor

-- ------------------------------------------------------------------ fields
function M.field(fid) return M.meta and M.meta.fields[fid] end

-- Current value of a page field and whether its key is set.
function M.value(fid)
  local change = M.fieldChanges[fid]
  if change then
    if change.unset then return nil, false end
    return change.value, true
  end
  local base = M.state and M.state.fields[fid]
  return base, base ~= nil
end

function M.isChanged(fid) return M.fieldChanges[fid] ~= nil end

function M.setField(fid, value)
  local base = M.state and M.state.fields[fid]
  if base ~= nil and equal(base, value) then
    M.fieldChanges[fid] = nil
  else
    M.fieldChanges[fid] = { value = value }
  end
end

function M.unsetField(fid)
  local base = M.state and M.state.fields[fid]
  M.fieldChanges[fid] = base ~= nil and { unset = true } or nil
end

function M.revertField(fid) M.fieldChanges[fid] = nil end

function M.differs(field, value)
  if value == nil then return false end
  if field.kind == "color" then
    local a, b = normalizeColor(value), normalizeColor(field.default)
    if a and b then return a ~= b end
  end
  return not equal(value, field.default)
end

function M.isOverridden(fid)
  local value, set = M.value(fid)
  return set and M.differs(M.field(fid), value)
end

function M.groupCounts(fids)
  local changed, overridden = 0, 0
  for _, fid in ipairs(fids) do
    if M.fieldChanges[fid] then changed = changed + 1 end
    if M.isOverridden(fid) then overridden = overridden + 1 end
  end
  return changed, overridden
end

-- ------------------------------------------------------------------ entries
local function readablePattern(text)
  text = tostring(text)
  if string.sub(text, 1, 1) == "^" then text = string.sub(text, 2) end
  if string.sub(text, -1) == "$" and string.sub(text, -2) ~= "\\$" then text = string.sub(text, 1, -2) end
  return (string.gsub(text, "\\%.", "."))
end

local function readableMatch(key, value)
  local patterns = type(value) == "table" and value or { value }
  local names = {}
  for _, pattern in ipairs(patterns) do
    local text = readablePattern(pattern)
    if key == "app_id" then
      local last = string.match(text, "^[%w_-]+%.[%w_-]+%.[%w_.-]*%.([%w_-]+)$")
        or string.match(text, "^[%w_-]+%.[%w_-]+%.([%w_-]+)$")
      if last then text = last end
    end
    table.insert(names, text)
  end
  local kind = key == "app_id" and "app id" or key == "namespace" and "layer" or key
  return table.concat(names, ", ") .. " (" .. kind .. ")"
end

-- Display title for an entry, following the app's rules for automatic names.
function M.entryTitle(eid, index, item)
  if M.meta.editors[eid].mode == "map" then return tostring(item.name), false end
  local prefix = tostring(index) .. ". "
  if item.label and item.label ~= "" then return prefix .. item.label, false end
  local values = item.values or {}
  if values.name ~= nil and values.name ~= "" then return prefix .. tostring(values.name), false end
  for _, key in ipairs({ "app_id", "title", "namespace" }) do
    local value = values["match." .. key]
    if value ~= nil and value ~= "" then return prefix .. readableMatch(key, value), true end
  end
  if values.index ~= nil then return prefix .. "Workspace " .. tostring(values.index), true end
  for path, value in pairs(values) do
    if string.sub(path, 1, 6) == "match." and type(value) == "boolean" then
      local word = string.gsub(string.gsub(string.sub(path, 7), "^is_", ""), "_", " ")
      return prefix .. (value and word or ("not " .. word)), true
    end
  end
  return prefix .. "(matches everything)", true
end

function M.entryItems(eid) return M.entries[eid] or {} end

-- Apply an entry operation locally and record it for the helper.
function M.entryOp(eid, op)
  local items = M.entries[eid]
  local kind = op.op
  if kind == "add" then
    table.insert(items, { name = op.name, label = "", values = {} })
  elseif kind == "remove" then
    table.remove(items, op.index + 1)
  elseif kind == "move" then
    local item = table.remove(items, op.index + 1)
    table.insert(items, op.to + 1, item)
  elseif kind == "duplicate" then
    local copy = deepCopy(items[op.index + 1])
    copy.label = ""
    if op.name then copy.name = op.name; table.insert(items, copy)
    else table.insert(items, op.index + 2, copy) end
  elseif kind == "label" then
    items[op.index + 1].label = op.text
  elseif kind == "set" then
    items[op.index + 1].values[op.field] = op.value
  elseif kind == "unset" then
    items[op.index + 1].values[op.field] = nil
  end
  op.editor = eid
  local last = M.entryOps[#M.entryOps]
  if (kind == "set" or kind == "label") and last and last.editor == eid and last.op == kind
      and last.index == op.index and last.field == op.field then
    M.entryOps[#M.entryOps] = op  -- typing replaces the previous edit of the same value
  else
    table.insert(M.entryOps, op)
  end
end

function M.entryOpCount(eid)
  local count = 0
  for _, op in ipairs(M.entryOps) do
    if op.editor == eid then count = count + 1 end
  end
  return count
end

-- ------------------------------------------------------------------ maps
function M.mapRows(eid) return M.maps[eid] or {} end

function M.mapSet(eid, name, text, from)
  local rows = M.maps[eid]
  local found = false
  for _, row in ipairs(rows) do
    if row[1] == (from or name) then row[1] = name; row[2] = text; found = true end
  end
  if not found then table.insert(rows, { name, text }) end
  table.insert(M.mapOps, { editor = eid, op = "set", name = name, value = text, from = from })
end

function M.mapRemove(eid, name)
  local rows = M.maps[eid]
  for index, row in ipairs(rows) do
    if row[1] == name then table.remove(rows, index); break end
  end
  table.insert(M.mapOps, { editor = eid, op = "remove", name = name })
end

function M.mapOpCount(eid)
  local count = 0
  for _, op in ipairs(M.mapOps) do
    if op.editor == eid then count = count + 1 end
  end
  return count
end

-- ------------------------------------------------------------------ desktop
function M.desktopChanges()
  local d = M.desktop
  if not d then return nil end
  local request, any = {}, false
  local folders = {}
  for key, value in pairs(d.userdirs.values) do
    if value ~= (d.userdirs.original[key] or "") then folders[key] = value; any = true end
  end
  for key in pairs(d.userdirs.original) do
    if d.userdirs.values[key] == nil then folders[key] = ""; any = true end
  end
  if next(folders) then request.userdirs = { revision = d.userdirs.revision, changes = folders } end
  local apps = {}
  for role, value in pairs(d.apps.roles) do
    if value ~= (d.apps.originalRoles[role] or "") and value ~= "<multiple>" then
      table.insert(apps, { kind = "role", key = role, value = value })
    end
  end
  for mime, value in pairs(d.apps.mimes) do
    if value ~= (d.apps.originalMimes[mime] or "") then
      table.insert(apps, { kind = "mime", key = mime, value = value })
    end
  end
  if #apps > 0 then request.apps = { revision = d.apps.revision, changes = apps }; any = true end
  return any and request or nil
end

-- ------------------------------------------------------------------ totals
function M.pendingCount()
  local count = #M.entryOps + #M.mapOps
  for _ in pairs(M.fieldChanges) do count = count + 1 end
  if M.keybindsDirty then count = count + 1 end
  local desktop = M.desktopChanges()
  if desktop then
    if desktop.userdirs then for _ in pairs(desktop.userdirs.changes) do count = count + 1 end end
    if desktop.apps then count = count + #desktop.apps.changes end
  end
  return count
end

function M.hasConfigChanges()
  return next(M.fieldChanges) ~= nil or #M.entryOps > 0 or #M.mapOps > 0 or M.keybindsDirty
end

function M.changeSet()
  local changes = { revision = M.state.revision, fields = M.fieldChanges, entries = M.entryOps, maps = M.mapOps }
  if M.keybindsDirty then
    local rows, locks = {}, {}
    for _, row in ipairs(M.keybinds.rows) do
      table.insert(rows, { key = row.key, action = row.action, opts = row.opts or {}, group = row.group or "" })
      if row.locked then table.insert(locks, row.key) end
    end
    changes.keybinds = { rows = rows, groups = M.keybinds.groups, locks = locks }
  end
  if M.rebuild ~= nil then changes.rebuild = M.rebuild end
  return changes
end

-- Replace the snapshot. Field edits survive a reload; index-based edits survive only when the
-- file is unchanged, since rules may have moved. Returns a note when edits were dropped.
function M.load(state)
  local previous = M.state
  local sameFile = previous ~= nil and previous.path == state.path
  local unchanged = sameFile and equal(previous.revision, state.revision)
  local dropped = false
  if not sameFile then
    M.fieldChanges = {}
  else
    for fid, change in pairs(M.fieldChanges) do
      local base = state.fields[fid]
      if (change.unset and base == nil) or (not change.unset and equal(change.value, base)) then
        M.fieldChanges[fid] = nil
      end
    end
  end
  if not unchanged then
    dropped = #M.entryOps > 0 or #M.mapOps > 0 or M.keybindsDirty
    M.entryOps, M.mapOps, M.keybindsDirty = {}, {}, false
  end
  M.state = state
  if not unchanged or not M.keybinds then
    M.entries = deepCopy(state.editors)
    M.maps = deepCopy(state.maps)
    M.keybinds = { rows = deepCopy(state.keybinds.rows), groups = deepCopy(state.keybinds.groups) }
  end
  if dropped then return "The config changed on disk; rule, curve and keybind edits were discarded." end
  return nil
end

function M.discardAll()
  M.fieldChanges, M.entryOps, M.mapOps, M.keybindsDirty = {}, {}, {}, false
  if M.state then
    M.entries = deepCopy(M.state.editors)
    M.maps = deepCopy(M.state.maps)
    M.keybinds = { rows = deepCopy(M.state.keybinds.rows), groups = deepCopy(M.state.keybinds.groups) }
  end
  if M.desktop then
    M.desktop.userdirs.values = deepCopy(M.desktop.userdirs.original)
    M.desktop.apps.roles = deepCopy(M.desktop.apps.originalRoles)
    M.desktop.apps.mimes = deepCopy(M.desktop.apps.originalMimes)
  end
end

function M.loadDesktop(data)
  local apps = data.apps
  M.desktop = {
    userdirs = { values = deepCopy(data.userdirs.values), original = deepCopy(data.userdirs.values),
                 revision = data.userdirs.revision },
    apps = { roles = deepCopy(apps.roles), originalRoles = deepCopy(apps.roles), mimes = deepCopy(apps.mimes),
             originalMimes = deepCopy(apps.mimes), revision = apps.revision, apps = apps.apps,
             roleMimes = apps.role_mimes },
  }
end

-- ------------------------------------------------------------------ drafts
-- Unsaved edits survive a Noctalia restart in the plugin data directory.
local function draftPath()
  local dir = noctalia.pluginDataDir()
  return dir and (dir .. "/draft.json") or nil
end

function M.saveDraft()
  local path = draftPath()
  if not path or not M.state then return end
  if M.pendingCount() == 0 then
    if noctalia.fileExists(path) then noctalia.removeFile(path) end
    return
  end
  local draft = {
    path = M.state.path, revision = M.state.revision, fields = M.fieldChanges, entryOps = M.entryOps,
    mapOps = M.mapOps, keybinds = M.keybindsDirty and M.keybinds or nil,
  }
  local encoded = noctalia.json.encode(draft)
  if encoded then noctalia.writeFile(path, encoded) end
end

-- Re-apply a draft after the first `read`; returns a message or nil.
function M.restoreDraft()
  local path = draftPath()
  if not path or not noctalia.fileExists(path) or not M.state then return nil end
  local raw = noctalia.readFile(path)
  local draft = raw and noctalia.json.decode(raw)
  noctalia.removeFile(path)
  if type(draft) ~= "table" or draft.path ~= M.state.path then return nil end
  local restored = 0
  for fid, change in pairs(draft.fields or {}) do
    if M.meta.fields[fid] then M.fieldChanges[fid] = change; restored = restored + 1 end
  end
  if equal(draft.revision, M.state.revision) then
    for _, op in ipairs(draft.entryOps or {}) do M.entryOp(op.editor, op); restored = restored + 1 end
    for _, op in ipairs(draft.mapOps or {}) do
      if op.op == "remove" then M.mapRemove(op.editor, op.name) else M.mapSet(op.editor, op.name, op.value, op.from) end
      restored = restored + 1
    end
    if draft.keybinds then M.keybinds = draft.keybinds; M.keybindsDirty = true; restored = restored + 1 end
  end
  if restored == 0 then return nil end
  return "Restored " .. restored .. " unsaved change(s) from last time."
end

return M
