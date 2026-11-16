---
paths:
  - "noctalia-plugin/umbriel-settings/**/*"
---

# Shared Luau UI, plugin, helper (`noctalia-plugin/umbriel-settings/`)

Noctalia loads `panel.luau`/`bar.luau`, the app (lupa) loads `app.luau`; `lib/ ui/ pages/ umbriel_settings.py` serve both → verify `plugin host`.

| File | Notes |
| --- | --- |
| `plugin.toml`, `bar.luau` | ID `0rz0rz0rz/umbriel-settings` (dir = ID suffix), panel ID `folders` (legacy, keep), API 43 (Noctalia ≥ 5.4). Bar dot while state `umbriel.pending` > 0 (always laid out, hidden with `opacity`: a widget that changes width moves the anchored panel); setting `display` = `icon`/`icon_text`/`text` (`translations/en.json`); setting `icon` = one of 11 Tabler glyphs (list in `bar.luau`, `plugin.toml`, `en.json`; names must exist in Noctalia's `tabler.json`) |
| `panel.luau`, `app.luau` | Layout + entry globals only (`onOpen onClose onFrameTick onKey onMenu`; app adds `onExternalChange onRelaunch`). Chords: `ctrl+f ctrl+s ctrl+z alt+Left` (`capture_keys`), app also `Escape` (Noctalia keeps Esc for closing). App options via global `APP` (`isApp appVersion initialConfig validateDefault rebuildDefault`) |
| `lib/shell.luau` | `shell.create(layout, options)` → `ctx, handlers`; `ctx.render/renderSoon/go/replace/back/home/openPage/flash/undo/reload/switchConfig/loadDesktop/loadSearchIndex/loadKde`; routes in `body()`; save bar always present once a config is loaded (quiet + disabled when nothing is pending: a bar that comes and goes toggles the page's scrollbar, and plugins can't reserve its gutter); publishes `umbriel.pending`/`umbriel.config`. Failed meta load → **Try again** (`loadMeta`); `onExternalChange` mid-reload sets `ctx.changedDuringLoad` → re-read; `onRelaunch(path)` (second app launch) opens that config unless there are config edits |
| `lib/helper.luau` | `python3 -Xpycache_prefix=<data>/pycache`; JSON request/response files in `pluginDataDir()/run/`; stdout only `{ok,error,code}`; generation guard drops stale callbacks; crash → last stderr line |
| `lib/store.luau` | Field changes by id; entry/map ops replayed by the helper; `history` + `undo()` (cap 50; repeats of one value are one step; entry/map undo replays the remaining ops on the snapshot; keybind pages call `keybindsChanged(step)` after editing in place, desktop pages `setDesktop(part, key, value)`); cleared by `load` (new snapshot), `discardAll`, draft restore, save; `draft.json` holds config edits (per path) and desktop edits (`store.desktopDraft` until `loadDesktop`; dropped if the file's revision changed) |
| `lib/search.luau` | Lower-cased text from `search.json` |
| `lib/titlebar.luau` + `umbriel_core/titlebar_theme.py` | KDE/KDE header buttons + opacity on `colors.title_bar.background(_unfocused)` → Noctalia user template `umbriel_titlebar` with one `# config: <path>` block per config; `post_hook` = `titlebar_apply.py <rendered>` (stdlib, copied to `~/.config/umbriel-settings/`; old `<rendered> <config>` still works) writes into each config (Noctalia's umbriel template keeps `noctalia.toml` last, so an include can't win). Color is queued as a normal edit; a fixed color stops following |
| `ui/fields.luau`, `ui/kit.luau` | Row per field kind; tri-state for optional bools without default; locale numbers (`M.number`, `M.parseNumber`; comma from `LC_ALL`/`LC_NUMERIC`/`LANG`). `kit.header` hides close when `ctx.isApp`; `kit.notice`, `kit.plural` |
| `ui/sidebar.luau` | App: search, Home, `meta.nav`, unsaved badges (`home.pageChanges`: changes only, cheap on every render) |
| `pages/*.luau` | `home form entries maps keybinds desktop review about`; return `{header, content}`; `home.renderCustomized` = route `customized` (overridden page fields, capped 40) |
| `umbriel_settings.py` | `run(argv)` → stdout text (app calls in-process). Commands: `meta read preview save set-config backups backup-diff restore delete-backups desktop desktop-save extension outputs kde-colors pick-folder launch-app open-config set-editor about palette-template titlebar titlebar-follow` (titlebar ones per `config`). `meta` has schema coverage. `WRITE_COMMANDS` run under `paths.write_lock(data_dir)` (flock; timeout → `code:"busy"`). Empty request may be `[]`. Unexpected exceptions → `{ok:false, code:"internal"}` |

Rules:

- Edit `python/umbriel_core/`, then `tools/sync_plugin_core.py`; never the copy. Desktop commands work without tomlkit.
- Field metadata (labels, kinds, defaults, ranges, choices, help, glyphs) only from `meta`; no field lists in Luau.
- 25 ms per callback (3 overruns disable the runtime): one open group per page, capped lists (search 40, apps 40, MIME 50), big JSON in its own `readFileAsync` callback, `ctx.renderSoon()` for bursts.
- Inputs are uncontrolled: stable keys, bump `ctx.view.gen[key]` to replace text; `ctx.resetInputs()` replaces all of them (discard, save), `ctx.discardAll()` = store discard + diagnostics + inputs. Never assign `view.gen = {}`. Keys of per-entry inputs include the entry index. `onOpen` clears busy flags of requests the close dropped. `ui.select` is zero-based. Toggles, sliders, selects, color pickers need their value every render. Sliders go through `fields.luau` `slider()`: preview on `onChange`, commit on `onDragEnd`; in the panel a single change + immediate `onDragEnd` within 3 steps (a wheel notch; Noctalia offers plugins no `wheelAdjustEnabled`) is dropped and the slider rebuilt (key generation). Never index a built node's `.children`.
- Context-menu `onActivate` names an entry global (handlers in `ctx.menuHandlers`); the app has no context menus, so every menu action needs a visible button.
- Syntax: Luau ∩ Lua 5.4/5.5 (checked by `luac -p` and `luau-compile --null`). `cond and nil or x` is always `x`. Glyphs must exist in Tabler (`test_host_bridge.py`). Icon-only buttons need a `tooltip` (accessible name).
- Helper only via `lib/helper.luau` (argv array, JSON files); never shell strings. The helper validates and answers `{ok:false,error,code}`.
- Store edits go through the store setters (undo records them); never assign `store.desktop` values or keybind rows without `setDesktop`/`keybindsChanged`.
- Keep unrelated content, MIME fallbacks, revision checks, write lock, validation, backups (`backups.snapshot_file`, newest 10), atomic writes (`paths.atomic_write`), symlink refusal.
- Check the Noctalia API of the target release first (local Noctalia git cache; old notes: `git show 588a1bf:'noctalia-plugin/Noctalia API'`).
