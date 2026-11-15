"""The `noctalia` and `panel` globals for the shared UI, implemented for the standalone app.

Only the functions the shared Luau code calls are provided. Helper commands (umbriel_settings.py) run
in-process on a worker thread instead of as a subprocess; other commands run as processes.
"""

import collections
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback

from umbriel_core.launch import child_env
from umbriel_core.paths import atomic_write


class ManualScheduler:
    """Runs posted work when asked (tests). The Qt window uses QtScheduler with the same interface."""

    def __init__(self):
        self.queue = collections.deque()

    def post(self, function):
        self.queue.append(function)

    def background(self, work, done):
        """Run work() off the GUI thread, then done(result) on it; here both run on the next drain."""
        self.post(lambda: done(work()))

    def drain(self, limit=10000):
        count = 0
        while self.queue and count < limit:
            self.queue.popleft()()
            count += 1
        return count


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
                     "fileExists", "removeFile", "renameFile", "fileInfo", "listDir", "getenv",
                     "commandExists", "runAsync", "notify", "notifyError", "fuzzyScore", "appIconPath",
                     "getColor", "nowMs", "togglePanel"):
            noctalia[name] = getattr(self, name)
        noctalia["json"] = lua.to_lua({})
        noctalia["json"]["encode"] = self.json_encode
        noctalia["json"]["decode"] = self.json_decode
        noctalia["string"] = lua.to_lua({})
        noctalia["string"]["trim"] = lambda value: (value or "").strip()
        noctalia["state"] = lua.to_lua({})
        noctalia["state"]["set"] = self.on_state
        noctalia["state"]["get"] = lambda key: None
        noctalia["state"]["watch"] = lambda key, fn: None
        panel = lua.to_lua({})
        panel["render"] = lua.render
        panel["close"] = lambda: self.on_close()
        panel["setNeedsFrameTick"] = lambda wanted: self.on_frame_tick(bool(wanted))
        panel["setWantsSecondTicks"] = lambda wanted: None
        panel["openContextMenu"] = lambda request: False
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
        self.scheduler.background(work, done)
        return True

    def fileExists(self, path):
        return os.path.exists(os.path.expanduser(path))

    def removeFile(self, path):
        try:
            os.remove(os.path.expanduser(path))
            return True
        except OSError as error:
            return False, str(error)

    def renameFile(self, source, target):
        try:
            os.replace(os.path.expanduser(source), os.path.expanduser(target))
            return True
        except OSError as error:
            return False, str(error)

    def fileInfo(self, path):
        try:
            info = os.stat(os.path.expanduser(path))
        except OSError as error:
            return None, str(error)
        return self.host.to_lua({"size": info.st_size, "mtime": int(info.st_mtime),
                                 "isDir": os.path.isdir(os.path.expanduser(path))})

    def listDir(self, path):
        try:
            return self.host.to_lua(sorted(os.listdir(os.path.expanduser(path))))
        except OSError as error:
            return None, str(error)

    # ------------------------------------------------------------------ processes
    def getenv(self, name):
        return os.environ.get(name)

    def commandExists(self, name):
        return shutil.which(name) is not None

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
        args = [str(argv[i]) for i in range(1, len(argv) + 1)] if self.host.is_table(argv) else [str(argv)]
        seconds = (timeout or 5000) / 1000
        in_process = len(args) >= 3 and os.path.basename(args[2]) == "umbriel_settings.py"

        def work():
            if in_process:
                # The callback must always run: an exception here would leave the UI waiting for the helper.
                try:
                    return {"exitCode": 0, "stdout": self._helper(args[2]).run(args[3:]), "stderr": "",
                            "timedOut": False}
                except Exception:  # an import error or a helper bug; reported like a crashed process
                    return {"exitCode": 1, "stdout": "", "stderr": traceback.format_exc(), "timedOut": False}
            try:
                command = args if self.host.is_table(argv) else ["/bin/sh", "-c", args[0]]
                result = subprocess.run(command, capture_output=True, text=True, timeout=seconds, check=False,
                                        env=child_env())
                return {"exitCode": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
                        "timedOut": False}
            except subprocess.TimeoutExpired:
                return {"exitCode": -1, "stdout": "", "stderr": "", "timedOut": True}
            except (OSError, ValueError) as error:  # ValueError: an argument with a NUL byte
                return {"exitCode": 127, "stdout": "", "stderr": str(error), "timedOut": False}

        def done(result):
            if callback is not None:
                result.update(stdoutTruncated=False, stderrTruncated=False)
                self.host.guard(callback, self.host.to_lua(result))
        self.scheduler.background(work, done)
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

    def notifyError(self, title, body=None):
        self.notify_cb(title, body or "")

    def fuzzyScore(self, pattern, text):
        return fuzzy_score(pattern or "", text or "")

    def appIconPath(self, app_id, size=None):
        return self.icon_path(app_id, size)

    def getColor(self, role):
        return self.colors(role)

    def nowMs(self):
        return int(time.time() * 1000)

    def togglePanel(self, panel_id):
        return None
