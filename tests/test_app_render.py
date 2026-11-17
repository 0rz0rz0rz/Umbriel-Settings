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

# QtWebEngine must load before QApplication exists
from umbriel_settings.app_window import AppWindow, load_window_state, save_window_state

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
                                      "XDG_DATA_DIRS": str(root / "share"),
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
        # Let background helper calls finish before the temp dir goes: they still write to app-ui/run.
        self.win.scheduler.pool.shutdown(wait=True)
        self.win.scheduler.slow_pool.shutdown(wait=True)
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
        # Screen readers: clickable rows are buttons, and icon-only buttons are named by their tooltip.
        self.assertGreater(self.js("document.querySelectorAll('#root button.icon').length"), 0)
        self.assertGreater(self.js("document.querySelectorAll('#root [role=button]').length"), 0)
        unnamed = self.js("[...document.querySelectorAll('#root button.icon, #root [role=button]')]"
                          ".filter(b => !b.getAttribute('aria-label') && !b.innerText.replace(/[\\ue000-\\uf8ff]/g, '')"
                          ".trim()).map(b => b.outerHTML.slice(0, 160)).join('\\n')")
        self.assertEqual(unnamed, "", "icon-only controls need a tooltip")

        self.click("Window rules")
        self.wait_for_text("firefox")

        self.assertEqual(self.win.view.page().console_errors, [])
        self.assertEqual(self.win.host.errors, [])

    def test_window_size_is_remembered_across_runs(self):
        self.assertEqual(load_window_state(self.win.data_dir), {})
        self.win.resize(1000, 700)
        self.pause()
        self.win.pending = 0
        self.win.close()
        self.assertEqual(load_window_state(self.win.data_dir), {"width": 1000, "height": 700, "maximized": False})
        save_window_state(self.win.data_dir, {"width": 5, "height": 5})  # unusable: falls back to the default
        self.assertEqual(load_window_state(self.win.data_dir), {})

    def test_a_slider_drag_is_stored_when_released(self):
        self.wait_for_text("Home", "Appearance")
        self.click("Appearance")
        self.click("Windows")
        self.wait_for_text("Border width")
        # The release (change) comes right after the last move (input), which the page sends one frame later.
        self.js("const s = document.querySelector('#root input[type=range]'); s.value = s.max;"
                "s.dispatchEvent(new Event('input')); s.dispatchEvent(new Event('change')); 'ok'")
        deadline = time.monotonic() + 5
        while self.win.pending != 1 and time.monotonic() < deadline:
            self.pause(50)
        self.assertEqual(self.win.pending, 1, "the dragged value is one unsaved change")
        self.pause(200)  # a late duplicate of the last move must not start a gesture that never ends
        self.assertEqual(self.js("String(document.querySelector('#root input[type=range]').value === "
                                 "document.querySelector('#root input[type=range]').max)"), "true")
        self.assertEqual(self.win.host.errors, [])

    def test_a_shortcut_is_dragged_into_a_group(self):
        self.wait_for_text("Home", "Keybinds")
        self.click("Keybinds")
        self.wait_for_text("Mod+Return", "Groups")
        self.js("const i = document.querySelector('#root input[placeholder^=\"New group name\"]'); i.value = 'Apps';"
                "i.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter'})); 'ok'")
        group = "document.querySelector('[data-key=\"kbgl-Apps\"]')"
        self.wait_until(f"{group} ? {group}.textContent : ''", "Apps  ·  0")
        # A press without movement neither drags nor opens the row around the grip.
        pointer = ("(el, type, x, y) => el.dispatchEvent(new PointerEvent(type, {bubbles: true, button: 0,"
                   " pointerId: 7, clientX: x, clientY: y}))")
        grip = "document.querySelector('[data-key=\"kbgrip-1\"]')"
        self.js(f"(() => {{ const p = {pointer}, g = {grip}, r = g.getBoundingClientRect();"
                "p(g, 'pointerdown', r.x + 5, r.y + 5); p(g, 'pointerup', r.x + 5, r.y + 5); g.click(); return 'ok'; })()")
        self.pause(300)
        self.assertEqual(self.js("String(!!document.querySelector('[data-key=\"kb-filter\"]'))"), "true",
                         "still on the list, not the shortcut's page")
        # Drag past the threshold onto the group's header: the shortcut moves into the group.
        self.js(f"(() => {{ const p = {pointer}, g = {grip}, r = g.getBoundingClientRect();"
                " const t = document.querySelector('[data-key^=\"kbgroup-1-Apps\"]').getBoundingClientRect();"
                " p(g, 'pointerdown', r.x + 5, r.y + 5); p(g, 'pointermove', r.x + 15, r.y + 15);"
                " const ghost = !!document.querySelector('.drag-ghost');"
                " p(g, 'pointermove', t.x + 40, t.y + 6); p(g, 'pointerup', t.x + 40, t.y + 6);"
                " return String(ghost); })()")
        self.wait_until(f"{group} ? {group}.textContent : ''", "Apps  ·  1")
        self.assertEqual(self.js("String(!document.querySelector('.drag-ghost, .drag-lifted, .drop-over'))"), "true")
        self.assertEqual(self.win.view.page().console_errors, [])
        self.assertEqual(self.win.host.errors, [])

    def wait_until(self, script, expected, timeout=10.0):
        deadline = time.monotonic() + timeout
        value = None
        while time.monotonic() < deadline:
            self.app.processEvents()
            value = self.js(script)
            if value == expected:
                return
            self.pause(50)
        self.fail(f"{script} is {value!r}, not {expected!r}")

    def test_notifications_show_the_status_bar_only_while_they_last(self):
        bar = self.win.statusBar()
        self.assertTrue(bar.isHidden())
        self.win.api.notify("Umbriel Settings", "Saved after the panel closed.")
        self.assertFalse(bar.isHidden())
        self.assertEqual(bar.currentMessage(), "Umbriel Settings: Saved after the panel closed.")
        bar.clearMessage()
        self.assertTrue(bar.isHidden())

    def test_ui_errors_are_shown_and_the_ui_recovers(self):
        self.wait_for_text("Home", "Appearance")
        errors = len(self.win.host.errors)
        with patch("sys.stderr"):
            self.win.on_lua_error(RuntimeError("boom\nstack traceback: ..."))
        self.assertEqual(self.win.statusBar().currentMessage(), "Something went wrong: boom")
        self.assertEqual(len(self.win.host.errors), errors, "onRecover ran without a new error")

    def test_desktop_files_are_watched(self):
        xdg = Path(os.environ["XDG_CONFIG_HOME"])
        xdg.mkdir(exist_ok=True)
        dirs = xdg / "user-dirs.dirs"
        dirs.write_text('XDG_DESKTOP_DIR="$HOME/Desktop"\n')
        self.win.on_directory_change(str(xdg))
        self.assertIn(str(dirs), self.win.watcher.files())
        self.assertTrue(self.win.desktop_timer.isActive(), "a new desktop file reloads the desktop page")

    def test_a_config_that_is_deleted_and_written_again_is_watched_again(self):
        self.wait_for_text("Home", "Appearance")
        # The path is published once the config has loaded, which slow runners finish after the first render.
        deadline = time.monotonic() + 30
        while not self.win.config_path and time.monotonic() < deadline:
            self.pause(50)
        config = Path(self.win.config_path)
        self.assertTrue(self.win.config_path, "the config path was never published")
        self.assertIn(str(config), self.win.watcher.files())
        config.unlink()
        self.pause(700)
        self.assertNotIn(str(config), self.win.watcher.files())
        config.write_text(CONFIG)
        deadline = time.monotonic() + 5
        while str(config) not in self.win.watcher.files() and time.monotonic() < deadline:
            self.pause(50)
        self.assertIn(str(config), self.win.watcher.files())

    def test_sigterm_closes_like_the_close_button_without_asking(self):
        import signal

        from umbriel_settings.app_window import quit_on_signals

        previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}

        def restore():
            signal.set_wakeup_fd(-1)
            for number, handler in previous.items():
                signal.signal(number, handler)
        self.addCleanup(restore)
        self.win.pending = 3  # the close button would ask; a signal must not
        called = []
        with patch.object(self.win.host, "call", side_effect=lambda name, *args: called.append(name)), \
                patch.object(self.app, "quit") as quit_app:
            quit_on_signals(self.app, self.win)
            os.kill(os.getpid(), signal.SIGTERM)
            deadline = time.monotonic() + 5
            while not quit_app.called and time.monotonic() < deadline:
                self.pause(20)
        self.assertIn("onClose", called, "the draft is written")
        self.assertFalse(self.win.isVisible())
        quit_app.assert_called_once_with()

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
