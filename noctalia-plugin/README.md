# Umbriel Settings for Noctalia

A Noctalia 5 plugin that edits your whole Umbriel configuration, XDG user folders and default apps from a
shell panel. The standalone app runs the same interface code (`lib/`, `ui/`, `pages/`) with a sidebar
(`app.luau`) and the same core (`python/umbriel_core`), so both edit the config the same way and share
backups, rule names and keybind locks.

Requirements, usage and the files it touches: [plugin README](umbriel-settings/README.md). This page covers
running it from a checkout and developing it.

## Run from a checkout

```sh
noctalia plugins lint /path/to/Umbriel-Settings/noctalia-plugin/umbriel-settings
noctalia msg plugins source add umbriel-settings path /path/to/Umbriel-Settings/noctalia-plugin
noctalia msg plugins enable 0rz0rz0rz/umbriel-settings
noctalia msg panel-toggle 0rz0rz0rz/umbriel-settings:folders
```

Then add the `0rz0rz0rz/umbriel-settings:settings` widget to a bar. After changing `plugin.toml`, run
`noctalia msg config-reload`.

**Old plugin ID** `umbriel-settings/Umbriel-GUI-Plugin` (before the 0.1.x versions): run
`noctalia msg config-reload`, `noctalia msg plugins disable umbriel-settings/Umbriel-GUI-Plugin`, enable the new
ID and re-add the bar widget. Drafts start fresh; config backups are kept (they live in the app's data folder).

## Development

| Part | Used by |
| --- | --- |
| `lib/`, `ui/`, `pages/` (UI), `umbriel_settings.py` (helper) | plugin and app |
| `panel.luau`, `bar.luau`, `plugin.toml` | plugin |
| `app.luau` (not in `plugin.toml`, so Noctalia never loads it) | app |
| `umbriel_core/` (copy of `python/umbriel_core`: edit the original, then run `tools/sync_plugin_core.py`) | plugin |

The panel writes a JSON request file, runs `python3 -Xpycache_prefix=<data>/pycache umbriel_settings.py <command> --request F --response G`
and reads the response file (helper output and argv are size-limited); the app calls the same commands
in-process. Commands that write (save, restore, desktop-save, …) hold `write.lock` in the shared data
directory, so the plugin and the app never write at the same time (a writer waits up to 20 s for it; write
commands get a 60 s timeout, and once a file is written, later failures are reported as `warnings`). Shared UI code must parse as both Luau and Lua 5.4 (the app runs it with lupa), stay within
Noctalia's 25 ms per-callback CPU budget, and use only the API the app host implements
(`python/umbriel_settings/host/api.py`).

```sh
python tools/check.py plugin host   # plugin tests, Lua/Luau parse, plugin lint, then the app host tests
```

`test_panel.py` drives `panel.luau`, `app.luau` and `bar.luau` under plain `lua` with a mocked Noctalia API
(`tests/harness.lua`) and real helper output (`panel_test.lua`, `state_test.lua`, `app_test.lua`, `bar_test.lua`,
`budget_test.lua`; shared Python fixtures in `tests/support.py`); live rendering and the real CPU budget need a
running Noctalia. One test file: `python tools/check.py test_panel`.
