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

# Standalone app host (shared Luau UI in a web view)

The app is a thin host that implements the Noctalia API the shared UI uses, runs `app.luau` with lupa (Lua 5.4) and draws each rendered tree as HTML. UI behavior belongs in the shared Luau files, not here.

| Need to change | Module | Key symbols |
| --- | --- | --- |
| CLI and startup | `app.py` | `parse_args`, `app_options` (→ Lua `APP`), `check_schema`, `main`. `APP_NAME`/`__version__` live in `__init__.py` |
| Window, title `[*]`, close prompt, file watch, icons | `app_window.py` | `AppWindow` (`on_ready`, `on_invoke`, `on_key`, `on_state`, `on_external_change`, `closeEvent`), `Page` (records JS console errors, prints them to stderr), `icon_file` |
| App icon and desktop entry | `appicon.py` | `create_app_icon` (assets/icon.jpg, embedded fallback), `install_desktop_icon` (per-user `.desktop`, `$APPIMAGE` aware) |
| Qt palette from qt6ct | `qt6ct_theme.py` | `Qt6ctThemeFollower` (follows the qt6ct KDE scheme; the web theme reads the palette) |
| Lua runtime | `host/runtime.py` | `LuaHost` (`start`, `call`, `guard`, `render`, `invoke`, `to_py`/`to_lua`), `BOOTSTRAP` (ui constructors, lexical `require`, private module env), `as_callback_arg`. Sets `LC_NUMERIC=C` so Lua number formatting works under Qt |
| Noctalia API subset | `host/api.py` | `NoctaliaApi.globals()`; `runAsync` runs `umbriel_settings.py` in-process (`_helper`, `run(argv)`), others as subprocesses with `umbriel_core.launch.child_env()`; `json_encode` (empty table → `[]`); `ManualScheduler` (tests), `ThreadedScheduler`, `fuzzy_score` |
| Python ↔ JS channel | `host/bridge.py` | `Bridge` (signals `renderTree`, `themeCss`, `glyphMap`; slots `ready`, `invoke`, `key`), `QtScheduler` (results back on the GUI thread) |
| Where the UI lives | `host/paths.py` | `shared_ui_dir()`: `$UMBRIEL_SETTINGS_UI_DIR` → bundled `ui_shared/` (AppImage) → checkout; `app_data_dir()` |
| Theme | `host/theme.py`, `umbriel_core/noctalia_theme.py` | Roles from Noctalia palette template → qt6ct KDE scheme → Qt palette; `shell_style()` (Noctalia `font_family`, `corner_radius_scale`); `css_variables`; files are watched |
| Rendering | `host/web/renderer.js`, `style.css`, `index.html` | Keyed DOM reconciler, one builder per `ui` kind; inputs uncontrolled; `revealKey` scrolls into view. Tabler font + `tabler-map.json` in `host/web/fonts/` (never read them) |

Rules:

- Lua functions in props become `{"$callback": "cbN"}` ids, rebuilt every render; strings name entry globals. Callback args reach Lua as strings like Noctalia's (`"true"`, `"2"`).
- Keep `NoctaliaApi` signatures identical to Noctalia's; if the shared UI needs a new API, add it here and to the Lua mock in `noctalia-plugin/tests/harness.lua`.
- Programs started from the app (helper launches, `runAsync` commands) must get `child_env()`: inside the AppImage it restores the host's Python variables.
- Tests: `tests/test_host_runtime.py` (lupa, no widgets: real core + temp config + fake `umbriel`), `tests/test_host_bridge.py` (bridge, scheduler, glyph names), `tests/test_app_render.py` (real web view, DOM clicks, no JS errors), `tests/test_app_icon.py`. Run `python tools/check.py host`.
- Look at changes with `.claude/skills/edit-controls/render_app.py` (offscreen PNGs).
- The AppImage must keep QtWebEngine/QtWebChannel and bundle the shared UI as `umbriel_settings/ui_shared/` (`appimage/build-appimage.sh`).
