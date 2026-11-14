"""The real app window offscreen: the web page renders the Luau UI, clicks in the DOM reach Lua, no JS errors."""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from test_host_runtime import CONFIG, FAKE_UMBRIEL, lupa
from umbriel_settings.app_window import AppWindow  # QtWebEngine must load before QApplication exists

# Clicks the innermost element showing exactly this text; the click bubbles to the node's handler.
CLICK_JS = """(() => {
  const all = [...document.querySelectorAll('#root *')].filter(e => e.textContent.trim() === %s);
  const target = all.find(e => ![...e.children].some(c => c.textContent.trim() === %s));
  if (!target) return false;
  target.click();
  return true;
})()"""


@unittest.skipIf(lupa is None, "lupa is required for the app UI host")
class AppRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        config = root / "config.toml"
        config.write_text(CONFIG)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        (bin_dir / "umbriel").write_text(f"#!{sys.executable}\n" + FAKE_UMBRIEL)
        (bin_dir / "umbriel").chmod(0o755)
        env = patch.dict(os.environ, {"XDG_DATA_HOME": str(root / "data"), "XDG_CONFIG_HOME": str(root / "xdg"),
                                      "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]})
        env.start()
        self.addCleanup(env.stop)

        self.win = AppWindow({"initialConfig": str(config)})
        self.win.resize(1100, 760)
        self.addCleanup(self.close_window)
        self.win.show()

    def close_window(self):
        self.win.pending = 0
        self.win.close()
        self.win.deleteLater()
        # Delete the page before Python tears down QApplication, or QtWebEngine crashes at exit.
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def js(self, script, timeout=5.0):
        result, loop = [], QEventLoop()
        self.win.view.page().runJavaScript(script, 0, lambda value: (result.append(value), loop.quit()))
        QTimer.singleShot(int(timeout * 1000), loop.quit)
        loop.exec()
        self.assertTrue(result, f"no JavaScript result for {script[:60]}")
        return result[0]

    def wait_for_text(self, *texts, timeout=30.0):
        deadline = time.monotonic() + timeout
        shown = ""
        while time.monotonic() < deadline:
            self.app.processEvents()
            shown = self.js("document.getElementById('root') ? document.getElementById('root').innerText : ''") or ""
            if all(text in shown for text in texts):
                return shown
            self.pause()
        self.fail(f"page never showed {texts}; it shows: {shown[:500]!r}")

    def pause(self, ms=100):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def click(self, text, timeout=30.0):
        """Click the element showing exactly `text`, waiting for it: substrings (help text) don't count."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.js(CLICK_JS % (json.dumps(text), json.dumps(text))):
                self.app.processEvents()
                return
            self.pause()
        near = self.js("[...document.querySelectorAll('#root *')].filter(e => e.children.length === 0"
                       f" && e.textContent.includes({json.dumps(text)})).map(e => e.outerHTML).join('\\n')")
        self.fail(f"no element shows {text!r}; elements containing it:\n{near}")

    def painted_colors(self, timeout=30.0):
        """Distinct sampled colors of the window, once painting has caught up with the DOM (slow CI runners)."""
        deadline = time.monotonic() + timeout
        while True:
            image = self.win.view.grab().toImage()
            colors = {image.pixel(x, y) for x in range(0, image.width(), 37) for y in range(0, image.height(), 29)}
            if len(colors) > 3 or time.monotonic() > deadline:
                return colors
            self.pause()

    def test_page_renders_and_dom_clicks_reach_lua(self):
        self.wait_for_text("Home", "Appearance", "Window rules")
        self.assertTrue(self.js("getComputedStyle(document.body).backgroundColor") not in ("", None))
        self.assertGreater(len(self.painted_colors()), 3, "the page looks blank")

        self.click("General")
        shown = self.wait_for_text("Session", "Only customized")
        self.assertNotIn("Mod key", shown, "groups start collapsed in the app")
        self.click("Session")
        self.wait_for_text("Mod key")
        self.click("Window rules")
        self.wait_for_text("firefox")

        self.assertEqual(self.win.view.page().console_errors, [])
        self.assertEqual(self.win.host.errors, [])

    def test_page_cannot_navigate_away_or_load_remote_content(self):
        self.wait_for_text("Home", "Appearance")
        home = self.win.view.url()
        self.js("window.open('file:///etc/hostname'); location.href = 'https://example.com/'; true")
        self.pause(500)
        self.js("document.body.appendChild(Object.assign(document.createElement('a'), {href: 'file:///etc/'})).click(); true")
        self.pause(500)
        self.assertEqual(self.win.view.url(), home)
        self.wait_for_text("Home", "Appearance")
        self.assertIsNotNone(self.js("document.querySelector('meta[http-equiv=\"Content-Security-Policy\"]').content"))
        self.js("fetch('file:///etc/hostname').catch(() => {}); true")
        self.pause(300)
        errors = self.win.view.page().console_errors
        self.assertTrue(any("Content Security Policy" in e for e in errors), errors)
        self.assertFalse([e for e in errors if "Content Security Policy" not in e], errors)


if __name__ == "__main__":
    unittest.main()
