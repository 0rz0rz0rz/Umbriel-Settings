---
name: update-screenshots
description: "Use when the README screenshots (docs/*.png, the plugin's screenshot*.png) or the plugin-store thumbnail (thumbnail.webp) must be regenerated after a visible change, or before a community-plugins submission or update."
---

# Update screenshots and the plugin thumbnail

Scripts live in `.claude/skills/edit-controls/` and run from the repo root (`_render_common.py` sets offscreen Qt
and the import path). They use Umbriel's sample config, shown as `~/.config/umbriel/config.toml`, and temporary
data dirs, so no personal paths or settings appear; the theme follows your Noctalia/qt6ct colors.

- Home changed: `python .claude/skills/edit-controls/render_docs.py` (`--out <scratchpad>` to preview) rewrites
  `docs/home-app.png` (app, 1280×860) and `noctalia-plugin/umbriel-settings/screenshot.png` (panel.luau in the
  web view, 1028×808 with Noctalia's 24 px margin). The root README shows the plugin folder's screenshots, so
  each image exists once.
- Outputs page changed: `render_docs.py --page outputs` rewrites the plugin's `screenshot-outputs.png` (three
  made-up displays from a wrapper `umbriel` that answers `outputs --json`).
- Panel look changed, and always before a community-plugins submission or update:
  `python .claude/skills/edit-controls/render_thumbnail.py` (`--out <scratchpad>/t.webp` to preview; needs
  network) drives Noctalia's own thumbnail generator (required by the community-plugins rules) and writes
  `noctalia-plugin/umbriel-settings/thumbnail.webp` (960×540, from its own 800×450 panel shot at 2× density).

Look at every PNG/WebP before committing. Images are in `.ignore`; open them with Read, not grep.
