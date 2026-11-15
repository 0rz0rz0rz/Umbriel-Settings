---
paths:
  - "noctalia-plugin/tests/**/*"
---

# Plugin tests (`noctalia-plugin/tests/`)

See `test-noctalia-plugin`. `unittest`, temp XDG dirs, Lua mock `harness.lua`; never real config or a live shell. `test_panel.py` runs `panel_test.lua`, `state_test.lua`, `app_test.lua`, `bar_test.lua` under plain `lua` (skipped without it: report the skip). Add cases for changed behavior and check they can fail. Run `check.py plugin host` (shared UI affects the app).
