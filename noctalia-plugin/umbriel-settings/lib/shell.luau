-- Shared by both frontends: navigation stack, loading, notices, the save bar and key handling.
-- shell.create(layout, options) returns ctx and the handlers an entry script exposes as globals.
-- layout(ctx, parts) builds the outer tree from parts = { header, notices, content, saveBar, route }.
local helper = require("./helper.luau")
local store = require("./store.luau")
local kit = require("../ui/kit.luau")
local home = require("../pages/home.luau")
local form = require("../pages/form.luau")
local entries = require("../pages/entries.luau")
local maps = require("../pages/maps.luau")
local keybinds = require("../pages/keybinds.luau")
local desktop = require("../pages/desktop.luau")
local review = require("../pages/review.luau")
local about = require("../pages/about.luau")

local M = {}

function M.create(layout, options)
  options = options or {}
  local stack = { { name = "home" } }
  local view = { gen = {}, invalid = {}, custom = {}, help = {}, expanded = {}, query = "" }
  local loading = { meta = false, config = false, desktop = false }
  local notices = {}
  local draftChecked = false
  local firstLoad = true
  local ctx = { view = view, store = store, helper = helper, loading = loading, options = options,
                isApp = options.isApp == true, menuHandlers = {} }
  if options.rebuildDefault == false then store.rebuild = false end

  local function route() return stack[#stack] end
  ctx.route = route
  function ctx.rootRoute() return stack[1] end

  local function body(current)
    if not store.meta then
      return { header = { kit.header(ctx, "Umbriel Settings", "Loading settings…") },
               content = { ctx.loadError and kit.notice(ctx.loadError, "error") or kit.empty("Loading…", "loader") } }
    end
    local name = current.name
    if name == "home" then return home.render(ctx) end
    if name == "form" then return form.render(ctx, current) end
    if name == "entries" or name == "entry" or name == "outputs" then return entries.render(ctx, current) end
    if name == "map" then return maps.render(ctx, current) end
    if name == "keybinds" or name == "keybind" or name == "actions" then return keybinds.render(ctx, current) end
    if name == "folders" or name == "apps" or name == "appPicker" then return desktop.render(ctx, current) end
    if name == "about" then return about.render(ctx, current) end
    return review.render(ctx, current)
  end

  function ctx.render()
    local current = route()
    local parts = body(current)
    local noticeNodes = {}
    for index, notice in ipairs(notices) do
      table.insert(noticeNodes, kit.notice(notice.text, notice.kind, function()
        table.remove(notices, index)
        ctx.render()
      end, "flash-" .. index))
    end
    local content = ui.scroll({ key = "content-" .. #stack .. "-" .. current.name, gap = 10, flexGrow = 1,
                                revealKey = current.reveal }, parts.content or parts)
    local pending = store.pendingCount()
    local saveBar = nil
    if store.meta and pending > 0 and current.name ~= "review" then
      saveBar = ui.row({ key = "savebar", gap = 8, align = "center", padding = 10, radius = 12,
                         fill = "primary_container" }, {
        ui.glyph({ name = "pencil", size = 16, color = "primary" }),
        ui.label({ text = kit.plural(pending, "unsaved change"), fontSize = 13, flexGrow = 1 }),
        ui.button({ text = "Discard", variant = "ghost", controlSize = "sm", onClick = function()
          store.discardAll()
          view.gen = {}
          ctx.flash("All unsaved changes were discarded.", "info")
        end }),
        ui.button({ text = "Review & save", glyph = "device-floppy", variant = "primary", controlSize = "sm",
                    tooltip = "Ctrl+S", onClick = function() ctx.go({ name = "review" }) end }),
      })
    end
    panel.render(layout(ctx, { header = parts.header or {}, notices = noticeNodes, content = content,
                               saveBar = saveBar, route = current }))
    noctalia.state.set("umbriel.pending", pending)
    noctalia.state.set("umbriel.config", store.state and store.state.path or "")
  end

  -- Coalesce bursts (slider drags) into one render per frame.
  function ctx.renderSoon() panel.setNeedsFrameTick(true) end

  function ctx.go(next)
    table.insert(stack, next)
    notices = {}
    ctx.render()
  end
  function ctx.replace(next)
    stack[#stack] = next
    ctx.render()
  end
  function ctx.canGoBack() return #stack > 1 end
  function ctx.back()
    if #stack > 1 then table.remove(stack) end
    notices = {}
    ctx.render()
  end
  function ctx.home()
    stack = { { name = "home" } }
    notices = {}
    ctx.render()
  end

  function ctx.flash(text, kind)
    for _, notice in ipairs(notices) do
      if notice.text == text then ctx.render(); return end
    end
    table.insert(notices, { text = text, kind = kind or "info" })
    while #notices > 3 do table.remove(notices, 1) end
    ctx.render()
  end

  local function pageRoute(name, extra)
    local page = store.meta.pages[name]
    local kind = page and page.kind or "form"
    local next = { page = name }
    if kind == "form" then next.name = "form"
    elseif kind == "entries" then next.name = "entries"
    elseif kind == "map" then next.name = "map"
    elseif kind == "keybinds" then next.name = "keybinds"
    elseif kind == "userdirs" then next.name = "folders"
    else next.name = "apps" end
    for key, value in pairs(extra or {}) do next[key] = value end
    return next
  end

  -- Opens the page for a nav entry (form, entry list, map, keybinds, desktop). The app's sidebar opens
  -- pages as the root of the stack, so they have no back button.
  function ctx.openPage(name, extra)
    if ctx.isApp then
      stack = { pageRoute(name, extra) }
      notices = {}
      ctx.render()
    else
      ctx.go(pageRoute(name, extra))
    end
  end

  function ctx.swatches()
    local result = {}
    for _, role in ipairs({ "primary", "secondary", "tertiary", "error", "surface", "on_surface" }) do
      local color = noctalia.getColor and noctalia.getColor(role)
      if color then table.insert(result, color) end
    end
    return result
  end

  -- ---------------------------------------------------------------- loading
  -- path switches configs (and remembers the choice); without it the current config is re-read.
  function ctx.reload(path, remember)
    loading.config = true
    ctx.render()
    local request = {}
    if path then request.config = path elseif store.state then request.config = store.state.path end
    helper.call((path and remember ~= false) and "set-config" or "read", request, function(err, state)
      loading.config = false
      if err then
        ctx.configError = err.error
        ctx.render()
        return
      end
      ctx.configError = nil
      local note = store.load(state)
      if note then table.insert(notices, { text = note, kind = "warning" }) end
      if not draftChecked then
        draftChecked = true
        local restored = store.restoreDraft()
        if restored then table.insert(notices, { text = restored, kind = "info" }) end
      end
      ctx.render()
    end)
  end

  function ctx.switchConfig()
    local path = noctalia.string.trim(view.pathDraft or "")
    if path == "" or (store.state and path == store.state.path) then return end
    if store.hasConfigChanges() then
      ctx.flash("Save or discard your changes before opening another config.", "warning")
      return
    end
    ctx.reload(path)
  end

  function ctx.loadDesktop(force)
    if loading.desktop or (store.desktop and not force) then return end
    loading.desktop = true
    helper.call("desktop", {}, function(err, data)
      loading.desktop = false
      if err then
        ctx.desktopError = err.error
      else
        ctx.desktopError = nil
        store.loadDesktop(data)
      end
      ctx.render()
    end)
  end

  function ctx.loadSearchIndex()
    if store.searchIndex or loading.search or not ctx.searchPath then return end
    loading.search = true
    helper.readJson(ctx.searchPath, function(err, data)
      loading.search = false
      if err then ctx.flash(err.error, "error"); return end
      store.searchIndex = data
      ctx.render()
    end)
  end

  function ctx.loadKde()
    if ctx.kde ~= nil then return end
    ctx.kde = false
    helper.call("kde-colors", {}, function(err, data)
      ctx.kde = (not err and data.available) and data or false
      ctx.render()
    end)
  end

  local function loadMeta()
    if loading.meta then return end
    loading.meta = true
    local dataDir = noctalia.pluginDataDir()
    helper.call("meta", { out_dir = dataDir and (dataDir .. "/cache") or nil }, function(err, paths)
      if err then
        loading.meta = false
        ctx.loadError = err.error
        ctx.render()
        return
      end
      ctx.searchPath = paths.search
      helper.readJson(paths.meta, function(readError, meta)
        loading.meta = false
        if readError then ctx.loadError = readError.error; ctx.render(); return end
        store.meta = meta
        ctx.loadError = nil
        ctx.render()
        if firstLoad and options.initialConfig then ctx.reload(options.initialConfig, false) else ctx.reload() end
        firstLoad = false
        ctx.loadDesktop()
      end)
    end)
  end

  -- ---------------------------------------------------------------- entry points
  local handlers = {}

  function handlers.onOpen()
    helper.generation = helper.generation + 1
    loading.meta, loading.config, loading.desktop, loading.search = false, false, false, false
    notices = {}
    if not store.meta then
      loadMeta()
    else
      ctx.reload()
      if not store.desktopChanges() then ctx.loadDesktop(true) end
    end
    ctx.render()
  end

  function handlers.onClose()
    store.saveDraft()
    helper.generation = helper.generation + 1
  end

  function handlers.onFrameTick()
    panel.setNeedsFrameTick(false)
    ctx.render()
  end

  function handlers.onKey(chord, pressed)
    if not pressed or not store.meta then return end
    if chord == "ctrl+f" then
      stack = { { name = "home" } }
      view.gen.search = (view.gen.search or 0) + 1
      ctx.render()
    elseif chord == "ctrl+s" then
      if route().name ~= "review" and store.pendingCount() > 0 then ctx.go({ name = "review" }) end
    elseif chord == "alt+Left" then
      ctx.back()
    end
  end

  -- Context menus must call a global function of the entry script; entries forward it here.
  function handlers.onMenu(action, context)
    local handler = ctx.menuHandlers[tostring(context)]
    if handler then handler(action) end
  end

  -- The app re-reads the config when it changes on disk; unsaved edits are rebased by store.load.
  function handlers.onExternalChange()
    if store.meta and store.state and not loading.config then ctx.reload() end
  end

  return ctx, handlers
end

return M
