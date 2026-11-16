---
paths:
  - "tests/**/*.py"
---

# App tests (`tests/`)

`unittest`, offscreen Qt; run with `python tools/check.py <file>`. Patch `XDG_DATA_HOME`/`XDG_CONFIG_HOME` to temp dirs. A new test must fail without its fix. Run the touched file first.

| File | Covers |
| --- | --- |
| `test_core.py` | import rules (no Qt; desktop modules without tomlkit), copy drift, entries, keybind apply, layout rebuild (lossless, stable), paths, schema coverage rules + speed bound, KDE lookup |
| `test_core_values.py` | `from_ui`/`to_ui`/`apply_value`, overridden checks, help coverage, keybind checks |
| `test_core_files.py` | backups/snapshots, atomic writes, write lock, cursor themes, KDE colors, Noctalia templates, title-bar follow/apply, `child_env` |
| `test_core_session.py` | `ConfigSession.save` without the CLI: odd `[keybinds]` headers, dotted/inline keybinds, non-table shapes, text that lost a setting is refused, lock file shape |
| `test_host_runtime.py` | callback ids per render, Lua sandbox; lupa runs `app.luau` with the real core, temp config, fake `umbriel`; `find`/`click`/`host.invoke` + `settle()`; `new_app(dir)` = restart; fake a crash via `api._helpers[path]` |
| `test_host_bridge.py` | `Bridge`, `QtScheduler` (incl. failing work), single instance (temp socket path), glyph names |
| `test_app_render.py` | real `AppWindow`: DOM text/clicks, no JS/Lua errors, ARIA names |
| `test_app_icon.py` | icon, desktop entry, `app.main` with Qt and `instance.claim` patched (never reach a real app's socket) |

Qt pitfalls: import `app_window` (QtWebEngine) before any `QApplication` and before patching it; after closing an `AppWindow` flush `QEvent.Type.DeferredDelete` (else crash at exit). Restore globals (stylesheet, palette, locale, env) with `addCleanup`. Offscreen: send `Leave` before non-hover baselines, don't assert text widths. In `runJavaScript`, return strings (an empty array comes back as `''`).
