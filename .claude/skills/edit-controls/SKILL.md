---
name: edit-controls
description: "Use when changing how Umbriel Settings looks in the app: the web renderer (renderer.js, style.css), control styling, theme colors, fonts, radii and design tokens, or when checking a visual change with offscreen renders. Page structure and behavior: edit-noctalia-panel; README screenshots and the plugin thumbnail: update-screenshots."
---

# Edit controls and layout

## New app and plugin (shared Luau UI)

- What a row or page contains is decided in Luau and is the same in both frontends: `ui/fields.luau` (one row per field kind), `ui/kit.luau` (header, cards, badges, notices, `navRow`), `ui/sidebar.luau` (app sidebar), `pages/*.luau`. See `edit-noctalia-panel`.
- Sizes in Luau come from `kit.RADIUS` and `kit.FONT` (`ui/kit.luau`); add a token rather than a literal. Radii must use `kit.RADIUS`: the plugin scales those tokens by Noctalia's corner roundness (the app scales in CSS).
- How a `ui.*` node looks in the app is decided by `python/umbriel_settings/host/web/renderer.js` (find builders with `grep -n "^function\|kind === " renderer.js`; one builder per kind: layout props → flexbox, button variants, toggle, slider, select, input, colorPicker, markdown, glyph) and `style.css`. Match Noctalia's look (control heights sm 32 / md 38, radii scaled by `--radius-scale`, theme roles as CSS variables like `--primary`, `--surface_container`); never hard-code colors.
- Theme roles and fonts: `umbriel_core/noctalia_theme.py` (`load_roles`, `shell_style`, `css_variables`), watched by `host/theme.py`.
- Accessibility in `renderer.js`: icon-only buttons and clickable containers get `aria-label` from `tooltip` and clickable containers `role=button`; switches, inputs, sliders and the color picker are labelled. Give every icon-only button a tooltip (`tests/test_app_render.py` fails otherwise).
- Keyed reuse matters: inputs stay uncontrolled (text set only on creation), `focus` autofocuses on mount, `revealKey` scrolls into view. A wrong key loses focus while typing.
- Don't read `host/web/fonts/` (2.5 MB font, 130 KB map); look up a glyph with `grep -o '"<name>":[0-9]*' python/umbriel_settings/host/web/fonts/tabler-map.json`.
- Look at the result offscreen (temp config copy and data dir, your Noctalia/qt6ct colors). Each positional argument clicks the node showing that text:

  ```sh
  python .claude/skills/edit-controls/render_app.py --out <scratchpad>/app General "Review & save"
  # [--config sample.toml] [--size 1280x860]; _render_common sets offscreen Qt and the import path
  ```

- Verify with `python tools/check.py plugin host`.
- The renderer only handles the `ui` kinds and props the pages use (`UI_KINDS` in `host/runtime.py`); a page that needs another Noctalia kind or prop (e.g. `ui.progress`, a multiline input) adds it there and in `renderer.js`/`style.css`.
- `render_app.py` and `render_docs.py` share their setup and teardown in `_render_common.py`.
- README screenshots and the plugin thumbnail after a visible change: `update-screenshots`.
