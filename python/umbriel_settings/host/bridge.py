"""QWebChannel object between the web renderer and the Lua host, plus a Qt scheduler for the API."""

import concurrent.futures
import json
import threading

from PySide6.QtCore import QObject, Signal, Slot


class Bridge(QObject):
    """Exposed to the page as `host`: Python → JS via signals, JS → Python via slots."""

    renderTree = Signal(str)
    themeCss = Signal(str)
    glyphMap = Signal(str)

    def __init__(self, glyph_json, on_ready, on_invoke, on_key, parent=None):
        super().__init__(parent)
        self.glyph_json = glyph_json
        self.on_ready, self.on_invoke, self.on_key = on_ready, on_invoke, on_key
        self.is_ready = False
        self.last_tree = None

    def send_tree(self, tree):
        self.last_tree = json.dumps(tree, ensure_ascii=False)
        if self.is_ready:
            self.renderTree.emit(self.last_tree)

    @Slot()
    def ready(self):
        self.is_ready = True
        self.glyphMap.emit(self.glyph_json)
        before = self.last_tree
        self.on_ready()
        # a reloaded page gets the last tree again, unless on_ready rendered (and sent) a new one
        if self.last_tree is not None and self.last_tree is before:
            self.renderTree.emit(self.last_tree)

    @Slot(str, str)
    def invoke(self, callback_json, args_json):
        try:
            callback, args = json.loads(callback_json), json.loads(args_json)
        except ValueError:
            return
        if isinstance(args, list):
            self.on_invoke(callback, args)

    @Slot(str)
    def key(self, chord):
        self.on_key(chord)


class QtScheduler(QObject):
    """background() runs work off the GUI thread, then done(result) on it."""

    _deliver = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        # commands that ask the compositor (`umbriel outputs`, up to 5 s) must not use up the threads that saves
        # and file reads need
        self.slow_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        # file reads (every helper reply goes through one) never wait behind a validating save
        self.io_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self._deliver.connect(lambda function: function())

    def background(self, work, done, on_error, lane="fast"):
        """work() on a pool thread ("slow", "io": separate pools; "long": a thread of its own, for long polls), then
        done(result) on the GUI thread. If work() raises, done(on_error(error)) runs instead, so a Lua callback
        waiting on the result is never left hanging."""
        def run():
            try:
                result = work()
            except Exception as error:  # every failure must reach the GUI thread
                result = on_error(error)
            self._deliver.emit(lambda: done(result))
        if lane == "long":
            threading.Thread(target=run, daemon=True).start()
        else:
            {"slow": self.slow_pool, "io": self.io_pool}.get(lane, self.pool).submit(run)
