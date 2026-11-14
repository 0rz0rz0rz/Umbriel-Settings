# Umbriel Settings for Noctalia

A Noctalia 5 plugin that edits your whole Umbriel configuration from a shell
panel: every setting page, window/layer/workspace/security rules, outputs,
scratchpads, input devices, effects, animation curves, environment variables
and keybinds, plus XDG user folders and default applications.

The standalone Umbriel Settings app runs this plugin's own interface code
(`lib/`, `ui/`, `pages/`) with a sidebar layout (`app.luau`), and both use the
same core (`python/umbriel_core`). So the panel and the app look alike, edit the
config the same way and share backups, rule names and keybind locks.

## Requirements

- Noctalia 5.4.0 or newer (plugin API 43).
- Python 3.11 or newer on `PATH`, with **tomlkit** (Arch: `pacman -S python-tomlkit`,
  otherwise `pip install --user tomlkit`). Without tomlkit the panel explains what
  to install; user folders and default apps still work.
- The `umbriel` CLI for defaults, ranges and validation. Without it, settings
  can still be edited but are not checked before writing.
- Optional: `zenity` or `kdialog` (Browse for folders), `gio` (open the
  standalone app), `xdg-open` (Edit file).

## Install

```sh
noctalia plugins lint /path/to/Umbriel-GUI/noctalia-plugin/Umbriel-GUI-Plugin
noctalia msg plugins source add umbriel-dev path /path/to/Umbriel-GUI/noctalia-plugin
noctalia msg plugins enable umbriel-settings/Umbriel-GUI-Plugin
noctalia msg panel-open umbriel-settings/Umbriel-GUI-Plugin:folders
```

Then add the `umbriel-settings/Umbriel-GUI-Plugin:settings` widget to a bar. Its
**Umbriel-GUI** button toggles the panel and shows a dot while edits are unsaved.
Run `noctalia msg config-reload` after updating the plugin's manifest.

Upgrading from 0.1.x: the plugin ID changed from `umbriel-settings/user-folders`
to `umbriel-settings/Umbriel-GUI-Plugin`. Run `noctalia msg config-reload`,
disable the old ID (`noctalia msg plugins disable umbriel-settings/user-folders`),
enable the new one, and re-add the bar widget. Panel drafts and cache start fresh;
config backups are unaffected (they live in the app's data directory).

## Using it

- **Home** opens with a search box. Type anything: setting names, words from
  their help, config keys (`border_width`), rule names or shortcuts. Results jump
  straight to the setting. Below the search, cards lead to every page and show
  how many settings you have customized and how many edits are unsaved.
- **Setting pages** show one group at a time. Each row has the control, the
  default value, an ⓘ button with the full help and config key, ↶ to undo your
  edit and the eraser to remove the key so Umbriel's default applies. Turn on
  **Only customized** to see just what differs from the defaults.
- **Rules, outputs, devices and effects** are lists; open an entry to edit it,
  give rules a display name, reorder, duplicate or delete them. **Inspect
  connected outputs** adds a monitor with one of its real modes.
- **Keybinds** are grouped. Build shortcuts from modifier chips plus a key, pick
  actions from a searchable catalog with argument hints, set repeat/locked
  options, manage groups and lock shortcuts you never want to change by accident.
- **Default apps** uses a searchable app list with icons.

Nothing is written until you press **Review & save** (Ctrl+S). The review lists
every change in words, shows the file diff by section, and checks the new file
with `umbriel config validate` first: if Umbriel rejects it, nothing is written
and each problem links to its setting. **Tidy file layout** regroups the file in
canonical order with section banners (on by default only for files that
already have them).

Edits survive closing the panel (Esc) and even a Noctalia restart: they are kept
as a draft until you save or discard them. If the config changes on disk in the
meantime, setting edits are kept and rule/keybind edits are dropped with a note.

Keys: Ctrl+F search, Ctrl+S review, Alt+Left back, Esc close.

## Files

- Config: the path last chosen in the app or the panel
  (`$XDG_DATA_HOME/umbriel-config-gui/gui-config-path`), else
  `~/.config/umbriel/config.toml`. Change it at the bottom of the home page.
  Symlinked configs are refused; open the link's target instead. Included files
  are validated but not shown.
- Backups: a timestamped copy before every save or restore, in
  `$XDG_DATA_HOME/umbriel-config-gui/configs/<id>/backups/`, shared with the app.
  **Backups** on the home page compares, restores and deletes them.
- Desktop backups: `$XDG_DATA_HOME/umbriel-config-gui/backups/user-dirs.dirs.bak`
  and `mimeapps.list.bak`.
- Panel cache and drafts: Noctalia's plugin data directory, normally
  `~/.local/state/noctalia/plugins/data/umbriel-settings/Umbriel-GUI-Plugin/`.

## Development

| Part | Used by |
| --- | --- |
| `lib/`, `ui/`, `pages/` (shared UI) and `umbriel_settings.py` (helper) | plugin and app |
| `panel.luau`, `bar.luau`, `plugin.toml` | plugin |
| `app.luau` (sidebar layout; not listed in `plugin.toml`, so Noctalia never loads it) | app |
| `umbriel_core/` (copy of `python/umbriel_core`) | plugin |

`umbriel_settings.py` is the only helper. The panel writes a JSON request file,
runs `python3 -B umbriel_settings.py <command> --request F --response G` and reads
the response file (helper output and argv are size-limited). The app calls the
same commands in-process. Edit `python/umbriel_core`, never the copy here, and run
`tools/sync_plugin_core.py` (a test fails when the copy is stale).

Shared-UI code must parse as both Luau and Lua 5.4 (the app runs it with lupa),
stay within Noctalia's 25 ms per-callback CPU budget, and use only API calls the
app host implements (`python/umbriel_config_gui/host/api.py`).

```sh
python tools/check.py plugin host   # plugin tests, luac, lint, then the app host tests
```

`test_panel.py` drives `panel.luau` and `app.luau` under plain `lua` with a mocked
Noctalia API (`tests/harness.lua`) and real helper output; it does not prove live
rendering or the CPU budget, which need a running Noctalia.
