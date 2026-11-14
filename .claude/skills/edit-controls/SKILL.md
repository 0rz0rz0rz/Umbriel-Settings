---
name: edit-controls
description: "Use when changing how Umbriel Settings looks or behaves visually: controls, field rows, navigation, sidebar, page layout, theme colors and fonts (shared Luau UI + web renderer)."
---

# Edit controls and layout

## New app and plugin (shared Luau UI)

- What a row or page contains is decided in Luau and is the same in both frontends: `ui/fields.luau` (one row per field kind), `ui/kit.luau` (header, cards, badges, notices, `navRow`), `ui/sidebar.luau` (app sidebar), `pages/*.luau`. See `edit-noctalia-panel`.
- How a `ui.*` node looks in the app is decided by `python/umbriel_settings/host/web/renderer.js` (one builder per kind: layout props → flexbox, button variants, toggle, slider, select, input, colorPicker, markdown, glyph) and `style.css`. Match Noctalia's look (control heights sm 32 / md 38 / lg 44, radii scaled by `--radius-scale`, theme roles as CSS variables like `--primary`, `--surface_container`); never hard-code colors.
- Theme roles and fonts: `umbriel_core/noctalia_theme.py` (`load_roles`, `shell_style`, `css_variables`), watched by `host/theme.py`.
- Keyed reuse matters: inputs stay uncontrolled (text set only on creation), `focus` autofocuses on mount, `revealKey` scrolls into view. A wrong key loses focus while typing.
- Don't read `host/web/fonts/` (2.5 MB font, 130 KB map); look up a glyph with `grep -o '"<name>":[0-9]*' python/umbriel_settings/host/web/fonts/tabler-map.json`.
- Look at the result offscreen (temp config copy and data dir, your Noctalia/qt6ct colors). Each positional argument clicks the node showing that text:

  ```sh
  cd python
  QT_QPA_PLATFORM=offscreen PYTHONPATH=. python ../.claude/skills/edit-controls/render_app.py \
      --out <scratchpad>/app General "Review & save"   # [--config sample.toml] [--size 1280x860]
  ```

- Verify with `python tools/check.py plugin host`.
