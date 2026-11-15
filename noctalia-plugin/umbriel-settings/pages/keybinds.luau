-- Keybinds: grouped list, a detail page with a shortcut builder, and a searchable action picker.
local kit = require("../ui/kit.luau")

local M = {}

local MODIFIERS = { "Mod", "Super", "Ctrl", "Alt", "Shift" }
local OPTION_CHOICES = { "Default", "On", "Off" }

local function normalize(key) return string.lower((string.gsub(noctalia.string.trim(key), "%s+", " "))) end

local function splitShortcut(key)
  local mods, rest = {}, {}
  for part in string.gmatch(key or "", "[^+]+") do
    local known = false
    for _, mod in ipairs(MODIFIERS) do
      if string.lower(part) == string.lower(mod) and #rest == 0 then mods[mod] = true; known = true end
    end
    if not known then table.insert(rest, part) end
  end
  return mods, table.concat(rest, "+")
end

local function joinShortcut(mods, key)
  local parts = {}
  for _, mod in ipairs(MODIFIERS) do if mods[mod] then table.insert(parts, mod) end end
  if key ~= "" then table.insert(parts, key) end
  return table.concat(parts, "+")
end

local function reduceTemplate(text)
  local head, rest = string.match(text, "^(%S+)%s+(.*)$")
  if not head then return text end
  if string.sub(rest, 1, 1) == "[" then return head end
  if string.sub(rest, 1, 1) == "<" then return head .. " " end
  return text
end

-- Action templates by full text and by first word, built once per meta: the list describes every row
-- on every render, and scanning all actions per row is the costliest loop on a large config.
local actionIndex = { meta = nil, exact = {}, head = {} }
local function describe(meta, action)
  if actionIndex.meta ~= meta then
    actionIndex = { meta = meta, exact = {}, head = {} }
    for _, category in ipairs(meta.actions.categories) do
      for _, item in ipairs(category[2]) do
        local head = string.match(item[1], "^(%S+)")
        if actionIndex.exact[item[1]] == nil then actionIndex.exact[item[1]] = item end
        if head and actionIndex.head[head] == nil then actionIndex.head[head] = item end
      end
    end
  end
  local item = actionIndex.exact[action or ""] or actionIndex.head[string.match(action or "", "^(%S+)") or ""]
  if item then return item[2], item[1] end
  return nil, nil
end

local function argHelp(meta, template)
  local lines = {}
  for name in string.gmatch(template or "", "<([%w_.-]+)>") do
    local help = meta.actions.args[name] or meta.actions.args[string.gsub(name, "%.%.%.$", "")]
    if help then table.insert(lines, "<" .. name .. ">: " .. help) end
  end
  return table.concat(lines, "\n")
end

local function conflict(store, key, index)
  local wanted = normalize(key)
  if wanted == "" then return nil end
  for i, row in ipairs(store.keybinds.rows) do
    if i ~= index and normalize(row.key) == wanted then return row.key end
  end
  return nil
end

local function changed(store) store.keybindsDirty = true end

