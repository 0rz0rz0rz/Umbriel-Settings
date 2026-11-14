-- Review & save (readable changes, diff, validation) and backups.
local kit = require("../ui/kit.luau")
local search = require("../lib/search.luau")
local fields = require("../ui/fields.luau")

local M = {}

local function diffBlock(text)
  -- Long diffs stay readable and cheap to render.
  local lines, count = {}, 0
  for line in string.gmatch(text, "[^\n]*\n?") do
    if line == "" then break end
    count = count + 1
    if count <= 80 then table.insert(lines, line) end
  end
  local body = table.concat(lines)
  if count > 80 then body = body .. "\n… " .. (count - 80) .. " more lines\n" end
  return "```diff\n" .. body .. "```"
end

local function goToField(ctx, fid)
  local where = search.locate(ctx.store.meta, fid)
  if not where then return end
  if where.editor then ctx.openPage(where.page) else
    ctx.openPage(where.page, { group = where.group, reveal = "f:" .. fid })
  end
end

local function requestPreview(ctx, state)
  local store = ctx.store
  state.preview, state.error, state.loading = nil, nil, true
  if not store.hasConfigChanges() then
    state.loading = false
    state.preview = { changed = false, summary = {}, sections = {}, validation = { ran = false } }
    return
  end
  ctx.helper.call("preview", { config = store.state.path, changes = store.changeSet(), validate = state.validate },
    function(err, report)
      state.loading = false
      if err then state.error = err.error else state.preview = report end
      ctx.render()
    end, { timeout = 45000 })
end

local function finishSave(ctx, state, message)
  state.saving = false
  ctx.diagnostics = nil
  ctx.view.gen = {}
  ctx.back()
  ctx.flash(message, "info")
end

local function saveDesktop(ctx, state, message)
  local store = ctx.store
  local desktop = store.desktopChanges()
  if not desktop then finishSave(ctx, state, message); return end
  ctx.helper.call("desktop-save", desktop, function(err)
    if err then
      state.saving = false
      state.error = (message ~= "" and (message .. " ") or "") .. "Desktop settings were not saved: " .. err.error
      ctx.render()
      return
    end
    store.desktop = nil
    ctx.loadDesktop(true)
    finishSave(ctx, state, (message ~= "" and (message .. " ") or "") .. "Desktop settings saved; restart apps to use them.")
  end)
end

local function save(ctx, state)
  local store = ctx.store
  state.saving, state.error = true, nil
  ctx.render()
  if not store.hasConfigChanges() then saveDesktop(ctx, state, ""); return end
  local generation = ctx.helper.generation
  ctx.helper.call("save", { config = store.state.path, changes = store.changeSet(), validate = state.validate },
    function(err, report)
      if generation ~= ctx.helper.generation then
        noctalia.notify("Umbriel Settings", err and ("Saving failed: " .. err.error)
          or (report.saved and "Saved after the panel closed." or "Not saved: Umbriel rejected the config."))
        if not err and report.saved then
          store.fieldChanges, store.entryOps, store.mapOps, store.keybindsDirty = {}, {}, {}, false
          store.load(report.state)
        end
        return
      end
      if err then
        state.saving, state.error = false, err.error
        ctx.render()
        return
      end
      if not report.saved then
        state.saving = false
        state.preview = report
        ctx.diagnostics = {}
        for _, item in ipairs(report.validation.diagnostics or {}) do
          if item.field then ctx.diagnostics[item.field] = item.message end
        end
        state.error = "Umbriel rejected the new config, so nothing was written. Fix the problems below."
        ctx.render()
        return
      end
      store.fieldChanges, store.entryOps, store.mapOps, store.keybindsDirty = {}, {}, {}, false
      store.load(report.state)
      local warnings = 0
      for _, item in ipairs(report.validation.diagnostics or {}) do
        if item.severity ~= "error" then warnings = warnings + 1 end
      end
      local message = "Saved" .. (warnings > 0 and (" with " .. kit.plural(warnings, "warning")) or "") .. "."
      saveDesktop(ctx, state, message)
    end, { timeout = 60000, always = true })
end

