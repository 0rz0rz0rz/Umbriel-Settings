-- Keybinds: grouped list, a detail page with a shortcut builder, and a searchable action picker.
local kit = require("../ui/kit.luau")
local order = require("./keybind_order.luau")

local M = {}

local MODIFIERS = { "Mod", "Super", "Ctrl", "Alt", "Shift" }
local OPTION_CHOICES = { "Default", "On", "Off" }

-- Why "Run now" refuses an action (same rules as the helper's `run_block_reason`), or nil.
local function blockReason(meta, action)
  local words = {}
  for word in string.gmatch(action or "", "%S+") do table.insert(words, word) end
  if #words == 0 then return "Enter an action first" end
  local blocked = meta.actions.blocked or { heads = {}, spawn = {} }
  local head, rest = words[1], table.concat(words, " ", 2)
  if blocked.heads[head] then return blocked.heads[head] end
  if head == "submap" and rest ~= "reset" then return blocked.submap end
  if head == "spawn" then
    for phrase, reason in pairs(blocked.spawn) do
      if string.find(rest, phrase, 1, true) then return reason end
    end
  end
  return nil
end

local function runButton(ctx, action)
  local reason = blockReason(ctx.store.meta, action)
  local view = ctx.view
  return kit.confirmButton(ctx, { key = "kb-run", text = view.kbRunning and "Running…" or "Run now",
                                  armedText = "Click again to run", glyph = "player-play", controlSize = "sm",
                                  enabled = reason == nil and not view.kbRunning,
                                  tooltip = reason or "Send this action to Umbriel once, to see what it does" },
    function()
      view.kbRunning = true
      ctx.render()
      ctx.helper.call("run-action", { action = action }, function(err)
        view.kbRunning = false
        if err then ctx.flash(err.error, "error") else ctx.flash("Sent “" .. action .. "” to Umbriel.", "info") end
        ctx.render()
      end)
    end)
end

local function normalizeKey(key) return string.lower((string.gsub(noctalia.string.trim(key), "%s+", " "))) end

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

-- Choices for an action's first argument, by its placeholder in the catalog template: names the config defines
-- (and the connected outputs). Base lists are module constants so the store's cache can keep them.
local EFFECT_OFF, SUBMAP_RESET = { "off" }, { "reset" }
local function argumentKind(head, placeholder)
  if placeholder == "output" or placeholder == "destination" then return "output" end
  if placeholder == "pool" or placeholder == "scratchpad" or placeholder == "workspace" then return placeholder end
  if placeholder == "name" and head == "submap" then return "submap", SUBMAP_RESET end
  if placeholder == "name" and string.match(head, "^effect%-") then
    return "effect", string.match(head, "%-set$") and EFFECT_OFF or nil
  end
  return nil
end

-- A select that fills in the first argument of the action (keeping the rest), or nil when there is nothing
-- to offer.
local function argumentPicker(ctx, action, template, enabled, onPick)
  local head, rest = string.match(template or "", "^(%S+)%s+(.*)$")
  local placeholder = rest and string.match(rest, "^%[?<([%w-]+)>")
  if not placeholder then return nil end
  local kind, base = argumentKind(head, placeholder)
  if not kind then return nil end
  local known = ctx.store.namedChoices(kind, base, kind == "output" and ctx.liveOutputs() or nil)
  if #known == 0 then return nil end
  local words = {}
  for word in string.gmatch(action or "", "%S+") do table.insert(words, word) end
  local current = words[2] and not string.match(words[2], "^%-") and words[2] or nil
  local choices, options, selected = known, { "Choose " .. placeholder .. "…" }, 0
  for i, choice in ipairs(choices) do
    table.insert(options, choice)
    if choice == current then selected = i end
  end
  if current and selected == 0 then  -- a name the config doesn't define (yet) is still shown as chosen
    choices = { table.unpack(known) }
    table.insert(choices, current)
    table.insert(options, current .. " (not defined here)")
    selected = #choices
  end
  return kit.optionRow("kb-arg", "<" .. placeholder .. ">", ui.select({
    key = "kb-arg-select", options = options, selectedIndex = selected, width = 220, controlSize = "sm",
    enabled = enabled, onChange = function(value)
      local choice = choices[tonumber(value) or 0]
      if not choice then return end
      if current then words[2] = choice else table.insert(words, 2, choice) end
      onPick(table.concat(words, " "))
    end }))
end

local function conflict(store, key, index)
  local wanted = normalizeKey(key)
  if wanted == "" then return nil end
  for i, row in ipairs(store.keybinds.rows) do
    if i ~= index and normalizeKey(row.key) == wanted then return row.key end
  end
  return nil
end

-- Whether a group of that name exists (and says so).
local function groupTaken(ctx, name)
  for _, other in ipairs(ctx.store.keybinds.groups) do
    if other == name then ctx.flash("That group already exists.", "warning"); return true end
  end
  return false
end

local GAP = 8        -- the list's spacing; between rows it is an insertion zone while sorting is possible
local SLOP = 32      -- drag-only reach of a gap: about half a row, so the nearest gap follows the pointer

local function gapZone(key, accepts, value, height)
  return ui.dropZone({ key = key, accepts = { accepts }, value = value, onDrop = "onDrop", height = height,
                       expandOnDrag = true, hitSlop = SLOP })
end

local function grip(key, dragType, payload, ancestors, tooltip)
  return ui.dragSource({ key = key, dragType = dragType, payload = payload, previewAncestor = ancestors,
                         liftFromLayout = true, tooltip = tooltip, width = 20, height = 24, align = "center",
                         justify = "center" },
                       { ui.glyph({ name = "grip-vertical", size = 16, color = kit.MUTED }) })
end

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
  -- Sorting needs every row of a group on screen: a gap between filtered rows would be ambiguous.
  local sortable = filter == ""
  if sortable then
    ctx.dropHandler = function(payload, value) order.drop(ctx, payload, value) end
  elseif #store.keybinds.rows > 1 then
    table.insert(content, kit.muted("Clear the filter to reorder shortcuts and groups."))
  end
  local groups = {}
  for _, name in ipairs(store.keybinds.groups) do table.insert(groups, name) end
  table.insert(groups, "")
  view.kbCollapsed = view.kbCollapsed or {}
  local others = store.state and store.state.keybinds.other or {}
  for position, group in ipairs(groups) do
    local groupIndex = position < #groups and position or 0
    local groupRef = "g|" .. groupIndex .. "|" .. group
    local name = group == "" and "Ungrouped" or group
    local collapsed = view.kbCollapsed[name] and filter == ""
    local rows, count = {}, 0
    for index, row in ipairs(store.keybinds.rows) do
      local inGroup = (row.group or "") == group
      if inGroup and (filter == "" or string.find(string.lower(row.key .. " " .. row.action), filter, 1, true)) then
        count = count + 1
        if not collapsed then
          local desc = describe(store.meta, row.action)
          local badges = {}
          if row.locked then table.insert(badges, ui.glyph({ name = "lock", size = 14, color = kit.MUTED })) end
          local open = function() ctx.go({ name = "keybind", index = index }) end
          local ref = "r|" .. index .. "|" .. row.key
          if sortable then table.insert(rows, gapZone("kbgap-" .. index, "kbrow", ref, GAP)) end
          table.insert(rows, kit.navRow({ key = "kb-" .. index .. "-" .. row.key, title = row.key,
            subtitle = row.action .. (desc and ("  ·  " .. desc) or ""), badges = badges, onClick = open,
            leading = sortable and (row.locked and ui.box({ width = 20 })
              or grip("kbgrip-" .. index, "kbrow", ref, 1, "Drag to move this shortcut")) or nil }))
        end
      end
    end
    -- An empty group, and Ungrouped once groups exist, stay visible while sorting: they are drop targets.
    local shown = count > 0 or (filter == "" and (group ~= "" or (sortable and #groups > 1)))
    if shown then
      local headerChildren = {}
      if sortable then  -- Ungrouped stays last: a blank in place of the grip keeps the headers aligned
        table.insert(headerChildren, group == "" and ui.box({ width = 20 })
          or grip("kbggrip-" .. groupIndex, "kbgroup", groupRef, 2, "Drag to reorder this group"))
      end
      table.insert(headerChildren, ui.glyph({ name = collapsed and "chevron-right" or "chevron-down", size = 14,
                                              color = kit.MUTED }))
      table.insert(headerChildren, kit.section(name .. "  ·  " .. count, "kbgl-" .. name))
      local children = { ui.row({ key = "kbg-" .. name, gap = 8, align = "center", onClick = function()
        view.kbCollapsed[name] = not view.kbCollapsed[name]
        ctx.render()
      end }, headerChildren) }
      for _, row in ipairs(rows) do table.insert(children, row) end
      local key = groupIndex .. "-" .. name
      if sortable then
        if not collapsed and count > 0 then table.insert(children, gapZone("kbgend-" .. key, "kbrow", groupRef, 4)) end
        table.insert(content, gapZone("kbggap-" .. key, "kbgroup", groupRef, 4))
        -- the whole group takes rows (appended) and groups (placed before it)
        table.insert(content, ui.dropZone({ key = "kbgroup-" .. key, accepts = { "kbrow", "kbgroup" }, value = groupRef,
                                            onDrop = "onDrop", gap = 0 }, children))
      else
        table.insert(content, ui.column({ key = "kbgroup-" .. key, gap = GAP }, children))
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
                   if groupTaken(ctx, text) then return end
                   store.keybinds.groups[index] = text
                   for _, row in ipairs(store.keybinds.rows) do if row.group == group then row.group = text end end
                   store.keybindsChanged()
                   ctx.render()
                 end }),
      -- the keyboard way to reorder groups (dragging is pointer-only)
      ui.button({ key = "grp-up-" .. index, glyph = "arrow-up", variant = "ghost", controlSize = "sm",
                  tooltip = "Move group up", enabled = index > 1, onClick = function()
                    order.moveGroup(store.keybinds, index, index - 1)
                    store.keybindsChanged()
                    ctx.render()
                  end }),
      ui.button({ key = "grp-down-" .. index, glyph = "arrow-down", variant = "ghost", controlSize = "sm",
                  tooltip = "Move group down", enabled = index < #store.keybinds.groups, onClick = function()
                    order.moveGroup(store.keybinds, index + 1, index)
                    store.keybindsChanged()
                    ctx.render()
                  end }),
      ui.button({ glyph = "trash", variant = "ghost", controlSize = "sm",
                  tooltip = "Delete group (its shortcuts move to Ungrouped)", onClick = function()
                    table.remove(store.keybinds.groups, index)
                    for _, row in ipairs(store.keybinds.rows) do if row.group == group then row.group = "" end end
                    store.keybindsChanged()
                    ctx.render()
                  end }),
    }))
  end
  table.insert(content, ui.row({ key = "grp-add", gap = 6 }, {
    ui.input({ key = "grp-new-" .. ctx.gen("grp"), value = "", flexGrow = 1, controlSize = "sm",
               placeholder = "New group name (press Enter)",
               onSubmit = function(text)
                 text = noctalia.string.trim(text)
                 if text == "" then return end
                 if groupTaken(ctx, text) then return end
                 table.insert(store.keybinds.groups, text)
                 ctx.bump("grp")
                 store.keybindsChanged()
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
  local function edit(step) if not isNew then store.keybindsChanged(step and (step .. ":" .. route.index)) end end
  -- the keyboard way to reorder shortcuts (dragging is pointer-only): swap with the neighbor in the group
  local moves = {}
  if not isNew then
    local above, below
    for i, other in ipairs(store.keybinds.rows) do
      if (other.group or "") == (row.group or "") then
        if i < route.index then above = i elseif i > route.index and not below then below = i end
      end
    end
    local function move(from, before)
      order.moveRow(store.keybinds, from, row.group or "", before)
      store.keybindsChanged()
      for i, other in ipairs(store.keybinds.rows) do
        if other == row then ctx.replace({ name = "keybind", index = i }); return end
      end
    end
    moves = {
      ui.button({ key = "kb-up", glyph = "arrow-up", variant = "ghost", controlSize = "sm",
                  tooltip = "Move up in its group", enabled = not locked and above ~= nil,
                  onClick = function() move(route.index, above) end }),
      ui.button({ key = "kb-down", glyph = "arrow-down", variant = "ghost", controlSize = "sm",
                  tooltip = "Move down in its group", enabled = not locked and below ~= nil,
                  onClick = function() move(below, route.index) end }),
    }
  end
  local header = { kit.header(ctx, isNew and "New shortcut" or row.key, row.action, moves) }
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
        ctx.bump("kbkey")
        edit(); ctx.render()
      end }))
  end
  table.insert(chips, ui.input({ key = "kb-key-" .. ctx.gen("kbkey"), value = key, flexGrow = 1,
    controlSize = "sm", enabled = not locked, placeholder = "Key: Return, Q, F1, XF86AudioMute…",
    onChange = function(text)
      row.key = joinShortcut(mods, noctalia.string.trim(text))
      edit("key"); ctx.render()
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
      ui.input({ key = "kb-action-" .. ctx.gen("kbaction"), value = row.action, flexGrow = 1,
                 controlSize = "sm", enabled = not locked, placeholder = "e.g. spawn kitty",
                 onChange = function(text) row.action = text; edit("action"); ctx.render() end }),
      ui.button({ text = "Choose…", glyph = "list-search", controlSize = "sm", enabled = not locked,
                  onClick = function() ctx.go({ name = "actions", target = route.index }) end }),
    }),
  }
  if desc then table.insert(actionCard, kit.muted(desc, { maxLines = 3 })) end
  local args = argHelp(store.meta, template)
  if args ~= "" then table.insert(actionCard, kit.muted(args, { maxLines = 6 })) end
  local picker = argumentPicker(ctx, row.action, template, not locked, function(action)
    row.action = action
    edit("action")
    ctx.bump("kbaction")  -- the action box shows the new text
    ctx.render()
  end)
  if picker then table.insert(actionCard, picker) end
  table.insert(actionCard, ui.row({ key = "kb-run-row", gap = 8, align = "center" }, {
    runButton(ctx, noctalia.string.trim(row.action or "")),
    kit.muted(ctx.isApp and "Window actions act on the focused window: this one."
              or "Window actions act on the window behind this panel.", { flexGrow = 1, maxLines = 2 }),
  }))
  table.insert(content, kit.card({ key = "action" }, actionCard))
  -- options
  local optionRows = {}
  for _, option in ipairs(store.meta.actions.options) do
    local name, label = option[1], option[2]
    local value = row.opts[name]
    table.insert(optionRows, kit.optionRow("opt-" .. name, label,
      ui.select({ options = OPTION_CHOICES, selectedIndex = value == nil and 0 or (value and 1 or 2), width = 160,
                  controlSize = "sm", enabled = not locked, onChange = function(i)
                    i = tonumber(i) or 0
                    row.opts[name] = i == 1 and true or i == 2 and false or nil
                    edit(); ctx.render()
                  end })))
  end
  for _, item in ipairs({ { "cooldown_ms", "Cooldown (ms)", "0 = none" }, { "submap", "Submap", "Name (optional)" } }) do
    local name = item[1]
    table.insert(optionRows, kit.optionRow("opt-" .. name, item[2],
      ui.input({ key = "opt-in-" .. name, value = row.opts[name] ~= nil and tostring(row.opts[name]) or "", width = 160,
                 controlSize = "sm", enabled = not locked, placeholder = item[3], onChange = function(text)
                   text = noctalia.string.trim(text)
                   if name == "cooldown_ms" then
                     local number = tonumber(text)
                     row.opts[name] = (number and number > 0) and math.floor(number) or nil
                   else
                     row.opts[name] = text ~= "" and text or nil
                   end
                   edit("opt-" .. name)
                 end })))
  end
  local groupOptions, selected = { "Ungrouped" }, 0
  for index, group in ipairs(store.keybinds.groups) do
    table.insert(groupOptions, group)
    if group == row.group then selected = index end
  end
  table.insert(optionRows, kit.optionRow("opt-group", "Group",
    ui.select({ options = groupOptions, selectedIndex = selected, width = 160, controlSize = "sm",
                enabled = not locked, onChange = function(i)
                  i = tonumber(i) or 0
                  row.group = i == 0 and "" or store.keybinds.groups[i]
                  edit(); ctx.render()
                end })))
  if not isNew then
    table.insert(optionRows, kit.optionRow("opt-lock", "Locked (protect from edits here and in the app)",
      ui.toggle({ checked = locked, onChange = function(value) row.locked = value == "true"; edit(); ctx.render() end })))
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
        store.keybindsChanged()
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
        ctx.bump("kbkey")  -- the inputs keep their keys: show the copy's (empty) shortcut
        ctx.bump("kbaction")
        ctx.replace({ name = "keybind", index = nil })
      end }),
      ui.spacer({ flexGrow = 1 }),
      kit.confirmButton(ctx, { key = "kbdel", text = "Delete", armedText = "Click again to delete", glyph = "trash",
                               controlSize = "sm", enabled = not locked }, function()
        table.remove(store.keybinds.rows, route.index)
        store.keybindsChanged()
        ctx.back()
      end),
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
      if route.target then store.keybindsChanged() end
    end
    ctx.bump("kbaction")
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
