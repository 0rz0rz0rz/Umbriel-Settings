# Umbriel Settings

Edit your whole Umbriel configuration from a Noctalia panel without losing the comments and formatting of
your config: every setting page, window/layer/workspace/security rules, outputs, scratchpads, input devices,
effects, animation curves, environment variables and keybinds, plus XDG user folders and default apps.
The same interface also runs as a standalone app: see the
[Umbriel-Settings repository](https://github.com/0rz0rz0rz/Umbriel-Settings).

## Plugin

| Field | Value |
| --- | --- |
| ID | `0rz0rz0rz/umbriel-settings` |
| Entries | Bar widget: `settings`; panel: `folders` |

## Requirements

- Noctalia 5.4.0 or newer (plugin API 43) and `python3` 3.11+ (runs the bundled helper).
- `python-tomlkit`: edits the config while keeping its formatting. Without it the panel says what to
  install; user folders and default apps still work.
- `umbriel` on `PATH`: defaults, ranges, validation before saving and **Inspect connected outputs**.
  Without it settings can still be edited, but aren't checked before writing.
- Optional: `zenity` or `kdialog` (folder **Browse**), `gio` (open the standalone app), `xdg-open` or an
  editor command set under **About** (**Edit file**). Buttons explain what's missing.

## Usage

Add the `settings` widget to a bar: it toggles the panel and shows a dot while edits are unsaved. Or run
`noctalia msg panel-toggle 0rz0rz0rz/umbriel-settings:folders`.

- **Home** has a search over setting names, help text, config keys (`border_width`), rule names and
  shortcuts, and cards for every page with customized/unsaved counts.
- **Setting rows** show the control, the default, ⓘ help with the config key, undo, and an eraser that
  removes the key so Umbriel's default applies. **Only customized** hides settings at their default.
- **Rules, outputs, devices and effects** are lists: edit, name, reorder, duplicate, delete.
- **Keybinds** are grouped: build shortcuts from modifier chips, pick actions from a searchable catalog,
  lock shortcuts against accidental changes.
- **User folders** and **Default apps** edit `user-dirs.dirs` and `mimeapps.list`.
- **Title-bar colors**: on Colors → Title bar, **KDE** / **KDE header** make a background follow Noctalia's
  palette at the chosen opacity; after one save, palette changes update it even with the panel closed. A
  fixed color stops following. Each config follows on its own.
- **About** shows the version, options your Umbriel has that aren't covered yet, and the editor command.

Nothing is written until **Review & save** (Ctrl+S): the review lists every change, shows the diff and runs
`umbriel config validate` first; if Umbriel rejects the file, nothing is written and each problem links to
its setting. Unsaved edits (including folders and default apps) survive closing the panel and restarting
Noctalia as a draft.

Keys: Ctrl+F search, Ctrl+S review, Alt+Left back, Esc close.

## Settings

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| `display` | `select` | `icon` | What the bar widget shows: `icon` (with a dot while edits are unsaved), `icon_text` or `text`. A vertical bar always shows only the icon. |
| `icon` | `select` | `moon-stars` | The bar widget's icon: `settings`, `settings-2`, `settings-cog`, `adjustments-horizontal`, `adjustments-cog`, `tool`, `tools`, `moon`, `moon-stars`, `moon-2` or `home-cog`. Unknown values fall back to `moon-stars`. |

## Notes

- **Files read**: the Umbriel config (last chosen in the panel or app, else `~/.config/umbriel/config.toml`),
  `user-dirs.dirs`, `mimeapps.list`, installed `.desktop` files, qt6ct/KDE color files (KDE title-bar colors),
  `noctalia-config.toml` and the palette file (title bars that follow Noctalia).
- **Files written**, only when you save, restore or delete backups: the Umbriel config (validated, written
  atomically, symlinks refused), `$XDG_CONFIG_HOME/user-dirs.dirs` and `$XDG_CONFIG_HOME/mimeapps.list` (other
  entries and MIME fallbacks kept). Each write is preceded by a timestamped backup (newest 10 per file) in
  `$XDG_DATA_HOME/umbriel-settings/`, which also holds the chosen config path, rule names, keybind locks and
  the editor command. Drafts and cache live in Noctalia's plugin data directory.
- **Title bars that follow Noctalia**, only after pressing **KDE** / **KDE header**: the user template
  `~/.config/noctalia/templates/umbriel-titlebar.toml`, its `umbriel_titlebar` entry in `noctalia-config.toml`
  (backed up first) and `~/.config/umbriel-settings/titlebar_apply.py`. On palette changes Noctalia renders
  `~/.config/umbriel-settings/titlebar-colors.toml` and runs the script, which sets only `background` /
  `background_unfocused` in `[colors.title_bar]` of each following config (an include can't, because
  Noctalia's umbriel template always loads `noctalia.toml` last).
- **Processes**: `python3 -B umbriel_settings.py <command>` (JSON request/response files in the plugin data
  directory); `umbriel config validate` (on a temporary `.umbriel-settings-*.toml` next to the config,
  removed afterwards), `umbriel config schema --json`, `umbriel outputs --json`; on button press only:
  `zenity`/`kdialog`, `gio launch`, `xdg-open` or your editor. Noctalia runs `python3 titlebar_apply.py`
  after palette changes while a title-bar color follows it.
- **Network**: none.
- `umbriel_core/` is the config library shared with the standalone app, bundled so the plugin works alone.
  `app.luau` is the app's layout; it isn't in `plugin.toml`, so Noctalia never loads it.
- MIT License; see `LICENSE`.
