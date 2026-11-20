---
name: edit-noctalia-panel
description: "Use when changing the shared Luau UI (Noctalia panel and standalone app): pages, forms, controls, navigation, sidebar, save/review flow, menus or helper callbacks."
---

# Edit the shared Luau UI

The same Luau code runs in the Noctalia panel (`panel.luau`) and in the standalone app (`app.luau`, via lupa and a web view). Change it once; check both. The module table and the rules (inputs, store setters, 25 ms budget, syntax, tooltips, menus) are in `.claude/rules/noctalia-plugin.md` (loads with any `.luau` file), page details in `noctalia-plugin-pages.md` (pages, `ui/fields.luau`), helper commands in `core-helper.md`.

1. Find the function instead of reading whole modules: `grep -n "^function\|^local function\|function ctx\." <file>`.
2. Pages return `{ header = {...}, content = {...} }`. A new route needs a branch in `body()` (`lib/shell.luau`) and, for a nav page, `ctx.openPage`; reuse `kit` pieces (`optionRow`, `confirmButton`, `card`, `navRow`, `iconButton`, `filterBox`, tokens `RADIUS`/`FONT`) instead of building rows by hand. A page showing what the running Umbriel reports calls `ctx.watchLive(events, onChange)` while rendering to refresh itself.
3. App-only or plugin-only behavior: branch on `ctx.isApp` (no close button and no "Standalone app" button in the app). App options arrive in `ctx.options` (`appVersion`, `validateDefault`, `rebuildDefault`, `initialConfig`).
4. A new capture chord also goes into `plugin.toml` `capture_keys` and `KEYS` in `host/web/renderer.js`. A new `ui` kind or prop may need a builder in `renderer.js` (see `edit-controls`); a new Noctalia API also needs `host/api.py` and `noctalia-plugin/tests/harness.lua`. Check it against the target Noctalia API level first.
5. Drag and drop: `ui.dropZone` with `onDrop = "onDrop"` (entry global → `ctx.dropHandler`, set during render); keep a button alternative, as there is no keyboard drag.
6. Test (`add-test`: `panel_test.lua`, `state_test.lua`, `app_test.lua` or `tests/test_host_runtime.py`), verify with `python tools/check.py plugin host` (`verify-changes`) and look at the app with `.claude/skills/edit-controls/render_app.py`. None of these prove live Noctalia rendering.
