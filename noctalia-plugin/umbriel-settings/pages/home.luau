-- Home: search everything, or pick a page from cards grouped like the app's sidebar.
local kit = require("../ui/kit.luau")
local search = require("../lib/search.luau")
local fields = require("../ui/fields.luau")

local M = {}

function M.pageCounts(store, name)
  local page = store.meta.pages[name]
  local changed, customized = 0, 0
  if page.kind == "form" then
    for _, group in ipairs(page.groups) do
      local c, o = store.groupCounts(group.fields)
      changed, customized = changed + c, customized + o
    end
  elseif page.kind == "entries" then
    for _, eid in ipairs(page.editors) do
      changed = changed + store.entryOpCount(eid)
      customized = customized + #store.entryItems(eid)
    end
  elseif page.kind == "map" then
    for _, eid in ipairs(page.maps) do
      changed = changed + store.mapOpCount(eid)
      customized = customized + #store.mapRows(eid)
    end
  elseif page.kind == "keybinds" then
    changed = store.keybindsDirty and 1 or 0
    customized = store.keybinds and #store.keybinds.rows or 0
  end
  return changed, customized
end

-- Only the unsaved changes of a page: the app's sidebar shows them on every render, so this skips the
-- per-field default comparison pageCounts needs for "customized".
function M.pageChanges(store, name)
  local page = store.meta.pages[name]
  local changed = 0
  if page.kind == "form" then
    if next(store.fieldChanges) == nil then return 0 end
    for _, group in ipairs(page.groups) do
      for _, fid in ipairs(group.fields) do
        if store.fieldChanges[fid] then changed = changed + 1 end
      end
    end
  elseif page.kind == "entries" then
    for _, eid in ipairs(page.editors) do changed = changed + store.entryOpCount(eid) end
  elseif page.kind == "map" then
    for _, eid in ipairs(page.maps) do changed = changed + store.mapOpCount(eid) end
  elseif page.kind == "keybinds" then
    changed = store.keybindsDirty and 1 or 0
  end
  return changed
end

local function countLabel(kind, count)
  if kind == "form" then return kit.plural(count, "customized setting") end
  if kind == "keybinds" then return kit.plural(count, "shortcut") end
  if kind == "map" then return kit.plural(count, "entry", "entries") end
  if kind == "entries" then return kit.plural(count, "entry", "entries") end
  return nil
end

local function pageCard(ctx, name)
  local store = ctx.store
  local page = store.meta.pages[name]
  local changed, customized = M.pageCounts(store, name)
  local badges = {}
  if changed > 0 then table.insert(badges, kit.badge(changed .. " unsaved", "primary", "b-" .. name)) end
  local summary = countLabel(page.kind, customized)
  return ui.row({ key = "card-" .. name, gap = 12, align = "center", padding = 12, radius = 12, flexGrow = 1,
                  fill = "surface_container", tooltip = page.help, onClick = function() ctx.openPage(name) end }, {
    ui.glyph({ name = page.glyph or "settings", size = 22, color = "primary" }),
    ui.column({ gap = 2, flexGrow = 1 }, {
      ui.label({ text = name, fontSize = 14, fontWeight = "bold", maxLines = 1 }),
      kit.muted(summary or page.help or "", { maxLines = 1 }),
    }),
    ui.row({ gap = 4 }, badges),
  })
end

local function results(ctx, query)
  local store = ctx.store
  if not store.searchIndex then
    ctx.loadSearchIndex()
    return { kit.empty("Preparing search…", "search") }
  end
  local hits, cut = search.run(store, query)
  if #hits == 0 then return { kit.empty("Nothing matches “" .. query .. "”.", "search") } end
  local rows = {}
  for index, hit in ipairs(hits) do
    local key = "hit-" .. index
    if hit.kind == "page" then
      local page = store.meta.pages[hit.page]
      table.insert(rows, kit.navRow({ key = key, glyph = page.glyph, title = hit.page, subtitle = page.help,
                                      bold = true, onClick = function() ctx.openPage(hit.page) end }))
    elseif hit.kind == "field" then
      local field = store.meta.fields[hit.id]
      local where = search.locate(store.meta, hit.id)
      local subtitle = where and (where.page .. (where.group and (" › " .. where.group) or "")) or field.path
      local value, set = store.value(hit.id)
      local badges = {}
      if store.isChanged(hit.id) then table.insert(badges, kit.badge("changed", "primary", key .. "-c")) end
      if where and not where.editor and set then
        table.insert(badges, kit.badge(fields.format(field, value), "secondary", key .. "-v"))
      end
      table.insert(rows, kit.navRow({ key = key, glyph = "adjustments", title = field.label, subtitle = subtitle,
        badges = badges, tooltip = field.help, onClick = function()
          if where and where.editor then
            ctx.openPage(where.page)
          elseif where then
            ctx.openPage(where.page, { group = where.group, focus = hit.id, reveal = "f:" .. hit.id })
          end
        end }))
    elseif hit.kind == "entry" then
      local editor = store.meta.editors[hit.editor]
      table.insert(rows, kit.navRow({ key = key, glyph = store.meta.pages[editor.page].glyph, title = hit.title,
        subtitle = editor.page, onClick = function()
          ctx.go({ name = "entry", editor = hit.editor, index = hit.index })
        end }))
    else
      local row = store.keybinds.rows[hit.index]
      table.insert(rows, kit.navRow({ key = key, glyph = "command", title = row.key, subtitle = row.action,
        onClick = function() ctx.go({ name = "keybind", index = hit.index }) end }))
    end
  end
  if cut then table.insert(rows, kit.muted("Showing the best 40 matches. Type more to narrow the search.")) end
  return rows
