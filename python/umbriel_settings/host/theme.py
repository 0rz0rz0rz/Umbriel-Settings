"""Theme for the web renderer: Noctalia palette → qt6ct scheme → Qt palette, plus Noctalia's font."""

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal
from PySide6.QtGui import QPalette

from umbriel_core import noctalia_theme

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
    """Current roles and CSS; emits changed(css) when any source file changes."""

    changed = Signal(str)

    def __init__(self, palette_source, parent=None):
        super().__init__(parent)
        self.palette_source = palette_source  # callable returning the app's QPalette
        self.roles, self.source, self.css = {}, "", ""
        self.watcher = QFileSystemWatcher(self)
        self.timer = QTimer(self, singleShot=True, interval=250)
        self.timer.timeout.connect(self.refresh)
        self.watcher.fileChanged.connect(self.timer.start)
        self.watcher.directoryChanged.connect(self.timer.start)
        self.refresh()

    def refresh(self):
        self.roles, self.source = noctalia_theme.load_roles(palette_roles(self.palette_source()))
        self.css = noctalia_theme.css_variables(self.roles, noctalia_theme.shell_style())
        self._watch()
        self.changed.emit(self.css)

    def _watch(self):
        paths = [noctalia_theme.palette_file(), noctalia_theme.noctalia_config_file(),
                 noctalia_theme.noctalia_settings_file()]
        scheme = noctalia_theme.qt6ct_scheme()
        if scheme:
            paths.append(scheme)
        watch_with_parents(self.watcher, paths)

    def color(self, role):
        return self.roles.get(role)
