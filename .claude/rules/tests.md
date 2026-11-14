---
paths:
  - "tests/**/*.py"
---

# App tests (`tests/`)

- `unittest` only, offscreen Qt (`QT_QPA_PLATFORM=offscreen`); `python tools/check.py <test_file>` sets the environment and prints a one-line result.
- Which file:
  - `test_core.py`: import rules (no Qt; desktop modules without tomlkit), plugin copy drift, entries, keybind apply, paths, KDE scheme lookup.
  - `test_core_values.py`: field value conversion (`from_ui`/`to_ui`/`apply_value`), overridden checks, help coverage, keybind checks.
  - `test_core_files.py`: backups, cursor themes, KDE colors, `launch.child_env` (AppImage environment).
  - `test_host_runtime.py`: the new app without widgets. lupa runs `app.luau` against the real core, a temp config and a fake `umbriel` on `PATH`. Drive it through node props (`find`, `click`, `host.invoke`) and `ManualScheduler.drain()`; skipped without lupa.
  - `test_host_bridge.py`: `Bridge` messages, `QtScheduler` thread hand-off, glyph names used by the shared UI.
  - `test_app_render.py`: the real `AppWindow` offscreen; waits for DOM text, clicks DOM elements, asserts no JS console or Lua errors.
  - `test_app_icon.py`: `appicon` (icon, desktop entry) and `app.main` startup with Qt classes patched.
- Never read or write the real user config or data: patch `XDG_DATA_HOME`/`XDG_CONFIG_HOME` to temp dirs.
- Check that a new test fails without the fix before trusting it.
- Import Qt modules that bind `QApplication` at import (`app_window`) before patching `PySide6.QtWidgets.QApplication`, and import QtWebEngine before the first `QApplication`. After closing an `AppWindow`, flush `QEvent.Type.DeferredDelete` or QtWebEngine crashes at exit.
- Restore anything global you change (`app.styleSheet()`, `app.palette()`, locale, env) with `addCleanup`. Offscreen, send `Leave` before a non-hover baseline and don't assert text widths.
- Run the touched file first; broaden only when the change or failure needs it.