end

local function footer(ctx)
  local store, view = ctx.store, ctx.view
  local path = store.state and store.state.path or ""
  local rows = {
    kit.section("Config file"),
    ui.row({ key = "path-row", gap = 8, align = "center" }, {
      ui.input({ key = "path:" .. tostring(view.gen.path or 0), value = path, flexGrow = 1, controlSize = "sm",
                 placeholder = "~/.config/umbriel/config.toml",
                 onChange = function(text) view.pathDraft = text end,
                 onSubmit = function(text) view.pathDraft = text; ctx.switchConfig() end }),
      ui.button({ text = "Open", controlSize = "sm", tooltip = "Load this config file", enabled = not ctx.loading.config,
                  onClick = function() ctx.switchConfig() end }),
      ui.button({ glyph = "refresh", variant = "ghost", controlSize = "sm", tooltip = "Reload from disk",
                  enabled = not ctx.loading.config, onClick = function() ctx.reload() end }),
    }),
  }
  local tools = {
    ui.button({ text = "Backups", glyph = "history", controlSize = "sm", variant = "outline",
                onClick = function() ctx.go({ name = "backups" }) end }),
    ui.button({ text = "Edit file", glyph = "file-text", controlSize = "sm", variant = "outline",
                tooltip = "Open the config in your editor (set under About)",
                onClick = function()
                  ctx.helper.call("open-config", { config = path }, function(err)
                    if err then ctx.flash(err.error, "error") end
                  end)
                end }),
  }
  if not ctx.isApp then  -- the app is the standalone app
    table.insert(tools, ui.button({ text = "Standalone app", glyph = "external-link", controlSize = "sm",
      variant = "outline", onClick = function()
        ctx.helper.call("launch-app", {}, function(err)
          if err then ctx.flash(err.error, "error") else panel.close() end
        end)
      end }))
  end
  table.insert(tools, ui.button({ text = "About", glyph = "info-circle", controlSize = "sm", variant = "ghost",
                                  onClick = function() ctx.go({ name = "about" }) end }))
  table.insert(rows, ui.row({ key = "tools", gap = 8 }, tools))
  return rows
end

function M.render(ctx)
  local store, view = ctx.store, ctx.view
  local subtitle = store.state and store.state.path or (ctx.loading.config and "Loading config…" or "")
  local header = { kit.header(ctx, ctx.isApp and "Home" or "Umbriel Settings", subtitle) }
  -- the app's sidebar has the search box; the panel shows it here
  if not ctx.isApp then
    table.insert(header, ui.input({
      key = "search:" .. tostring(view.gen.search or 0), value = view.query, focus = true,
      placeholder = "Search settings, rules and shortcuts  (Ctrl+F)",
      onChange = function(text)
        view.query = text
        ctx.render()
      end,
    }))
  end
  local content = {}
  if ctx.configError then
    table.insert(content, kit.notice(ctx.configError, "error", nil, "config-error"))
  end
  local query = noctalia.string.trim(view.query or "")
  if query ~= "" then
    for _, row in ipairs(results(ctx, query)) do table.insert(content, row) end
    return { header = header, content = content }
  end
  if not store.state then
    if not ctx.configError then table.insert(content, kit.empty("Loading config…", "loader")) end
  else
    for _, section in ipairs(store.meta.nav) do
      table.insert(content, kit.section(section.title))
      local row = {}
      for _, name in ipairs(section.pages) do
        if store.meta.pages[name] then
          table.insert(row, pageCard(ctx, name))
          if #row == 2 then
            table.insert(content, ui.row({ key = "cards-" .. name, gap = 10 }, row))
            row = {}
          end
        end
      end
      if #row == 1 then
        table.insert(row, ui.column({ flexGrow = 1, padding = 12 }, {}))  -- same padding as a card so both columns match
        table.insert(content, ui.row({ key = "cards-end-" .. section.title, gap = 10 }, row))
      end
    end
  end
  for _, item in ipairs(footer(ctx)) do table.insert(content, item) end
  return { header = header, content = content }
end

return M
