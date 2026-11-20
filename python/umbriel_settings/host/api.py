"""The `noctalia` and `panel` globals for the shared UI, implemented for the standalone app.

Only the functions the shared Luau code calls are provided. `runAsync` only runs the helper
(umbriel_settings.py), in-process on a worker thread instead of as a subprocess.
"""

import importlib.util
import json
import os
import sys
import threading
import time
import traceback

from umbriel_core.paths import atomic_write

# Helper commands that ask the running compositor (up to 5 s): the scheduler's separate slow pool.
SLOW_HELPER_COMMANDS = {"outputs", "windows", "layers", "xkb", "run-action", "focused-window"}
# Long polls (wait for a compositor event or a timer): a thread each, so they never hold a pool thread.
LONG_HELPER_COMMANDS = {"wait-live", "wait"}


def fuzzy_score(pattern, text):
    """Subsequence match like Noctalia's matcher: higher for consecutive and early hits, None when absent."""
    pattern, text = pattern.casefold(), text.casefold()
    if not pattern:
        return 0
    if pattern in text:
        return 1000 - text.index(pattern)
    score, position, streak = 0, 0, 0
    for char in pattern:
        found = text.find(char, position)
        if found < 0:
            return None
        streak = streak + 1 if found == position else 0
        score += 10 + streak * 5 - min(found - position, 9)
        position = found + 1
    return score


