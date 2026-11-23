---
paths:
  - "tests/**/*.py"
---

# App tests (`tests/`)

`unittest`, offscreen Qt; run with `python tools/check.py <file> [-k name]`. The drift of the plugin's core copy is `check.py core`'s sync step, not a test. Patch `XDG_DATA_HOME`/`XDG_CONFIG_HOME`/`XDG_STATE_HOME` to temp dirs (and `NOCTALIA_STATE_HOME` to `""`). A new test must fail without its fix. Run the touched file first.

| File | Covers |
| --- | --- |
| `test_core.py` | import rules (no Qt; desktop modules without tomlkit), `test_versions_agree` (app/plugin version, targets, READMEs), `test_appimage_lock_matches_the_requirements`, entry names, keybind apply, layout rebuild (lossless, stable), paths, locked keybinds, schema coverage rules + speed bound, KDE lookup |
| `test_core_values.py` | `from_ui`/`to_ui`/`apply_value`, help coverage, keybind checks |
| `test_core_files.py` | backups/snapshots (old rolling `.bak` adopted by `legacy.migrate_data_dir`), private modes (0600 snapshots/sidecars, 0700 dirs, `.private-v1`), atomic writes, write lock, cursor themes, KDE colors, Noctalia templates (stale check), `child_env`; every created dir 0700 and `write.lock` 0600, `replace_checked` re-check, pruning keeps a pending Try's rollback, the stale-temp sweep's exact names; `TempDirTestCase` is imported by the two below |
| `test_core_titlebar.py` | title-bar follow (`status` reads only, `sources`, stop/cleanup remove hook and `.bak`, symlinked Noctalia config, `refresh_script` versions, script before entry, cleanup removing the script even when Noctalia's config can't change) and `titlebar_apply` (lock incl. the rendered read, re-read, 0600 backup, hidden temp names) |
| `test_core_trial.py` | `trial`: expire/restore/prune/result file, changed config, confirmed-but-unwritten, `pending_backup`/`protect_pending` (stale token), failed `confirm` message, claim, `abandon` (a written Try stays the watcher's), lock wait, deadline from `confirm`, busy, host python outside `$APPDIR`, a real detached watcher with a stub `notify-send` on `PATH` |
| `test_core_live.py` | `live` (open windows/layers, exact patterns, keyboard layout hint) with `run_umbriel_json` patched, `xkb` parser/catalog, `included_names`, Run-now blocking and `msg_argv`, meta `names_from`/`picker`/`file`/`actions.blocked` |
| `test_core_session.py` | `ConfigSession.save` without the CLI (`before_write` sees the new SHA-256, raising writes nothing): odd `[keybinds]` headers, dotted/inline keybinds, non-table shapes, text that lost a setting is refused, lock file shape |
| `test_host_runtime.py` | callback ids per render, Lua sandbox; lupa runs `app.luau` with the real core in `host_support.isolated_home(self)` (temp config, XDG dirs, fake `umbriel`; also used by `test_app_render.py`); `find`/`click`/`host.invoke` + `settle()` (`host_support.ManualScheduler`); `new_app(dir)` = restart; fake a crash via `api._helpers[path]` |
| `test_host_bridge.py` | `Bridge`, `QtScheduler` (incl. failing work), `runAsync` lanes and helper-only, single instance (temp socket path), glyph names (also `kit.iconButton("<glyph>"`), `fuzzy_score` |
| `test_app_render.py` | real `AppWindow`: DOM text/clicks, no JS/Lua errors, ARIA names, the display arrangement filling the window (fake `umbriel outputs --json` in `host_support`), close prompt during a Try (`umbriel.trying`), `window.json` 0600 |
| `test_app_icon.py` | icon (patch `appicon.APP_ICON_PATH`), desktop entry, `app.main` with Qt and `instance.claim` patched (never reach a real app's socket) |

Qt pitfalls: import `app_window` (QtWebEngine) before any `QApplication` and before patching it; after closing an `AppWindow` flush `QEvent.Type.DeferredDelete` (else crash at exit). Restore globals (stylesheet, palette, locale, env) with `addCleanup`. Offscreen: send `Leave` before non-hover baselines, don't assert text widths. In `runJavaScript`, return strings (an empty array comes back as `''`).
