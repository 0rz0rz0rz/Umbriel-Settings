---
paths:
  - "tests/**/*.py"
---

# App tests (`tests/`)

- `unittest` only, offscreen Qt (`QT_QPA_PLATFORM=offscreen`); `python tools/check.py <test_file>` sets the environment and prints a one-line result.
- Which file:
  - `test_core.py`: Qt-free `umbriel_core` logic, the no-Qt/no-`state` import rule, the plugin copy drift check.
  - `test_host_runtime.py`: the new app without widgets. lupa runs `app.luau` against the real core, a temp config and a fake `umbriel` on `PATH`. Drive it through node props (`find`, `click`, `host.invoke`) and `ManualScheduler.drain()`; skipped without lupa.
  - `test_host_bridge.py`: `Bridge` messages, `QtScheduler` thread hand-off, glyph names used by the shared UI.
  - The rest cover the legacy Qt UI (`--legacy-ui`); see `add-test` for their patch targets. Don't extend them for new features.
- Never read or write the real user config or data: patch `XDG_DATA_HOME`/`XDG_CONFIG_HOME` to temp dirs (host tests) or patch `state.PATH` with `patch.object` (legacy tests).
- Check that a new test fails without the fix before trusting it.
- Restore anything global you change (`app.styleSheet()`, `app.palette()`, locale, env) with `addCleanup`. Offscreen, send `Leave` before a non-hover baseline and don't assert text widths.
- Run the touched file first; broaden only when the change or failure needs it.
