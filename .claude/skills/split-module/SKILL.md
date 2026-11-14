---
name: split-module
description: "Use when a Python or Luau module grows past roughly 800 lines and should be split, or when moving functions between modules without breaking imports, tests, or import cycles."
---

# Split or move code between modules

- Luau (shared UI): modules return a table `M`; `require("./x.luau")` is relative to the requiring file and each module has private globals. Move whole functions, export with `M.name`, and update `require` lines. Verify with `python tools/check.py plugin host`.
- Python: the steps below. Prefer moving Qt-free logic into `umbriel_core` (then `tools/sync_plugin_core.py`).

1. Locate blocks with `grep -n "^class \|^def " <file>`; move whole top-level blocks only, verbatim.
2. Do the move with a small throwaway Python script (cut by line ranges, write the new file with its own imports). Delete the script afterwards. This is cheaper and safer than retyping.
3. Keep the import direction acyclic: `umbriel_core` sits below everything and never imports `umbriel_settings` or Qt. In the app, `app.py` imports Qt modules lazily (so `--version` and `--check-schema` stay fast); `app_window` composes `host/`; `appicon` and `qt6ct_theme` are leaves. Check with `grep -n "^from \.[a-z_.]* import" python/umbriel_settings/*.py python/umbriel_settings/host/*.py` before adding an import.
4. After the move, remove unused imports in the touched files only and make sure no name is undefined: `cd python && python -c "import umbriel_settings.app_window"` plus the tests (Pylance `source.unusedImports` only works on indexed files).
5. Update tests to import and patch names from their owning modules (see the `add-test` skill) and the module tables in `.claude/rules/` (`app-host.md`, `noctalia-plugin.md`).
6. Verify with `python tools/check.py` (picks the checks from the changed files).