class NoctaliaApi:
    def __init__(self, host, scheduler, data_dir, colors=None, icon_path=None, notify=None, on_state=None,
                 on_close=None, on_frame_tick=None):
        self.host = host
        self.scheduler = scheduler
        self.data_dir = data_dir
        self.colors = colors or (lambda role: None)
        self.icon_path = icon_path or (lambda app_id, size=None: None)
        self.notify_cb = notify or (lambda title, body: None)
        self.on_state = on_state or (lambda key, value: None)
        self.on_close = on_close or (lambda: None)
        self.on_frame_tick = on_frame_tick or (lambda wanted: None)
        self._helpers = {}
        self._helper_lock = threading.Lock()

    # ------------------------------------------------------------------ globals
    def globals(self):
        lua = self.host
        noctalia = lua.to_lua({})
        for name in ("pluginDir", "pluginDataDir", "mkdirAll", "writeFile", "readFile", "readFileAsync",
                     "fileExists", "removeFile", "getenv", "runAsync", "notify", "fuzzyScore",
                     "appIconPath", "getColor", "nowMs", "copyToClipboard"):
            noctalia[name] = getattr(self, name)
        noctalia["json"] = lua.to_lua({})
        noctalia["json"]["encode"] = self.json_encode
        noctalia["json"]["decode"] = self.json_decode
        noctalia["string"] = lua.to_lua({})
        noctalia["string"]["trim"] = lambda value: (value or "").strip()
        noctalia["state"] = lua.to_lua({})
        noctalia["state"]["set"] = self.on_state
        panel = lua.to_lua({})
        panel["render"] = lua.render
        panel["close"] = lambda: self.on_close()
        panel["setNeedsFrameTick"] = lambda wanted: self.on_frame_tick(bool(wanted))
        return {"noctalia": noctalia, "panel": panel}

    # ------------------------------------------------------------------ files
    def pluginDir(self):
        return self.host.ui_dir

    def pluginDataDir(self):
        os.makedirs(self.data_dir, mode=0o700, exist_ok=True)
        return self.data_dir

    def mkdirAll(self, path):
        try:
            os.makedirs(os.path.expanduser(path), exist_ok=True)
            return True
        except OSError as error:
            return False, str(error)

    def writeFile(self, path, content):
        path = os.path.expanduser(path)
        try:
            # Atomic (a crash never leaves half a draft) and private from the first byte.
            atomic_write(path, content, None if os.path.exists(path) else 0o600)
            return True
        except OSError as error:
            return False, str(error)

    def readFile(self, path):
        try:
            with open(os.path.expanduser(path), encoding="utf-8") as handle:
                return handle.read()
        except (OSError, UnicodeError) as error:
            return None, str(error)

    def readFileAsync(self, path, callback):
        def work():
            return self.readFile(path)

        def done(result):
            if isinstance(result, tuple):
                self.host.guard(callback, None, result[1])
            else:
                self.host.guard(callback, result, None)
        self.scheduler.background(work, done, lambda error: (None, f"{type(error).__name__}: {error}"))
        return True

    def fileExists(self, path):
        return os.path.exists(os.path.expanduser(path))

    def removeFile(self, path):
        try:
            os.remove(os.path.expanduser(path))
            return True
        except OSError as error:
            return False, str(error)

    # ------------------------------------------------------------------ processes
    def getenv(self, name):
        return os.environ.get(name)

    def _helper(self, path):
        """Import umbriel_settings.py once and reuse it (its commands then run in this process)."""
        path = os.path.abspath(path)
        with self._helper_lock:  # the first calls arrive together on worker threads; import once, undisturbed
            if path not in self._helpers:
                spec = importlib.util.spec_from_file_location("umbriel_settings_app_helper", path)
                module = importlib.util.module_from_spec(spec)
                # The helper puts its folder first on sys.path; that folder holds umbriel_settings.py, which would
                # shadow this package (also umbriel_settings) for later imports, so the path is restored.
                saved_path = list(sys.path)
                try:
                    spec.loader.exec_module(module)
                finally:
                    sys.path[:] = saved_path
                self._helpers[path] = module
            return self._helpers[path]

    def runAsync(self, argv, callback=None, timeout=None):
        is_list = self.host.is_table(argv)  # here, not in the worker thread: it would wait for the Lua lock
        args = [str(argv[i]) for i in range(1, len(argv) + 1)] if is_list else [str(argv)]
        command = args[3] if len(args) > 3 else ""
        lane = "long" if command in LONG_HELPER_COMMANDS else "slow" if command in SLOW_HELPER_COMMANDS else "fast"

        def work():
            if len(args) < 3 or os.path.basename(args[2]) != "umbriel_settings.py":
                return {"exitCode": 127, "stdout": "", "stderr": "The app only runs umbriel_settings.py.",
                        "timedOut": False}
            # The callback must always run: an exception here would leave the UI waiting for the helper.
            try:
                return {"exitCode": 0, "stdout": self._helper(args[2]).run(args[3:]), "stderr": "",
                        "timedOut": False}
            except Exception:  # an import error or a helper bug; reported like a crashed process
                return {"exitCode": 1, "stdout": "", "stderr": traceback.format_exc(), "timedOut": False}

        def done(result):
            if callback is not None:
                result.update(stdoutTruncated=False, stderrTruncated=False)
                self.host.guard(callback, self.host.to_lua(result))
        self.scheduler.background(work, done, lambda error: {
            "exitCode": 1, "stdout": "", "stderr": "".join(traceback.format_exception(error)), "timedOut": False},
            lane=lane)
        return True

    # ------------------------------------------------------------------ misc
    def json_encode(self, value, pretty=False):
        try:
            return json.dumps(self.host.to_py(value), ensure_ascii=False, indent=2 if pretty else None)
        except (TypeError, ValueError) as error:
            return None, str(error)

    def json_decode(self, text):
        try:
            return self.host.to_lua(json.loads(text))
        except (TypeError, ValueError) as error:
            return None, str(error)

    def notify(self, title, body=None):
        self.notify_cb(title, body or "")

    def fuzzyScore(self, pattern, text):
        return fuzzy_score(pattern or "", text or "")

    def appIconPath(self, app_id, size=None):
        return self.icon_path(app_id, size)

    def getColor(self, role):
        return self.colors(role)

    def nowMs(self):
        return int(time.time() * 1000)

    def copyToClipboard(self, text, mime="text/plain"):
        """Like Noctalia's: `text` on the clipboard as `mime`; False without a Qt application (tests)."""
        from PySide6.QtCore import QMimeData
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        if app is None:
            return False
        data = QMimeData()
        if mime == "text/plain":
            data.setText(str(text))
        else:
            data.setData(str(mime), str(text).encode("utf-8"))
        app.clipboard().setMimeData(data)
        return True
