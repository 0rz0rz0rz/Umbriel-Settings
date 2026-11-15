import json
import re
import threading
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from umbriel_core.meta import PAGE_GLYPHS
from umbriel_settings.host.api import fuzzy_score
from umbriel_settings.host.bridge import Bridge, QtScheduler

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "noctalia-plugin" / "umbriel-settings"
GLYPH_MAP = ROOT / "python" / "umbriel_settings" / "host" / "web" / "fonts" / "tabler-map.json"
GLYPH_NAME = re.compile(r'\b(?:glyph|icon)\s*=\s*"([a-z0-9-]+)"|ui\.glyph\(\{\s*name\s*=\s*"([a-z0-9-]+)"')


def wait_until(app, predicate, timeout_ms=3000):
    loop = QEventLoop()
    timer = QTimer(singleShot=True, interval=timeout_ms)
    timer.timeout.connect(loop.quit)
    timer.start()
    while not predicate() and timer.isActive():
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
    return predicate()


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def make_bridge(self):
        calls = {"ready": 0, "invoke": [], "key": []}
        bridge = Bridge('{"x": 1}', lambda: calls.__setitem__("ready", calls["ready"] + 1),
                        lambda callback, args: calls["invoke"].append((callback, args)),
                        lambda chord: calls["key"].append(chord))
        emitted = []
        bridge.renderTree.connect(lambda text: emitted.append(("tree", text)))
        bridge.glyphMap.connect(lambda text: emitted.append(("glyphs", text)))
        return bridge, calls, emitted

    def test_tree_waits_for_the_page_then_follows_the_glyph_map(self):
        bridge, calls, emitted = self.make_bridge()
        bridge.send_tree({"kind": "label", "props": {"text": "Grün"}, "children": []})
        self.assertEqual(emitted, [])
        bridge.ready()
        self.assertEqual([kind for kind, _ in emitted], ["glyphs", "tree"])
        self.assertEqual(json.loads(emitted[1][1])["props"]["text"], "Grün")
        self.assertIn("Grün", emitted[1][1])  # not escaped: keeps messages small
        self.assertEqual(calls["ready"], 1)
        bridge.send_tree({"kind": "column", "props": {}, "children": []})
        self.assertEqual(len(emitted), 3)

    def test_invoke_and_key_decode_the_page_messages(self):
        bridge, calls, _ = self.make_bridge()
        bridge.invoke(json.dumps({"$callback": "cb3"}), json.dumps(["text", 2]))
        bridge.invoke(json.dumps("onMenuDelete"), "[]")
        bridge.key("ctrl+s")
        for callback, args in (("{not json", "[]"), ('"onKey"', "nope"), ('"onKey"', '{"a": 1}'), ('"onKey"', '"x"')):
            bridge.invoke(callback, args)  # malformed page messages are dropped, not raised into Qt
        self.assertEqual(calls["invoke"], [({"$callback": "cb3"}, ["text", 2]), ("onMenuDelete", [])])
        self.assertEqual(calls["key"], ["ctrl+s"])

    def test_scheduler_delivers_background_results_on_the_gui_thread(self):
        scheduler = QtScheduler()
        self.addCleanup(scheduler.pool.shutdown)
        gui_thread = threading.get_ident()
        seen = {}
        scheduler.background(lambda: threading.get_ident(),
                             lambda worker: seen.update(worker=worker, done=threading.get_ident()))
        posted = []
        scheduler.post(lambda: posted.append(True))
        self.assertTrue(wait_until(self.app, lambda: "done" in seen and posted))
        self.assertEqual(seen["done"], gui_thread)
        self.assertNotEqual(seen["worker"], gui_thread)


class SharedAssetTests(unittest.TestCase):
    def test_every_glyph_used_by_the_shared_ui_is_in_the_icon_map(self):
        glyphs = json.loads(GLYPH_MAP.read_text(encoding="utf-8"))
        used = set(PAGE_GLYPHS.values())
        for path in UI_DIR.rglob("*.luau"):
            for match in GLYPH_NAME.finditer(path.read_text(encoding="utf-8")):
                used.add(match.group(1) or match.group(2))
        self.assertGreater(len(used), 20)
        self.assertEqual(sorted(used - glyphs.keys()), [])

    def test_fuzzy_score_prefers_substrings_and_rejects_missing_letters(self):
        self.assertIsNone(fuzzy_score("xyz", "border width"))
        self.assertEqual(fuzzy_score("", "anything"), 0)
        self.assertGreater(fuzzy_score("border", "border width"), fuzzy_score("bdr", "border width"))
        self.assertGreater(fuzzy_score("width", "width"), fuzzy_score("width", "border width"))


if __name__ == "__main__":
    unittest.main()
