---
name: edit-controls
description: "Use when changing how Umbriel Settings looks or behaves visually: controls, field rows, navigation, sidebar, page layout, theme colors and fonts (shared Luau UI + web renderer), or the legacy Qt widgets."
---

# Edit controls and layout

## New app and plugin (shared Luau UI)

- What a row or page contains is decided in Luau and is the same in both frontends: `ui/fields.luau` (one row per field kind), `ui/kit.luau` (header, cards, badges, notices, `navRow`), `ui/sidebar.luau` (app sidebar), `pages/*.luau`. See `edit-noctalia-panel`.
- How a `ui.*` node looks in the app is decided by `python/umbriel_config_gui/host/web/renderer.js` (one builder per kind: layout props → flexbox, button variants, toggle, slider, select, input, colorPicker, markdown, glyph) and `style.css`. Match Noctalia's look (control heights sm 32 / md 38 / lg 44, radii scaled by `--radius-scale`, theme roles as CSS variables like `--primary`, `--surface_container`); never hard-code colors.
- Theme roles and fonts: `umbriel_core/noctalia_theme.py` (`load_roles`, `shell_style`, `css_variables`), watched by `host/theme.py`.
- Keyed reuse matters: inputs stay uncontrolled (text set only on creation), `focus` autofocuses on mount, `revealKey` scrolls into view. A wrong key loses focus while typing.
- Don't read `host/web/fonts/` (2.5 MB font, 130 KB map); look up a glyph with `grep -o '"<name>":[0-9]*' python/umbriel_config_gui/host/web/fonts/tabler-map.json`.
- Look at the result offscreen (temp config copy and data dir, your Noctalia/qt6ct colors). Each positional argument clicks the node showing that text:

  ```sh
  cd python
  QT_QPA_PLATFORM=offscreen PYTHONPATH=. python ../.claude/skills/edit-controls/render_app.py \
      --out <scratchpad>/app General "Review & save"   # [--config sample.toml] [--size 1280x860]
  ```

- Verify with `python tools/check.py plugin host`.

## Legacy Qt UI (`--legacy-ui`, removed after the new app is confirmed)

Only fix bugs here; new UI work goes into the shared Luau UI.

- Locate shared controls in `python/umbriel_config_gui/widgets.py`; `TriStateControl` paints segmented pills, and `KdeColorControl` inherits its painting and interaction.
- `SettingRow`, `SettingLabel`, and `FlowLayout` handle form layout. `FieldWidget` in `field_widget.py` and `form_page` in `settings_layout.py` wire controls to fields; locate methods with grep and read only relevant ranges.

### Row anatomy (keep every row aligned)

- `SettingRow` = `SettingLabel` (stretch 1) + `FieldWidget`. It paints a rounded `Midlight` hover highlight and pads itself 6/3 px; `form_page` compensates with card form margins `(6, 2, 6, 10)` and vertical spacing 0. Desktop cards keep the default margins.
- `FieldWidget` lays out `[stretch][switch slot][editor_column][?]`. The slot is `SWITCH_WIDTH` wide: the optional-field switch or `switch_placeholder()`. Never use `addSpacing` for it; spacer items skip the layout spacing and shift the row by 8 px.
- `editor_column` is `EDITOR_WIDTH` (300) wide. Editors either fill it (stretch 1) or sit left with a trailing stretch. It may only grow past 300 when its contents can't shrink (comma lists, command lists). `test_every_field_uses_the_shared_editor_column` enforces this.
- `setMinimumWidth(0)` means "unset", so Qt falls back to a range- or content-based size hint. Give range-sized widgets a small explicit minimum, and give combos `AdjustToMinimumContentsLengthWithIcon`.
- The title-bar opacity row mirrors the slot: `opacity_check` or a placeholder, then the slider and spin box.

### States and styling

