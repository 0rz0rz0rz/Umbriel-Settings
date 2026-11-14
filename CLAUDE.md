# CLAUDE.md

Guidance for Claude Code in this repository. Keep this file short: it is loaded on every turn. Detailed module tables live in path-scoped rules (`.claude/rules/`) that load only when matching files are touched.

## Project

Umbriel Settings edits the Umbriel (Wayland compositor) TOML config, keeping comments and formatting, plus XDG `user-dirs.dirs` and `mimeapps.list`. It has **one core, one UI codebase and two frontends**:

```
python/umbriel_core/                    shared logic (Python, Qt-free)                  both
noctalia-plugin/Umbriel-GUI-Plugin/
  umbriel_settings.py                   helper commands over the core                   both
  lib/ ui/ pages/                       shared UI (Luau)                                both
  panel.luau  bar.luau  plugin.toml     Noctalia panel layout + bar widget              plugin only
  app.luau                              app layout (left sidebar + page)                app only
  umbriel_core/                         vendored copy (never edit; it's .ignore'd)      plugin only
python/umbriel_config_gui/
  app.py  app_window.py  host/          PySide6 host: lupa runs the Luau UI, a          app only
                                        QWebEngineView draws it as HTML/CSS
  everything else                       legacy Qt widget UI (`--legacy-ui`), to be      app only
                                        removed once the user confirms the new app
```

A UI change is made once in the Luau files and shows up in both frontends. The app runs helper commands in-process; the plugin runs them as `python3 umbriel_settings.py <cmd>`.

| Area | Rule file (auto-loaded) | Skill |
| --- | --- | --- |
| Shared UI, plugin, helper | `rules/noctalia-plugin.md` | `edit-noctalia-panel`, `edit-noctalia-desktop-settings`, `test-noctalia-plugin` |
| App host (lupa, bridge, renderer, theme) | `rules/app-host.md` | `edit-controls` |
| Legacy Qt UI | `rules/legacy-qt-app.md` | `split-module` |
| Tests | `rules/tests.md`, `rules/noctalia-plugin-tests.md` | `add-test` |

Other skills: `add-setting-field`, `sync-umbriel-schema`, `verify-changes`, `verify-noctalia-plugin`, `build-appimage`. Use the matching skill before starting such a task. `copilot-backup/` is archived; ignore it.

## Commands

Dependencies (`python/requirements.txt`): Python 3.11+, PySide6 (with QtWebEngine), tomlkit, lupa. Plugin: tomlkit only. Optional: `umbriel` CLI (validation, schema), `lua`/`luac` (plugin harness), `noctalia` (lint).

```sh
python tools/check.py                 # checks picked from `git status`; one line per check, failures only
python tools/check.py core plugin host app schema all   # or name them
python tools/check.py test_sidebar    # single test file(s)
python tools/sync_plugin_core.py      # after editing python/umbriel_core (--check reports drift)
python python/umbriel-config-gui.py [config.toml]       # run the app: --config --no-validate --no-rebuild --check-schema --version --legacy-ui
```

`check.py` names: `core` = sync check + `tests/test_core.py`; `plugin` = `noctalia-plugin/tests` + `luac -p` + `noctalia plugins lint`; `host` = `test_host_runtime.py` + `test_host_bridge.py`; `app` = the legacy Qt tests (~125, 2–3 min); `schema` = `--check-schema` (must report 0 unsupported, 0 stale).

## Verifying (run the smallest thing that covers the change)

- Prefer `python tools/check.py` over raw unittest commands: it picks the suites and prints compact results. Use `-v` only to debug a failure.
- Shared Luau UI or helper → `plugin host`. Core → `core plugin host` (+ `app` while the legacy UI exists). Fields/actions → add `schema`.
- Visual change → render offscreen and look at the PNGs: `render_app.py` (new app) or `render_page.py` (legacy), see `edit-controls`.
- Don't launch the app or build the AppImage to verify; don't touch the live Noctalia session or real config.

## Saving tokens

- Never read whole large files: `grep -n "^function\|^local function\|^def \|^class "` to find a symbol, then read that range. Avoid the vendored `umbriel_core` copy, `host/web/fonts/` (2.5 MB font, 130 KB glyph map) and `docs/*.png`.
- Use `check.py` output instead of full test logs; rerun only the failing file (`python tools/check.py test_x`).
- When delegating searches, ask for conclusions (file:line), not file dumps.

## Conventions

- Config edits preserve TOML comments/formatting (tomlkit) and only write keys the user changed; validate before writing, back up, refuse symlinks.
- `umbriel_core` never imports Qt or reads `state.*`; only its TOML modules import tomlkit (`tests/test_core.py` enforces it). Edit `python/umbriel_core`, never the plugin copy.
- Shared Luau must parse as both Luau and Lua 5.4/5.5 (no `continue`, `+=`, type annotations, backtick strings) and respect Noctalia's 25 ms per-callback CPU budget.
- Keep files under ~800 lines (`window.py`, `common.py` are legacy exceptions). When modules move, update the rule tables.
- Tests: one file per area, `unittest`, temporary paths; never the real user config.
- Versions: app `__version__` in `python/umbriel_config_gui/__init__.py` (`<Umbriel version>-<NNN>`); plugin in `plugin.toml`; README versions table. After Umbriel/Noctalia version changes, check their release notes for needed updates.
- GPL-3.0-only: keep `LICENSE` and the AppImage license bundling; the Tabler icon font is MIT (license file next to it).
- Comment only code that needs it. No planning or notes files. Prefer the repo and `umbriel config schema --json` over web searches.
- Don't commit, push, tag or publish unless asked; never force-push. Commit messages are short and imperative.
- Ask one concise question only when a choice changes behavior; otherwise decide and state the assumption.
