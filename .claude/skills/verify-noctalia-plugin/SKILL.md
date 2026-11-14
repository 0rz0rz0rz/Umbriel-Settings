---
name: verify-noctalia-plugin
description: "Use after changing the Noctalia plugin or the shared Luau UI to run focused isolated tests, plugin lint and Luau syntax checks without altering the live session."
---

# Verify the Noctalia plugin

From the repository root:

```sh
python tools/check.py plugin host   # plugin tests + luac + luau + lint, then the app host tests (shared UI)
python tools/check.py test_x        # app-side single files; plugin files run via:
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s noctalia-plugin/tests -p 'test_umbriel_settings.py'
```

- `plugin` = `noctalia-plugin/tests` (helper, desktop files, Lua harness for panel/app/bar), `luac -p` (Lua 5.4, as the app runs it) and `luau-compile --null` (Luau, as Noctalia runs it) on every `.luau`, `noctalia plugins lint`. `host` runs the same Luau through lupa in the app host; shared-UI changes need both.
- If the change touched `python/umbriel_core`, run `tools/sync_plugin_core.py` and add `core`.
- `test_panel.py` skips without `lua`; the real-`gio` and real-`umbriel` tests skip when those tools are missing; `check.py` reports `skip` for missing `luac`/`luau-compile`/`noctalia`. Report skipped checks.
- Optional deeper look: `luau-analyze <files>` finds real bugs (e.g. `MisleadingAndOr`, `LocalUnused`), but ignore its TypeErrors about the Noctalia globals (`noctalia`, `ui`, `panel`) and `FunctionUnused` on entry globals.
- `luac`/`luau-compile` check syntax, not the Noctalia runtime; lint checks the manifest and entry paths, not rendering or the 25 ms CPU budget.
- Don't install dependencies, build the AppImage, or change the live shell or user config to verify. For real GUI behavior, use an isolated host or say live rendering was not tested.
