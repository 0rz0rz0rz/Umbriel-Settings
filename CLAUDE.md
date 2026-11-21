# CLAUDE.md

Loaded every turn: keep it short. Module tables live in `.claude/rules/` (loaded per path).

## Project

Umbriel Settings edits the Umbriel (Wayland compositor) TOML config keeping comments/formatting, plus XDG `user-dirs.dirs` and `mimeapps.list`. One core, one Luau UI, two frontends:

```
python/umbriel_core/                 shared Qt-free logic                       both
noctalia-plugin/umbriel-settings/
  umbriel_settings.py                helper commands over the core              both (app: in-process; plugin: python3 subprocess)
  lib/ ui/ pages/                    shared UI (Luau)                           both
  panel.luau bar.luau plugin.toml    Noctalia panel + bar widget                plugin
  app.luau                           app layout (sidebar + page)                app
  umbriel_core/                      vendored copy: never edit, .ignore'd       plugin
python/umbriel_settings/             PySide6 host: lupa runs the Luau, QWebEngineView draws HTML   app
```

| Area | Rule (auto) | Skills |
| --- | --- | --- |
| Shared UI, plugin | `noctalia-plugin.md`, `noctalia-plugin-pages.md` | `edit-noctalia-panel`, `edit-noctalia-desktop-settings` |
| Helper, core | `core-helper.md` | `add-setting-field` |
| App host | `app-host.md` | `edit-controls`, `split-module` |
| Tests | `tests.md`, `noctalia-plugin-tests.md` | `add-test` |

Also: `sync-umbriel-schema`, `verify-changes`, `update-screenshots`, `build-appimage`. Use the matching skill first.

## Commands

Deps: Python 3.11+, PySide6 + QtWebEngine, tomlkit, lupa (`pyproject.toml` ranges; `python/requirements.txt` = AppImage pins; after changing it run `tools/update_appimage_pins.py`). Plugin: tomlkit. Optional (else `skip`): `umbriel`, `lua`/`luac`, `luau-compile`, `noctalia`, `ruff`, `shellcheck`, `gio`.

```sh
python tools/check.py                # checks picked from git status; failures only
python tools/check.py core plugin host schema lint all | test_core_values [-k name]   # or any test file
python tools/sync_plugin_core.py     # after editing python/umbriel_core (--check: drift)
python python/umbriel-settings.py [config.toml]   # --config --no-validate --no-rebuild --check-schema --version
```

Checks: `core` = sync + `tests/test_core*.py`; `plugin` = `noctalia-plugin/tests` (incl. 25 ms CPU budget) + `luac -p` + `luau-compile --null` + `noctalia plugins lint` + community validator (`tools/validate_plugin.py`: `$NOCTALIA_VALIDATOR` or Noctalia's local official source; CI pins it, with `langdetect`); `host` = other `tests/` (lupa, bridge, web render, icon); `schema` = `--check-schema` (0 unsupported, 0 stale); `lint` = ruff + shellcheck. CI runs `lint` once and `core plugin host` on 3.11/3.12/3.13.

## Verify (smallest set)

Run checks only after edits, only for what changed (`check.py` without arguments picks them); never `all` unasked; docs, rules and skills need none. Luau UI/helper → `plugin host`; core → `core plugin host`; fields/actions → `+schema`; visual → `render_app.py` PNGs (`edit-controls`). Launching the app to test is allowed (from the checkout; prefer a temp config and `XDG_DATA_HOME`; close it afterwards); never build the AppImage, touch the live Noctalia session, or save to the real config to verify.

## Tokens

Grep for symbols (`^function\|^local function\|^def \|^class `) and read ranges, not whole files. Skip the vendored core, `host/web/fonts/`, `docs/*.png`. Use `check.py` output; rerun only the failing file. Delegated searches return file:line conclusions.

## Conventions

- Config edits: tomlkit, only changed keys, validate, back up, refuse symlinks.
- `umbriel_core`: no Qt; tomlkit only in TOML modules (`test_core.py` enforces). Edit `python/umbriel_core`, never the copy.
- `plugin_api` = the oldest level the plugin needs, never above the API of the Noctalia release before the newest one (numbers: `noctalia-plugin.md`).
- Files < ~800 lines and ~40 KB. Tests: one file per area, `unittest`, temp paths.
- After every code change, update whatever it made stale in the READMEs (root, `noctalia-plugin/`, `noctalia-plugin/umbriel-settings/`), skills, rules and this file before reporting done.
- Names: "Umbriel Settings"; package `umbriel_settings`; launcher `python/umbriel-settings.py`; desktop ID/data dirs `umbriel-settings`; plugin ID `0rz0rz0rz/umbriel-settings`. Old `umbriel-config-gui` only for migration (`paths.LEGACY_DIR_NAME`); older file layouts move once via `umbriel_core/legacy.py`. The app imports the helper (`umbriel_settings.py`) under a private name and restores `sys.path`.
- Versions: own `MAJOR.MINOR.PATCH`, the same for app `__version__`, `plugin.toml`, AppImage and tag (rules: `build-appimage`). Targets in `umbriel_core/meta.py`: `UMBRIEL_VERSION` (schema sync), `NOCTALIA_VERSION` (follows `plugin_api`); all three READMEs list version and targets (`test_versions_agree`). Versions change only when a new AppImage is built and released; never for commits or pushes. Check Umbriel/Noctalia release notes after their updates.
- MIT: keep both `LICENSE` copies, AppImage license bundling, Tabler font license.
- Comment only what needs it. No planning/notes files. Prefer repo and `umbriel config schema --json` over the web.
- AppImage builds, commits, pushes, tags, releases: only on explicit permission for that action; a permitted build that is then pushed also gets its tag and GitHub release without asking. Never force-push; short imperative commit messages.
- Ask one concise question only when a choice changes behavior; otherwise decide and state the assumption.
