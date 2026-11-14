---
name: test-noctalia-plugin
description: "Use when adding or fixing tests for the Noctalia plugin, the shared Luau UI (panel and app layouts), or the umbriel_settings.py helper."
---

# Test the plugin and the shared UI

- `unittest` files under `noctalia-plugin/tests/`:
  - `test_umbriel_settings.py`: helper commands (meta, read, preview, save, entries, maps, keybinds and locks, backups, config path) with a fake `umbriel` on `PATH`, plus a real-`umbriel` round trip on the stock config (skipped without it).
  - `test_user_dirs.py` / `test_default_apps.py`: desktop files through `desktop`/`desktop-save`/`extension`, and the standalone launcher.
  - `test_panel.py`: builds fixtures with the real helper, then runs under plain `lua`: `panel_test.lua` (plugin layout flows), `app_test.lua` (app layout: sidebar, search, locale) and `bar_test.lua`. Skipped without `lua`.
- `harness.lua` is the shared Noctalia API mock: JSON codec, lexical `require` with private module globals, `H.start(name, app)`, `H.env` for `getenv`, helper replies per command in `replies`. A new API the UI uses must be added here and in `python/umbriel_settings/host/api.py`.
- Drive the UI through node props (`onClick`, `onChange`) found by key or text; assert on texts. Check that a new assertion can fail.
- Use temp `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_DATA_DIRS`; never write real config or touch the live Noctalia session.
- For the same flows in the app host (lupa, real helper in-process), extend `tests/test_host_runtime.py`.
- Run: `python tools/check.py plugin host` (or one file with `python -m unittest discover -s noctalia-plugin/tests -p 'test_x.py'`). The harness doesn't prove live rendering or the CPU budget.
