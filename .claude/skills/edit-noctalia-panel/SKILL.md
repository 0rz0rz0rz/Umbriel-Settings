---
name: edit-noctalia-panel
description: "Use when changing the shared Luau UI (Noctalia panel and standalone app): pages, forms, controls, navigation, sidebar, save/review flow, menus or helper callbacks."
---

# Edit the shared Luau UI

The same Luau code runs in the Noctalia panel (`panel.luau`) and in the standalone app (`app.luau`, via lupa and a web view). Change it once; check both.

- Find the module instead of reading everything (`grep -n "^function\|^local function\|function ctx\." <file>`):
  - `lib/shell.luau`: ctx, navigation stack (`go/back/replace/home/openPage`), loading, save bar, `onKey`, menus; routes dispatch in `body()`.
  - `panel.luau` / `app.luau`: only layout and entry globals.
  - `lib/store.luau` (unsaved edits, `changeSet`, drafts), `lib/helper.luau`, `lib/search.luau`.
  - `ui/fields.luau` (one row per field kind, locale-aware numbers), `ui/kit.luau` (header, cards, badges, notices, `navRow`, `plural`), `ui/sidebar.luau` (app only).
  - `pages/*.luau`: `home`, `form`, `entries`, `maps`, `keybinds`, `desktop`, `review`.
- Pages return `{ header = {...}, content = {...} }`. New routes need a branch in `body()` and, for nav pages, `ctx.openPage`.
- App-only or plugin-only behavior: branch on `ctx.isApp` (e.g. no close button or "Standalone app" button in the app). App options arrive in `ctx.options` (`validateDefault`, `rebuildDefault`, `initialConfig`).
- Field metadata comes from the helper's `meta`; never hard-code field lists. New settings come from `umbriel_core/fields.py`.
- Edits go through `store` (`setField`/`unsetField`, `entryOp`, `mapSet`/`mapRemove`, `keybindsDirty`); the helper replays them on save. Entry ops use zero-based indices.
- Inputs are uncontrolled: stable keys, bump `ctx.view.gen[key]` to replace text. `ui.select` is zero-based. Never read `.children` of a built node; build lists first.
- 25 ms CPU budget: one open group per page, capped lists, `ctx.renderSoon()` for slider drags.
- Syntax: Luau ∩ Lua 5.4/5.5 (no `continue`, `+=`, type annotations, backtick strings). Glyphs from Tabler (`tests/test_host_bridge.py` checks names).
- Context-menu `onActivate` names an entry global; the app host has no context menus, so keep a visible button for every menu action.
- Check features against the target Noctalia API level before using them; a new API also needs the app host (`host/api.py`) and the mock (`tests/harness.lua`).
- Test with `test-noctalia-plugin` (extend `panel_test.lua` / `app_test.lua`, or `tests/test_host_runtime.py`), verify with `python tools/check.py plugin host`, and look at the app with `.claude/skills/edit-controls/render_app.py`. Neither proves live Noctalia rendering.
