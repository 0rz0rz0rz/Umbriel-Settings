"""Regenerate the plugin's thumbnail.webp with Noctalia's own thumbnail generator, offscreen.

Run from the repo root:
    QT_QPA_PLATFORM=offscreen python .claude/skills/edit-controls/render_thumbnail.py [--out FILE]

Downloads the generator page (https://assets.noctalia.dev/plugins/thumbnail-generator.html, the one the
community-plugins README asks for) and its html-to-image script into a temporary folder, points the page at
the local script (the offscreen page itself gets no network), sets the title and tags from plugin.toml, the
one-line description and the Mint accent, and loads a screenshot like its "Choose file…" button. The card's
screenshot frame is only 588x331 and tilted, so the panel is rendered for it (render_docs.py, sample config):
16:9 at 800x450 and twice the pixel density, which keeps its text about twice as large as in the README shot.
The card is exported at --scale (2) times the size and drawn down to 960x540 with high-quality smoothing
before the page's own WebP encoder (0.98) writes noctalia-plugin/umbriel-settings/thumbnail.webp.
"""

import argparse
import base64
import json
import os
import re
import shutil
import sys
import tempfile
import tomllib
import urllib.request
from urllib.parse import urlencode

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PLUGIN = os.path.join(REPO, "noctalia-plugin", "umbriel-settings")
GENERATOR = "https://assets.noctalia.dev/plugins/thumbnail-generator.html"
SCRIPT_RE = re.compile(r'<script src="(https://cdn\.jsdelivr\.net/npm/html-to-image@[0-9.]+/dist/html-to-image\.js)">')
DESCRIPTION = "Edit Umbriel settings, rules and keybinds from a panel"  # the generator allows 100 characters
ACCENT = "mint"  # yellow, iris, mint or red

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--out", default=os.path.join(PLUGIN, "thumbnail.webp"))
parser.add_argument("--shot", help="use this screenshot instead of rendering the panel (16:9 fits the card)")
parser.add_argument("--scale", type=int, default=2,
                    help="render the card at this pixel ratio, then downscale (smooths the tilted screenshot)")
args = parser.parse_args()

with open(os.path.join(PLUGIN, "plugin.toml"), "rb") as handle:
    manifest = tomllib.load(handle)

tmp = tempfile.mkdtemp(prefix="umbriel-thumb-")
try:
    with urllib.request.urlopen(GENERATOR, timeout=30) as response:
        page = response.read().decode("utf-8")
    match = SCRIPT_RE.search(page)
    if not match:
        sys.exit("The generator page changed (no pinned html-to-image script); check it by hand.")
    with urllib.request.urlopen(match.group(1), timeout=30) as response:
        library = response.read()
except OSError as error:
    shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(f"Could not download the generator: {error}")
with open(os.path.join(tmp, "html-to-image.js"), "wb") as handle:
    handle.write(library)
with open(os.path.join(tmp, "generator.html"), "w", encoding="utf-8") as handle:
    handle.write(page.replace(match.group(1), "html-to-image.js"))
print("generator:", GENERATOR, "| library:", match.group(1))

from PySide6.QtCore import QTimer, QUrl  # noqa: E402
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

shot_path = args.shot
if not shot_path:
    import subprocess

    shot_path = os.path.join(tmp, "shot.png")
    render = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "render_docs.py"),
         "--layout", "panel", "--size", "800x450", "--no-margin", "--file", shot_path],
        cwd=os.path.join(REPO, "python"), env=dict(os.environ, QT_SCALE_FACTOR="2", PYTHONPATH="."))
    if render.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        sys.exit("Rendering the panel screenshot failed.")
with open(shot_path, "rb") as handle:
    shot = "data:image/png;base64," + base64.b64encode(handle.read()).decode()
params = {"title": manifest["name"], "tag": " · ".join(manifest.get("tags", [])), "desc": DESCRIPTION,
          "accent": ACCENT, "render": "1"}

# What "Choose file…" does (a data: URL in the screenshot field), then the page's own export call.
EXPORT = """
(async (shot, scale) => {
  const field = document.getElementById('f_shot');
  field.value = shot; field.dispatchEvent(new Event('input'));
  await document.fonts.ready;
  await new Promise(r => setTimeout(r, 500));
  const big = await window.htmlToImage.toCanvas(document.getElementById('thumb'), {
    pixelRatio: scale, width: 960, height: 540, cacheBust: true, style: { margin: '0', boxShadow: 'none' } });
  const canvas = document.createElement('canvas');
  canvas.width = 960; canvas.height = 540;
  const context = canvas.getContext('2d');
  context.imageSmoothingEnabled = true; context.imageSmoothingQuality = 'high';
  context.drawImage(big, 0, 0, 960, 540);
  window.__out = canvas.toDataURL('image/webp', 0.98);
})""" + "(" + json.dumps(shot) + ", " + str(args.scale) + ").catch(e => { window.__out = 'error:' + e; });"

app = QApplication([])
view = QWebEngineView()
view.resize(1200, 800)
url = QUrl.fromLocalFile(os.path.join(tmp, "generator.html"))
url.setQuery(urlencode(params))
tries = {"n": 0}


def done(code, message):
    print(message, file=sys.stderr if code else sys.stdout)
    shutil.rmtree(tmp, ignore_errors=True)
    app.exit(code)


def poll():
    def got(value):
        tries["n"] += 1
        if isinstance(value, str) and value.startswith("data:image/webp;base64,"):
            with open(args.out, "wb") as handle:
                handle.write(base64.b64decode(value.split(",", 1)[1]))
            done(0, args.out)
        elif isinstance(value, str) and value:
            done(1, f"export failed: {value[:200]}")
        elif tries["n"] > 60:
            done(1, "export timed out")
        else:
            QTimer.singleShot(500, poll)
    view.page().runJavaScript("window.__out || ''", 0, got)


def loaded(ok):
    if not ok:
        done(1, "the generator page failed to load")
        return

    def start(ready):
        if not ready:
            done(1, "html-to-image did not load")
            return
        view.page().runJavaScript(EXPORT)
        QTimer.singleShot(1000, poll)
    view.page().runJavaScript("!!window.htmlToImage", 0, start)


view.loadFinished.connect(loaded)
view.load(url)
view.show()
sys.exit(app.exec())
