# CLAUDE.md

Guidance for Claude Code in this repository. Keep this file short: it is loaded on every turn. Detailed module tables live in path-scoped rules (`.claude/rules/`) that load only when matching files are touched.

## Project

Umbriel Settings edits the Umbriel (Wayland compositor) TOML config, keeping comments and formatting, plus XDG `user-dirs.dirs` and `mimeapps.list`. It has **one core, one UI codebase and two frontends**:

```
python/umbriel_core/                    shared logic (Python, Qt-free)                  both
noctalia-plugin/umbriel-settings/
  umbriel_settings.py                   helper commands over the core                   both
  lib/ ui/ pages/                       shared UI (Luau)                                both
  panel.luau  bar.luau  plugin.toml     Noctalia panel layout + bar widget              plugin only
  app.luau                              app layout (left sidebar + page)                app only
  umbriel_core/                         vendored copy (never edit; it's .ignore'd)      plugin only
python/umbriel_settings/
  app.py  app_window.py  host/          PySide6 host: lupa runs the Luau UI, a          app only
  appicon.py  qt6ct_theme.py            QWebEngineView draws it as HTML/CSS
```

A UI change is made once in the Luau files and shows up in both frontends. The app runs helper commands in-process; the plugin runs them as `python3 umbriel_settings.py <cmd>`.

| Area | Rule file (auto-loaded) | Skill |
| --- | --- | --- |
| Shared UI, plugin, helper | `rules/noctalia-plugin.md` | `edit-noctalia-panel`, `edit-noctalia-desktop-settings`, `test-noctalia-plugin` |
| App host (lupa, bridge, renderer, theme) | `rules/app-host.md` | `edit-controls`, `split-module` |
| Tests | `rules/tests.md`, `rules/noctalia-plugin-tests.md` | `add-test` |

Other skills: `add-setting-field`, `sync-umbriel-schema`, `verify-changes`, `verify-noctalia-plugin`, `build-appimage`. Use the matching skill before starting such a task.

## Commands

Dependencies (`pyproject.toml` ranges; `python/requirements.txt` pins what the AppImage bundles): Python 3.11+, PySide6 (with QtWebEngine), tomlkit, lupa. Plugin: tomlkit only. Optional: `umbriel` CLI (validation, schema), `lua`/`luac` (plugin harness), `noctalia` (plugin lint), `ruff` (Python lint, config in `pyproject.toml`).

```sh
python tools/check.py                 # checks picked from `git status`; one line per check, failures only
python tools/check.py core plugin host schema lint all   # or name them
python tools/check.py test_core_values    # single test file(s)
python tools/sync_plugin_core.py      # after editing python/umbriel_core (--check reports drift)
python python/umbriel-settings.py [config.toml]       # run the app: --config --no-validate --no-rebuild --check-schema --version
```

`check.py` names: `core` = sync check + `tests/test_core*.py`; `plugin` = `noctalia-plugin/tests` (incl. the 25 ms CPU budget check on a large config) + `luac -p` + `noctalia plugins lint`; `host` = the other `tests/` files (lupa runtime, bridge, web render, app icon); `schema` = `--check-schema` (must report 0 unsupported, 0 stale); `lint` = `ruff check`. Missing tools are reported as `skip`. CI (`.github/workflows/check.yml`) runs `core plugin host lint` on Python 3.11 and 3.13.

## Verifying (run the smallest thing that covers the change)

- Prefer `python tools/check.py` over raw unittest commands: it picks the suites and prints compact results. Use `-v` only to debug a failure.
- Shared Luau UI or helper → `plugin host`. Core → `core plugin host`. Fields/actions → add `schema`.
- Visual change → render offscreen and look at the PNGs: `render_app.py`, see `edit-controls`.
- Don't launch the app or build the AppImage to verify; don't touch the live Noctalia session or real config.

## Saving tokens

- Never read whole large files: `grep -n "^function\|^local function\|^def \|^class "` to find a symbol, then read that range. Avoid the vendored `umbriel_core` copy, `host/web/fonts/` (2.5 MB font, 130 KB glyph map) and `docs/*.png`.
- Use `check.py` output instead of full test logs; rerun only the failing file (`python tools/check.py test_x`).
- When delegating searches, ask for conclusions (file:line), not file dumps.

## Conventions

- Config edits preserve TOML comments/formatting (tomlkit) and only write keys the user changed; validate before writing, back up, refuse symlinks.
- `umbriel_core` never imports Qt; only its TOML modules import tomlkit (`tests/test_core.py` enforces it). Edit `python/umbriel_core`, never the plugin copy.
- Shared Luau must parse as both Luau and Lua 5.4/5.5 (no `continue`, `+=`, type annotations, backtick strings) and respect Noctalia's 25 ms per-callback CPU budget.
- Keep files under ~800 lines. When modules move, update the rule tables.
- Tests: one file per area, `unittest`, temporary paths; never the real user config.
- Names: product "Umbriel Settings"; package `umbriel_settings`, launcher `python/umbriel-settings.py`, desktop ID and data/config dirs `umbriel-settings`, plugin ID `0rz0rz0rz/umbriel-settings`. The old `umbriel-config-gui` names are only read for migration (`umbriel_core.paths.LEGACY_DIR_NAME`). The helper module is also called `umbriel_settings` (plugin file); the app loads it under a private name and restores `sys.path`.
- Versions: app `__version__` in `python/umbriel_settings/__init__.py` is `<Umbriel version>-<NNN>` (`0.1.0-004`); plugin `plugin.toml` is `<Umbriel major>.<minor>.<NNN as number>` (`0.1.4`, Noctalia needs plain semver); README versions table. A new build only raises `NNN`; the `0.1.0` part changes only when Umbriel's version changes (`NNN` restarts at `001`). After Umbriel/Noctalia version changes, check their release notes for needed updates.
- MIT: keep `LICENSE` (root and plugin copy) and the AppImage license bundling; the Tabler icon font is MIT (license file next to it).
- Comment only code that needs it. No planning or notes files. Prefer the repo and `umbriel config schema --json` over web searches.
- Build the AppImage only when the user explicitly allows that build; an earlier "go ahead" or a release plan is not permission.
- Commit, push, tag or publish only when the user explicitly allows it; when it seems due, ask first. Never force-push. Commit messages are short and imperative.
- Ask one concise question only when a choice changes behavior; otherwise decide and state the assumption.
