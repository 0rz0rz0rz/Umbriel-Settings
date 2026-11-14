---
name: add-test
description: "Use when writing or fixing a unit test for this repo: core, app host (lupa) or legacy Qt tests, which modules to import or patch, and how to run a single test file."
---

# Add a headless test

- Pick the layer first:
  - Qt-free logic in `umbriel_core` → `tests/test_core.py` (no `QApplication`).
  - Shared Luau UI or helper flows → `noctalia-plugin/tests/` (see `test-noctalia-plugin`) and/or `tests/test_host_runtime.py`, which runs `app.luau` through lupa with the real core. Its `setUp` creates a temp config, temp `XDG_*` dirs and a fake `umbriel`; use `self.find(predicate)`, `self.click(text)`, `self.host.invoke(node["props"]["onChange"], value)` and `self.settle()` (drains `ManualScheduler`, asserts no Lua errors).
  - Python↔JS bridge, scheduler, glyph names → `tests/test_host_bridge.py`.
  - Legacy Qt widgets (`--legacy-ui`) → the files below; only for bug fixes there.

## Legacy Qt widget tests

- One file per area in `tests/test_<area>.py`, `unittest` style (no pytest).
- Qt setup: `cls.app = QApplication.instance() or QApplication([])` in `setUpClass`; `self.addCleanup(widget.close)`; call `self.app.processEvents()` after showing.
- Import from the module that owns the symbol, not through `settings`:
  - `field_defs`: `F`, `TABS`, field specs (data in `umbriel_core.fields`)
  - `umbriel_core.*`: Qt-free logic; test it in `tests/test_core.py` without `QApplication`
  - `widgets`: `SwitchCheckBox`, `SettingSlider`, ...
  - `field_widget`: `FieldWidget`, `apply_fields`, `installed_cursor_themes`
  - `setting_help`: `FIELD_HELP`, `GROUP_HELP`, `CATEGORY_HELP`, `setting_description` (data in `umbriel_core.help`)
  - `settings_layout`: `CollapsibleGroup`, `form_page`, group expansion state
  - `settings`: compatibility facade only
  - `desktop`: `USER_DIRS`, `MIMEAPPS_PATH`, `installed_desktop_apps`
  - `keybind_ui`: `KeybindEditor`, `KeybindItemDelegate`
  - `keybinds`: table-backed keybind logic and group metadata
  - `editors`: `EntryEditor` (list/detail splitter)
  - `tables`: `EffectsPage` (preset and pool entry editors)
  - `window`: `Window`, `load_umbriel_schema`, `list_backup_snapshots`, `delete_backup_snapshots`
  - `sidebar`: `SideTabs` (lazy pages, debounced search and overridden filter)
  - `sidebar_icons`: `sidebar_icon` (palette-aware pictograms)
- Patch where the name is looked up, e.g. `patch("umbriel_config_gui.window.load_umbriel_schema")`, and `patch.object(desktop, "USER_DIRS", ...)`.
- Never touch the real `~/.config`; use `tempfile.TemporaryDirectory()` and patch paths.
- For backup dialogs, see `tests/test_backups.py`: patch the config/data paths and confirmation dialog, and exercise marked deletion without touching real backups.
- For sidebar search, overridden filtering, section shortcut state and monochrome palette changes, see `tests/test_sidebar.py`; allow Qt's event loop to process timers and deferred page builds.
- For resizable entry editors (including effects), see `tests/test_entry_editor_layout.py`: patch the config path, schema and label storage; process deferred splitter setup, test long names and user resizing, and explicitly delete Qt widgets when needed for clean shutdown.
- For keybind UI tests, see `tests/test_keybind_ui.py`; patch `state.PATH` and `keybinds.config_gui_data_dir` to a temporary directory, process deferred list updates, and exercise selection, grouping and persistence through the visible cards and backing model.
- Where new tests go:
  - `test_settings_switches.py`: switches, tri-states (custom labels, segment hit tests), row hover, editor-column alignment.
  - `test_settings_cards.py`: card styling and the app stylesheet (hover, disabled). Save and restore `app.palette()`/`app.styleSheet()` with `addCleanup` before calling `apply_interaction_styles`.
  - `test_toml_values.py`: `raw`/`table` parsing and write-back. Drive `apply_fields` on a `tomlkit` document and compare `doc.as_string()`.
  - `test_save_workflow.py`: save pipeline (namespace window) and `SaveButtonStateTests`, a real `Window` with the full patch list (state paths, `common.GUI_DATA_DIR`, `settings_layout` expansion state, `desktop` paths, `window.load_umbriel_schema`).
  - `test_settings_help.py`: help text and orphaned help keys.
- Offscreen quirks: showing a widget may send it an Enter event, so send `QEvent.Type.Leave` before asserting a non-hovered baseline. Font metrics are wider than on the desktop, so don't assert text widths. Scrolling a `QScrollArea` doesn't take effect, so grab or inspect the child widget directly.
- Check that a new test catches the regression: temporarily revert the fix, see the test fail, then restore it.
- Run one file: `python tools/check.py test_<area>` (compact). One test: `cd python && QT_QPA_PLATFORM=offscreen PYTHONPATH=.:../tests python -m unittest test_<area> -k <test_name>`.
