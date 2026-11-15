# Umbriel Settings

Edit your [Umbriel](https://github.com/noctalia-dev/umbriel) config, XDG user folders and default
applications without losing the comments and formatting of your files. It comes as a **standalone app**
(PySide6) and as a **[Noctalia](https://github.com/noctalia-dev/noctalia) shell plugin**. Both share the
same core and interface code, so they look and behave alike; the app adds a sidebar and doesn't need Noctalia.

| Standalone app | Noctalia plugin |
| --- | --- |
| ![Home page of the standalone app](docs/home-app.png) | ![Home page of the Noctalia plugin panel](docs/home-plugin.png) |

## Features

- **Every Umbriel setting**: general, appearance, colors, animation and curves, effects, input, layout,
  workspaces and keybinds, plus window, layer, workspace and security rules, outputs, scratchpads, input
  devices and environment variables.
- **Search** (Ctrl+F) over setting names, help text, config keys (`border_width`), rule names and shortcuts.
- **Clear rows**: control, default value, ⓘ help with the config key, ↶ undo, and an eraser that removes
  the key so Umbriel's default applies. **Only customized** hides settings at their default.
- **Lists** for rules, outputs, devices and effects: edit, name, reorder, duplicate, delete.
  **Inspect connected outputs** adds a monitor with one of its real modes.
- **Keybinds** in groups: build shortcuts from modifier chips, pick actions from a searchable catalog, set
  repeat/locked options, and lock shortcuts against accidental changes.
- **User folders and default apps** with folder pickers, a searchable app list and per-MIME-type choices.
- **Follows your theme** (Noctalia or qt6ct/KDE colors, see [Theming](#theming)) and your locale's decimal
  separator.
- **Title bars that follow Noctalia's palette** at an opacity you choose ([details](#title-bar-colors)).
- **About** shows the version and which options of your Umbriel version have no setting yet, and sets the
  editor for **Edit file**.

## Saving safely

Nothing is written until you press **Review & save** (Ctrl+S):

- The review lists every change in words and shows the file diff by section.
- **Check with Umbriel before writing** (on by default; `--no-validate` turns it off) runs
  `umbriel config validate` on a temporary copy. If Umbriel rejects it, nothing is written and each problem
  links to its setting. Skipped when `umbriel` isn't installed.
- **Tidy file layout** regroups the file in canonical order with section banners (may move comments). It is
  on by default only for files that already have banners; `--no-rebuild` turns it off.
- Every save or restore makes a timestamped backup (newest 10 kept). **Backups** on the home page compares,
  restores and deletes them. User folders, default apps and Noctalia's config get their own backups.
- Unsaved edits are kept as a draft when you close and restored next time, unless the file changed meanwhile.
- If the config changes on disk, it is reloaded: setting edits are kept, rule and keybind edits are dropped
  with a note.
- Symlinked files are refused; open the link's target instead.

## Install

There are two ways to get the app. The `umbriel` command is optional either way; with it, the app shows
defaults and ranges, checks your config before saving and compares its settings with your Umbriel version.

### Option 1: AppImage (easiest)

Download the latest `.AppImage` from the [releases](https://github.com/0rz0rz0rz/Umbriel-Settings/releases).
It bundles Python and every library, so nothing else needs to be installed:

```sh
chmod +x Umbriel-Settings-*.AppImage
./Umbriel-Settings-*.AppImage
```

### Option 2: From source

You need Python 3.11 or newer, PySide6 with QtWebEngine, tomlkit and lupa. First get the code:

```sh
git clone https://github.com/0rz0rz0rz/Umbriel-Settings.git
cd Umbriel-Settings
```

Then install the dependencies with your package manager:

```sh
# Arch Linux
sudo pacman -S python pyside6 qt6-webengine python-tomlkit python-lupa

# Debian 13 or newer
sudo apt install python3 python3-pyside6.qtwidgets python3-pyside6.qtwebenginewidgets \
    python3-pyside6.qtwebchannel python3-tomlkit python3-lupa

# Fedora
sudo dnf install python3 python3-pyside6 python3-tomlkit python3-lupa
```

Package names differ between distributions. If one is missing, use a virtual environment instead; it works
everywhere:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r python/requirements.txt
```

To use the Noctalia plugin instead of (or next to) the app, see [Noctalia plugin](#noctalia-plugin).

## Run

```sh
python python/umbriel-settings.py [path/to/config.toml]
```

Without a path it opens the config used last, else `~/.config/umbriel/config.toml` (switch files at the
bottom of the home page). Options: `--config PATH`, `--no-validate`, `--no-rebuild`, `--check-schema`
(compare the app's fields with your Umbriel and exit), `--version`. Keys: Ctrl+F search, Ctrl+S review,
Alt+Left back.

**Launch with a keybind** (in `[keybinds]` or on the Keybinds page; replace `/home/you`, quote paths with spaces):

```toml
# From a checkout (with a virtual environment, use .venv/bin/python instead of /usr/bin/python3)
"Mod+Shift+C" = "spawn /usr/bin/python3 /home/you/Applications/Umbriel-Settings/python/umbriel-settings.py"
# From the AppImage
"Mod+Shift+C" = "spawn /home/you/Applications/Umbriel-Settings-0.1.0-004-x86_64.AppImage"
# Works for any install: the desktop entry the app creates on first start
"Mod+Shift+C" = "spawn gio launch /home/you/.local/share/applications/umbriel-settings.desktop"
```

**AppImage build**: `appimage/build-appimage.sh` writes `dist/Umbriel-Settings-<version>-<arch>.AppImage`
(needs network, `python3` with `venv`, and FUSE or `APPIMAGE_EXTRACT_AND_RUN=1`). The desktop entry points
at the AppImage, so keep it at a stable path.

**Upgrading from `umbriel-config-gui`** (the old name): data moves to `$XDG_DATA_HOME/umbriel-settings`
automatically, and the desktop entry is replaced. By hand: point keybinds at `python/umbriel-settings.py`,
and change the Noctalia palette template's `output_path` (see below); until then the old palette file is
still read.

## Theming

The app uses the first available source and follows changes live:

1. **Noctalia's palette** (exact plugin colors). **About → Set up palette template** installs it for you
   (backing up `noctalia-config.toml`). By hand: save this as
   `~/.config/noctalia/templates/umbriel-settings-palette.conf`

   ```text
   # Written by Noctalia for Umbriel Settings; regenerated on every theme change.
   <* for name, value in colors *>
   {{ name }}={{ value.default.hex }}
   <* endfor *>
   ```

   and add to `~/.config/noctalia/noctalia-config.toml` (use full paths if your Noctalia doesn't expand
   `$XDG_CONFIG_HOME`):

   ```toml
   [theme.templates.user.umbriel_settings]
   input_path = "$XDG_CONFIG_HOME/noctalia/templates/umbriel-settings-palette.conf"
   output_path = "$XDG_CONFIG_HOME/umbriel-settings/noctalia-palette.conf"
   ```

2. **The qt6ct color scheme** (`color_scheme_path` in `~/.config/qt6ct/qt6ct.conf`, e.g. Noctalia's
   `noctalia.colors`).
3. **Your desktop's Qt palette.**

Font and corner roundness come from `font_family` and `corner_radius_scale` in Noctalia's `[shell]`. The
app's own dialogs also follow qt6ct's style, font, icons and colors when `QT_QPA_PLATFORMTHEME` is
`qt6ct`/`qt5ct` (needed in the AppImage); `UMBRIEL_QT_THEME=none` disables that, `=qt6ct` forces it.

### Title-bar colors

Umbriel draws the title bars of server-side decorated windows (`prefer_no_csd = true`) from
`[colors.title_bar]`. On **Colors → Title bar**, **Background** and **Background unfocused** have an
**Opacity** slider (stored as the color's alpha: 0.84 → `D6`) and two buttons:

- **KDE**: Noctalia's `primary_container` (focused) / `surface` (unfocused), like KDE window decorations.
- **KDE header**: `surface_container` / `surface`, like KDE headers.

A button makes the color **follow Noctalia**: it is queued as a normal edit, and after you save, every
palette change updates it, even with the app closed. A fixed color or the unlink button stops following.
Each config file follows on its own.

How it works: a Noctalia user template (`~/.config/noctalia/templates/umbriel-titlebar.toml`, entry
`umbriel_titlebar`) renders the colors to `~/.config/umbriel-settings/titlebar-colors.toml` and runs
`titlebar_apply.py`, which copies them into `[colors.title_bar]` of each following config and changes nothing
else. (An include can't do it: Noctalia's built-in umbriel template always loads `noctalia.toml` last.)

## Desktop settings

**User folders** are stored in `$XDG_CONFIG_HOME/user-dirs.dirs`, **default apps** in the
`[Default Applications]` section of `$XDG_CONFIG_HOME/mimeapps.list` (custom desktop-file IDs work too).
Other entries and comments are kept. Folders are recorded, not created or moved.

## Noctalia plugin

The plugin opens the same interface in a Noctalia panel, with a bar button that shows a dot while edits are
unsaved, and shares backups, rule names and keybind locks with the app. Setup:
[plugin README](noctalia-plugin/README.md).

## Files

`$XDG_DATA_HOME` defaults to `~/.local/share`, `$XDG_CONFIG_HOME` to `~/.config`.

| Path | Contents |
| --- | --- |
| Your Umbriel config | Saved changes; custom keybind groups are TOML comments |
| `$XDG_DATA_HOME/umbriel-settings/` | `gui-config-path` (last config), `configs/<id>/` (backups, rule names, keybind locks), `backups/` (user folders, default apps), `noctalia-backups/`, `app-ui/` (drafts, cache, icons), `editor-command` |
| `$XDG_CONFIG_HOME/umbriel-settings/` | `noctalia-palette.conf` (from Noctalia), `titlebar-colors.toml`, `titlebar_apply.py`, `*.titlebar.bak` (config before the script's last change) |
| `$XDG_CONFIG_HOME/noctalia/templates/` | `umbriel-settings-palette.conf`, `umbriel-titlebar.toml` (entries in `noctalia-config.toml`) |
| `$XDG_DATA_HOME/applications/umbriel-settings.desktop`, `…/icons/hicolor/128x128/apps/umbriel-settings.png` | Desktop entry and icon |

Custom icon: replace `python/umbriel_settings/assets/icon.png` with your own PNG (transparency is kept), or delete it
and add `icon.jpg`/`icon.jpeg`. The first of `icon.png`, `icon.jpg`, `icon.jpeg` that exists is used; the built-in
icon is used if none exists or the file is invalid.

## Versions

| Item | Version |
| --- | --- |
| App (`python/umbriel_settings/__init__.py`) | `0.1.0-004` |
| AppImage (latest release) | `0.1.0-004` |
| Noctalia plugin (`plugin.toml`) | `0.1.4` |

The app version is `<Umbriel version>-<revision>`; each build raises the revision, which restarts at `001`
when Umbriel's version changes. The plugin uses plain `MAJOR.MINOR.PATCH` (`0.1.0-004` → `0.1.4`).

## Development

```text
python/umbriel_core/               Shared logic: fields, schema, TOML edits, rules, keybinds, desktop files, backups, theme
noctalia-plugin/umbriel-settings/  lib/ ui/ pages/ (shared Luau UI), umbriel_settings.py (commands over the core),
                                   panel.luau + bar.luau (plugin), app.luau (app layout)
python/umbriel_settings/           The app: lupa runs the Luau UI (host/runtime.py), a web view draws it (host/web/)
appimage/  tools/  tests/  noctalia-plugin/tests/
```

```sh
python tools/check.py            # checks for your changed files, one line each
python tools/check.py all        # core, plugin (CPU budget, Lua/Luau parse), app host (web render), schema, ruff, shellcheck
python tools/sync_plugin_core.py # after editing python/umbriel_core (the plugin bundles a copy)
```

CI runs the same checks (except the schema check) on Python 3.11, 3.12 and 3.13. Dependency ranges and lint
settings: `pyproject.toml`; AppImage pins: `python/requirements.txt`. Icons: [Tabler Icons](https://tabler.io/icons)
(MIT, license in `host/web/fonts/`).

## License

MIT, see [LICENSE](LICENSE).

> **Disclaimer:** This project was created entirely by AI.

## Related projects

- [Umbriel](https://github.com/noctalia-dev/umbriel): the Wayland compositor this app configures.
- [Noctalia](https://github.com/noctalia-dev/noctalia): the shell the plugin runs in and whose theme the app follows.