local function reviewPage(ctx, route)
  local store, view = ctx.store, ctx.view
  route.state = route.state or { validate = ctx.options.validateDefault ~= false }
  local state = route.state
  if state.preview == nil and not state.loading and not state.error then requestPreview(ctx, state) end
  local header = { kit.header(ctx, "Review changes", store.state and store.state.path or "") }
  local content = {}
  if state.error then table.insert(content, kit.notice(state.error, "error", nil, "review-error")) end
  if state.loading then table.insert(content, kit.empty("Checking your changes…", "loader")) end
  local preview = state.preview
  if preview then
    if #preview.summary > 0 then
      table.insert(content, kit.section("Changes"))
      for index, item in ipairs(preview.summary) do
        local function shown(value)
          if value == nil then return "unset" end
          local number = string.match(tostring(value), "^%-?%d+%.%d+$") and tonumber(value)
          return number and fields.number(number) or tostring(value)
        end
        local text = item.label
        if item.old ~= nil or item.new ~= nil then
          text = text .. ":  " .. shown(item.old) .. "  →  " .. shown(item.new)
        end
        table.insert(content, ui.row({ key = "sum-" .. index, gap = 8, align = "center" }, {
          kit.badge(item.page or "", "secondary", "sp-" .. index),
          ui.label({ text = text, fontSize = 13, flexGrow = 1, maxLines = 3 }),
          item.id and ui.button({ glyph = "arrow-right", variant = "ghost", controlSize = "sm", tooltip = "Go to setting",
                                  onClick = function() goToField(ctx, item.id) end }) or ui.spacer({ width = 1 }),
        }))
      end
    end
    local desktop = store.desktopChanges()
    if desktop then
      table.insert(content, kit.section("Desktop"))
      for key, value in pairs(desktop.userdirs and desktop.userdirs.changes or {}) do
        table.insert(content, kit.label("User folder " .. key .. ":  " .. (value ~= "" and value or "removed")))
      end
      for _, change in ipairs(desktop.apps and desktop.apps.changes or {}) do
        table.insert(content, kit.label(change.key .. ":  " .. (change.value ~= "" and change.value or "removed")))
      end
    end
    local validation = preview.validation or {}
    if validation.ran then
      table.insert(content, kit.section("Validation"))
      if validation.valid and #(validation.diagnostics or {}) == 0 then
        table.insert(content, kit.notice("Umbriel accepts the new config.", "info", nil, "valid"))
      end
      for index, item in ipairs(validation.diagnostics or {}) do
        local kind = item.severity == "error" and "error" or "warning"
        local text = item.message .. (item.line and ("  (line " .. item.line .. ")") or "")
        table.insert(content, ui.row({ key = "diag-" .. index, gap = 6, align = "center" }, {
          ui.column({ flexGrow = 1 }, { kit.notice(text, kind, nil, "diagn-" .. index) }),
          item.field and ui.button({ text = "Go to setting", controlSize = "sm", variant = "outline",
                                     onClick = function() goToField(ctx, item.field) end }) or ui.spacer({ width = 1 }),
        }))
      end
    elseif store.hasConfigChanges() and validation.reason then
      table.insert(content, kit.notice(validation.reason, "warning", nil, "novalid"))
    end
    if #preview.sections > 0 then
      table.insert(content, kit.section("File changes"))
      view.diffOpen = view.diffOpen or {}
      for index, section in ipairs(preview.sections) do
        local open = view.diffOpen[section.title]
        table.insert(content, kit.navRow({ key = "diff-" .. index, title = section.title, bold = true,
          trailing = open and "chevron-up" or "chevron-down", onClick = function()
            view.diffOpen[section.title] = not open or nil
            ctx.render()
          end }))
        if open then table.insert(content, ui.markdown({ key = "diffmd-" .. index, text = diffBlock(section.diff) })) end
      end
    end
  end
  local blocked = state.validate and preview and preview.validation and preview.validation.ran
    and not preview.validation.valid
  local rebuild = store.rebuild
  if rebuild == nil then rebuild = store.state and store.state.rebuild_default end
  table.insert(content, kit.section("Options"))
  table.insert(content, ui.row({ key = "opt-validate", gap = 8, align = "center" }, {
    ui.label({ text = "Check with Umbriel before writing (recommended)", fontSize = 13, flexGrow = 1 }),
    ui.toggle({ checked = state.validate, onChange = function(value)
      state.validate = value == "true"
      requestPreview(ctx, state)
      ctx.render()
    end }),
  }))
  table.insert(content, ui.row({ key = "opt-rebuild", gap = 8, align = "center",
    tooltip = "Regroup the file in canonical order with section banners. Settings never change; comments may move." }, {
    ui.label({ text = "Tidy file layout", fontSize = 13, flexGrow = 1 }),
    ui.toggle({ checked = rebuild == true, onChange = function(value)
      store.rebuild = value == "true"
      requestPreview(ctx, state)
      ctx.render()
    end }),
  }))
  table.insert(content, ui.row({ key = "review-actions", gap = 8 }, {
    ui.button({ text = state.saving and "Saving…" or "Save", glyph = "device-floppy", variant = "primary",
                enabled = not state.saving and not state.loading and store.pendingCount() > 0 and not blocked,
                onClick = function() save(ctx, state) end }),
    ui.button({ text = "Keep editing", variant = "ghost", onClick = function() ctx.back() end }),
    ui.spacer({ flexGrow = 1 }),
    ui.button({ text = view.confirm == "discard" and "Click again to discard" or "Discard all", glyph = "trash",
                variant = view.confirm == "discard" and "destructive" or "outline", onClick = function()
                  if view.confirm ~= "discard" then view.confirm = "discard"; ctx.render(); return end
                  view.confirm = nil
                  store.discardAll()
                  view.gen = {}
                  ctx.home()
                end }),
  }))
  if blocked then
    table.insert(content, kit.muted("Saving is disabled until Umbriel accepts the config, or turn off the check."))
  end
  return { header = header, content = content }
