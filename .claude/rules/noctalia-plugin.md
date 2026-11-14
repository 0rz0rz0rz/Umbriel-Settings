---
paths:
  - "noctalia-plugin/**/*"
---

# Shared Luau UI, Noctalia plugin and helper

`noctalia-plugin/umbriel-settings/` is the canonical home of the UI for **both** frontends: Noctalia loads `panel.luau`/`bar.luau`; the standalone app (lupa host) loads `app.luau`. Every change in `lib/`, `ui/`, `pages/` or `umbriel_settings.py` affects both, so verify with `python tools/check.py plugin host`.

| Need to change | File | Notes |
| --- | --- | --- |
| Identity, entries, API level, panel size/keys | `plugin.toml`, `bar.luau` | ID `0rz0rz0rz/umbriel-settings` (dir name = ID suffix), panel ID `folders`, API 43 (Noctalia ≥ 5.4.0). Bar dot while `noctalia.state` `umbriel.pending` > 0; bar `display` widget setting (`icon` default/`icon_text`/`text`, labels in `translations/en.json`) |
| Frontend layouts | `panel.luau` (single column), `app.luau` (sidebar + page) | Only layout + entry globals (`onOpen`, `onClose`, `onFrameTick`, `onKey`, `onMenu`; app adds `onExternalChange`). App options come from the host global `APP` (`isApp`, `appVersion`, `initialConfig`, `validateDefault`, `rebuildDefault`) |
| Routing, ctx, loading, save bar, keys, menus | `lib/shell.luau` | `shell.create(layout, options)` → `ctx, handlers`. `ctx.render/renderSoon/go/replace/back/home/openPage/flash/reload/switchConfig/loadDesktop/loadSearchIndex/loadKde`; routes dispatch in `body()`. Publishes `umbriel.pending` / `umbriel.config` |
| Helper calls | `lib/helper.luau` | Request/response JSON files under `pluginDataDir()/run/`; stdout only carries `{ok,error,code}`; generation guard drops stale callbacks |
| Unsaved edits, change set, drafts | `lib/store.luau` | Field changes by id; entry/map ops replayed in order by the helper; `draft.json` survives restarts |
| Search | `lib/search.luau` | Lower-cased text from the helper's `search.json` |
| Title bar follows Noctalia | `lib/titlebar.luau`, `umbriel_core/titlebar_theme.py` | KDE/KDE header buttons and the opacity slider on `colors.title_bar.background(_unfocused)` write a Noctalia user template (`umbriel_titlebar`); its `post_hook` runs `umbriel_core/titlebar_apply.py` (stdlib, copied to `~/.config/umbriel-settings/`) to write the colors into the config itself, because Noctalia's built-in umbriel template always moves `noctalia.toml` last in the includes. The UI queues the color as a normal edit; a fixed color stops following |
| Rows and controls per field kind | `ui/fields.luau`, `ui/kit.luau` | Tri-state for optional bools without default; locale-aware numbers (`M.number`, `M.parseNumber`, decimal comma from `LC_ALL`/`LC_NUMERIC`/`LANG`). `kit.header` hides close when `ctx.isApp`; `kit.plural` |
| App sidebar | `ui/sidebar.luau` | Search, Home, `meta.nav` sections, unsaved badges from `home.pageCounts` |
| Pages | `pages/*.luau` | `home`, `form` (accordion groups), `entries`, `maps`, `keybinds`, `desktop`, `review` (review/save, backups), `about` (version, schema coverage, editor command, app-only palette template). Pages return `{header, content}` |
| Helper commands | `umbriel_settings.py` | `run(argv)` returns stdout text (the app calls it in-process). `meta`, `read`, `preview`, `save`, `set-config`, `backups`, `backup-diff`, `restore`, `delete-backups`, `desktop`, `desktop-save`, `extension`, `outputs`, `kde-colors`, `pick-folder`, `launch-app`, `open-config` (saved editor command or `xdg-open`), `set-editor`, `about`, `palette-template`, `titlebar`, `titlebar-follow`. `meta` carries schema coverage (`schema.missing`/`schema.stale`). An empty request may arrive as `[]` (empty Lua table) |

Rules:

- The helper uses the shared `umbriel_core` (Python 3.11+, tomlkit). Never edit `umbriel-settings/umbriel_core/`; edit `python/umbriel_core/` and run `tools/sync_plugin_core.py`. Desktop commands must keep working without tomlkit.
- Field metadata (labels, kinds, defaults, ranges, choices, help, page glyphs) comes from the helper's `meta`; never hard-code field lists in Luau.
- 25 ms per-callback CPU budget (3 overruns disable the runtime): one open group per page (~60 rows), capped lists (search 40, apps 40, MIME types 50), big JSON decoded in its own `readFileAsync` callback, `ctx.renderSoon()` for bursts.
- Inputs are uncontrolled after creation: keep keys stable, bump `ctx.view.gen[key]` to replace text. `ui.select` is zero-based. Toggles, sliders, selects and color pickers need their value on every render.
- Never index `.children` of a built `ui.*` node (Noctalia nodes are opaque); build child lists first.
- Context-menu `onActivate` must name an entry global (module globals are private); register handlers in `ctx.menuHandlers`. The app host has no context menus yet (`openContextMenu` returns false), so every menu action needs a visible alternative.
- Syntax must parse as Luau and Lua 5.4/5.5: no `continue`, `+=`, type annotations or backtick strings. Glyph names must exist in Tabler (`tests/test_host_bridge.py` checks them against the app's icon map).
- Call the helper only through `lib/helper.luau` (argv array, JSON files); never build shell commands from user input. The helper validates input and reports `{ok:false,error,code}`.
- Preserve unrelated file content and MIME fallbacks, revision checks, validation before writing, backups, atomic writes and symlink refusal.
- Check the exact Noctalia release API before using newer features (the local Noctalia git cache; older notes: `git show 588a1bf:'noctalia-plugin/Noctalia API'`). Don't change the live Noctalia session or user config to run tests.
