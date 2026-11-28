"""Theme for the web renderer: Noctalia palette → qt6ct scheme → Qt palette, plus Noctalia's font."""

import os

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal
from PySide6.QtGui import QPalette

from umbriel_core import kde, noctalia_theme

from .paths import watch_with_parents


def palette_roles(palette):
    """Fallback roles from a QPalette (desktops without Noctalia)."""
    def hexof(role):
        return palette.color(role).name()
    return {
        "surface": hexof(QPalette.ColorRole.Window),
        "on_surface": hexof(QPalette.ColorRole.WindowText),
        "surface_container_low": hexof(QPalette.ColorRole.Base),
        "surface_container": hexof(QPalette.ColorRole.Button),
        "primary": hexof(QPalette.ColorRole.Highlight),
        "on_primary": hexof(QPalette.ColorRole.HighlightedText),
        "on_surface_variant": hexof(QPalette.ColorRole.PlaceholderText),
    }


class Theme(QObject):
    """Current roles and CSS; emits changed(css) when a source file changes what the page shows."""

    changed = Signal(str)

    def __init__(self, palette_source, parent=None):
        super().__init__(parent)
        self.palette_source = palette_source  # callable returning the app's QPalette
        self.roles, self.css, self.stamps = {}, "", None
        self.watcher = QFileSystemWatcher(self)
        self.timer = QTimer(self, singleShot=True, interval=250)
        self.timer.timeout.connect(self._changed)
        self.watcher.fileChanged.connect(self.timer.start)
        self.watcher.directoryChanged.connect(self.timer.start)
        self.refresh()

    @staticmethod
    def _files():
        files = [noctalia_theme.palette_file(), noctalia_theme.noctalia_config_file(),
                 noctalia_theme.noctalia_settings_file(), kde.qt6ct_config_path()]
        scheme = noctalia_theme.qt6ct_scheme()
        return files + [scheme] if scheme else files

    @staticmethod
    def _stamps(files):
        stamps = []
        for path in files:
            try:
                info = os.stat(path)
                stamps.append((path, info.st_mtime_ns, info.st_size))
            except OSError:
                stamps.append((path, None, None))
        return stamps

    def _changed(self):
        # the watched folders also hold files Noctalia writes all the time (state, usage counts)
        if self._stamps(self._files()) != self.stamps:
            self.refresh()
        else:
            self._watch(self._files())  # an atomic replace ends a file watch: add it again

    def refresh(self):
        files = self._files()
        self.stamps = self._stamps(files)
        self.roles, _ = noctalia_theme.load_roles(palette_roles(self.palette_source()))
        css = noctalia_theme.css_variables(self.roles, noctalia_theme.shell_style())
        self._watch(files)
        if css != self.css:
            self.css = css
            self.changed.emit(css)

    def _watch(self, files):
        watch_with_parents(self.watcher, files, prune=True)  # prune: a scheme no longer chosen

    def color(self, role):
        return self.roles.get(role)
