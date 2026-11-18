---
name: verify-changes
description: "Use after editing Python or Luau code in this repo (core, app host, Noctalia plugin, shared Luau UI) to cheaply confirm nothing broke: compact test runs picked from the changed files, Luau syntax and plugin lint, schema check and offscreen renders, without building the AppImage or touching the live session."
---

# Verify changes cheaply

From the repository root:

```sh
python tools/check.py            # picks checks from `git status`, prints one line per check
python tools/check.py host       # or name them: core plugin host schema lint all
python tools/check.py test_core  # or single test files (tests/ or noctalia-plugin/tests/)
```

Which checks cover which change, and what each runs: CLAUDE.md "Commands" and "Verify". Also:

- After editing `python/umbriel_core/` run `tools/sync_plugin_core.py` first (`core` checks the copy).
- Python files, `pyproject.toml` and the AppImage shell scripts also need `lint` (`ruff check` + `shellcheck`). The app host (`app.py`, `app_window.py`, `appicon.py`, `host/`, `host/web/`) needs `host`, which includes the web render test.
- Shared Luau changes need `plugin` and `host`: `luac -p` parses as Lua 5.4 (the app), `luau-compile --null` as Luau (Noctalia), `noctalia plugins lint` checks the manifest and entry paths. These check syntax, not the Noctalia runtime.
- Failing checks print only their failure blocks. Rerun just that file, with `-v` if the trimmed output isn't enough.
- Visual change: render offscreen and Read the PNGs (`edit-controls`: `render_app.py`).
- Optional deeper look at Luau: `luau-analyze <files>` finds real bugs (`MisleadingAndOr`, `LocalUnused`); ignore its TypeErrors about the Noctalia globals (`noctalia`, `ui`, `panel`) and `FunctionUnused` on entry globals.
- Never install dependencies, build the AppImage, launch the app, or touch the live shell or user config to verify. Report skipped checks (no `lua`, `luac`, `luau-compile`, `noctalia`, `umbriel`, `ruff`, `shellcheck`, `gio`) and say when live rendering was not tested.
