---
name: add-setting-field
description: "Use when adding, renaming, or removing a single GUI setting (an F(...) field) such as a new toggle, number, choice, or color for an Umbriel option, without reading the large modules."
---

# Add a setting field

1. Find the sibling: `grep -n "<sibling.toml.path>" python/umbriel_core/fields.py`, then view about 30 lines around the hit.
2. Add `F(label, "dotted.toml.path", kind, default, extra, opt)` next to it in the same group. `kind` is one of `bool`, `int`, `float`, `color`, `choice`, `combo`, `str`, `list`, `strorlist`, `command_list`, `raw`, `table`. `extra` is the `(min, max)` range for numbers, the option list for choices, or the key names for `table` (prefer `table` over `raw` for small fixed tables like `{width, height}` or `[x, y]`). Use `opt=True` for keys that are absent by default.
3. For a choice list, add or reuse a constant near the top of `umbriel_core/fields.py` (e.g. `ON_OFF`, `LAYOUTS`).
4. Optional help text: add an entry to `FIELD_HELP` in `umbriel_core/help.py`, keyed by the field's exact **label** (not its path); fields sharing a label share the text. Renaming a label means renaming its `FIELD_HELP` key too (`test_help_keys_match_existing_labels_and_groups` fails on orphans). For optional booleans (tri-state default/on/off), say what on and off each do, e.g. "On matches only floating windows; off matches only tiled windows." Keep TOML syntax hints out of `table` labels; the controls show the keys.
5. Get type, default and range from `umbriel config schema --json` (it has no descriptions). Take the description from the comment next to the key in `/usr/share/umbriel/config.toml`; do not guess.
6. For entry editors (window/layer rules, outputs), check the group predicates (`LOOK_KEYS`, `OUTPUT_GROUPS`, ...) at the bottom of `umbriel_core/fields.py`; unmatched keys fall into the last catch-all group.
7. Run `python tools/sync_plugin_core.py` (the plugin carries a copy of the core and picks the field up automatically), then `python tools/check.py core plugin host schema` (schema must report 0 unsupported and 0 stale). The field then appears in the plugin and the app without UI changes.

Do not edit the Luau files, `window.py` or `common.py` for a plain field; they need no change. Read `fields.py`/`help.py` by grep hits only.
