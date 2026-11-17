"""Render the README screenshots offscreen: the app's Home and the plugin panel's Home.

Run from python/:
    QT_QPA_PLATFORM=offscreen PYTHONPATH=. python ../.claude/skills/edit-controls/render_docs.py [--out DIR]

Without --out it writes docs/home-app.png (1280x860), docs/home-plugin.png and the plugin's own copy
noctalia-plugin/umbriel-settings/screenshot.png (both 1028x808: the 980x760 panel plus a 24 px margin).
Both use a temporary copy of Umbriel's sample config (/usr/share/umbriel/config.toml), shown as
~/.config/umbriel/config.toml, and temporary data dirs, so no personal paths or settings appear; the theme
follows the user's Noctalia/qt6ct colors. The panel runs panel.luau (with onOpen) in the app's web view.
Read-only: nothing is clicked or saved.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SAMPLE = "/usr/share/umbriel/config.toml"
SIZES = {"app": (1280, 860), "panel": (1028, 808)}
SHOWN_PATH = "~/.config/umbriel/config.toml"

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--out", help="write home-app.png and home-plugin.png here instead of the repo")
parser.add_argument("--layout", choices=sorted(SIZES), help=argparse.SUPPRESS)  # one child render
parser.add_argument("--file", help=argparse.SUPPRESS)
parser.add_argument("--size", help=argparse.SUPPRESS)  # WxH instead of SIZES (render_thumbnail.py)
parser.add_argument("--no-margin", action="store_true", help=argparse.SUPPRESS)
parser.add_argument("--settle", type=int, default=4000, help="ms to wait before the grab")
args = parser.parse_args()

if not args.layout:
    targets = ([("app", os.path.join(args.out, "home-app.png")), ("panel", os.path.join(args.out, "home-plugin.png"))]
               if args.out else
               [("app", os.path.join(REPO, "docs", "home-app.png")),
                ("panel", os.path.join(REPO, "docs", "home-plugin.png"))])
    failed = False
    for layout, path in targets:
        # one process per layout: the panel patches LuaHost.start, and QtWebEngine runs once per process
        result = subprocess.run([sys.executable, __file__, "--layout", layout, "--file", path,
                                 "--settle", str(args.settle)])
        failed = failed or result.returncode != 0
    if not args.out and not failed:
        plugin_copy = os.path.join(REPO, "noctalia-plugin", "umbriel-settings", "screenshot.png")
        shutil.copy(os.path.join(REPO, "docs", "home-plugin.png"), plugin_copy)
        print(plugin_copy)
    sys.exit(1 if failed else 0)

tmp = tempfile.mkdtemp(prefix="umbriel-docs-")
data = os.path.join(tmp, "data")
os.environ["XDG_DATA_HOME"] = data
config = os.path.join(tmp, "config.toml")
shutil.copy(SAMPLE, config)
# The panel opens the config remembered in its data dir (the app takes initialConfig).
os.makedirs(os.path.join(data, "umbriel-settings"))
with open(os.path.join(data, "umbriel-settings", "gui-config-path"), "w", encoding="utf-8") as handle:
    handle.write(config)

from PySide6.QtCore import QCoreApplication, QEvent, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from umbriel_settings.app_window import AppWindow  # noqa: E402
from umbriel_settings.host import runtime  # noqa: E402

if args.layout == "panel":
    start = runtime.LuaHost.start

    def panel_start(self, entry, options, api):
        start(self, "panel.luau", {}, api)
        self.call("onOpen")

    runtime.LuaHost.start = panel_start

app = QApplication([])
win = AppWindow({"initialConfig": config})
win.resize(*(tuple(int(v) for v in args.size.split("x")) if args.size else SIZES[args.layout]))
win.show()

# Show the temporary config path as the usual one; give the panel the margin Noctalia draws around it.
JS = """
((from, to, margin) => {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = walker.nextNode());) if (n.nodeValue.includes(from)) n.nodeValue = n.nodeValue.split(from).join(to);
  for (const el of document.querySelectorAll("input")) if (el.value.includes(from)) el.value = el.value.split(from).join(to);
  if (margin) { document.body.style.padding = "24px"; document.body.style.boxSizing = "border-box"; }
})""" + "(" + json.dumps([config, SHOWN_PATH, args.layout == "panel" and not args.no_margin])[1:-1] + ");"


def finish():
    os.makedirs(os.path.dirname(os.path.abspath(args.file)), exist_ok=True)
    ok = win.view.grab().save(args.file)
    print(args.file if ok else f"could not write {args.file}")
    if win.host.errors:
        print("Lua errors:", *win.host.errors, sep="\n  ", file=sys.stderr)
    # Close and delete the page before Qt shuts down, or QtWebEngine can crash at exit.
    win.closing_confirmed = True
    win.close()
    win.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    shutil.rmtree(tmp, ignore_errors=True)
    app.exit(0 if ok and not win.host.errors else 1)


def prepare():
    win.view.page().runJavaScript(JS)
    QTimer.singleShot(600, finish)


QTimer.singleShot(args.settle, prepare)
sys.exit(app.exec())
