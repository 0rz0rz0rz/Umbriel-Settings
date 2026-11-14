---
name: add-test
description: "Use when writing or fixing a unit test for this repo: core, app host (lupa, web view) or plugin tests, which file to use, and how to run a single test file."
---

# Add a headless test

- Pick the layer first:
  - Qt-free logic in `umbriel_core` → `tests/test_core*.py` (no `QApplication`).
  - Shared Luau UI or helper flows → `noctalia-plugin/tests/` (see `test-noctalia-plugin`) and/or `tests/test_host_runtime.py`, which runs `app.luau` through lupa with the real core. Its `setUp` creates a temp config, temp `XDG_*` dirs and a fake `umbriel`; use `self.find(predicate)`, `self.click(text)`, `self.host.invoke(node["props"]["onChange"], value)` and `self.settle()` (drains `ManualScheduler`, asserts no Lua errors).
  - Python↔JS bridge, scheduler, glyph names → `tests/test_host_bridge.py`.
  - The rendered web page (DOM, JS errors, clicks through the bridge) → `tests/test_app_render.py` (slow: about 1 s per window).
  - App icon, desktop entry, startup wiring → `tests/test_app_icon.py`.
- Core tests by area: `test_core.py` (import rules, entries, keybind apply, layout rebuild, paths), `test_core_values.py` (value conversion, overridden checks, help coverage, keybind checks), `test_core_files.py` (backups and snapshots, atomic writes, cursor themes, KDE colors, Noctalia templates, title-bar follow/apply, launch environment).
- App host: `test_host_runtime.py` has `new_app(data_dir)` for a restart on the same files (drafts) and swaps `api._helpers[path]` to fake a crashing helper.
- `unittest` style (no pytest), temporary paths; never touch the real `~/.config` or `~/.local/share` (patch `XDG_*`).
- Qt order: import `app_window` (QtWebEngine) before any `QApplication` exists and before patching `PySide6.QtWidgets.QApplication`. Close windows with `deleteLater()` plus `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)`, or QtWebEngine segfaults at exit.
- Check that a new test catches the regression: temporarily revert the fix, see the test fail, then restore it.
- Run one file: `python tools/check.py test_<area>` (compact). One test: `cd python && QT_QPA_PLATFORM=offscreen PYTHONPATH=.:../tests python -m unittest test_<area> -k <test_name>`.
