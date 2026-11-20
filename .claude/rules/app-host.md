---
paths:
  - "python/umbriel_settings/host/**/*"
  - "python/umbriel_settings/*.py"
  - "python/umbriel_core/noctalia_theme.py"
---

# App host (shared Luau UI in a web view)

Thin host: implements the Noctalia API subset, runs `app.luau` with lupa (Lua 5.4), draws each tree as HTML. UI behavior belongs in the Luau files.

| Module | Key symbols |
| --- | --- |
| `app.py` | `parse_args`, `app_options` (→ Lua `APP`), `check_schema`, `main` (`instance.claim` first: a second launch hands over and exits 0); `APP_NAME`/`__version__` in `__init__.py` |
| `instance.py` | Single instance: `QLocalServer` at `$XDG_RUNTIME_DIR/umbriel-settings-<uid>.sock`; `hand_over` sends `{config, token}` (`XDG_ACTIVATION_TOKEN`), `InstanceServer.activated` → `AppWindow.activate_from` → Lua `onRelaunch` (then drops `XDG_ACTIVATION_TOKEN` from `os.environ`: used up); `claim` asks and listens under a `flock` on `<socket>.lock` (Qt's `listen` replaces any socket file, so two launches at once would both open a window); stale sockets removed |
| `app_window.py` | `AppWindow` (`on_ready on_invoke on_key on_state on_external_change activate_from show_notice on_lua_error closeEvent`; Lua errors → status bar + Lua `onRecover`; watches `user-dirs.dirs`/`mimeapps.list` too (`desktop_files`, `on_desktop_change` → `onExternalChange("desktop")`); status bar only while a `notify` message shows; title `[*]`, close prompt, file watch, size saved to `window.json` via `load_window_state`/`save_window_state`), `Page` (logs JS errors; stays on `index.html`, no new windows; a terminated render process reloads the page, and `Bridge.ready` resends theme, glyphs and the last tree), `icon_file` |
| `appicon.py` | `create_app_icon` (`assets/icon.png`; missing or unreadable → warning + null icon, then no desktop entry), `install_desktop_icon` (per-user `.desktop`, `$APPIMAGE` aware; removes the pre-rename entry/icon) |
| `qt6ct_theme.py` | `Qt6ctThemeFollower`: Qt palette from the qt6ct KDE scheme (`kde.qt6ct_scheme_path`, `kde.read_scheme`) |
| `host/runtime.py` | `LuaHost` (`start call guard render invoke to_py/to_lua`), `BOOTSTRAP` (ui constructors, lexical `require`, private module env), `as_callback_arg`; sets `LC_NUMERIC=C` |
| `host/api.py` | `NoctaliaApi.globals()` (only what the shared Luau calls); `runAsync` (reads the Lua argv on the GUI thread) runs only `umbriel_settings.py`, in-process (`_helper`, `run(argv)`; exceptions → `exitCode 1` + traceback, callback always runs; anything else → 127); lanes: `SLOW_HELPER_COMMANDS` (ask the compositor) → `slow`, `LONG_HELPER_COMMANDS` (`wait-live`, `wait`) → `long`; `json_encode` (empty table → `[]`); `copyToClipboard(text, mime)` (Qt clipboard; False without a `QGuiApplication`); `fuzzy_score`; `writeFile` is atomic |
| `host/bridge.py` | `Bridge` (signals `renderTree themeCss glyphMap`; slots `ready invoke key`), `QtScheduler.background(work, done, on_error, lane="fast")` (`done` on the GUI thread; a raising `work` delivers `on_error(error)`, so callbacks never hang; `slow` = a separate 2-thread pool, `long` = a daemon thread per call, for long polls). Tests use `host_support.ManualScheduler` (same interface, records `lanes`) |
| `host/paths.py` | `shared_ui_dir()`: `$UMBRIEL_SETTINGS_UI_DIR` → bundled `ui_shared/` → checkout; `app_data_dir()`; `watch_with_parents(watcher, files, prune)` (files + folders, re-added after atomic replace; theme, qt6ct and desktop files) |
| `host/theme.py`, `umbriel_core/noctalia_theme.py` | Roles: Noctalia palette template → qt6ct KDE scheme → Qt palette; `shell_style()` (`font_family`, `corner_radius_scale`); `css_variables`; files watched |
| `host/web/dragdrop.js` | `ui.dragSource`/`ui.dropZone` like Noctalia (pointer events, 4 px threshold else the source's `onClick`, ghost of `previewAncestor`, `liftFromLayout`, zones with `hitSlop` first then deepest, never a zone inside a drag source without `hitSlop` (Noctalia can't hit it), zones in the dragged element stay targets like in Noctalia (only `accepts` rules them out), source dimmed to 28 % and ghost at 96 % like Noctalia, `expandOnDrag`, Escape cancels; a drag whose source a render replaced (pointerup/capture lost: window `pointerup`, `lostpointercapture`) is cancelled; pointerdown clears the pending tooltip; auto-scroll near `.scroll` edges); release → `invoke(onDrop, payload, value)` |
| `host/web/renderer.js`, `style.css`, `index.html` | CSP (local + `qrc:` only); keyed reconciler, one builder per `ui` kind the pages use (`UI_KINDS` in `runtime.py`; unused Noctalia kinds/props are left out); `.scroll` reserves its scrollbar gutter; inputs uncontrolled; `KEYS` chords (Ctrl+Z/Ctrl+Y/Ctrl+Shift+Z only outside text fields, Escape); `onKeyRecord` (app-only prop: while a `.key-record` container is shown, a capture-phase listener sends the next key press as an Umbriel shortcut, `""` for Esc); radii (`radius` props and `style.css`) are scaled by `--radius-scale`; `revealKey`; `onResize` (app-only prop, the app's pages set it only when `ctx.isApp`: a `ResizeObserver` calls it with the container's width/height on change, never 0×0 or while detached; removed elements' observers are disconnected; `.resize-watch` clips overflow); ARIA (icon-only buttons, clickable containers and drag sources with `onClick` named by `tooltip`; a drag source's click also on Enter/Space). Never read `host/web/fonts/` |

Rules:

- Lua functions in props → `{"$callback": "g<render>:cbN"}` (ids of the last 16 renders stay valid); strings name `on*` handlers the entry script defines. The Lua state has no `io`/`package`/`debug`/`require`/`load*`, like Luau. Callback args reach Lua as strings (`"true"`, `"2"`).
- `NoctaliaApi` signatures = Noctalia's; a new API also goes into `noctalia-plugin/tests/harness.lua`.
- Everything the app launches gets `child_env()` (restores host Python vars inside the AppImage).
- Visuals: `render_app.py` (edit-controls).
- The AppImage keeps QtWebEngine/QtWebChannel and bundles the UI as `umbriel_settings/ui_shared/`.
