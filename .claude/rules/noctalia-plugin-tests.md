---
paths:
  - "noctalia-plugin/tests/**/*"
---

# Plugin and shared-UI tests (`noctalia-plugin/tests/`)

- Follow `test-noctalia-plugin`: `unittest`, temporary XDG directories, the shared Lua mock in `harness.lua`; never real user config or a live shell.
- `test_panel.py` builds fixtures with the real helper, then runs `panel_test.lua` (plugin layout), `app_test.lua` (app layout, sidebar, locale) and `bar_test.lua` under plain `lua`; skipped without `lua`, so report a skip rather than claiming UI callbacks were tested.
- Shared-UI changes affect the app too: also run `python tools/check.py host`.
- Add focused cases for changed behavior: helper errors, config preservation, backups, external changes, panel callbacks. Check that a new assertion can fail.
- Run with `python tools/check.py plugin` (tests + `luac` + lint, compact output).
