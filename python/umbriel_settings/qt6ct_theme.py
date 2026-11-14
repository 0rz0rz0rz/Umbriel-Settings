"""Follow the user's qt6ct settings (style, fonts, icons, KDE-format color scheme).

A normal install gets this from the qt6ct platform theme plugin. A bundled Qt (AppImage,
pip wheels) cannot load the system plugin, so the same settings are applied here.
Noctalia rewrites the configured color scheme when its theme changes; it is watched
and re-applied while the app runs.

Set UMBRIEL_QT_THEME=none to disable, or =qt6ct to force it.
"""
import os

from PySide6.QtCore import QFileSystemWatcher, QSettings, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import QStyleFactory

from umbriel_core.kde import qt6ct_config_path, read_scheme

_ROLE_SECTIONS = (
    (QPalette.ColorRole.Window, "Window", "BackgroundNormal"),
    (QPalette.ColorRole.WindowText, "Window", "ForegroundNormal"),
    (QPalette.ColorRole.Base, "View", "BackgroundNormal"),
    (QPalette.ColorRole.AlternateBase, "View", "BackgroundAlternate"),
    (QPalette.ColorRole.Text, "View", "ForegroundNormal"),
    (QPalette.ColorRole.PlaceholderText, "View", "ForegroundInactive"),
    (QPalette.ColorRole.Link, "View", "ForegroundLink"),
    (QPalette.ColorRole.LinkVisited, "View", "ForegroundVisited"),
    (QPalette.ColorRole.Button, "Button", "BackgroundNormal"),
    (QPalette.ColorRole.ButtonText, "Button", "ForegroundNormal"),
    (QPalette.ColorRole.Highlight, "Selection", "BackgroundNormal"),
    (QPalette.ColorRole.HighlightedText, "Selection", "ForegroundNormal"),
    (QPalette.ColorRole.ToolTipBase, "Tooltip", "BackgroundNormal"),
    (QPalette.ColorRole.ToolTipText, "Tooltip", "ForegroundNormal"),
)
_DISABLED_TEXT_ROLES = (
    (QPalette.ColorRole.WindowText, "Window"),
    (QPalette.ColorRole.Text, "View"),
    (QPalette.ColorRole.ButtonText, "Button"),
)


def read_kde_color_scheme(path):
    """Return {(section, key): QColor} from a KDE .colors file ("Colors:" dropped from sections), or {}."""
    return {(section[len("Colors:"):], key): QColor(*rgb) for (section, key), rgb in read_scheme(path).items()
            if section.startswith("Colors:")}


def build_palette(colors, base_palette):
    """Map KDE color scheme entries onto a copy of base_palette; None if too incomplete."""
    if ("Window", "BackgroundNormal") not in colors or ("View", "BackgroundNormal") not in colors:
        return None
    palette = QPalette(base_palette)
    # Let Qt derive Light/Midlight/Mid/Dark/Shadow from the button and window colors.
    derived = QPalette(
        colors.get(("Button", "BackgroundNormal"), palette.color(QPalette.ColorRole.Button)),
        colors[("Window", "BackgroundNormal")],
    )
    for role in (
        QPalette.ColorRole.Light, QPalette.ColorRole.Midlight, QPalette.ColorRole.Mid,
        QPalette.ColorRole.Dark, QPalette.ColorRole.Shadow,
    ):
        palette.setColor(role, derived.color(role))
    for role, section, key in _ROLE_SECTIONS:
        color = colors.get((section, key))
        if color is not None:
            palette.setColor(role, color)
    accent = colors.get(("Selection", "BackgroundNormal"))
    if accent is not None:
        palette.setColor(QPalette.ColorRole.Accent, accent)
    for role, section in _DISABLED_TEXT_ROLES:
        color = colors.get((section, "ForegroundInactive"))
        if color is not None:
            palette.setColor(QPalette.ColorGroup.Disabled, role, color)
    return palette


def _font(settings, key):
    text = settings.value(f"Fonts/{key}", "", str)
    if not text:
        return None
    font = QFont()
    return font if font.fromString(text.strip('"')) else None


def should_apply(app, settings):
    """Skip when disabled or when Qt already honors the qt6ct platform theme."""
    mode = os.environ.get("UMBRIEL_QT_THEME", "").lower()
    if mode == "none":
        return False
    if mode == "qt6ct":
        return True
    if os.environ.get("QT_QPA_PLATFORMTHEME", "") not in ("qt6ct", "qt5ct"):
        return False
    current = app.style().name().lower()
    if current.startswith("qt6ct") or current.startswith("qt5ct"):
        return False
    wanted = settings.value("Appearance/style", "", str)
    return bool(wanted) and current != wanted.lower()


def apply_qt6ct_theme(app, config_path=None, first_run=True):
    """Apply qt6ct style, palette, fonts and icon theme to app. Returns the files read."""
    config_path = config_path or qt6ct_config_path()
    if not os.path.isfile(config_path):
        return []
    settings = QSettings(config_path, QSettings.Format.IniFormat)
    if first_run and not should_apply(app, settings):
        return []
    files = [config_path]

    style_name = settings.value("Appearance/style", "", str)
    available = {name.lower(): name for name in QStyleFactory.keys()}
    style_name = available.get(style_name.lower()) or available.get("fusion")
    if style_name and app.style().name().lower() != style_name.lower():
        app.setStyle(style_name)

    scheme_path = settings.value("Appearance/color_scheme_path", "", str)
    if settings.value("Appearance/custom_palette", False, bool) and scheme_path:
        scheme_path = os.path.expanduser(scheme_path)
        files.append(scheme_path)
        palette = build_palette(read_kde_color_scheme(scheme_path), app.style().standardPalette())
        if palette is not None:
            app.setPalette(palette)

    font = _font(settings, "general")
    if font is not None:
        app.setFont(font)
    icon_theme = settings.value("Appearance/icon_theme", "", str)
    if icon_theme:
        QIcon.setThemeName(icon_theme)
    return files


class Qt6ctThemeFollower:
    """Re-applies the qt6ct theme whenever its config or color scheme file changes."""

    def __init__(self, app):
        self.app = app
        self.watcher = QFileSystemWatcher()
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.refresh)
        self.watcher.fileChanged.connect(self.timer.start)
        self.watcher.directoryChanged.connect(self.timer.start)

    def start(self):
        files = apply_qt6ct_theme(self.app)
        self._watch(files)
        return bool(files)

    def refresh(self):
        self._watch(apply_qt6ct_theme(self.app, first_run=False))

    def _watch(self, files):
        # Theme tools often replace files atomically, which drops the file watch; watch
        # the parent directories too and re-add the files after every change.
        paths = [path for path in files if os.path.exists(path)]
        paths += sorted({os.path.dirname(path) for path in files if os.path.isdir(os.path.dirname(path))})
        stale = [path for path in self.watcher.files() + self.watcher.directories() if path not in paths]
        if stale:
            self.watcher.removePaths(stale)
        missing = [path for path in paths if path not in self.watcher.files() + self.watcher.directories()]
        if missing:
            self.watcher.addPaths(missing)
