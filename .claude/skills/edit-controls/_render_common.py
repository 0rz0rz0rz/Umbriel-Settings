"""Shared by render_app.py and render_docs.py: temporary data with a config copy, the app window, its teardown."""

import os
import shutil
import sys
import tempfile

# Runs from anywhere: offscreen Qt and the app's package on the import path (no `cd python`, no env prefix).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "python"))


def temp_home(source, prefix):
    """A temp dir as XDG_DATA_HOME (its data/) holding a copy of `source`; returns (temp dir, config path)."""
    tmp = tempfile.mkdtemp(prefix=prefix)
    os.environ["XDG_DATA_HOME"] = os.path.join(tmp, "data")
    config = os.path.join(tmp, "config.toml")
    shutil.copy(source, config)
    return tmp, config


def open_window(config, size):
    """The QApplication and a shown AppWindow on `config`; returns (app, window)."""
    from PySide6.QtWidgets import QApplication

    from umbriel_settings.app_window import AppWindow  # QtWebEngine must load before QApplication exists

    app = QApplication([])
    win = AppWindow({"initialConfig": config})
    win.resize(*size)
    win.show()
    return app, win


def close_window(win, tmp):
    """Print Lua errors, then close and delete the page before Qt shuts down (else QtWebEngine can crash at
    exit) and remove `tmp`. Returns whether the UI ran without Lua errors."""
    from PySide6.QtCore import QCoreApplication, QEvent

    if win.host.errors:
        print("Lua errors:", *win.host.errors, sep="\n  ", file=sys.stderr)
    win.closing_confirmed = True
    win.close()
    win.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    shutil.rmtree(tmp, ignore_errors=True)
    return not win.host.errors
