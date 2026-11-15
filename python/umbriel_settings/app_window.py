"""Standalone window: the shared Luau UI (app.luau) rendered as HTML in a QWebEngineView."""

import json
import os
import sys

from PySide6.QtCore import QFileSystemWatcher, QSize, QTimer, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from .host.api import NoctaliaApi
from .host.bridge import Bridge, QtScheduler
from .host.paths import app_data_dir, shared_ui_dir
from .host.runtime import LuaHost
from .host.theme import Theme

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "host", "web")
TITLE = "Umbriel Settings"


class Page(QWebEnginePage):
    """Keeps JavaScript errors (renderer bugs) for tests and prints them for bug reports.

    The page may only ever show index.html: links, scripts, drops and new windows can't navigate it away."""

    HOME = QUrl.fromLocalFile(os.path.join(WEB_DIR, "index.html"))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.console_errors = []

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        return url.isLocalFile() and url.path() == self.HOME.path()

    def createWindow(self, window_type):
        return None

    def javaScriptConsoleMessage(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            text = f"{os.path.basename(source)}:{line}: {message}"
            self.console_errors.append(text)
            print(f"Umbriel Settings page error: {text}", file=sys.stderr)


def icon_file(app_id, size, cache_dir):
    """Resolve a desktop app id to an icon file the page can show (themed icons are rendered to PNG)."""
    name = (app_id or "").removesuffix(".desktop")
    if not name:
        return None
    icon = QIcon.fromTheme(name)
    if icon.isNull():
        return None
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"{name}-{int(size or 32)}.png")
    if not os.path.exists(path):
        pixmap = icon.pixmap(QSize(int(size or 32), int(size or 32)))
        if pixmap.isNull() or not pixmap.save(path, "PNG"):
            return None
    return path


def load_window_state(data_dir):
    """Saved {width, height, maximized}, or {} when missing or unusable."""
    try:
        with open(os.path.join(data_dir, "window.json"), encoding="utf-8") as handle:
            state = json.load(handle)
        width, height = int(state["width"]), int(state["height"])
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    if not (400 <= width <= 10000 and 300 <= height <= 10000):
        return {}
    return {"width": width, "height": height, "maximized": bool(state.get("maximized"))}


def save_window_state(data_dir, state):
    try:
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, "window.json"), "w", encoding="utf-8") as handle:
            json.dump(state, handle)
    except OSError:
        pass


class AppWindow(QMainWindow):
    def __init__(self, app_options=None):
        super().__init__()
        self.setWindowTitle(f"{TITLE}[*]")
        self.pending = 0
        self.config_path = ""
        self.closing_confirmed = False
        self.data_dir = app_data_dir()
        saved = load_window_state(self.data_dir)
        self.resize(saved.get("width", 1280), saved.get("height", 860))
        self.normal_size = self.size()  # last size while not maximized
        self.restore_maximized = saved.get("maximized", False)

        self.view = QWebEngineView(self)
        self.view.setPage(Page(self.view))
        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.setCentralWidget(self.view)

        with open(os.path.join(WEB_DIR, "fonts", "tabler-map.json"), encoding="utf-8") as handle:
            glyphs = handle.read()
        self.bridge = Bridge(glyphs, self.on_ready, self.on_invoke, self.on_key, self)
        self.channel = QWebChannel(self)
        self.channel.registerObject("host", self.bridge)
        self.view.page().setWebChannel(self.channel)

        self.theme = Theme(QApplication.palette, self)
        self.theme.changed.connect(self.bridge.themeCss.emit)

        self.scheduler = QtScheduler(self)
        self.host = LuaHost(shared_ui_dir(), on_render=self.bridge.send_tree)
        self.api = NoctaliaApi(
            self.host, self.scheduler, self.data_dir, colors=self.theme.color,
            icon_path=lambda app_id, size=None: icon_file(app_id, size, os.path.join(self.data_dir, "icons")),
            notify=lambda title, body: self.statusBar().showMessage(f"{title}: {body}" if body else title, 8000),
            on_state=self.on_state, on_close=self.close, on_frame_tick=self.on_frame_tick,
        )
        options = {"isApp": True}
        options.update(app_options or {})
        self.host.start("app.luau", options, self.api.globals())

        self.frame_timer = QTimer(self, singleShot=True, interval=16)
        self.frame_timer.timeout.connect(lambda: self.host.call("onFrameTick", 16))
        self.watcher = QFileSystemWatcher(self)
        self.watch_timer = QTimer(self, singleShot=True, interval=400)
        self.watch_timer.timeout.connect(self.on_external_change)
        self.watcher.fileChanged.connect(self.watch_timer.start)

        self.view.load(Page.HOME)
        self.statusBar().hide()

    # ------------------------------------------------------------------ bridge callbacks
    def on_ready(self):
        self.bridge.themeCss.emit(self.theme.css)
        if not getattr(self, "_opened", False):
            self._opened = True
            self.host.call("onOpen")

    def on_invoke(self, callback, args):
        self.host.invoke(callback, *args)

    def on_key(self, chord):
        self.host.call("onKey", chord, True)

    def on_frame_tick(self, wanted):
        if wanted and not self.frame_timer.isActive():
            self.frame_timer.start()

    def on_state(self, key, value):
        if key == "umbriel.pending":
            self.pending = int(value or 0)
            self.setWindowModified(self.pending > 0)
        elif key == "umbriel.config" and value != self.config_path:
            if self.config_path:
                self.watcher.removePath(self.config_path)
            self.config_path = value or ""
            if self.config_path and os.path.exists(self.config_path):
                self.watcher.addPath(self.config_path)
                self.setWindowFilePath(self.config_path)

    def on_external_change(self):
        # editors replace the file, which drops the watch; re-add it before reloading
        if self.config_path and os.path.exists(self.config_path) and self.config_path not in self.watcher.files():
            self.watcher.addPath(self.config_path)
        self.host.call("onExternalChange")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not (self.isMaximized() or self.isFullScreen()):
            self.normal_size = self.size()

    # ------------------------------------------------------------------ closing
    def closeEvent(self, event):
        if self.pending > 0 and not self.closing_confirmed:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle("Unsaved changes")
            box.setText(f"You have {self.pending} unsaved change(s).")
            box.setInformativeText("They are kept as a draft and restored the next time you open Umbriel Settings.")
            review = box.addButton("Review && save", QMessageBox.ButtonRole.AcceptRole)
            keep = box.addButton("Keep draft and close", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() is review:
                self.host.call("onKey", "ctrl+s", True)
                event.ignore()
                return
            if box.clickedButton() is not keep:
                event.ignore()
                return
        self.host.call("onClose")
        save_window_state(self.data_dir, {
            "width": self.normal_size.width(), "height": self.normal_size.height(),
            "maximized": self.isMaximized() or self.isFullScreen(),
        })
        event.accept()


def ui_selftest_tree(window):
    """Last rendered tree as JSON text (used by tests and the render tool)."""
    return json.loads(window.bridge.last_tree) if window.bridge.last_tree else None
