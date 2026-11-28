--!nonstrict
-- Icon themes from the Pling store, route `iconStore` (the page itself: ui/store.luau), from the Icon theme page's
-- **Browse icon themes…**. Nothing is downloaded here: **Open page** opens the theme's store page in the browser
-- (helper `open-store-page`, xdg-open; the URL is built from the item's number), where the user downloads it and
-- extracts it into the icon folder (**Browse folder**), then picks it after Refresh.
local cursor = require("../ui/cursor.luau")
local storePage = require("../ui/store.luau")

local M = {}

local function openPage(ctx, row)
  ctx.helper.call("open-store-page", { id = row.id }, function(err)
    if err then
      ctx.flash(err.error, "warning")
    else
      ctx.flash("Opened the page of " .. row.name .. " in your browser.", "info")
    end
    ctx.render()
  end)
end

local SPEC = {
  stateKey = "iconStore", prefix = "istore", command = "icon-store",
  title = "Icon themes", subtitle = "Community uploads from the Pling store (gnome-look.org, store.kde.org)",
  header = function(ctx)
    return { ui.button({ key = "istore-folder", text = "Browse folder", glyph = "folder-open", controlSize = "sm",
                         variant = "outline", tooltip = "Open the folder to extract icon themes into",
                         onClick = function() cursor.openFolder(ctx) end }) }
  end,
  introTitle = "Browse icon themes", browseText = "Browse icon themes",
  intro = "About 1200 icon themes people uploaded to the Pling store. Nothing is downloaded here: Open page "
    .. "shows a theme's store page in your browser, where you download it. Uploads aren't reviewed by anyone. "
    .. "Extract a theme folder (the one holding index.theme) into ~/.local/share/icons/, then pick it on the "
    .. "Icon theme page. The list and previews come from api.pling.com and images.pling.com once you ask.",
  hint = "Extract a downloaded theme into ~/.local/share/icons/ (Browse folder), then pick it on the Icon theme "
    .. "page.",
  rowParts = function(ctx, s, row)
    return {}, { ui.button({ key = "istore-open-" .. row.id, text = "Open page", glyph = "external-link",
                             variant = "outline", controlSize = "sm",
                             tooltip = "Open " .. row.name .. " on pling.com in your browser",
                             onClick = function() openPage(ctx, row) end }) }
  end,
}

function M.render(ctx) return storePage.render(ctx, SPEC) end

return M
