-- The standalone app's left navigation: search, Home, and the pages grouped like the plugin's home cards.
local kit = require("./kit.luau")
local home = require("../pages/home.luau")

local M = {}

M.WIDTH = 270

-- The tooltip names the item when a narrow window shows the sidebar as icons only (style.css).
local function navItem(ctx, key, glyph, title, active, badge, onClick)
  local children = {
    ui.glyph({ name = glyph or "settings", size = 18, color = active and "primary" or kit.MUTED }),
    ui.label({ text = title, fontSize = 13, fontWeight = active and "bold" or nil, flexGrow = 1, maxLines = 1 }),
  }
  if badge then table.insert(children, badge) end
  return ui.row({ key = key, gap = 10, align = "center", paddingH = 10, paddingV = 7, radius = 10,
                  fill = active and "primary_container" or nil, tooltip = title, onClick = onClick }, children)
end

-- Pinned below the page list: tools that sit on top of Home.
local TOOLS = {
  { "customized", "adjustments-check", "Customized" },
  { "backups", "history", "Backups" },
  { "about", "info-circle", "About" },
}

function M.render(ctx)
  local store, view = ctx.store, ctx.view
  local root = ctx.rootRoute()
  local top = ctx.route().name
  local tool = nil
  for _, item in ipairs(TOOLS) do
    if top == item[1] then tool = item[1] end
  end
  local active = tool and "" or (root.name == "home" and "Home" or root.page or "")
  local items = {
    ui.label({ key = "app-title", text = "Umbriel Settings", fontSize = 16, fontWeight = "bold" }),
    kit.searchBox(ctx, { controlSize = "sm", placeholder = "Search  (Ctrl+F)",
                         onChange = function(text)
                           view.query = text
                           -- results show on Home, also when a page (About, Review) sits on top of it
                           if root.name ~= "home" or ctx.canGoBack() then ctx.home() else ctx.render() end
                         end }),
    navItem(ctx, "nav-home", "home", "Home", active == "Home", nil, function()
      view.query = ""
      view.gen.search = (view.gen.search or 0) + 1
      ctx.home()
    end),
  }
  if store.meta then
    for _, section in ipairs(store.meta.nav) do
      table.insert(items, ui.row({ key = "navsec-" .. section.title, paddingH = 10, paddingV = 2 }, {
        kit.section(section.title),
      }))
      for _, name in ipairs(section.pages) do
        local page = store.meta.pages[name]
        if page then
          local changed = store.state and home.pageChanges(store, name) or 0
          local badge = changed > 0 and kit.badge(tostring(changed), "primary", "navb-" .. name) or nil
          table.insert(items, navItem(ctx, "nav-" .. name, page.glyph, name, active == name, badge, function()
            ctx.openPage(name)
          end))
        end
      end
    end
  end
  local tools = { ui.separator({ key = "sidebar-sep", thickness = 1, spacing = 4, opacity = 0.6 }) }
  for _, item in ipairs(TOOLS) do
    table.insert(tools, navItem(ctx, "nav-tool-" .. item[1], item[2], item[3], tool == item[1], nil, function()
      if tool == item[1] then return end
      ctx.home()
      ctx.go({ name = item[1] })
    end))
  end
  return ui.column({ key = "sidebar", width = M.WIDTH, gap = 2, padding = 10, radius = 12,
                     fill = "surface_container_low" }, {
    ui.scroll({ key = "sidebar-scroll", gap = 2, flexGrow = 1 }, items),
    ui.column({ key = "sidebar-tools", gap = 2 }, tools),
  })
end

return M
