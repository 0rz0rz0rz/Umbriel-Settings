---
paths:
  - "noctalia-plugin/**/*"
---

# Shared Luau UI, plugin, helper (`noctalia-plugin/umbriel-settings/`)

Noctalia loads `panel.luau`/`bar.luau`, the app (lupa) loads `app.luau`; `lib/ ui/ pages/ umbriel_settings.py` serve both → verify `plugin host`.

| File | Notes |
| --- | --- |
| `plugin.toml`, `bar.luau` | ID `0rz0rz0rz/umbriel-settings` (dir = ID suffix), panel ID `folders` (legacy, keep), API 43 (Noctalia ≥ 5.4). Bar dot while state `umbriel.pending` > 0; setting `display` = `icon`/`icon_text`/`text` (`translations/en.json`); setting `icon` = one of 11 Tabler glyphs (list in `bar.luau`, `plugin.toml`, `en.json`; names must exist in Noctalia's `tabler.json`) |
| `panel.luau`, `app.luau` | Layout + entry globals only (`onOpen onClose onFrameTick onKey onMenu`; app adds `onExternalChange`). App options via global `APP` (`isApp appVersion initialConfig validateDefault rebuildDefault`) |
| `lib/shell.luau` | `shell.create(layout, options)` → `ctx, handlers`; `ctx.render/renderSoon/go/replace/back/home/openPage/flash/reload/switchConfig/loadDesktop/loadSearchIndex/loadKde`; routes in `body()`; publishes `umbriel.pending`/`umbriel.config`. Failed meta load → **Try again** (`loadMeta`); `onExternalChange` mid-reload sets `ctx.changedDuringLoad` → re-read |
| `lib/helper.luau` | JSON request/response files in `pluginDataDir()/run/`; stdout only `{ok,error,code}`; generation guard drops stale callbacks; crash → last stderr line |
| `lib/store.luau` | Field changes by id; entry/map ops replayed by the helper; `draft.json` holds config edits (per path) and desktop edits (`store.desktopDraft` until `loadDesktop`; dropped if the file's revision changed) |
| `lib/search.luau` | Lower-cased text from `search.json` |
| `lib/titlebar.luau` + `umbriel_core/titlebar_theme.py` | KDE/KDE header buttons + opacity on `colors.title_bar.background(_unfocused)` → Noctalia user template `umbriel_titlebar` with one `# config: <path>` block per config; `post_hook` = `titlebar_apply.py <rendered>` (stdlib, copied to `~/.config/umbriel-settings/`; old `<rendered> <config>` still works) writes into each config (Noctalia's umbriel template keeps `noctalia.toml` last, so an include can't win). Color is queued as a normal edit; a fixed color stops following |
| `ui/fields.luau`, `ui/kit.luau` | Row per field kind; tri-state for optional bools without default; locale numbers (`M.number`, `M.parseNumber`; comma from `LC_ALL`/`LC_NUMERIC`/`LANG`). `kit.header` hides close when `ctx.isApp`; `kit.notice`, `kit.plural` |
| `ui/sidebar.luau` | App: search, Home, `meta.nav`, unsaved badges (`home.pageCounts`) |
| `pages/*.luau` | `home form entries maps keybinds desktop review about`; return `{header, content}` |
| `umbriel_settings.py` | `run(argv)` → stdout text (app calls in-process). Commands: `meta read preview save set-config backups backup-diff restore delete-backups desktop desktop-save extension outputs kde-colors pick-folder launch-app open-config set-editor about palette-template titlebar titlebar-follow` (titlebar ones per `config`). `meta` has schema coverage. Empty request may be `[]`. Unexpected exceptions → `{ok:false, code:"internal"}` |

Rules:

- Edit `python/umbriel_core/`, then `tools/sync_plugin_core.py`; never the copy. Desktop commands work without tomlkit.
- Field metadata (labels, kinds, defaults, ranges, choices, help, glyphs) only from `meta`; no field lists in Luau.
- 25 ms per callback (3 overruns disable the runtime): one open group per page, capped lists (search 40, apps 40, MIME 50), big JSON in its own `readFileAsync` callback, `ctx.renderSoon()` for bursts.
- Inputs are uncontrolled: stable keys, bump `ctx.view.gen[key]` to replace text. `ui.select` is zero-based. Toggles, sliders, selects, color pickers need their value every render. Never index a built node's `.children`.
- Context-menu `onActivate` names an entry global (handlers in `ctx.menuHandlers`); the app has no context menus, so every menu action needs a visible button.
- Syntax: Luau ∩ Lua 5.4/5.5 (checked by `luac -p` and `luau-compile --null`). `cond and nil or x` is always `x`. Glyphs must exist in Tabler (`test_host_bridge.py`). Icon-only buttons need a `tooltip` (accessible name).
- Helper only via `lib/helper.luau` (argv array, JSON files); never shell strings. The helper validates and answers `{ok:false,error,code}`.
- Keep unrelated content, MIME fallbacks, revision checks, validation, backups (`backups.snapshot_file`, newest 10), atomic writes (`paths.atomic_write`), symlink refusal.
- Check the Noctalia API of the target release first (local Noctalia git cache; old notes: `git show 588a1bf:'noctalia-plugin/Noctalia API'`).
