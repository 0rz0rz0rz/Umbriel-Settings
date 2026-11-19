---
paths:
  - "noctalia-plugin/tests/**/*"
---

# Plugin tests (`noctalia-plugin/tests/`)

`unittest`, temp XDG dirs, Lua mock `harness.lua`; never real config or a live shell. Add cases for changed behavior and check they can fail. One file: `python tools/check.py test_panel`; all: `check.py plugin host` (shared UI affects the app). Workflow: `add-test`.

| File | Covers |
| --- | --- |
| `support.py` | `HelperTestCase` (temp root with `data/`, `xdg-config/`, `share/` as XDG dirs; `reply`/`ok`/`fails`/`expect` run the helper; `call` = `reply` unless a test file redefines it) and `ConfigTestCase` (+ `CONFIG` at `self.config`, `FAKE_UMBRIEL` first on `PATH`) |
| `test_umbriel_settings.py` | helper commands (meta, read, preview, save, entries, maps, keybinds and locks, backups, config path, title-bar follow per config, malformed requests, `internal` replies, `windows`/`layers`/`xkb`/`run-action`, `pick-file`/`pick-folder` with a fake `zenity` in `ChooserTests`) with the fake `umbriel` (answers `windows`/`layers`/`keyboard-layouts --json`; `msg` appends its argv to `$MSG_LOG`, fails with `$MSG_FAIL`); `RealUmbrielTests` round-trips the stock config through the installed one (skipped without it) |
| `test_user_dirs.py`, `test_default_apps.py` | `desktop`/`desktop-save`/`extension` (timestamped backups, localized app names, `OnlyShowIn`/`NotShowIn`: set `LANG`/`XDG_CURRENT_DESKTOP` in `self.env`), the standalone launcher (real-`gio` test skipped without it) |
| `test_panel.py` | manifest checks; builds fixtures with the real helper, then runs under plain `lua` (skipped without it: report the skip): `panel_test.lua` (plugin layout flows, incl. open-window/layer pickers, named curve/effect/output choices, action argument picker, Browse…, the XKB page, Run now), `state_test.lua` (drafts, discard, undo, reopening mid-request, inputs reused between entries), `app_test.lua` (app layout: sidebar, search, locale, Escape), `outputs_test.lua` (`arrange`/`displays` geometry, display tiles, drop/undo, default star, names, mode selects), `bar_test.lua`, `budget_test.lua` (every page on a large config plus XKB-sized lists and 300 open windows, each callback ≤ 25 ms, mock JSON excluded) |

`harness.lua`, the Noctalia API mock: JSON codec, lexical `require` with private module globals, `H.start(name, app)`, `H.env` for `getenv`, helper replies per command in `replies`; a new API the UI uses goes here and into `python/umbriel_settings/host/api.py`. `H.clock` is what `noctalia.nowMs()` returns; `H.slide(node, value, wheel)` drags a slider (or sends a wheel notch); like Noctalia, `panel.render` calls the previous slider's `onChange` when a render changes its `value`; `H.drag(sourceKey, zoneKey)` drops a drag source on a zone (checks `accepts`, and fails for a zone inside a drag source without `hitSlop`, which Noctalia never hits); `H.walk(node, visit)`, `H.byKey(key)`, `H.input(pattern)` (input by key pattern), `H.goHome()` (Ctrl+F + empty search). It doesn't prove live rendering or Noctalia's own CPU accounting.
