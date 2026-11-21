"""Render the README screenshots offscreen: the app's Home and the plugin panel's Home, or (--page outputs)
the panel's Outputs page.

Run from the repo root:
    python .claude/skills/edit-controls/render_docs.py [--out DIR]
        [--page home|outputs]

Without --out it writes docs/home-app.png (1280x860) and noctalia-plugin/umbriel-settings/screenshot.png
(1028x808: the 980x760 panel plus a 24 px margin), which both READMEs show; with --page outputs
noctalia-plugin/umbriel-settings/screenshot-outputs.png. The Outputs page shows three made-up displays: a
wrapper `umbriel` answers `outputs --json` and passes every other command to the real one.
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

from _render_common import close_window, open_window, temp_home

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SAMPLE = "/usr/share/umbriel/config.toml"
SIZES = {"app": (1280, 860), "panel": (1028, 808)}
SHOWN_PATH = "~/.config/umbriel/config.toml"

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--out", help="write the PNGs here instead of the repo")
parser.add_argument("--page", choices=["home", "outputs"], default="home")
parser.add_argument("--layout", choices=sorted(SIZES), help=argparse.SUPPRESS)  # one child render
parser.add_argument("--file", help=argparse.SUPPRESS)
parser.add_argument("--size", help=argparse.SUPPRESS)  # WxH instead of SIZES (render_thumbnail.py)
parser.add_argument("--no-margin", action="store_true", help=argparse.SUPPRESS)
parser.add_argument("--settle", type=int, default=4000, help="ms to wait before the grab")
args = parser.parse_args()

if not args.layout:
    docs = args.out or os.path.join(REPO, "docs")
    plugin = args.out or os.path.join(REPO, "noctalia-plugin", "umbriel-settings")  # self-contained for the store
    if args.page == "outputs":
        targets = [("panel", os.path.join(plugin, "screenshot-outputs.png"))]
    else:
        targets = [("app", os.path.join(docs, "home-app.png")), ("panel", os.path.join(plugin, "screenshot.png"))]
    failed = False
    for layout, path in targets:
        # one process per layout: the panel patches LuaHost.start, and QtWebEngine runs once per process
        result = subprocess.run([sys.executable, __file__, "--layout", layout, "--file", path, "--page", args.page,
                                 "--settle", str(args.settle)])
        failed = failed or result.returncode != 0
    sys.exit(1 if failed else 0)

tmp, config = temp_home(SAMPLE, "umbriel-docs-")
data = os.environ["XDG_DATA_HOME"]
# The panel opens the config remembered in its data dir (the app takes initialConfig).
os.makedirs(os.path.join(data, "umbriel-settings"))
with open(os.path.join(data, "umbriel-settings", "gui-config-path"), "w", encoding="utf-8") as handle:
    handle.write(config)

# Made-up displays for the Outputs page: a 1440p main display, a 1080p one centered above it, one at its right.
FAKE_OUTPUTS = [
    ("DP-1", "Example 27Q 0001", 0, 1080, 2560, 1440, [(2560, 1440, 164999), (2560, 1440, 59951), (1920, 1080, 60000)]),
    ("DP-2", "Example 24F 0002", 320, 0, 1920, 1080, [(1920, 1080, 60000), (1280, 720, 60000)]),
    ("HDMI-A-1", "Example 24F 0003", 2560, 1260, 1920, 1080, [(1920, 1080, 60000), (1280, 720, 60000)]),
]
if args.page == "outputs":
    real = shutil.which("umbriel")
    outputs = [{"name": name, "config_name": monitor, "enabled": True, "scale": 1.0, "transform": "normal",
                "position": {"x": x, "y": y}, "logical_size": {"width": w, "height": h},
                "modes": [{"width": mw, "height": mh, "refresh_mhz": rate, "current": i == 0, "preferred": i == 0}
                          for i, (mw, mh, rate) in enumerate(modes)]}
               for name, monitor, x, y, w, h, modes in FAKE_OUTPUTS]
    bin_dir = os.path.join(tmp, "bin")
    os.makedirs(bin_dir)
    wrapper = os.path.join(bin_dir, "umbriel")
    with open(wrapper, "w", encoding="utf-8") as handle:
        handle.write(f"#!{sys.executable}\nimport os, sys\n"
                     f"if sys.argv[1:] == ['outputs', '--json']:\n    print({json.dumps(json.dumps(outputs))})\n"
                     f"else:\n    os.execv({real!r}, [{real!r}, *sys.argv[1:]])\n")
    os.chmod(wrapper, 0o755)
    os.environ["PATH"] = bin_dir + os.pathsep + os.environ["PATH"]
    with open(config, "a", encoding="utf-8") as handle:  # the main display is the default (a filled star)
        handle.write(f'\n[output."{FAKE_OUTPUTS[0][1]}"]\nfocus_at_startup = true\n')

from umbriel_settings.host import runtime  # noqa: E402

if args.layout == "panel":
    start = runtime.LuaHost.start

    def panel_start(self, entry, options, api):
        start(self, "panel.luau", {}, api)
        self.call("onOpen")

    runtime.LuaHost.start = panel_start

app, win = open_window(config, tuple(int(v) for v in args.size.split("x")) if args.size else SIZES[args.layout])

from PySide6.QtCore import QTimer  # noqa: E402

# Show the temporary config path as the usual one; give the panel the margin Noctalia draws around it.
JS = """
((from, to, margin) => {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = walker.nextNode());) if (n.nodeValue.includes(from)) n.nodeValue = n.nodeValue.split(from).join(to);
  for (const el of document.querySelectorAll("input"))
    if (el.value.includes(from)) el.value = el.value.split(from).join(to);
  if (margin) { document.body.style.padding = "24px"; document.body.style.boxSizing = "border-box"; }
})""" + "(" + json.dumps([config, SHOWN_PATH, args.layout == "panel" and not args.no_margin])[1:-1] + ");"


def finish():
    os.makedirs(os.path.dirname(os.path.abspath(args.file)), exist_ok=True)
    ok = win.view.grab().save(args.file)
    print(args.file if ok else f"could not write {args.file}")
    clean = close_window(win, tmp)
    app.exit(0 if ok and clean else 1)


def prepare():
    win.view.page().runJavaScript(JS)
    QTimer.singleShot(600, finish)


# The Outputs card or sidebar row: the element showing exactly "Outputs" (not the help text mentioning it).
OPEN_OUTPUTS = """
(() => { const el = [...document.querySelectorAll('#root *')].find(e => e.children.length === 0
  && e.textContent.trim() === 'Outputs'); if (el) el.click(); return !!el; })()"""


def open_page():
    if args.page == "outputs":
        win.view.page().runJavaScript(OPEN_OUTPUTS)
        QTimer.singleShot(args.settle, prepare)
    else:
        prepare()


QTimer.singleShot(args.settle, open_page)
sys.exit(app.exec())
