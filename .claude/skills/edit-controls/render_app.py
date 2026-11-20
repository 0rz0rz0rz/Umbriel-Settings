"""Render the standalone app (shared Luau UI in the web view) offscreen and save PNGs.

Usage (from the repo root; offscreen and import path are set up by _render_common):
  python .claude/skills/edit-controls/render_app.py \
      --out <scratchpad>/app [--config sample.toml] [--size 1280x860] [click texts ...]

Each positional argument clicks the first clickable node showing that exact text (a sidebar page,
a group, an entry, "Review & save", ...) and writes <out>-<n>-<text>.png after it settles; the first
image is the start page. A temporary copy of the config (default: /usr/share/umbriel/config.toml)
and temporary data paths are used; the theme follows the user's Noctalia/qt6ct colors.
"""
import argparse
import json
import sys

from _render_common import close_window, open_window, temp_home

parser = argparse.ArgumentParser()
parser.add_argument("--out", required=True, help="PNG path prefix")
parser.add_argument("--config", default="/usr/share/umbriel/config.toml")
parser.add_argument("--size", default="1280x860")
parser.add_argument("--settle", type=int, default=1200, help="ms to wait after each click")
parser.add_argument("clicks", nargs="*")
args = parser.parse_args()

tmp, config = temp_home(args.config, "umbriel-render-")
app, win = open_window(config, tuple(int(v) for v in args.size.split("x")))

from PySide6.QtCore import QTimer  # noqa: E402

steps = ["start"] + args.clicks
state = {"i": 0}


def has_text(node, text):
    return node["props"].get("text") == text or any(has_text(c, text) for c in node["children"])


def clickable(node, text):
    if "onClick" in node["props"] and has_text(node, text):
        return node
    for child in node["children"]:
        found = clickable(child, text)
        if found:
            return found
    return None


def step():
    i = state["i"]
    if i > 0:
        name = steps[i - 1].replace(" ", "_").replace("/", "_")
        path = f"{args.out}-{i}-{name}.png"
        win.view.grab().save(path)
        print(path)
    if i >= len(steps):
        close_window(win, tmp)
        app.quit()
        return
    if i > 0:
        tree = json.loads(win.bridge.last_tree or "null")
        node = clickable(tree, steps[i]) if tree else None
        if node:
            win.host.invoke(node["props"]["onClick"])
        else:
            print(f"nothing clickable shows {steps[i]!r}", file=sys.stderr)
    state["i"] += 1
    QTimer.singleShot(args.settle, step)


QTimer.singleShot(3000, step)
app.exec()
