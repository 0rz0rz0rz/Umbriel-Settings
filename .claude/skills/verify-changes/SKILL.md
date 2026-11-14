---
name: verify-changes
description: "Use after editing Python or Luau code in this repo to cheaply confirm nothing broke: compact test runs picked from the changed files, schema check and offscreen renders, without building the AppImage."
---

# Verify changes cheaply

From the repository root:

```sh
python tools/check.py            # picks checks from `git status`, prints one line per check
python tools/check.py host       # or name them: core plugin host app schema all
python tools/check.py test_core  # or single test files
```

| Changed | Checks |
| --- | --- |
| `python/umbriel_core/` | `core plugin host` (+ `app` while the legacy UI exists); `check.py` runs the sync drift check, so run `tools/sync_plugin_core.py` first |
| Shared Luau UI or `umbriel_settings.py` | `plugin host` |
| App host (`app.py`, `app_window.py`, `host/`) | `host` |
| Fields or keybind actions | add `schema` (must report 0 unsupported, 0 stale) |
| Legacy Qt modules | the matching legacy test file, e.g. `test_sidebar` (see `add-test`) |

- Failing checks print only their failure blocks. Rerun just that file, with `-v` if the trimmed output isn't enough.
- Visual change: render offscreen and Read the PNGs (`edit-controls`: `render_app.py` for the new app, `render_page.py` for the legacy UI).
- The `app` suite takes 2–3 minutes; run it only when legacy modules or the core changed.
- Add a test for behavior changes and check that it fails without the fix.
- Never build the AppImage or launch the app to verify; report skipped checks (no `lua`, `luac`, `noctalia`, `umbriel`).
