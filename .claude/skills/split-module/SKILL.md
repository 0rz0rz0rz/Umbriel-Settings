---
name: split-module
description: "Use when a Python or Luau module grows past roughly 800 lines and should be split, or when moving functions between modules without breaking imports, tests, or import cycles."
---

# Split or move code between modules

- Luau (shared UI): modules return a table `M`; `require("./x.luau")` is relative to the requiring file and each module has private globals. Move whole functions, export with `M.name`, and update `require` lines. Verify with `python tools/check.py plugin host`.
- Python: the steps below. Prefer moving Qt-free logic into `umbriel_core` (then `tools/sync_plugin_core.py`). The legacy Qt UI is scheduled for removal; don't split it unless asked.

1. Locate blocks with `grep -n "^class \|^def " <file>`; move whole top-level blocks only, verbatim.
2. Do the move with a small throwaway Python script (cut by line ranges, write the new file with its own imports). Delete the script afterwards. This is cheaper and safer than retyping.
3. Keep the import direction acyclic:
   - `umbriel_core` sits below everything and never imports `umbriel_config_gui` or Qt; app modules re-export its names (`field_defs`, `setting_help`, `actions`, `schema`, `common`). Moving Qt-free logic means moving it into `umbriel_core` and keeping a re-export, then `tools/sync_plugin_core.py`.
   - `actions` and `widgets` depend on `common`; `field_defs` re-exports `umbriel_core.fields`; `schema` wraps `umbriel_core.schema`.
   - `field_widget` depends on `schema` and `widgets`; `setting_help` re-exports `umbriel_core.help`; `settings_layout` depends on `field_widget`, `setting_help`, and `widgets`.
   - `editors` depends on `field_widget` and `settings_layout`; `tables` depends on `editors`; `desktop` and `keybinds` may depend on `tables`; `keybind_ui` depends on `keybinds` and `settings_layout`.
   - `launch` is standard-library only; `tables` imports `parse_toml_value` from `field_widget`.
   - `sidebar_icons` uses Qt directly; `sidebar` depends on it, `editors` and the settings modules; `window` composes all modules. `settings.py` is a compatibility facade and implementation modules must not import it.
   Check with `grep -n "^from \.[a-z_]* import" python/umbriel_config_gui/*.py` before adding an import.
4. `common.py`, `window.py` and `qt6ct_theme.py` re-export names on purpose; do not prune their imports.
5. After the move, remove unused imports in the touched files only and make sure no name is undefined: `cd python && python -c "import umbriel_config_gui.window"` plus the tests (Pylance `source.unusedImports` only works on indexed files).
6. Update tests to import and patch names from their owning modules (see the `add-test` skill) and the module tables in `.claude/rules/` (`legacy-qt-app.md`, `app-host.md`, `noctalia-plugin.md`).
7. Verify with `python tools/check.py` (picks the checks from the changed files).
