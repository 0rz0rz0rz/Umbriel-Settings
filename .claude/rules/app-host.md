---
paths:
  - "python/umbriel_settings/host/**/*"
  - "python/umbriel_settings/app.py"
  - "python/umbriel_settings/app_window.py"
  - "python/umbriel_settings/appicon.py"
  - "python/umbriel_settings/qt6ct_theme.py"
  - "python/umbriel_core/noctalia_theme.py"
  - "tests/test_host_*.py"
  - "tests/test_app_*.py"
---

# App host (shared Luau UI in a web view)

Thin host: implements the Noctalia API subset, runs `app.luau` with lupa (Lua 5.4), draws each tree as HTML. UI behavior belongs in the Luau files.

| Module | Key symbols |
| --- | --- |
| `app.py` | `parse_args`, `app_options` (→ Lua `APP`), `check_schema`, `main`; `APP_NAME`/`__version__` in `__init__.py` |
| `app_window.py` | `AppWindow` (`on_ready on_invoke on_key on_state on_external_change closeEvent`; title `[*]`, close prompt, file watch, size saved to `window.json` via `load_window_state`/`save_window_state`), `Page` (logs JS errors; stays on `index.html`, no new windows), `icon_file` |
| `appicon.py` | `create_app_icon` (assets/icon.png → .jpg → .jpeg, embedded 128 px PNG fallback), `install_desktop_icon` (per-user `.desktop`, `$APPIMAGE` aware) |
| `qt6ct_theme.py` | `Qt6ctThemeFollower`: Qt palette from the qt6ct KDE scheme (`kde.read_scheme`) |
| `host/runtime.py` | `LuaHost` (`start call guard render invoke to_py/to_lua`), `BOOTSTRAP` (ui constructors, lexical `require`, private module env), `as_callback_arg`; sets `LC_NUMERIC=C` |
| `host/api.py` | `NoctaliaApi.globals()`; `runAsync`: helper in-process (`_helper`, `run(argv)`; exceptions → `exitCode 1` + traceback, callback always runs), other commands as subprocesses with `launch.child_env()`; `json_encode` (empty table → `[]`); `ManualScheduler` (tests), `ThreadedScheduler`, `fuzzy_score` |
| `host/bridge.py` | `Bridge` (signals `renderTree themeCss glyphMap`; slots `ready invoke key`), `QtScheduler` (results on the GUI thread) |
| `host/paths.py` | `shared_ui_dir()`: `$UMBRIEL_SETTINGS_UI_DIR` → bundled `ui_shared/` → checkout; `app_data_dir()` |
| `host/theme.py`, `umbriel_core/noctalia_theme.py` | Roles: Noctalia palette template → qt6ct KDE scheme → Qt palette; `shell_style()` (`font_family`, `corner_radius_scale`); `css_variables`; files watched |
| `host/web/renderer.js`, `style.css`, `index.html` | CSP (local + `qrc:` only); keyed reconciler, one builder per `ui` kind; inputs uncontrolled; `revealKey`; ARIA (icon-only buttons and clickable containers named by `tooltip`). Never read `host/web/fonts/` |

Rules:

- Lua functions in props → `{"$callback": "cbN"}` (rebuilt each render); strings name entry globals. Callback args reach Lua as strings (`"true"`, `"2"`).
- `NoctaliaApi` signatures = Noctalia's; a new API also goes into `noctalia-plugin/tests/harness.lua`.
- Everything the app launches gets `child_env()` (restores host Python vars inside the AppImage).
- Tests: `test_host_runtime.py` (lupa + real core + fake `umbriel`), `test_host_bridge.py`, `test_app_render.py` (real web view), `test_app_icon.py` → `check.py host`. Visuals: `render_app.py`.
- The AppImage keeps QtWebEngine/QtWebChannel and bundles the UI as `umbriel_settings/ui_shared/`.
