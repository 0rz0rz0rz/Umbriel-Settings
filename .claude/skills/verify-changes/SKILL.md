---
name: verify-changes
description: "Use after editing Python or Luau code in this repo to cheaply confirm nothing broke: compact test runs picked from the changed files, schema check and offscreen renders, without building the AppImage."
---

# Verify changes cheaply

From the repository root:

```sh
python tools/check.py            # picks checks from `git status`, prints one line per check
python tools/check.py host       # or name them: core plugin host schema lint all
python tools/check.py test_core  # or single test files
```

| Changed | Checks |
| --- | --- |
| `python/umbriel_core/` | `core plugin host`; `check.py` runs the sync drift check, so run `tools/sync_plugin_core.py` first |
| Shared Luau UI or `umbriel_settings.py` | `plugin host` |
| App host (`app.py`, `app_window.py`, `appicon.py`, `host/`, `web/`) | `host` (includes the web render test) |
| Fields or keybind actions | add `schema` (must report 0 unsupported, 0 stale) |
| Any Python file, `pyproject.toml`, AppImage shell scripts | `lint` (`ruff check` + `shellcheck`; each skipped when missing) |

- Failing checks print only their failure blocks. Rerun just that file, with `-v` if the trimmed output isn't enough.
- Visual change: render offscreen and Read the PNGs (`edit-controls`: `render_app.py`).
- `plugin` includes the CPU budget check (`budget_test.lua`: every page on a large config, each callback ≤ 25 ms under plain Lua, mock JSON excluded).
- Add a test for behavior changes and check that it fails without the fix.
- Never build the AppImage or launch the app to verify; report skipped checks (no `lua`, `luac`, `luau-compile`, `noctalia`, `umbriel`, `ruff`, `shellcheck`).
- Afterwards, update every README, skill, rule and `CLAUDE.md` the change made stale (module tables, check names, file locations, behavior).
