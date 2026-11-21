---
paths:
  - "noctalia-plugin/umbriel-settings/umbriel_settings.py"
  - "python/umbriel_core/**/*"
---

# Helper and core (`umbriel_settings.py`, `python/umbriel_core/`)

The app imports the helper in-process (`host/api.py` `runAsync`; `SLOW_HELPER_COMMANDS` on a 2-thread pool,
`LONG_HELPER_COMMANDS` (`wait-live`, `wait`) on a thread each); the plugin runs it with `python3`.

| File | Notes |
| --- | --- |
| `umbriel_settings.py` | `run(argv)` → stdout text (app calls in-process). Commands: `meta read preview (check: validate even unchanged) save set-config backups backup-diff restore delete-backups desktop desktop-save extension outputs windows layers xkb run-action focused-window wait-live wait kde-colors pick-folder pick-file list-dir app-command launch-app open-config set-editor about palette-template titlebar titlebar-follow` (titlebar ones per `config`). `outputs windows layers focused-window wait-live` map `umbriel` failures through `ask_umbriel` (here; readers in `umbriel_core/live.py`: one row per app id/namespace with an exact `pattern`; `wait_change(events, timeout)` reads `umbriel subscribe`, takes each event's first line as the baseline and answers on the first change of what a page shows (`_digest`), else null; `schema.run_umbriel` runs every `umbriel` call with `child_env()`; `schema.umbriel_executable()` finds it); `wait {seconds ≤ 5}` is a UI timer; `xkb` = `umbriel_core/xkb.py` catalog + `current`; `run-action` refuses `actions.run_block_reason` (checked on the `shlex` words, so quotes don't get past it; same lists in `meta.actions.blocked`, checked in `keybind_actions.luau` `blockReason` with quotes dropped) and runs `umbriel msg` (`msg_argv`: spawn keeps its command as one word, split off on any whitespace). `meta` has schema coverage, `targets` (`meta.UMBRIEL_VERSION`/`NOCTALIA_VERSION`; About shows them), per-page group help (`help.group_help`), labels without bracket notes (`help.split_label` → `unit special hint`, `restart`). `WRITE_COMMANDS` run under `paths.write_lock(data_dir)` (flock, 20 s; timeout → `code:"busy"`). `save`/`restore` return `warnings` for failures after the write (`state` may then be null → reload); `restore` validates; `desktop-save` saves each part on its own (`{part: {revision}}`, `errors:{part}`); `desktop` reads each file on its own (`error` per part) and adds `apps.names` for hidden assigned apps. SIGTERM → `SystemExit` (temp files cleaned). Empty request may be `[]`. Unexpected exceptions → `{ok:false, code:"internal"}` |
| `lib/titlebar.luau` + `umbriel_core/titlebar_theme.py` | KDE/KDE header buttons + opacity on `colors.title_bar.background(_unfocused)` → Noctalia user template `umbriel_titlebar` with one `# config: <path>` block per config; `post_hook` = `titlebar_apply.py <rendered>` (stdlib, copied to `~/.config/umbriel-settings/`; old `<rendered> <config>` still works) writes into each config (Noctalia's umbriel template keeps `noctalia.toml` last, so an include can't win). Color is queued as a normal edit; a fixed color stops following |

Rules:

- Edit `python/umbriel_core/`, then `tools/sync_plugin_core.py`; never the vendored copy. Desktop commands work without tomlkit.
- A new helper command: `COMMANDS` (+ `WRITE_COMMANDS` if it writes), `host/api.py` lanes if it waits, a reply or hold in `noctalia-plugin/tests/harness.lua` for UI tests, a case in `test_umbriel_settings.py` (fake `umbriel` in `support.py`).
- `legacy.migrate_data_dir` adopts rolling `.bak` files of releases up to 0.1.0-004; `paths.LEGACY_DIR_NAME` and the title-bar `OLD_*` paths cover 0.1.0-001…005.
