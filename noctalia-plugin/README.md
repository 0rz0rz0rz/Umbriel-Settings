# Umbriel Settings for Noctalia

A Noctalia 5 plugin that edits your whole Umbriel configuration from a shell
panel: every setting page, window/layer/workspace/security rules, outputs,
scratchpads, input devices, effects, animation curves, environment variables
and keybinds, plus XDG user folders and default applications.

The standalone Umbriel Settings app runs this plugin's own interface code
(`lib/`, `ui/`, `pages/`) with a sidebar layout (`app.luau`), and both use the
same core (`python/umbriel_core`). So the panel and the app look alike, edit the
config the same way and share backups, rule names and keybind locks.

Users: see the plugin's own [README](umbriel-settings/README.md) for requirements, usage, settings and the
files it reads and writes. This page covers running it from a checkout and developing it.

## Run from a checkout

```sh
noctalia plugins lint /path/to/Umbriel-Settings/noctalia-plugin/umbriel-settings
noctalia msg plugins source add umbriel-dev path /path/to/Umbriel-Settings/noctalia-plugin
noctalia msg plugins enable 0rz0rz0rz/umbriel-settings
noctalia msg panel-toggle 0rz0rz0rz/umbriel-settings:folders
```

Then add the `0rz0rz0rz/umbriel-settings:settings` widget to a bar. Run `noctalia msg config-reload` after
changing the plugin's manifest.

Upgrading from 0.2.x: the plugin ID changed from `umbriel-settings/Umbriel-GUI-Plugin` to
`0rz0rz0rz/umbriel-settings` (community plugin rules). Run `noctalia msg config-reload`, disable the old ID
(`noctalia msg plugins disable umbriel-settings/Umbriel-GUI-Plugin`), enable the new one and re-add the bar
widget. Panel drafts and cache start fresh; config backups are unaffected (they live in the app's data
directory).

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
app host implements (`python/umbriel_settings/host/api.py`).

```sh
python tools/check.py plugin host   # plugin tests, luac, lint, then the app host tests
```

`test_panel.py` drives `panel.luau` and `app.luau` under plain `lua` with a mocked
Noctalia API (`tests/harness.lua`) and real helper output; it does not prove live
rendering or the CPU budget, which need a running Noctalia.