-- ------------------------------------------------------------------ list
local function listPage(ctx)
  local store, view = ctx.store, ctx.view
  local header = { kit.header(ctx, "Keybinds", "Shortcuts, grouped. Locked shortcuts are protected from edits.", {
    ui.button({ key = "add", text = "Add shortcut", glyph = "plus", variant = "primary", controlSize = "sm",
                onClick = function()
                  view.kbNew = { key = "", action = "", opts = {}, group = view.kbGroup or "" }
                  ctx.go({ name = "keybind", index = nil })
                end }),
  }) }
  if not store.keybinds then return { header = header, content = { kit.empty("Loading…", "loader") } } end
  local content = {
    ui.input({ key = "kb-filter", value = view.kbFilter or "", controlSize = "sm",
               placeholder = "Filter shortcuts and actions",
               onChange = function(text) view.kbFilter = text; ctx.render() end }),
  }
  local filter = string.lower(noctalia.string.trim(view.kbFilter or ""))
  local groups = {}
  for _, name in ipairs(store.keybinds.groups) do table.insert(groups, name) end
  table.insert(groups, "")
  view.kbCollapsed = view.kbCollapsed or {}
  local others = store.state and store.state.keybinds.other or {}
  for _, group in ipairs(groups) do
    local rows = {}
    for index, row in ipairs(store.keybinds.rows) do
      local inGroup = (row.group or "") == group
      local text = string.lower(row.key .. " " .. row.action)
      if inGroup and (filter == "" or string.find(text, filter, 1, true)) then
        local desc = describe(store.meta, row.action)
        local badges = {}
        if row.locked then table.insert(badges, ui.glyph({ name = "lock", size = 14, color = kit.MUTED })) end
        table.insert(rows, kit.navRow({ key = "kb-" .. index .. "-" .. row.key, title = row.key, subtitle = row.action
          .. (desc and ("  ·  " .. desc) or ""), badges = badges, onClick = function()
            ctx.go({ name = "keybind", index = index })
          end }))
      end
    end
    local name = group == "" and "Ungrouped" or group
    if #rows > 0 or (group ~= "" and filter == "") then
      local collapsed = view.kbCollapsed[name] and filter == ""
      table.insert(content, ui.row({ key = "kbg-" .. name, gap = 8, align = "center", onClick = function()
        view.kbCollapsed[name] = not view.kbCollapsed[name]
        ctx.render()
      end }, {
        ui.glyph({ name = collapsed and "chevron-right" or "chevron-down", size = 14, color = kit.MUTED }),
        kit.section(name .. "  ·  " .. #rows, "kbgl-" .. name),
      }))
      if not collapsed then
        for _, row in ipairs(rows) do table.insert(content, row) end
      end
    end
  end
  if #others > 0 then
    table.insert(content, kit.notice("Kept as written (not editable here): " .. table.concat(others, ", "), "info",
      nil, "kb-others"))
  end
  -- group management
  table.insert(content, kit.section("Groups"))
  for index, group in ipairs(store.keybinds.groups) do
    table.insert(content, ui.row({ key = "grp-" .. index, gap = 6, align = "center" }, {
      ui.input({ key = "grp-name-" .. index .. "-" .. group, value = group, flexGrow = 1, controlSize = "sm",
                 onSubmit = function(text)
                   text = noctalia.string.trim(text)
                   if text == "" or text == group then return end
                   for _, other in ipairs(store.keybinds.groups) do
                     if other == text then ctx.flash("That group already exists.", "warning"); return end
                   end
                   store.keybinds.groups[index] = text
                   for _, row in ipairs(store.keybinds.rows) do if row.group == group then row.group = text end end
                   changed(store)
                   ctx.render()
                 end }),
      ui.button({ glyph = "trash", variant = "ghost", controlSize = "sm",
                  tooltip = "Delete group (its shortcuts move to Ungrouped)", onClick = function()
                    table.remove(store.keybinds.groups, index)
                    for _, row in ipairs(store.keybinds.rows) do if row.group == group then row.group = "" end end
                    changed(store)
                    ctx.render()
                  end }),
    }))
  end
  table.insert(content, ui.row({ key = "grp-add", gap = 6 }, {
    ui.input({ key = "grp-new-" .. tostring(view.gen.grp or 0), value = "", flexGrow = 1, controlSize = "sm",
               placeholder = "New group name (press Enter)",
               onSubmit = function(text)
                 text = noctalia.string.trim(text)
                 if text == "" then return end
                 for _, other in ipairs(store.keybinds.groups) do
                   if other == text then ctx.flash("That group already exists.", "warning"); return end
                 end
                 table.insert(store.keybinds.groups, text)
                 view.gen.grp = (view.gen.grp or 0) + 1
                 changed(store)
                 ctx.render()
               end }),
  }))
  return { header = header, content = content }
end

-- ------------------------------------------------------------------ detail
local function detailPage(ctx, route)
  local store, view = ctx.store, ctx.view
  local isNew = route.index == nil
  local row = isNew and view.kbNew or store.keybinds.rows[route.index]
  if not row then return { header = { kit.header(ctx, "Keybind") }, content = { kit.empty("This shortcut no longer exists.") } } end
  local locked = row.locked == true
  local function edit() if not isNew then changed(store) end end
  local header = { kit.header(ctx, isNew and "New shortcut" or row.key, row.action) }
  local content = {}
  if locked then
    table.insert(content, kit.notice("This shortcut is locked. Unlock it to change or delete it.", "info", nil, "locked"))
  end
  -- shortcut builder
  local mods, key = splitShortcut(row.key)
  local chips = {}
  for _, mod in ipairs(MODIFIERS) do
    table.insert(chips, ui.button({ key = "mod-" .. mod, text = mod, controlSize = "sm", selected = mods[mod] == true,
      variant = mods[mod] and "primary" or "outline", enabled = not locked,
      tooltip = mod == "Mod" and "The modifier chosen in General › Mod key" or nil,
      onClick = function()
        mods[mod] = not mods[mod] or nil
        row.key = joinShortcut(mods, key)
        view.gen.kbkey = (view.gen.kbkey or 0) + 1
        edit(); ctx.render()
      end }))
  end
  table.insert(chips, ui.input({ key = "kb-key-" .. tostring(view.gen.kbkey or 0), value = key, flexGrow = 1,
    controlSize = "sm", enabled = not locked, placeholder = "Key: Return, Q, F1, XF86AudioMute…",
    onChange = function(text)
      row.key = joinShortcut(mods, noctalia.string.trim(text))
      edit(); ctx.render()
    end }))
  local clash = conflict(store, row.key, route.index)
  local shortcutCard = {
    kit.muted("Shortcut"),
    ui.row({ gap = 6, align = "center" }, chips),
    kit.muted("Writes: " .. (row.key ~= "" and row.key or "—")),
  }
  if clash then table.insert(shortcutCard, kit.notice("Conflicts with “" .. clash .. "”.", "error", nil, "clash")) end
  table.insert(content, kit.card({ key = "shortcut" }, shortcutCard))
  -- action
  local desc, template = describe(store.meta, row.action)
  local actionCard = {
    kit.muted("Action"),
    ui.row({ gap = 6, align = "center" }, {
      ui.input({ key = "kb-action-" .. tostring(view.gen.kbaction or 0), value = row.action, flexGrow = 1,
                 controlSize = "sm", enabled = not locked, placeholder = "e.g. spawn kitty",
                 onChange = function(text) row.action = text; edit(); ctx.render() end }),
      ui.button({ text = "Choose…", glyph = "list-search", controlSize = "sm", enabled = not locked,
                  onClick = function() ctx.go({ name = "actions", target = route.index }) end }),
    }),
  }
  if desc then table.insert(actionCard, kit.muted(desc, { maxLines = 3 })) end
  local args = argHelp(store.meta, template)
  if args ~= "" then table.insert(actionCard, kit.muted(args, { maxLines = 6 })) end
  table.insert(content, kit.card({ key = "action" }, actionCard))
  -- options
  local optionRows = {}
  for _, option in ipairs(store.meta.actions.options) do
    local name, label = option[1], option[2]
    local value = row.opts[name]
    table.insert(optionRows, ui.row({ key = "opt-" .. name, gap = 8, align = "center" }, {
      ui.label({ text = label, fontSize = 13, flexGrow = 1 }),
      ui.select({ options = OPTION_CHOICES, selectedIndex = value == nil and 0 or (value and 1 or 2), width = 160,
                  controlSize = "sm", enabled = not locked, onChange = function(i)
                    i = tonumber(i) or 0
                    row.opts[name] = i == 1 and true or i == 2 and false or nil
                    edit(); ctx.render()
                  end }),
    }))
  end
  for _, item in ipairs({ { "cooldown_ms", "Cooldown (ms)", "0 = none" }, { "submap", "Submap", "Name (optional)" } }) do
    local name = item[1]
    table.insert(optionRows, ui.row({ key = "opt-" .. name, gap = 8, align = "center" }, {
      ui.label({ text = item[2], fontSize = 13, flexGrow = 1 }),
      ui.input({ key = "opt-in-" .. name, value = row.opts[name] ~= nil and tostring(row.opts[name]) or "", width = 160,
                 controlSize = "sm", enabled = not locked, placeholder = item[3], onChange = function(text)
                   text = noctalia.string.trim(text)
                   if name == "cooldown_ms" then
                     local number = tonumber(text)
                     row.opts[name] = (number and number > 0) and math.floor(number) or nil
                   else
                     row.opts[name] = text ~= "" and text or nil
                   end
                   edit()
                 end }),
    }))
  end
  local groupOptions, selected = { "Ungrouped" }, 0
  for index, group in ipairs(store.keybinds.groups) do
    table.insert(groupOptions, group)
    if group == row.group then selected = index end
  end
  table.insert(optionRows, ui.row({ key = "opt-group", gap = 8, align = "center" }, {
    ui.label({ text = "Group", fontSize = 13, flexGrow = 1 }),
    ui.select({ options = groupOptions, selectedIndex = selected, width = 160, controlSize = "sm",
                enabled = not locked, onChange = function(i)
                  i = tonumber(i) or 0
                  row.group = i == 0 and "" or store.keybinds.groups[i]
                  edit(); ctx.render()
                end }),
  }))
  if not isNew then
    table.insert(optionRows, ui.row({ key = "opt-lock", gap = 8, align = "center" }, {
      ui.label({ text = "Locked (protect from edits here and in the app)", fontSize = 13, flexGrow = 1 }),
      ui.toggle({ checked = locked, onChange = function(value) row.locked = value == "true"; edit(); ctx.render() end }),
    }))
  end
  table.insert(content, kit.card({ key = "options" }, optionRows))
  -- actions
  if isNew then
    table.insert(content, ui.row({ key = "new-actions", gap = 6 }, {
      ui.button({ text = "Add shortcut", glyph = "plus", variant = "primary", onClick = function()
        if noctalia.string.trim(row.key) == "" or noctalia.string.trim(row.action) == "" then
          ctx.flash("Enter a shortcut and an action.", "warning"); return
        end
        if clash then ctx.flash("That shortcut is already used by “" .. clash .. "”.", "warning"); return end
        table.insert(store.keybinds.rows, row)
        changed(store)
        view.kbNew = nil
        ctx.replace({ name = "keybind", index = #store.keybinds.rows })
      end }),
    }))
  else
    table.insert(content, ui.row({ key = "row-actions", gap = 6 }, {
      ui.button({ text = "Duplicate", glyph = "copy", controlSize = "sm", variant = "outline", onClick = function()
        local copy = store.deepCopy(row)
        copy.key, copy.locked = "", false
        view.kbNew = copy
        view.gen.kbkey = (view.gen.kbkey or 0) + 1  -- the inputs keep their keys: show the copy's (empty) shortcut
        view.gen.kbaction = (view.gen.kbaction or 0) + 1
        ctx.replace({ name = "keybind", index = nil })
      end }),
      ui.spacer({ flexGrow = 1 }),
      ui.button({ text = view.confirm == "kbdel" and "Click again to delete" or "Delete", glyph = "trash",
                  controlSize = "sm", variant = view.confirm == "kbdel" and "destructive" or "outline",
                  enabled = not locked, onClick = function()
                    if view.confirm ~= "kbdel" then view.confirm = "kbdel"; ctx.render(); return end
                    view.confirm = nil
                    table.remove(store.keybinds.rows, route.index)
                    changed(store)
                    ctx.back()
                  end }),
    }))
  end
  return { header = header, content = content }
end

-- ------------------------------------------------------------------ action picker
local function pickerPage(ctx, route)
  local store, view = ctx.store, ctx.view
  local header = { kit.header(ctx, "Choose an action", "Pick a template, then fill in any <argument>") ,
    ui.input({ key = "act-search", value = view.actQuery or "", focus = true, placeholder = "Search actions",
               onChange = function(text) view.actQuery = text; ctx.render() end }) }
  local function choose(template)
    local row = route.target and store.keybinds.rows[route.target] or view.kbNew
    if row then
      row.action = reduceTemplate(template)
      if route.target then changed(store) end
    end
    view.gen.kbaction = (view.gen.kbaction or 0) + 1
    view.actQuery = ""
    ctx.back()
  end
  local content = {}
  local query = string.lower(noctalia.string.trim(view.actQuery or ""))
  local shown = 0
  for _, category in ipairs(store.meta.actions.categories) do
    local name = category[1]
    local open = query ~= "" or view.actOpen == name
    local items = {}
    for index, item in ipairs(category[2]) do
      if query == "" or string.find(string.lower(item[1] .. " " .. item[2]), query, 1, true) then
        if shown < 60 or query == "" then
          table.insert(items, kit.navRow({ key = "act-" .. name .. "-" .. index, title = item[1], subtitle = item[2],
            trailing = "check", onClick = function() choose(item[1]) end }))
          shown = shown + 1
        end
      end
    end
    if #items > 0 then
      table.insert(content, kit.navRow({ key = "cat-" .. name, title = name, subtitle = kit.plural(#category[2], "action"),
        bold = true, trailing = open and "chevron-up" or "chevron-down", fill = "surface_container_high",
        onClick = function() view.actOpen = view.actOpen ~= name and name or nil; ctx.render() end }))
      if open then for _, item in ipairs(items) do table.insert(content, item) end end
    end
  end
  if #content == 0 then table.insert(content, kit.empty("No action matches. You can also type any action by hand.")) end
  return { header = header, content = content }
end

function M.render(ctx, route)
  if route.name == "keybind" then return detailPage(ctx, route) end
  if route.name == "actions" then return pickerPage(ctx, route) end
  return listPage(ctx)
end

return M
