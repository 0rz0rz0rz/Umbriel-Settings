---
name: edit-controls
description: "Use when changing how Umbriel Settings looks or behaves visually: controls, field rows, navigation, sidebar, page layout, theme colors and fonts (shared Luau UI + web renderer), or when updating the README screenshots."
---

# Edit controls and layout

## New app and plugin (shared Luau UI)

- What a row or page contains is decided in Luau and is the same in both frontends: `ui/fields.luau` (one row per field kind), `ui/kit.luau` (header, cards, badges, notices, `navRow`), `ui/sidebar.luau` (app sidebar), `pages/*.luau`. See `edit-noctalia-panel`.
- How a `ui.*` node looks in the app is decided by `python/umbriel_settings/host/web/renderer.js` (one builder per kind: layout props → flexbox, button variants, toggle, slider, select, input, colorPicker, markdown, glyph) and `style.css`. Match Noctalia's look (control heights sm 32 / md 38, radii scaled by `--radius-scale`, theme roles as CSS variables like `--primary`, `--surface_container`); never hard-code colors.
- Theme roles and fonts: `umbriel_core/noctalia_theme.py` (`load_roles`, `shell_style`, `css_variables`), watched by `host/theme.py`.
- Accessibility in `renderer.js`: icon-only buttons and clickable containers get `aria-label` from `tooltip` and clickable containers `role=button`; switches, inputs, sliders and the color picker are labelled. Give every icon-only button a tooltip (`tests/test_app_render.py` fails otherwise).
- Keyed reuse matters: inputs stay uncontrolled (text set only on creation), `focus` autofocuses on mount, `revealKey` scrolls into view. A wrong key loses focus while typing.
- Don't read `host/web/fonts/` (2.5 MB font, 130 KB map); look up a glyph with `grep -o '"<name>":[0-9]*' python/umbriel_settings/host/web/fonts/tabler-map.json`.
- Look at the result offscreen (temp config copy and data dir, your Noctalia/qt6ct colors). Each positional argument clicks the node showing that text:

  ```sh
  cd python
  QT_QPA_PLATFORM=offscreen PYTHONPATH=. python ../.claude/skills/edit-controls/render_app.py \
      --out <scratchpad>/app General "Review & save"   # [--config sample.toml] [--size 1280x860]
  ```

- Verify with `python tools/check.py plugin host`.
- The renderer only handles the `ui` kinds and props the pages use (`UI_KINDS` in `host/runtime.py`); a page that needs another Noctalia kind or prop (e.g. `ui.progress`, a multiline input) adds it there and in `renderer.js`/`style.css`.
- `render_app.py` and `render_docs.py` share their setup and teardown in `_render_common.py`.
- README screenshots after a visible change to Home: `render_docs.py` (same `cd python` + offscreen env, optional
  `--out <scratchpad>` to preview) rewrites `docs/home-app.png` (app, 1280×860), `docs/home-plugin.png` and the
  plugin's `noctalia-plugin/umbriel-settings/screenshot.png` (panel.luau in the web view, 1028×808 with Noctalia's
  24 px margin). It uses Umbriel's sample config shown as `~/.config/umbriel/config.toml` and temporary data dirs,
  so no personal paths or settings appear. After a visible change to the Outputs page: `render_docs.py --page
  outputs` rewrites `docs/outputs-plugin.png` and the plugin's `screenshot-outputs.png` (three made-up displays
  from a wrapper `umbriel` that answers `outputs --json`, the first one the default). Look at the PNGs before
  committing.
- Plugin thumbnail (`noctalia-plugin/umbriel-settings/thumbnail.webp`, the plugin-store card): run
  `QT_QPA_PLATFORM=offscreen python .claude/skills/edit-controls/render_thumbnail.py` from the repo root
  (`--out <scratchpad>/t.webp` to preview). It drives Noctalia's own
  [thumbnail generator](https://assets.noctalia.dev/plugins/thumbnail-generator.html), which the
  community-plugins rules require: it downloads the page and its html-to-image script into a temp dir and
  fills in `plugin.toml`'s name and tags, a one-line description and the Mint accent. The card's screenshot
  frame is small (588×331, tilted), so the README shot would turn to mush. Instead it renders its own panel shot
  (16:9 at 800×450, 2× density, no margin), exports the card at 2× and draws it down to 960×540 before the
  page's WebP encoder. It needs network access. Regenerate it whenever the panel's look changes, and always
  before a community-plugins submission or update.
