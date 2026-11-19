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
    key = "e:" .. eid .. ":" .. index .. ":" .. fid, field = field, value = value, set = value ~= nil, changed = false,
    entry = { editor = eid, index = index },
    onSet = function(v) store.entryOp(eid, { op = "set", index = index - 1, field = fpath, value = v }) end,
    onUnset = field.opt and function() store.entryOp(eid, { op = "unset", index = index - 1, field = fpath }) end or nil,
  }
end

local function nameForm(ctx, key, placeholder, buttonText, onAccept)
  local view = ctx.view
  return ui.row({ key = key, gap = 6, align = "center" }, {
    ui.input({ key = key .. ":" .. ctx.gen(key), value = "", flexGrow = 1, controlSize = "sm",
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
    local title = store.entryTitle(eid, index, item)
    local count = 0
    for _ in pairs(item.values) do count = count + 1 end
    local subtitle = kit.plural(count, "setting")
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
      ctx.bump("new-" .. eid)
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
    table.insert(content, ui.row({ key = "inspect", gap = 10, align = "center" }, {
      ui.button({ text = "Inspect connected outputs", glyph = "device-desktop", controlSize = "sm", variant = "outline",
                  tooltip = "Reads live modes from `umbriel outputs --json`; needs Umbriel running in this session",
                  onClick = function()
                    view.outputs = nil  -- ask again: monitors may have been plugged in since
                    ctx.go({ name = "outputs" })
                  end }),
      kit.muted("A monitor name follows the display between ports; a connector name (DP-1) targets a port.",
                { flexGrow = 1, maxLines = 2 }),
    }))
  end
  local filter = string.lower(noctalia.string.trim(view[filterKey] or ""))
  for _, eid in ipairs(page.editors) do
    for _, row in ipairs(editorList(ctx, eid, filter, #page.editors > 1)) do table.insert(content, row) end
  end
  return { header = header, content = content }
end

-- "windows" when the editor matches windows by app id, "layers" when it matches layer surfaces, else nil
-- (read from the field paths in meta).
local function liveKind(editor, eid)
  local found = nil
  for _, group in ipairs(editor.groups) do
    for _, fid in ipairs(group.fields) do
      local fpath = string.sub(fid, #eid + 2)
      if fpath == "match.app_id" then return "windows" end
      if fpath == "match.namespace" then found = "layers" end
    end
  end
  return found
end

local function entryPage(ctx, route)
  local store = ctx.store
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
  table.insert(actions, kit.confirmButton(ctx, { key = "delete-" .. eid .. "-" .. index, text = "Delete",
                                               armedText = "Click again to delete", glyph = "trash",
                                               controlSize = "sm" }, function()
    store.entryOp(eid, { op = "remove", index = index - 1 })
    ctx.back()
  end))
  local content = { ui.row({ key = "entry-actions", gap = 6, align = "center" }, actions) }
  local live = liveKind(editor, eid)
  if live then
    table.insert(content, ui.row({ key = "entry-live", gap = 6, align = "center" }, {
      ui.button({ text = live == "windows" and "Pick from open windows" or "Pick from open layers",
                  glyph = live == "windows" and "app-window" or "stack-2", controlSize = "sm", variant = "outline",
                  onClick = function()
                    ctx.view.live, ctx.view.liveFilter = nil, nil
                    ctx.bump("live-filter")
                    ctx.go({ name = "pick-live", editor = eid, index = index, kind = live })
                  end }),
    }))
  end
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

local LIVE_ROWS = 40

-- Pick a rule's match from what the running Umbriel shows: open windows (app id, title) or layer surfaces.
local function pickLivePage(ctx, route)
  local store, view = ctx.store, ctx.view
  local eid, index, kind = route.editor, route.index, route.kind
  local windows = kind == "windows"
  local rule = store.entryItems(eid)[index]
  local title = windows and "Open windows" or "Open layers"
  if not rule then
    return { header = { kit.header(ctx, title) }, content = { kit.empty("This entry no longer exists.", "trash") } }
  end
  local header = { kit.header(ctx, title, "Pick one for " .. store.entryTitle(eid, index, rule)) }
  if view.live == nil or view.live.kind ~= kind then
    view.live = { kind = kind, loading = true }
    ctx.helper.call(kind, {}, function(err, data)
      if not view.live or view.live.kind ~= kind then return end
      view.live = { kind = kind, items = (not err) and data[kind] or nil, error = err and err.error or nil }
      ctx.render()
    end)
  end
  local live = view.live
  if live.loading then
    return { header = header, content = { kit.empty("Asking Umbriel…", "loader") } }
  end
  if live.error then
    return { header = header, content = {
      kit.notice(live.error, "error", nil, "live-error"),
      ui.row({ key = "live-retry" }, {
        ui.button({ text = "Try again", glyph = "refresh", variant = "primary", onClick = function()
          view.live = nil
          ctx.render()
        end }),
      }),
    } }
  end
  local function choose(values, shown)
    for _, pair in ipairs(values) do
      store.entryOp(eid, { op = "set", index = index - 1, field = pair[1], value = pair[2] })
    end
    ctx.back()
    ctx.flash("The rule now matches “" .. shown .. "”.", "info")
  end
  local filter = string.lower(noctalia.string.trim(view.liveFilter or ""))
  local content = {
    ui.input({ key = "live-filter:" .. ctx.gen("live-filter"), value = view.liveFilter or "", controlSize = "sm",
               placeholder = windows and "Filter by app id or title" or "Filter by namespace",
               onChange = function(text) view.liveFilter = text; ctx.render() end }),
  }
  local shown, matches = 0, 0
  for position, item in ipairs(live.items or {}) do
    local name = windows and item.app_id or item.namespace
    local detail = windows and item.title or (item.layer .. " · " .. table.concat(item.outputs or {}, ", "))
    if filter == "" or string.find(string.lower(name .. " " .. detail), filter, 1, true) then
      matches = matches + 1
      if shown < LIVE_ROWS then
        shown = shown + 1
        local buttons = {}
        if windows then
          table.insert(buttons, ui.button({ text = "Match app", glyph = "check", variant = "primary", controlSize = "sm",
            tooltip = "Sets App ID to " .. item.pattern,
            onClick = function() choose({ { "match.app_id", item.pattern } }, name) end }))
          if item.title ~= "" then
            table.insert(buttons, ui.button({ text = "App and title", variant = "outline", controlSize = "sm",
              tooltip = "Also sets Title to this window's title",
              onClick = function()
                choose({ { "match.app_id", item.pattern }, { "match.title", item.title_pattern } }, name)
              end }))
          end
        else
          table.insert(buttons, ui.button({ text = "Match", glyph = "check", variant = "primary", controlSize = "sm",
            tooltip = "Sets Namespace to " .. item.pattern,
            onClick = function() choose({ { "match.namespace", item.pattern } }, name) end }))
        end
        local count = windows and item.count > 1 and (" · " .. item.count .. " windows") or ""
        table.insert(content, kit.card({ key = "live-" .. position }, {
          ui.row({ gap = 8, align = "center" }, {
            ui.column({ gap = 2, flexGrow = 1 }, {
              ui.label({ text = name .. count, fontSize = 14, fontWeight = "bold" }),
              kit.muted(detail ~= "" and detail or "(no title)", { maxLines = 1 }),
            }),
            ui.row({ gap = 6 }, buttons),
          }),
        }))
      end
    end
  end
  if matches == 0 then
    table.insert(content, kit.empty(#(live.items or {}) == 0
      and (windows and "Umbriel reported no open windows." or "Umbriel reported no layer surfaces.")
      or "No matches.", "search"))
  elseif matches > shown then
    table.insert(content, kit.muted(kit.plural(matches - shown, "more match", "more matches") .. "; filter to narrow."))
  end
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
      view.outputs, view.outputsError = (not err) and data.outputs or false, err and err.error or nil
      ctx.render()
    end)
  end
  if view.outputsLoading or view.outputs == nil then
    return { header = header, content = { kit.empty("Asking Umbriel for outputs…", "loader") } }
  end
  if view.outputs == false then
    return { header = header, content = {
      kit.notice(view.outputsError or "Umbriel did not answer.", "error", nil, "outputs-error"),
      ui.row({ key = "outputs-retry" }, {
        ui.button({ text = "Try again", glyph = "refresh", variant = "primary", onClick = function()
          view.outputs = nil
          ctx.render()
        end }),
      }),
    } }
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
  if route.name == "pick-live" then return pickLivePage(ctx, route) end
  return listPage(ctx, route)
end

return M
