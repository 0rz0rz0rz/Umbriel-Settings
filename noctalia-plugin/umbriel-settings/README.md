# Umbriel Settings

Edit your whole Umbriel configuration from a Noctalia panel, without losing the comments and formatting of
your config file. It covers every setting page, window, layer, workspace and security rules, outputs,
scratchpads, input devices, effects, animation curves, environment variables and keybinds, plus XDG user
folders and default applications.

The same interface also runs as a standalone desktop app, available from the
[Umbriel-Settings repository](https://github.com/0rz0rz0rz/Umbriel-Settings).

## Plugin

| Field | Value |
| --- | --- |
| ID | `0rz0rz0rz/umbriel-settings` |
| Entries | Bar widget: `settings`; panel: `folders` |

## Requirements

- Noctalia 5.4.0 or newer (plugin API 43).
- `python3` 3.11 or newer on `PATH`. The panel's logic runs in a bundled Python helper.
- `python-tomlkit` (the Python `tomlkit` module), used to edit the config while keeping its comments and
  formatting. Without it the panel explains what to install; user folders and default apps still work.
- `umbriel` on `PATH`, for setting defaults, ranges, validation before saving and **Inspect connected
  outputs**. Without it, settings can still be edited but are not checked before writing.
- Optional: `zenity` or `kdialog` for **Browse** on user folders, `gio` to open the standalone app, and
  `xdg-open` for **Edit file** (or an editor command set under **About**). Each button explains what is
  missing when its tool is not installed.

## Usage

Add the `settings` widget to a bar. It toggles the panel and shows a dot while edits are unsaved. You can
also toggle the panel directly:

```sh
noctalia msg panel-toggle 0rz0rz0rz/umbriel-settings:folders
```

- **Home** opens with a search box. Type setting names, words from their help, config keys
  (`border_width`), rule names or shortcuts; results jump straight to the setting. Below the search, cards
  lead to every page and show how many settings you have customized and how many edits are unsaved.
- **Setting pages** show one group at a time. Each row has the control, the default value, an info button
  with the full help and config key, an undo button and an eraser that removes the key so Umbriel's default
  applies. **Only customized** shows just what differs from the defaults.
- **Rules, outputs, devices and effects** are lists: open an entry to edit it, give rules a display name,
  reorder, duplicate or delete them.
- **Keybinds** are grouped. Build shortcuts from modifier chips and a key, pick an action from a searchable
  catalog with argument hints, and lock shortcuts so they can't be changed by accident.
- **User folders** and **Default apps** edit `user-dirs.dirs` and `mimeapps.list`, with a searchable app
  list and per-MIME-type associations.
- **Title-bar colors follow Noctalia**: on Colors → Title bar, the two background colors have an
  **Opacity** slider and **KDE** / **KDE header** buttons. A button makes the color follow Noctalia's palette
  at that opacity: after you save once, every palette change updates it, even with the panel closed. Typing
  a fixed color stops following.
- **About** shows the version, which options of your Umbriel version have no setting here yet, and the
  editor command **Edit file** uses.

Nothing is written until you press **Review & save** (Ctrl+S). The review lists every change in words,
shows the file diff and validates the new file with `umbriel config validate` first: if Umbriel rejects it,
nothing is written and each problem links to its setting. Edits survive closing the panel and restarting
Noctalia as a draft until you save or discard them.

Keys: Ctrl+F search, Ctrl+S review, Alt+Left back, Esc close.

## Settings

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| `display` | `select` | `icon` | What the bar widget shows: `icon` (icon only, with a dot while edits are unsaved), `icon_text` (icon and text) or `text` (text only). A vertical bar always shows only the icon. |

## Notes

- **Files read**: the Umbriel config (the path last chosen in the panel or app, else
  `~/.config/umbriel/config.toml`), `user-dirs.dirs`, `mimeapps.list`, installed `.desktop` files,
  `kdeglobals`/qt6ct color files when you choose KDE colors for title bars, and `noctalia-config.toml` plus
  the palette file for title bars that follow Noctalia.
- **Files written**, only when you save, restore or delete backups: the Umbriel config (validated first,
  written atomically, symlinks refused), `$XDG_CONFIG_HOME/user-dirs.dirs` and
  `$XDG_CONFIG_HOME/mimeapps.list` (other entries and MIME fallbacks are kept). A timestamped backup is
  made before every write (the newest 10 config backups are kept), under `$XDG_DATA_HOME/umbriel-settings/`, which also stores the chosen config
  path, rule names, keybind locks and the editor command. Panel drafts and cache live in Noctalia's plugin
  data directory.
- **Title bars that follow Noctalia**, only when you press **KDE** / **KDE header**: the plugin writes the
  user template `~/.config/noctalia/templates/umbriel-titlebar.toml` and its `umbriel_titlebar` entry in
  `noctalia-config.toml` (backed up first), plus `~/.config/umbriel-settings/titlebar_apply.py`. On every
  palette change Noctalia renders `~/.config/umbriel-settings/titlebar-colors.toml` and runs that script as
  the entry's `post_hook`. The script sets only `background` / `background_unfocused` in
  `[colors.title_bar]` of the Umbriel config. The config is edited directly because Noctalia's built-in
  umbriel template always puts `noctalia.toml` last among the includes.
- **Processes**: `python3 -B umbriel_settings.py <command>` with JSON request and response files in the
  plugin data directory; `umbriel config validate` (on a temporary `.umbriel-settings-*.toml` copy next to
  the config, removed afterwards), `umbriel config schema --json` and
  `umbriel outputs --json`; `zenity`/`kdialog` for the folder picker; `gio launch` to open the standalone
  app; `xdg-open` or your editor command to open the config. The last three run only when you press their
  buttons. Noctalia itself runs `python3 titlebar_apply.py` after palette changes while a title-bar color
  follows Noctalia.
- **Network**: none.
- `umbriel_core/` is the plain-Python config library shared with the standalone app, bundled so the plugin
  works on its own. `app.luau` is the standalone app's layout; it is not listed in `plugin.toml`, so
  Noctalia never loads it.
- Licensed under the MIT License; see `LICENSE`.