- An unset optional field disables its editor but still shows the default. The app sheet in `interaction_styles.py` greys `:disabled` editors and must come after `:hover`. A widget's own stylesheet overrides the app sheet, so `WheelSafeComboBox` (`common.py`) and the colour button (`FieldWidget.set_color`) carry their own `:disabled` rules.
- `TriStateControl.setLabels` renames segments, and only then are segments sized to their text. `segmentEdges` and `segmentAt` drive both painting and hit testing. `FieldWidget` shows `default (on/off)` only from a schema default; `F(...)` defaults on rule match fields don't mean "unset".
- Field kind `table` (`build_table_editors`) gives one compact spin box or combo per key, with ranges and enums from `<schema path>.<key>`. `get_table_value` returns the original tomlkit item while untouched, so partial tables are not rewritten. Scalar `raw` fields use a `QLineEdit` (`raw_single`); list and table defaults keep the multi-line editor.
- Entry lists: `EntryEditor.label_info` builds readable automatic names (`readable_match`: `firefox (app id)`, `not focused`), shown italic with the raw keys in the tooltip. `apply_filter` matches text and tooltip; call it after rebuilding items.
- Bottom bar: `Window._dirty` is a property. It enables Save, sets `windowModified` (title `"{path}[*]"`; Qt appends the app name) and accounts for `_validating`. Save is disabled while clean, so a new editor must report edits through signals `track_page_changes` connects (or call `mark_dirty`). Programmatic loads must not emit them; use `blockSignals`. `rebuild_box`, `diff_box` and `validate_box` are checkable `QAction`s in the "Save options" menu.
- `form_page` section buttons toggle their cards and reflect header, overview, saved, and temporary search expansion states. Keep them synchronized, including non-collapsible cards; test `tests/test_sidebar.py`.
- `SideTabs` combines debounced search with the overridden filter; `FieldWidget.is_overridden` and `valueChanged` provide live default comparisons. Preserve hidden rows, opacity rows, section buttons, lazy-page and entry-selection behavior. `sidebar_icons.py` draws palette-aware monochrome pictograms and `sidebar.py` refreshes them on palette changes; test `tests/test_sidebar.py`.
- `EntryEditor` in `editors.py` provides the draggable list/detail splitter for rules, outputs, scratchpads, devices, and effect presets/pools. Keep its initial roughly 1:2 split, user-adjusted width across selection and refresh, non-collapsible panes, and horizontal scrolling for long names; test `tests/test_entry_editor_layout.py`.
- The backup manager is `Window.restore_backup` in `window.py`; preserve separate restore selection and checked deletion, its confirmation, and the select/deselect-all state. Test with `tests/test_backups.py`.
- Keybind cards and list/detail layout live in `keybind_ui.py`; behavior and persistence remain in `keybinds.py`. Keep shared multi-selection mapped to table rows, and exclude collapsed or filtered rows from actions. `KeybindItemDelegate` aligns shortcut and description columns; retain key icons, raw-action search and tooltips, and the draggable splitter. Test with `tests/test_keybind_ui.py`.
- User-folder and default-app cards live in `desktop.py`; preserve editable paths, custom desktop IDs and unchanged associations. Test with `tests/test_user_dirs.py` and `tests/test_default_apps.py`.
- Reuse palette roles and shared controls. Keep mouse, keyboard, disabled-state, accessibility, and dirty-tracking behavior intact.
- Shared vertical scrollbar styling lives in `interaction_styles.py` and is applied at app startup. Keep its track borderless and thumb visible; check scroll areas, lists, trees, tables and text editors with `tests/test_scrollbar_styles.py`.
- Use `WheelSafeComboBox` for app combo-box inputs when its wheel behavior fits; apply `tidy_table` to editable table views so settings and editor pages share table styling.
- For segmented pills, round only the outer selected edge; internal selected edges are square. Test all segments and subclasses with headless Qt pixel checks in `tests/test_settings_switches.py`.
- Use `add-test` for test conventions and run touched test files first. Use `verify-changes` after Python edits; do not build the AppImage for verification.

### Look at the legacy UI

```sh
cd python
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python ../.claude/skills/edit-controls/render_page.py --page "Window rules" --out <scratchpad>/rules [--entry 1] [--config sample.toml]
```

It writes one whole-window image and one image per card, because scrolling doesn't take effect offscreen. Offscreen fonts are wider than on the desktop, so judge alignment and states, not exact text widths.
