"""Application icon and the per-user desktop entry that lets Wayland taskbars find it."""

import contextlib
import os
import sys
import warnings

from PySide6.QtGui import QIcon, QPixmap

from umbriel_core.paths import DESKTOP_ENTRY, LEGACY_DIR_NAME, write_text_file, xdg_data_home

from . import APP_NAME

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
LAUNCHER_PATH = os.path.join(os.path.dirname(PACKAGE_DIR), "umbriel-settings.py")
APP_ICON_PATH = os.path.join(PACKAGE_DIR, "assets", "icon.png")


def create_app_icon():
    """The bundled icon; a null QIcon (with a warning) when it is missing or unreadable."""
    pixmap = QPixmap(APP_ICON_PATH)
    if pixmap.isNull():
        warnings.warn(f"Could not load the application icon {APP_ICON_PATH}", RuntimeWarning, stacklevel=2)
        return QIcon()
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
