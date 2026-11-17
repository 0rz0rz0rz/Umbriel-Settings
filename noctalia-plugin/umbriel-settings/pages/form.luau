-- Settings pages: groups as an accordion (one open at a time keeps renders small), rows from ui/fields.
local kit = require("../ui/kit.luau")
local fields = require("../ui/fields.luau")
local titlebar = require("../lib/titlebar.luau")

local M = {}

-- KDE color buttons for title-bar colors. On the followable backgrounds they also show without a readable qt6ct
-- scheme when Noctalia is installed, because following uses Noctalia's palette roles, not the scheme file.
local function kdeSources(ctx, path, follows)
  if string.sub(path, 1, 17) ~= "colors.title_bar." then return nil end
  ctx.loadKde()
  local kde = ctx.kde or { colors = {}, backgrounds = {} }
  local state = follows and titlebar.state(ctx) or nil
  local noctalia = state ~= nil and state.noctalia == true
  local sources = {}
  if kde.colors[path] or noctalia then
    table.insert(sources, { label = "KDE", source = "kde", hex = kde.colors[path],
                           tooltip = "the KDE window decoration colors" })
  end
  if kde.backgrounds[path] or noctalia then
    table.insert(sources, { label = "KDE header", source = "kde_header", hex = kde.backgrounds[path],
                           tooltip = "the KDE header background" })
  end
  return #sources > 0 and sources or nil
end

function M.pageFieldSpec(ctx, fid)
  local store = ctx.store
  local field = store.meta.fields[fid]
  local value, set = store.value(fid)
  local changed = store.isChanged(fid)
  local follows = field.opacity and field.kind == "color"  -- title-bar backgrounds can follow Noctalia
  return {
    key = "f:" .. fid, field = field, value = value, set = set, changed = changed,
    onSet = function(v)
      store.setField(fid, v)
      if follows and titlebar.following(ctx, fid) then titlebar.follow(ctx, fid, nil) end  -- a fixed color stops following
    end,
    onUnset = field.opt and function() store.unsetField(fid) end or nil,
    onRevert = changed and function() store.revertField(fid) end or nil,
    diagnostic = ctx.diagnostics and ctx.diagnostics[fid] or nil,
    kdeColors = kdeSources(ctx, field.path, follows),
    follow = follows and titlebar.following(ctx, fid) or nil,
    onFollow = follows and function(source, opacity) titlebar.follow(ctx, fid, source, opacity) end or nil,
  }
end

-- groups: { { title, help, fields = { ids } } }; spec(fid) builds the row spec; counts(fids) -> changed, customized
function M.groups(ctx, pageKey, groups, spec, counts, defaultOpen)
  local view = ctx.view
  if view.expanded[pageKey] == nil then
    view.expanded[pageKey] = defaultOpen or (not ctx.isApp and groups[1] and groups[1].title) or false
  end
  local open = view.expanded[pageKey]
  local onlyCustomized = view.onlyCustomized
  local content = {}
  for _, group in ipairs(groups) do
    local changed, customized = counts(group.fields)
    local isOpen = open == group.title
    local badges = {}
    if changed > 0 then table.insert(badges, kit.badge(changed .. " unsaved", "primary", "gc-" .. group.title)) end
    if customized > 0 then
      table.insert(badges, kit.badge(customized .. " customized", "secondary", "go-" .. group.title))
    end
    if not onlyCustomized or customized > 0 or changed > 0 then
      if group.restart then
        table.insert(badges, 1, ui.glyph({ key = "gr-" .. group.title, name = "refresh-alert", size = 14,
                                           color = "tertiary", tooltip = "Takes effect after restarting Umbriel" }))
      end
      table.insert(content, kit.navRow({
        key = "group-" .. group.title, title = group.title, subtitle = group.help,
        bold = true, badges = badges, trailing = isOpen and "chevron-up" or "chevron-down",
        fill = isOpen and "surface_container_high" or "surface_container",
        onClick = function()
          view.expanded[pageKey] = (not isOpen) and group.title or false
          ctx.render()
        end,
      }))
    end
    if isOpen then
      local rows = {}
      local shown = 0
      for _, fid in ipairs(group.fields) do
        local row = spec(fid)
        if not onlyCustomized or row.changed or (row.set and ctx.store.differs(row.field, row.value)) then
          if shown > 0 then
            table.insert(rows, ui.separator({ key = "sep-" .. fid, thickness = 1, opacity = 0.5 }))
          end
          table.insert(rows, fields.row(ctx, row))
          shown = shown + 1
        end
      end
      if shown == 0 then table.insert(rows, kit.muted("No customized settings in this group.")) end
      table.insert(content, ui.column({ key = "group-body-" .. group.title, gap = 2, paddingH = 4 }, rows))
    end
  end
  if #content == 0 then
    table.insert(content, kit.empty("No settings on this page differ from their defaults.", "filter"))
  end
  return content
end

function M.onlyCustomizedToggle(ctx)
  return ui.row({ key = "only", gap = 6, align = "center", tooltip = "Show only settings that differ from the default" }, {
    kit.muted("Only customized"),
    ui.toggle({ checked = ctx.view.onlyCustomized == true, onChange = function(value)
      ctx.view.onlyCustomized = value == "true"
      ctx.render()
    end }),
  })
end

function M.render(ctx, route)
  local store = ctx.store
  local page = store.meta.pages[route.page]
  if route.group and not route.opened then
    ctx.view.expanded[route.page] = route.group
    route.opened = true
  end
  local header = { kit.header(ctx, route.page, page.help, { M.onlyCustomizedToggle(ctx) }) }
  if not store.state then return { header = header, content = { kit.empty("Loading config…", "loader") } } end
  local content = M.groups(ctx, route.page, page.groups, function(fid) return M.pageFieldSpec(ctx, fid) end,
    store.groupCounts)
  return { header = header, content = content }
end

return M
