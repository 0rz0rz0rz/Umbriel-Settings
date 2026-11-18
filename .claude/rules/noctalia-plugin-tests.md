---
paths:
  - "noctalia-plugin/tests/**/*"
---

# Plugin tests (`noctalia-plugin/tests/`)

`unittest`, temp XDG dirs, Lua mock `harness.lua`; never real config or a live shell. Add cases for changed behavior and check they can fail. One file: `python tools/check.py test_panel`; all: `check.py plugin host` (shared UI affects the app). Workflow: `add-test`.

| File | Covers |
| --- | --- |
| `support.py` | `HelperTestCase` (temp root with `data/`, `xdg-config/`, `share/` as XDG dirs; `reply`/`ok`/`fails`/`expect` run the helper; `call` = `reply` unless a test file redefines it) and `ConfigTestCase` (+ `CONFIG` at `self.config`, `FAKE_UMBRIEL` first on `PATH`) |
| `test_umbriel_settings.py` | helper commands (meta, read, preview, save, entries, maps, keybinds and locks, backups, config path, title-bar follow per config, malformed requests, `internal` replies) with the fake `umbriel`; `RealUmbrielTests` round-trips the stock config through the installed one (skipped without it) |
| `test_user_dirs.py`, `test_default_apps.py` | `desktop`/`desktop-save`/`extension` (timestamped backups, localized app names, `OnlyShowIn`/`NotShowIn`: set `LANG`/`XDG_CURRENT_DESKTOP` in `self.env`), the standalone launcher (real-`gio` test skipped without it) |
| `test_panel.py` | manifest checks; builds fixtures with the real helper, then runs under plain `lua` (skipped without it: report the skip): `panel_test.lua` (plugin layout flows), `state_test.lua` (drafts, discard, undo, reopening mid-request, inputs reused between entries), `app_test.lua` (app layout: sidebar, search, locale, Escape), `bar_test.lua`, `budget_test.lua` (every page on a large config, each callback ≤ 25 ms, mock JSON excluded) |

`harness.lua`, the Noctalia API mock: JSON codec, lexical `require` with private module globals, `H.start(name, app)`, `H.env` for `getenv`, helper replies per command in `replies`; a new API the UI uses goes here and into `python/umbriel_settings/host/api.py`. `H.clock` is what `noctalia.nowMs()` returns; `H.slide(node, value, wheel)` drags a slider (or sends a wheel notch); like Noctalia, `panel.render` calls the previous slider's `onChange` when a render changes its `value`; `H.drag(sourceKey, zoneKey)` drops a drag source on a zone (checks `accepts`); `H.walk(node, visit)`, `H.byKey(key)`, `H.input(pattern)` (input by key pattern), `H.goHome()` (Ctrl+F + empty search). It doesn't prove live rendering or Noctalia's own CPU accounting.
