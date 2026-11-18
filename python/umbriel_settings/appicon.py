"""Application icon and the per-user desktop entry that lets Wayland taskbars find it."""

import base64
import contextlib
import os
import sys
import warnings

from PySide6.QtGui import QIcon, QPixmap

from umbriel_core.paths import DESKTOP_ENTRY, LEGACY_DIR_NAME, write_text_file, xdg_data_home

from . import APP_NAME

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
LAUNCHER_PATH = os.path.join(os.path.dirname(PACKAGE_DIR), "umbriel-settings.py")
# The first of these that exists replaces the embedded icon; Qt detects the format from the content.
APP_ICON_PATHS = tuple(os.path.join(PACKAGE_DIR, "assets", "icon" + suffix)
                       for suffix in (".png", ".jpg", ".jpeg"))

_APP_ICON_DATA = (
    "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"
)


def create_app_icon():
    path = next((path for path in APP_ICON_PATHS if os.path.lexists(path)), None)
    if path:
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            return QIcon(pixmap)
        warnings.warn(
            f"Could not load application icon from {path}; using the embedded icon instead",
            RuntimeWarning,
            stacklevel=2,
        )
    pixmap = QPixmap()
    if not pixmap.loadFromData(base64.b64decode(_APP_ICON_DATA), "PNG"):
        raise RuntimeError("Could not decode the embedded Umbriel application icon")
    return QIcon(pixmap)


def desktop_entry_quote(value):
    """Quote one executable path according to the desktop-entry Exec syntax."""
    value = value.replace("%", "%%")
    for character in ("\\", '"', "`", "$"):
        value = value.replace(character, "\\" + character)
    return f'"{value}"'


def install_desktop_icon(icon):
    """Install a matching per-user desktop entry for Wayland taskbar icon lookup."""
    if sys.platform != "linux":
        return
    data_home = xdg_data_home()
    icon_directory = os.path.join(data_home, "icons", "hicolor", "128x128", "apps")
    application_directory = os.path.join(data_home, "applications")
    icon_path = os.path.join(icon_directory, "umbriel-settings.png")
    desktop_path = os.path.join(application_directory, DESKTOP_ENTRY)
    os.makedirs(icon_directory, exist_ok=True)
    os.makedirs(application_directory, exist_ok=True)
    if not icon.pixmap(128, 128).save(icon_path, "PNG"):
        raise OSError(f"Could not write application icon to {icon_path}")
    appimage_path = os.environ.get("APPIMAGE")
    if appimage_path:
        # Inside an AppImage, sys.executable and the launcher live on a temporary mount.
        exec_line = desktop_entry_quote(appimage_path)
    else:
        exec_line = f"{desktop_entry_quote(sys.executable)} {desktop_entry_quote(LAUNCHER_PATH)}"
    desktop_entry = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Configure the Umbriel desktop environment\n"
        f"Exec={exec_line}\n"
        "Icon=umbriel-settings\n"
        "Terminal=false\n"
        "Categories=Settings;DesktopSettings;\n"
        "StartupNotify=true\n"
        "StartupWMClass=umbriel-settings\n"
    )
    try:
        with open(desktop_path, encoding="utf-8") as handle:
            current = handle.read()
    except (OSError, UnicodeError):
        current = None
    if current != desktop_entry:  # an unchanged entry is left alone, so menus don't rescan on every start
        write_text_file(desktop_path, desktop_entry)
    # The entry and icon from before the rename point at a launcher that no longer exists.
    for legacy in (os.path.join(application_directory, LEGACY_DIR_NAME + ".desktop"),
                   os.path.join(icon_directory, LEGACY_DIR_NAME + ".png")):
        with contextlib.suppress(FileNotFoundError):
            os.remove(legacy)
