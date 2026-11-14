-- Rule-style editors: a filterable entry list, an entry page with the field groups, and the output inspector.
local kit = require("../ui/kit.luau")
local form = require("./form.luau")

local M = {}

local function fieldSpec(ctx, eid, index, fid)
  local store = ctx.store
  local field = store.meta.fields[fid]
  local fpath = string.sub(fid, #eid + 2)
  local item = store.entryItems(eid)[index]
  local value = item.values[fpath]
  return {
    key = "e:" .. eid .. ":" .. fid, field = field, value = value, set = value ~= nil, changed = false,
    onSet = function(v) store.entryOp(eid, { op = "set", index = index - 1, field = fpath, value = v }) end,
    onUnset = field.opt and function() store.entryOp(eid, { op = "unset", index = index - 1, field = fpath }) end or nil,
  }
end

local function confirmButton(ctx, key, text, action)
  local armed = ctx.view.confirm == key
  return ui.button({ key = key, text = armed and "Click again to delete" or text, glyph = "trash",
                     variant = armed and "destructive" or "outline", controlSize = "sm",
                     onClick = function()
                       if armed then ctx.view.confirm = nil; action() else ctx.view.confirm = key; ctx.render() end
                     end })
end

local function nameForm(ctx, key, placeholder, buttonText, onAccept)
  local view = ctx.view
  return ui.row({ key = key, gap = 6, align = "center" }, {
    ui.input({ key = key .. ":" .. tostring(view.gen[key] or 0), value = "", flexGrow = 1, controlSize = "sm",
               placeholder = placeholder, onChange = function(text) view[key] = text end,
               onSubmit = function(text) view[key] = text; onAccept(noctalia.string.trim(text)) end }),
    ui.button({ text = buttonText, glyph = "plus", controlSize = "sm", variant = "outline",
                onClick = function() onAccept(noctalia.string.trim(view[key] or "")) end }),
  })
end

local function nameTaken(store, eid, name)
  for _, item in ipairs(store.entryItems(eid)) do
    if item.name == name then return true end
  end
  return false
end

local function editorList(ctx, eid, filter, multiple)
  local store, view = ctx.store, ctx.view
  local editor = store.meta.editors[eid]
  local items = store.entryItems(eid)
  local rows = {}
  if multiple then table.insert(rows, kit.section(editor.title)) end
  local shown = 0
  for index, item in ipairs(items) do
    local title, automatic = store.entryTitle(eid, index, item)
    local count = 0
    for _ in pairs(item.values) do count = count + 1 end
    local subtitle = (automatic and "Automatic name · " or "") .. kit.plural(count, "setting")
    if filter == "" or string.find(string.lower(title), filter, 1, true) then
      shown = shown + 1
      table.insert(rows, kit.navRow({ key = "entry-" .. eid .. "-" .. index, title = title, subtitle = subtitle,
        onClick = function() ctx.go({ name = "entry", editor = eid, index = index }) end }))
    end
  end
  if shown == 0 then
    table.insert(rows, kit.muted(#items == 0 and ("No " .. string.lower(editor.title) .. " yet.") or "No matches."))
  end
  if editor.mode == "aot" then
    table.insert(rows, ui.row({ key = "add-" .. eid, gap = 6 }, {
      ui.button({ text = "Add", glyph = "plus", variant = "outline", controlSize = "sm", onClick = function()
        store.entryOp(eid, { op = "add" })
        ctx.go({ name = "entry", editor = eid, index = #store.entryItems(eid) })
      end }),
    }))
  else
    local placeholder = eid == "output" and "Connector or monitor name, e.g. DP-1" or "Name"
    table.insert(rows, nameForm(ctx, "new-" .. eid, placeholder, "Add", function(name)
      if name == "" then ctx.flash("Enter a name first.", "warning"); return end
      if nameTaken(store, eid, name) then ctx.flash("“" .. name .. "” already exists.", "warning"); return end
      store.entryOp(eid, { op = "add", name = name })
      view.gen["new-" .. eid] = (view.gen["new-" .. eid] or 0) + 1
      ctx.go({ name = "entry", editor = eid, index = #store.entryItems(eid) })
    end))
  end
  return rows
end

local function listPage(ctx, route)
  local store, view = ctx.store, ctx.view
  local page = store.meta.pages[route.page]
  local header = { kit.header(ctx, route.page, page.help) }
  local content = {}
  if not store.state then return { header = header, content = { kit.empty("Loading config…", "loader") } } end
  local filterKey = "filter-" .. route.page
  table.insert(content, ui.input({ key = filterKey, value = view[filterKey] or "", controlSize = "sm",
                                   placeholder = "Filter by name",
                                   onChange = function(text) view[filterKey] = text; ctx.render() end }))
  if route.page == "Outputs" then
    table.insert(content, ui.row({ key = "inspect", gap = 6 }, {
      ui.button({ text = "Inspect connected outputs", glyph = "device-desktop", controlSize = "sm", variant = "outline",
                  onClick = function() ctx.go({ name = "outputs" }) end }),
    }))
  end
  local filter = string.lower(noctalia.string.trim(view[filterKey] or ""))
  for _, eid in ipairs(page.editors) do
    for _, row in ipairs(editorList(ctx, eid, filter, #page.editors > 1)) do table.insert(content, row) end
  end
  return { header = header, content = content }
end

local function entryPage(ctx, route)
  local store, view = ctx.store, ctx.view
  local eid, index = route.editor, route.index
  local editor = store.meta.editors[eid]
  local items = store.entryItems(eid)
  local item = items[index]
  if not item then
    return { header = { kit.header(ctx, editor.page) }, content = { kit.empty("This entry no longer exists.", "trash") } }
  end
  local title = store.entryTitle(eid, index, item)
  local nav = {
    ui.button({ key = "prev", glyph = "chevron-left", variant = "ghost", enabled = index > 1, tooltip = "Previous",
                onClick = function() ctx.replace({ name = "entry", editor = eid, index = index - 1 }) end }),
    ui.button({ key = "next", glyph = "chevron-right", variant = "ghost", enabled = index < #items, tooltip = "Next",
                onClick = function() ctx.replace({ name = "entry", editor = eid, index = index + 1 }) end }),
  }
  local header = { kit.header(ctx, title, editor.page .. " · " .. index .. " of " .. #items, nav) }
  local actions = {}
  if editor.mode == "aot" then
    table.insert(actions, ui.input({ key = "label-" .. eid .. "-" .. index, value = item.label or "", width = 220,
      controlSize = "sm", placeholder = "Display name (optional)",
      onChange = function(text)
        store.entryOp(eid, { op = "label", index = index - 1, text = text })
        ctx.render()
      end }))
    table.insert(actions, ui.button({ glyph = "arrow-up", variant = "ghost", controlSize = "sm", enabled = index > 1,
      tooltip = "Move up (rules are checked in order)", onClick = function()
        store.entryOp(eid, { op = "move", index = index - 1, to = index - 2 })
        ctx.replace({ name = "entry", editor = eid, index = index - 1 })
      end }))
    table.insert(actions, ui.button({ glyph = "arrow-down", variant = "ghost", controlSize = "sm",
      enabled = index < #items, tooltip = "Move down", onClick = function()
        store.entryOp(eid, { op = "move", index = index - 1, to = index })
        ctx.replace({ name = "entry", editor = eid, index = index + 1 })
      end }))
    table.insert(actions, ui.button({ glyph = "copy", variant = "ghost", controlSize = "sm", tooltip = "Duplicate",
      onClick = function()
        store.entryOp(eid, { op = "duplicate", index = index - 1 })
        ctx.replace({ name = "entry", editor = eid, index = index + 1 })
      end }))
  end
  table.insert(actions, ui.spacer({ flexGrow = 1 }))
  table.insert(actions, confirmButton(ctx, "delete-" .. eid .. "-" .. index, "Delete", function()
    store.entryOp(eid, { op = "remove", index = index - 1 })
    ctx.back()
  end))
  local content = { ui.row({ key = "entry-actions", gap = 6, align = "center" }, actions) }
  if editor.mode == "map" then
    table.insert(content, nameForm(ctx, "dup-" .. eid, "Name for a copy", "Duplicate", function(name)
      if name == "" or nameTaken(store, eid, name) then ctx.flash("Choose a new, unused name.", "warning"); return end
      store.entryOp(eid, { op = "duplicate", index = index - 1, name = name })
      ctx.replace({ name = "entry", editor = eid, index = #store.entryItems(eid) })
    end))
  end
  local groups = form.groups(ctx, "entry:" .. eid, editor.groups,
    function(fid) return fieldSpec(ctx, eid, index, fid) end,
    function(fids)
      local set = 0
      for _, fid in ipairs(fids) do
        if item.values[string.sub(fid, #eid + 2)] ~= nil then set = set + 1 end
      end
      return 0, set
    end)
  for _, row in ipairs(groups) do table.insert(content, row) end
  return { header = header, content = content }
end

local function modeText(mode)
  return string.format("%dx%d@%s", mode.width, mode.height, string.format("%g", mode.refresh_mhz / 1000))
end

local function outputsPage(ctx)
  local store, view = ctx.store, ctx.view
  local header = { kit.header(ctx, "Connected outputs", "Pick a mode and add it to the config") }
  if view.outputs == nil and not view.outputsLoading then
    view.outputsLoading = true
    ctx.helper.call("outputs", {}, function(err, data)
      view.outputsLoading = false
      if err then view.outputs = false; ctx.flash(err.error, "error") else view.outputs = data.outputs end
      ctx.render()
    end)
  end
  if view.outputsLoading or view.outputs == nil then
    return { header = header, content = { kit.empty("Asking Umbriel for outputs…", "loader") } }
  end
  local content = {}
  for index, output in ipairs(view.outputs or {}) do
    local modes, labels = {}, {}
    for _, mode in ipairs(output.modes or {}) do
      if type(mode.width) == "number" and type(mode.refresh_mhz) == "number" and mode.refresh_mhz > 0 then
        table.insert(modes, mode)
      end
    end
    table.sort(modes, function(a, b)
      if (a.current == true) ~= (b.current == true) then return a.current == true end
      if (a.preferred == true) ~= (b.preferred == true) then return a.preferred == true end
      if a.width * a.height ~= b.width * b.height then return a.width * a.height > b.width * b.height end
      return a.refresh_mhz > b.refresh_mhz
    end)
    for _, mode in ipairs(modes) do
      local extra = mode.current and " (current)" or mode.preferred and " (preferred)" or ""
      table.insert(labels, modeText(mode) .. extra)
    end
    local key = "out-" .. index
    view[key .. "mode"] = view[key .. "mode"] or 0
    view[key .. "name"] = view[key .. "name"] or 0
    local names = { output.name }
    if type(output.config_name) == "string" and output.config_name ~= "" then table.insert(names, output.config_name) end
    table.insert(content, kit.card({ key = key }, {
      ui.label({ text = output.name, fontSize = 15, fontWeight = "bold" }),
      kit.muted(output.description or ""),
      kit.muted("Config entry name"),
      ui.select({ key = key .. "names", options = { "Connector: " .. output.name,
                    names[2] and ("Monitor: " .. names[2]) or nil }, selectedIndex = view[key .. "name"],
                  controlSize = "sm", onChange = function(i) view[key .. "name"] = tonumber(i) or 0; ctx.render() end }),
      kit.muted("Mode"),
      #labels > 0 and ui.select({ key = key .. "modes", options = labels, selectedIndex = view[key .. "mode"],
                                  controlSize = "sm",
                                  onChange = function(i) view[key .. "mode"] = tonumber(i) or 0; ctx.render() end })
        or kit.muted("No modes reported."),
      ui.row({ gap = 6 }, {
        ui.button({ text = "Use for this output", glyph = "check", variant = "primary", controlSize = "sm",
                    enabled = #labels > 0, onClick = function()
          local name = names[view[key .. "name"] + 1] or output.name
          local mode = modes[view[key .. "mode"] + 1]
          local items = store.entryItems("output")
          local at
          for i, item in ipairs(items) do if item.name == name then at = i end end
          if not at then
            store.entryOp("output", { op = "add", name = name })
            at = #store.entryItems("output")
          end
          store.entryOp("output", { op = "set", index = at - 1, field = "mode", value = modeText(mode) })
          ctx.replace({ name = "entry", editor = "output", index = at })
        end }),
      }),
    }))
  end
  if #content == 0 then table.insert(content, kit.empty("Umbriel reported no outputs.", "device-desktop-off")) end
  return { header = header, content = content }
end

function M.render(ctx, route)
  if route.name == "entry" then return entryPage(ctx, route) end
  if route.name == "outputs" then return outputsPage(ctx) end
  return listPage(ctx, route)
end

return M
