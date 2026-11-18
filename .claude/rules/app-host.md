---
paths:
  - "python/umbriel_settings/host/**/*"
  - "python/umbriel_settings/*.py"
  - "python/umbriel_core/noctalia_theme.py"
  - "tests/test_host_*.py"
  - "tests/test_app_*.py"
  - "tests/host_support.py"
---

# App host (shared Luau UI in a web view)

Thin host: implements the Noctalia API subset, runs `app.luau` with lupa (Lua 5.4), draws each tree as HTML. UI behavior belongs in the Luau files.

| Module | Key symbols |
| --- | --- |
| `app.py` | `parse_args`, `app_options` (→ Lua `APP`), `check_schema`, `main` (`instance.claim` first: a second launch hands over and exits 0); `APP_NAME`/`__version__` in `__init__.py` |
| `instance.py` | Single instance: `QLocalServer` at `$XDG_RUNTIME_DIR/umbriel-settings-<uid>.sock`; `hand_over` sends `{config, token}` (`XDG_ACTIVATION_TOKEN`), `InstanceServer.activated` → `AppWindow.activate_from` → Lua `onRelaunch`; stale sockets removed |
| `app_window.py` | `AppWindow` (`on_ready on_invoke on_key on_state on_external_change activate_from show_notice on_lua_error closeEvent`; Lua errors → status bar + Lua `onRecover`; watches `user-dirs.dirs`/`mimeapps.list` too (`desktop_files`, `on_desktop_change` → `onExternalChange("desktop")`); status bar only while a `notify` message shows; title `[*]`, close prompt, file watch, size saved to `window.json` via `load_window_state`/`save_window_state`), `Page` (logs JS errors; stays on `index.html`, no new windows), `icon_file` |
| `appicon.py` | `create_app_icon` (assets/icon.png → .jpg → .jpeg, embedded 128 px PNG fallback), `install_desktop_icon` (per-user `.desktop`, `$APPIMAGE` aware) |
| `qt6ct_theme.py` | `Qt6ctThemeFollower`: Qt palette from the qt6ct KDE scheme (`kde.qt6ct_scheme_path`, `kde.read_scheme`) |
| `host/runtime.py` | `LuaHost` (`start call guard render invoke to_py/to_lua`), `BOOTSTRAP` (ui constructors, lexical `require`, private module env), `as_callback_arg`; sets `LC_NUMERIC=C` |
| `host/api.py` | `NoctaliaApi.globals()`; `runAsync`: helper in-process (`_helper`, `run(argv)`; exceptions → `exitCode 1` + traceback, callback always runs), other commands as subprocesses with `launch.child_env()`; `json_encode` (empty table → `[]`); `ManualScheduler` (tests), `fuzzy_score`; `writeFile` is atomic |
| `host/bridge.py` | `Bridge` (signals `renderTree themeCss glyphMap`; slots `ready invoke key`), `QtScheduler` (results on the GUI thread; `background(work, done, on_error, slow=False)`: a raising `work` delivers `on_error(error)`, so callbacks never hang; `slow` = separate 2-thread pool for subprocesses and `SLOW_HELPER_COMMANDS` like `pick-folder`; `ManualScheduler` matches) |
| `host/paths.py` | `shared_ui_dir()`: `$UMBRIEL_SETTINGS_UI_DIR` → bundled `ui_shared/` → checkout; `app_data_dir()`; `watch_with_parents(watcher, files, prune)` (files + folders, re-added after atomic replace; theme, qt6ct and desktop files) |
| `host/theme.py`, `umbriel_core/noctalia_theme.py` | Roles: Noctalia palette template → qt6ct KDE scheme → Qt palette; `shell_style()` (`font_family`, `corner_radius_scale`); `css_variables`; files watched |
| `host/web/dragdrop.js` | `ui.dragSource`/`ui.dropZone` like Noctalia (pointer events, 4 px threshold else the source's `onClick`, ghost of `previewAncestor`, `liftFromLayout`, zones with `hitSlop` first then deepest, `expandOnDrag`, Escape cancels; auto-scroll near `.scroll` edges); release → `invoke(onDrop, payload, value)` |
| `host/web/renderer.js`, `style.css`, `index.html` | CSP (local + `qrc:` only); keyed reconciler, one builder per `ui` kind the pages use (`UI_KINDS` in `runtime.py`; unused Noctalia kinds/props are left out); `.scroll` reserves its scrollbar gutter; inputs uncontrolled; `KEYS` chords (Ctrl+Z only outside text fields, Escape); `revealKey`; ARIA (icon-only buttons and clickable containers named by `tooltip`). Never read `host/web/fonts/` |

Rules:

- Lua functions in props → `{"$callback": "g<render>:cbN"}` (ids of the last 16 renders stay valid); strings name `on*` handlers the entry script defines. The Lua state has no `io`/`package`/`debug`/`require`/`load*`, like Luau. Callback args reach Lua as strings (`"true"`, `"2"`).
- `NoctaliaApi` signatures = Noctalia's; a new API also goes into `noctalia-plugin/tests/harness.lua`.
- Everything the app launches gets `child_env()` (restores host Python vars inside the AppImage).
- Tests: `test_host_runtime.py` (lupa + real core + fake `umbriel` via `host_support.isolated_home`), `test_host_bridge.py`, `test_app_render.py` (real web view), `test_app_icon.py` → `check.py host`. Visuals: `render_app.py`.
- The AppImage keeps QtWebEngine/QtWebChannel and bundles the UI as `umbriel_settings/ui_shared/`.
