---
name: add-test
description: "Use when writing or fixing a unit test for this repo: core, app host (lupa, web view), the Noctalia plugin, the shared Luau UI (panel and app layouts) or the umbriel_settings.py helper: which file to use, the shared fixtures, and how to run a single test file."
---

# Add a headless test

Which file covers what, the shared fixtures and the Qt pitfalls: `.claude/rules/tests.md` (`tests/`) and `.claude/rules/noctalia-plugin-tests.md` (`noctalia-plugin/tests/`); they load with the test files.

1. Pick the layer:
   - Qt-free logic in `umbriel_core` → `tests/test_core*.py` (no `QApplication`).
   - Helper commands and desktop files → `noctalia-plugin/tests/test_umbriel_settings.py`, `test_user_dirs.py`, `test_default_apps.py` (`support.HelperTestCase`/`DesktopTestCase`/`ConfigTestCase`).
   - Shared Luau UI flows → the Lua scripts `test_panel.py` runs (`panel_test.lua` plugin layout, `state_test.lua` drafts/discard/undo/redo/reopening, `app_test.lua` app layout, `outputs_test.lua` displays and Try; long polls and timers are held: `H.liveChange`, `H.hold`/`H.release`), driven through node props (`onClick`, `onChange`) found by key or text, asserting on texts; and/or `tests/test_host_runtime.py`, which runs `app.luau` through lupa with the real core (`self.find`, `self.click`, `self.host.invoke(node["props"]["onChange"], value)`, `self.settle()`; `new_app(data_dir)` restarts on the same files; swap `api._helpers[path]` to fake a crashing helper).
   - The rendered web page (DOM, focus, JS errors, clicks through the bridge) → `tests/test_app_render.py` (about 1 s per window). Bridge, scheduler, glyph names → `test_host_bridge.py`; icon, desktop entry, startup → `test_app_icon.py`.
2. `unittest` only, temporary paths and `XDG_*` dirs from the fixtures; never the real `~/.config`, `~/.local/share` or the live Noctalia session.
3. Make sure the test catches the regression: revert the fix, see it fail, restore the fix.
4. Run one file with `python tools/check.py test_<area>` (tests/ or noctalia-plugin/tests/); one test with `-k <test_name>` (fails when nothing matches).
