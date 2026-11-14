---
paths:
  - "python/umbriel_config_gui/*.py"
---

# Legacy Qt UI (`--legacy-ui`)

These modules are the previous widget UI. The default app is now the web-view host (`app.py`, `app_window.py`, `host/`; see `app-host.md`). Keep the legacy UI working until the user confirms the new app, then it gets removed (Phase 5). Don't add features here; add them to the shared Luau UI in `noctalia-plugin/Umbriel-GUI-Plugin/`.

## Module lookup

`window.py` and `common.py` are over 1000 lines. Never read them whole: Grep for `^class |^def |    def ` to find a symbol, then Read only that range.

| Need to change | Module | Key symbols |
| --- | --- | --- |
| App start, CLI, load/save flow | `window.py` | `main`, `Window`, `load_config_document`, `group_diff_by_section` |
| Backup selection, restore and deletion | `window.py`, `umbriel_core/backups.py` | `Window.restore_backup`, `Window._restore_backup_snapshot`; `list_backup_snapshots`, `delete_backup_snapshots`, `create_backup_snapshot(path, config_dir)` |
| Config read/write, TOML edits | `umbriel_core/tomlops.py`, `layout.py`, `paths.py`; wrappers in `common.py` | `getp`/`putp`/`delp`, `parse_toml_value`, `rebuild_config`, `add_entry_name_comments`, `read_config_state`, `write_text_file`; `common.py` keeps `parse_cli_args` and path wrappers that read `common.GUI_DATA_DIR` (tests patch it) |
| Field definitions (what settings exist) | `umbriel_core/fields.py` (`field_defs.py` re-exports) | `F`, `Field`, `TABS`, `NAV_SECTIONS`, `layout_fields`, `color_group`, `anim`, `regroup` |
| Schema from installed Umbriel | `umbriel_core/schema.py`; `schema.py` wraps it | `load_umbriel_schema`, `schema_field_catalog`, `check_schema_coverage`, `field_schema_option(options, path)` (the app's version reads `state.ACTIVE_SCHEMA_OPTIONS`) |
| Field controls and config write-back | `field_widget.py` | `FieldWidget` (`EDITOR_WIDTH`, `build_table_editors`, `raw_single`), `apply_fields`; `installed_cursor_themes` lives in `umbriel_core/cursor_themes.py` |
| Help text for settings | `umbriel_core/help.py` (`setting_help.py` re-exports) | `FIELD_HELP`, `GROUP_HELP`, `CATEGORY_HELP`, `setting_help_text` (unwrapped), `setting_description` (wrapped for tooltips) |
| Settings pages and collapsible groups | `settings_layout.py` | `form_page`, `CollapsibleGroup`, `SIDEBAR_SECTIONS`, group expansion state |
| Compatibility imports | `settings.py` | Re-exports only; implementation modules must not import it |
| Shared controls | `widgets.py` | `SettingRow` (hover highlight), `SettingLabel`, `SwitchCheckBox`, `TriStateControl` (`setLabels`, `segmentEdges`), `KdeColorControl`, `SettingSlider`, `FlowLayout` |
| App-wide hover/scrollbar styles | `interaction_styles.py` | `apply_interaction_styles` (re-exported by `common.py`) |
| Title bar KDE colors | `umbriel_core/kde.py`, `kde_titlebar.py` | `read_title_bar_rgb`, `qt6ct_scheme_path`; Qt side `read_title_bar_colors`, `KdeTitleBarFollower` |
| Table and map editors | `tables.py` | `KVTable`, `RawValueMapEditor`, `AnimationCurvesPage`, `EffectsPage` |
| Keybinds | `umbriel_core/keybinds.py`, `keybinds.py`, `keybind_ui.py` | core: `parse_keybind_groups`, `write_keybind_groups`, locks, `check_action`, `apply_bindings`, `reorder_table`; Qt: `KeybindEditor` (table-backed logic / collapsible list-detail UI), `KeybindItemDelegate` |
| Actions | `umbriel_core/actions.py`; `actions.py` adds the Qt model | `ACTION_CATEGORIES`, `parse_actions`, `migrate_action`, `reduce_template`; `build_action_model` |
| Sidebar navigation, search, overridden filter | `sidebar.py`, `field_widget.py` | `SideTabs`, `load_sidebar_order`, `_materialize_search_page`, `_filter_search_results`, `FieldWidget.is_overridden` |
| Sidebar pictograms | `sidebar_icons.py`, `sidebar.py` | `sidebar_icon`, `_PAGE_PICTOGRAMS`, `_SidebarListWidget.changeEvent` |
| Entry editor and resizable panes | `editors.py`, `umbriel_core/entries.py` | `EntryEditor`, `splitter`, `_set_initial_splitter_sizes`, `select`, `commit`, `label_info`, `apply_filter`; core `entry_label_info`, `readable_match` |
| User dirs and default apps | `desktop.py` (app); `umbriel_core/xdg_dirs.py`, `mimeapps.py` (plugin) | `UserDirs`, `DefaultApps`, `update_mimeapps_defaults`; plugin side `save`, `update_text`, `installed_apps`, `extension_mime` |
| Inline TOML value parsing (raw fields, map tables) | `umbriel_core/tomlops.py` | `parse_toml_value` (rejects extra keys/tables) |
| Plugin-facing core | `umbriel_core/session.py`, `meta.py`, `values.py`, `entry_ops.py` | `ConfigSession.read/preview/save/validate` (validates a temp copy before writing), `build_meta`, `to_ui`/`from_ui`/`apply_value`, `ENTRY_EDITORS`, `MAP_EDITORS`, `apply_entry_op`, `apply_map_op` |
| Launching editors/terminals | `launch.py` | `child_env` (restores host `PYTHON*` vars inside the AppImage; pair with `appimage/recipe/entrypoint.sh`), `find_terminal`, `terminal_command` |
| Qt palette from qt6ct/KDE | `qt6ct_theme.py` | `apply_qt6ct_theme`, `Qt6ctThemeFollower`, `build_palette` |
| Readable palettes, icons, paths | `common.py` | `readable_palette`, `PaletteReadability`, `create_app_icon`, `normalize_config_path` |

## Behavior details

| Question | Answer |
| --- | --- |
| Which pages, groups and fields exist | `TABS[<page>] = [(group title, [F(...), ...]), ...]` in `field_defs.py`; `window.py` builds one lazy `form_page` per key. Sidebar order: `SIDEBAR_SECTIONS` (user reorder saved via `sidebar.py`) |
| Field kinds | `bool`, `int`, `float`, `str`, `choice`, `combo`, `color`, `list`, `strorlist`, `raw`, `command_list`, `table` (one control per key of a small table or `[x, y]` array; `extra` lists the keys, sub-ranges come from the schema); handled in `FieldWidget.__init__`, `set_value`, `get`. Every row uses a fixed switch slot and a `FieldWidget.EDITOR_WIDTH` editor column |
| `opt=True` | Row gets an on/off switch; off → `get()` returns `None` → `apply_fields` deletes the key. An optional `bool` becomes a tri-state (unset/on/off) |
| Help text | `FIELD_HELP` (by exact field label, not path; descriptions come from comments in `/usr/share/umbriel/config.toml`), `GROUP_HELP` (by group title), `CATEGORY_HELP` (by page); `setting_description` assembles it; search matches it |
| Save pipeline | `Window.save`: validate editors → `apply_fields` (only changed or optional keys) → `tomlkit.dumps` → `add_entry_name_comments` + `rebuild_config` → diff review (`confirm_save_diff`) → `create_backup_snapshot` → `write_text_file` → background `umbriel config validate` (errors restore the previous file). Desktop settings save separately after the diff is accepted |
| Dirty tracking | `Window.track_page_changes`, `mark_dirty`. `_dirty` is a property that enables Save (disabled while clean) and sets `windowModified`, so new editors must report edits through tracked signals and load values without emitting them |
| Process-wide state | `state.py`: `PATH`, `_CLI_ARGS`, `ACTIVE_SCHEMA_OPTIONS`. Always `state.PATH`, never `from state import PATH` (tests patch it). `umbriel_core` never reads it |
| Per-field schema info | `schema_path` passed to `FieldWidget`, looked up with `field_schema_option` |
| Colors | `#RRGGBB` or `#RRGGBBAA` (`qcolor`/`hexof` in `common.py`). Title-bar background opacity is the alpha channel; `FieldWidget.set_color` keeps it in sync with the opacity row built in `form_page` (`fw.opacity_widget`/`opacity_row`). KDE import: `TITLE_BAR_KEYS`/`BACKGROUND_KEYS` in `kde_titlebar.py`, `kde_*`/`opacity_*` methods on `FieldWidget` |
| Search and overridden filter | `SideTabs` debounces search, builds deferred pages incrementally and caches fields. `is_overridden` compares to the schema default (or field fallback); unset optional fields are hidden, includes aren't resolved, non-field editors aren't filtered. Both filters hide unmatched groups, section buttons, `fw.search_row` and `fw.opacity_row` — preserve this for any extra rows |
| Section shortcuts | `form_page` links each `section_button` to its card's expansion state; search temporarily opens matching cards and restores their prior state |
| Row layout | `SettingRow(label_widget, editor)` with hover highlight; `FieldWidget` is `[switch slot][editor_column EDITOR_WIDTH][?]` so every row lines up. Unset optional editors are disabled and styled greyed (app sheet plus widget sheets with their own `:disabled`) |
| GUI-only files | Global `common.GUI_DATA_DIR` (`$XDG_DATA_HOME/umbriel-config-gui/`: saved config path, sidebar order, group expansion); per-config `config_gui_data_dir(path)` (backups, `gui-labels.json`, locked keybinds) |
| Keybind UI | `keybind_ui.KeybindEditor` builds `CollapsibleGroup` cards from the hidden table model; tree items map to table rows via `Qt.ItemDataRole.UserRole`. `_sync_list` and `_select_items` must exclude filtered or collapsed rows. Keep raw actions searchable and in tooltips |
| Keybind groups and locks | Groups persist as TOML comments, locks in the per-config sidecar. Deleting a group moves bindings to Ungrouped without deleting or unlocking them |
| User dirs / default apps | `UserDirs` and `DefaultApps` in `desktop.py`; `commit` preserves unrelated entries, unchanged associations and desktop-file fallbacks |
| Entry-style pages (rules, outputs, scratchpads, devices, effect presets/pools) | `EntryEditor` splitter starts ~1/3 list, 2/3 detail; selection, commit and refresh must not reset a user-adjusted split. `EffectsPage` creates two. Unnamed rules get readable italic names (raw keys in tooltip); a filter box matches both |
