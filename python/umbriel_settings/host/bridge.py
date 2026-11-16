"""QWebChannel object between the web renderer and the Lua host, plus a Qt scheduler for the API."""

import concurrent.futures
import json
import traceback

from PySide6.QtCore import QObject, QTimer, Signal, Slot


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
        self.on_ready()
        if self.last_tree is not None:
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
    """post() runs on the GUI thread's event loop; background() runs work on a pool, done() on the GUI thread."""

    _deliver = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self._deliver.connect(lambda function: function())

    def post(self, function):
        QTimer.singleShot(0, function)

    def background(self, work, done, on_error=None):
        """work() on a pool thread, then done(result) on the GUI thread.

        If work() raises, done(on_error(error)) runs instead, so a Lua callback waiting on the result is never
        left hanging; without on_error the traceback is printed and done is skipped.
        """
        def run():
            try:
                result = work()
            except Exception as error:  # every failure must reach the GUI thread
                if on_error is None:
                    traceback.print_exception(error)
                    return
                result = on_error(error)
            self._deliver.emit(lambda: done(result))
        self.pool.submit(run)