end

local function backupsPage(ctx, route)
  local store, view = ctx.store, ctx.view
  route.state = route.state or { marked = {} }
  local state = route.state
  local path = store.state and store.state.path or nil
  local function refresh()
    state.loading = true
    ctx.helper.call("backups", { config = path }, function(err, data)
      state.loading = false
      if err then state.error = err.error else state.list = data.backups; state.error = nil end
      ctx.render()
    end)
  end
  if state.list == nil and not state.loading and not state.error then refresh() end
  local header = { kit.header(ctx, "Backups", "A copy is taken before every save and restore") }
  local content = {}
  if state.error then table.insert(content, kit.notice(state.error, "error", nil, "bk-error")) end
  if state.loading then table.insert(content, kit.empty("Loading…", "loader")) end
  local marked = 0
  for _ in pairs(state.marked) do marked = marked + 1 end
  for index, item in ipairs(state.list or {}) do
    local key = "bk-" .. index
    table.insert(content, ui.row({ key = key, gap = 8, align = "center", paddingH = 12, paddingV = 8, radius = 10,
                                   fill = "surface_container" }, {
      ui.toggle({ checked = state.marked[item.path] == true, onChange = function(value)
        state.marked[item.path] = value == "true" or nil
        ctx.render()
      end }),
      ui.column({ gap = 2, flexGrow = 1 }, {
        ui.label({ text = item.time, fontSize = 13, fontWeight = "bold" }),
        kit.muted(string.format("%.1f KB", item.size / 1024)),
      }),
      ui.button({ text = "Compare", controlSize = "sm", variant = "ghost", onClick = function()
        ctx.helper.call("backup-diff", { config = path, snapshot = item.path }, function(err, data)
          if err then ctx.flash(err.error, "error") return end
          state.diff = { path = item.path, text = data.diff }
          ctx.render()
        end)
      end }),
      ui.button({ text = view.confirm == key and "Click again to restore" or "Restore", controlSize = "sm",
                  variant = view.confirm == key and "destructive" or "outline", onClick = function()
        if store.hasConfigChanges() then ctx.flash("Save or discard your changes before restoring.", "warning") return end
        if view.confirm ~= key then view.confirm = key; ctx.render(); return end
        view.confirm = nil
        ctx.helper.call("restore", { config = path, snapshot = item.path, revision = store.state.revision },
          function(err, data)
            if err then ctx.flash(err.error, "error") return end
            store.load(data.state)
            state.list = data.backups.backups
            ctx.flash("Backup restored. The previous file was backed up first.", "info")
          end)
      end }),
    }))
    if state.diff and state.diff.path == item.path then
      table.insert(content, ui.markdown({ key = key .. "-diff", text = state.diff.text ~= "" and diffBlock(state.diff.text)
        or "Identical to the current file." }))
    end
  end
  if state.list and #state.list == 0 then table.insert(content, kit.empty("No backups yet.", "history")) end
  if marked > 0 then
    table.insert(content, ui.row({ key = "bk-delete", gap = 8 }, {
      ui.button({ text = "Delete " .. kit.plural(marked, "backup"), glyph = "trash", variant = "destructive",
                  controlSize = "sm", onClick = function()
        local paths = {}
        for snapshot in pairs(state.marked) do table.insert(paths, snapshot) end
        ctx.helper.call("delete-backups", { config = path, snapshots = paths }, function(err, data)
          if err then ctx.flash(err.error, "error") return end
          state.marked = {}
          state.list = data.backups.backups
          if #data.errors > 0 then ctx.flash(table.concat(data.errors, "\n"), "warning") else ctx.render() end
        end)
      end }),
    }))
  end
  return { header = header, content = content }
end

function M.render(ctx, route)
  if route.name == "backups" then return backupsPage(ctx, route) end
  return reviewPage(ctx, route)
end

return M
