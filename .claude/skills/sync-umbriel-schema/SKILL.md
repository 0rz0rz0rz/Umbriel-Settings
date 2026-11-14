---
name: sync-umbriel-schema
description: "Use when Umbriel was updated or the GUI may be out of date: compare GUI fields with the installed Umbriel schema, add missing options, remove stale ones, and update the version."
---

# Sync the GUI with the installed Umbriel schema

1. `umbriel --version` to see the installed version.
2. `python tools/check.py schema` (or `python python/umbriel-config-gui.py --check-schema` for the full list) shows unsupported options and stale GUI fields.
3. For each unsupported option, find a sibling field with `grep -n "<sibling path>" python/umbriel_core/fields.py` and add a new `F(...)` entry next to it in the same group (see `F` in `umbriel_core/fields.py`). Use `umbriel config schema --json` for the option's type, default and range, and the comment next to the key in `/usr/share/umbriel/config.toml` for help text (see `add-setting-field`). The Umbriel version string can stay the same while the build hash in `umbriel --version` changes and adds options.
4. Remove or rename stale fields flagged by the check. Keep keybind actions in `umbriel_core/actions.py` in step with the schema.
5. Re-run the check until it reports `0 unsupported option(s), 0 stale GUI field(s)`, then run `python tools/sync_plugin_core.py` and `python tools/check.py core plugin host schema`. Both frontends pick the fields up from the core.
6. If the Umbriel version changed, set `__version__` in `python/umbriel_config_gui/__init__.py` to `<new Umbriel version>-001`.

Do not read `umbriel_core/fields.py` whole. Work from grep hits and short view ranges.
