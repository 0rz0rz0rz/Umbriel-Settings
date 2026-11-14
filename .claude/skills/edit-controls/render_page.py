"""Render one Umbriel Settings page headlessly to PNG files for a visual layout check.

Run from python/:
    QT_QPA_PLATFORM=offscreen PYTHONPATH=. python ../.claude/skills/edit-controls/render_page.py \
        --page "Window rules" --out <scratchpad>/rules [--config sample.toml] [--entry 1] [--size 1500x1000]

Writes <out>-window.png (whole window, unsaved) and <out>-card-<n>.png for every settings
card on the page, because scrolling a QScrollArea does not take effect offscreen. Uses a
temporary copy of the config and temporary GUI data directories; never the real config.
Offscreen font metrics are wider than on the desktop, so judge alignment, not exact widths.
"""

import argparse
import os
import shutil
import sys
import tempfile
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

SAMPLE = """[general]
[[window_rule]]
match.app_id = "^dev.noctalia.Noctalia$"
open_floating = true
default_floating_size_px = {width = 800, height = 600}

[[window_rule]]
match.title = "^Picture-in-Picture$"
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", required=True, help="sidebar page name, e.g. Appearance or Window rules")
    parser.add_argument("--out", required=True, help="output path prefix, e.g. <scratchpad>/page")
    parser.add_argument("--config", help="TOML file to copy and load instead of the built-in sample")
    parser.add_argument("--entry", type=int, default=0, help="entry row to select on rule/output pages")
    parser.add_argument("--size", default="1500x1000")
    args = parser.parse_args()

    app = QApplication(sys.argv[:1])
    from umbriel_config_gui import common, desktop, settings_layout, state
    from umbriel_config_gui.common import PaletteReadability, apply_interaction_styles
    from umbriel_config_gui.qt6ct_theme import apply_qt6ct_theme
    from umbriel_config_gui.settings_layout import CollapsibleGroup
    from umbriel_config_gui.window import Window

    app.setApplicationDisplayName("Umbriel Settings")
    apply_qt6ct_theme(app)
    app.palette_readability = PaletteReadability(app)
    apply_interaction_styles(app)

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "config.toml")
        if args.config:
            shutil.copyfile(args.config, path)
        else:
            with open(path, "w", encoding="utf-8") as config:
                config.write(SAMPLE)
        with (
            patch.object(state, "PATH", path),
            patch.object(common, "GUI_DATA_DIR", os.path.join(directory, "data")),
            patch.object(settings_layout, "_GROUP_EXPANSION_PATH", os.path.join(directory, "state.json")),
            patch.object(settings_layout, "_group_expansion_states", {}),
            patch.object(desktop, "USER_DIRS", os.path.join(directory, "user-dirs.dirs")),
            patch.object(desktop, "MIMEAPPS_PATH", os.path.join(directory, "mimeapps.list")),
        ):
            window = Window(path)
            width, height = (int(value) for value in args.size.split("x"))
            window.resize(width, height)
            window.show()
            app.processEvents()
            tabs = window.side_tabs
            if args.page not in tabs.page_rows:
                sys.exit(f"Unknown page {args.page!r}; choose from: {', '.join(tabs.page_rows)}")
            tabs.nav.setCurrentRow(tabs.page_rows[args.page])
            for _ in range(3):
                app.processEvents()
            page = tabs.page_widgets[args.page]
            entry_list = getattr(page, "list", None)
            if entry_list is not None and entry_list.count() > args.entry:
                entry_list.setCurrentRow(args.entry)
                app.processEvents()
            window.grab().save(f"{args.out}-window.png")
            cards = [card for card in page.findChildren(CollapsibleGroup) if card.isVisible()]
            for index, card in enumerate(cards, 1):
                card.grab().save(f"{args.out}-card-{index}.png")
            titles = [card.header.text().strip() if card.header is not None else "" for card in cards]
            print(f"Wrote {args.out}-window.png and {len(cards)} card image(s): {titles}")
            window._dirty = False
            window.close()


if __name__ == "__main__":
    main()
