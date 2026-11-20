"""Standalone window: the shared Luau UI (app.luau) rendered as HTML in a QWebEngineView."""

import json
import os
import signal
import socket
import sys

from PySide6.QtCore import QFileSystemWatcher, QSize, QSocketNotifier, QTimer, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from umbriel_core import mimeapps, xdg_dirs
from umbriel_core.paths import atomic_write

from .host.api import NoctaliaApi
from .host.bridge import Bridge, QtScheduler
from .host.paths import app_data_dir, shared_ui_dir, watch_with_parents
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
        atomic_write(os.path.join(data_dir, "window.json"), json.dumps(state))
    except OSError:
        pass


def quit_on_signals(app, window):
    """Ctrl+C and SIGTERM (logout, kill) close the window like the close button, so the draft is kept.

    Python only runs signal handlers between bytecodes and Qt's event loop is native code, so a wakeup
    socket hands the event loop something to do when a signal arrives.
    """
    reader, writer = socket.socketpair()
    writer.setblocking(False)
    signal.set_wakeup_fd(writer.fileno())
    notifier = QSocketNotifier(reader.fileno(), QSocketNotifier.Type.Read, app)
    notifier.activated.connect(lambda *_: reader.recv(64))
    app._signal_wakeup = (reader, writer, notifier)

    def close(*_):
        window.closing_confirmed = True  # no "unsaved changes" question for a signal
        window.close()
        app.quit()
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, close)


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
        # a crashed or killed web renderer would leave the window blank: load the page again (on ready, the
        # bridge sends the theme, glyphs and the last tree)
        self.view.page().renderProcessTerminated.connect(lambda status, code: self.view.reload())
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
        self.host = LuaHost(shared_ui_dir(), on_render=self.bridge.send_tree, on_error=self.on_lua_error)
        self._recovering = False
        self.api = NoctaliaApi(
            self.host, self.scheduler, self.data_dir, colors=self.theme.color,
            icon_path=lambda app_id, size=None: icon_file(app_id, size, os.path.join(self.data_dir, "icons")),
            notify=lambda title, body: self.show_notice(f"{title}: {body}" if body else title),
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
        self.watcher.fileChanged.connect(self.on_file_change)
        self.watcher.directoryChanged.connect(self.on_directory_change)
        # user-dirs.dirs and mimeapps.list (both in $XDG_CONFIG_HOME); their folder brings back lost watches
        self.desktop_files = [str(xdg_dirs.config_path()), str(mimeapps.config_path())]
        self.desktop_timer = QTimer(self, singleShot=True, interval=400)
        self.desktop_timer.timeout.connect(self.on_desktop_change)
        self.watch_desktop_files()

        self.view.load(Page.HOME)
        # The status bar only appears while a notification (noctalia.notify) is shown.
        self.statusBar().hide()
        self.statusBar().messageChanged.connect(lambda text: self.statusBar().setVisible(bool(text)))

    def on_lua_error(self, error):
        """A UI error: report it where the user sees it, then let the shell clear busy flags it left set."""
        self.host._print_error(error)
        first = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
        self.show_notice(f"Something went wrong: {first}")
        if not self._recovering:  # an error inside onRecover must not recurse
            self._recovering = True
            try:
                self.host.call("onRecover")
            finally:
                self._recovering = False

    def show_notice(self, text):
        self.statusBar().show()
        self.statusBar().showMessage(text, 8000)

    def activate_from(self, message):
        """Another launch handed over (single instance): come to the front and open its config, if any."""
        token = message.get("token")
        if isinstance(token, str) and token:
            os.environ["XDG_ACTIVATION_TOKEN"] = token  # Qt's Wayland backend activates with it once
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        os.environ.pop("XDG_ACTIVATION_TOKEN", None)  # used up: programs launched later mustn't get it
        config = message.get("config")
        if isinstance(config, str) and config:
            self.host.call("onRelaunch", config)

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
                self.watcher.removePaths([self.config_path, os.path.dirname(self.config_path)])
            self.config_path = value or ""
            if self.config_path:
                # The folder too: a file watch ends when an editor replaces the file, and can't start before
                # the file exists.
                self.watcher.addPaths([self.config_path, os.path.dirname(self.config_path)])
                self.setWindowFilePath(self.config_path)

    def watch_desktop_files(self):
        """Watch the desktop files that exist and are not watched yet; returns True when one was added."""
        return any(path in self.desktop_files for path in watch_with_parents(self.watcher, self.desktop_files))

    def on_file_change(self, path):
        (self.desktop_timer if path in self.desktop_files else self.watch_timer).start()

    def on_directory_change(self, _path):
        """The config appeared, or came back after its watch was lost: watch it again and reload."""
        if self.config_path and self.config_path not in self.watcher.files() and os.path.exists(self.config_path):
            self.watcher.addPath(self.config_path)
            self.watch_timer.start()
        if self.watch_desktop_files():  # replaced atomically (xdg-mime, xdg-user-dirs-update) or created
            self.desktop_timer.start()

    def on_desktop_change(self):
        self.watch_desktop_files()
        self.host.call("onExternalChange", "desktop")

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
