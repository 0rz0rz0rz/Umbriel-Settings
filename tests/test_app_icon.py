import base64
import hashlib
import os
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

# Import app_window before any test patches PySide6.QtWidgets.QApplication; it binds the name at import.
from umbriel_settings import __version__, app, app_window, appicon  # noqa: F401


class AppIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.png_path = os.path.join(self.tempdir.name, "icon.png")
        self.icon_path = os.path.join(self.tempdir.name, "icon.jpg")
        icon_patch = patch.object(appicon, "APP_ICON_PATHS", (self.png_path, self.icon_path))
        icon_patch.start()
        self.addCleanup(icon_patch.stop)

    def write_icon(self, color):
        image = QImage(256, 256, QImage.Format.Format_RGB32)
        image.fill(QColor(color))
        self.assertTrue(image.save(self.icon_path, "JPEG"))

    def write_png(self, color):
        image = QImage(256, 256, QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        painter.fillRect(64, 64, 128, 128, QColor(color))
        painter.end()
        self.assertTrue(image.save(self.png_path, "PNG"))

    def install(self, icon, **environ):
        with patch.object(appicon.sys, "platform", "linux"), patch.dict(
            os.environ, {"XDG_DATA_HOME": self.tempdir.name, **environ}
        ):
            if "APPIMAGE" not in environ:
                os.environ.pop("APPIMAGE", None)
            appicon.install_desktop_icon(icon)
        with open(os.path.join(self.tempdir.name, "applications", "umbriel-settings.desktop"),
                  encoding="utf-8") as desktop_file:
            return desktop_file.read()

    def test_custom_jpeg_is_used_for_window_and_desktop_icon(self):
        self.write_icon("red")
        icon = appicon.create_app_icon()
        pixel = icon.pixmap(32, 32).toImage().pixelColor(16, 16)
        self.assertGreater(pixel.red(), 240)
        self.assertLess(pixel.green(), 15)
        self.assertLess(pixel.blue(), 15)

        entry = self.install(icon)
        desktop_icon = QImage(os.path.join(
            self.tempdir.name, "icons", "hicolor", "128x128", "apps", "umbriel-settings.png"
        ))
        self.assertFalse(desktop_icon.isNull())
        self.assertEqual((desktop_icon.width(), desktop_icon.height()), (128, 128))
        self.assertGreater(desktop_icon.pixelColor(64, 64).red(), 240)
        self.assertIn("Name=Umbriel Settings\n", entry)
        self.assertIn(appicon.desktop_entry_quote(appicon.LAUNCHER_PATH), entry)

    def test_custom_png_keeps_transparency_and_wins_over_jpeg(self):
        self.write_icon("red")
        self.write_png("blue")
        icon = appicon.create_app_icon()
        image = icon.pixmap(128, 128).toImage()
        self.assertEqual(image.pixelColor(2, 2).alpha(), 0)
        self.assertGreater(image.pixelColor(64, 64).blue(), 240)
        self.install(icon)
        desktop_icon = QImage(os.path.join(
            self.tempdir.name, "icons", "hicolor", "128x128", "apps", "umbriel-settings.png"
        ))
        self.assertEqual(desktop_icon.pixelColor(2, 2).alpha(), 0)
        self.assertGreater(desktop_icon.pixelColor(64, 64).blue(), 240)

    def test_entry_and_icon_from_before_the_rename_are_removed(self):
        applications = os.path.join(self.tempdir.name, "applications")
        icons = os.path.join(self.tempdir.name, "icons", "hicolor", "128x128", "apps")
        os.makedirs(applications)
        os.makedirs(icons)
        for path in (os.path.join(applications, "umbriel-config-gui.desktop"),
                     os.path.join(icons, "umbriel-config-gui.png")):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("old")
        self.assertIn("StartupWMClass=umbriel-settings\n", self.install(appicon.create_app_icon()))
        self.assertEqual(sorted(os.listdir(applications)), ["umbriel-settings.desktop"])
        self.assertEqual(sorted(os.listdir(icons)), ["umbriel-settings.png"])

    def test_appimage_desktop_entry_runs_the_appimage_with_quoting(self):
        entry = self.install(appicon.create_app_icon(), APPIMAGE='/opt/My "Apps"/100%.AppImage')
        self.assertIn('Exec="/opt/My \\"Apps\\"/100%%.AppImage"\n', entry)

    def test_missing_custom_icon_uses_embedded_icon(self):
        icon = appicon.create_app_icon()
        self.assertFalse(icon.isNull())
        self.assertEqual(icon.pixmap(128, 128).toImage().pixelColor(2, 2).alpha(), 0)
        self.assertEqual(
            hashlib.sha256(base64.b64decode(appicon._APP_ICON_DATA)).hexdigest(),
            "d0dae8fb814c9ff22fcb12cfb9ae4255b6424f70294b712893cdafe0f04a34be",
        )

    def test_bundled_icon_is_a_transparent_png(self):
        image = QImage(os.path.join(os.path.dirname(appicon.__file__), "assets", "icon.png"))
        self.assertFalse(image.isNull())
        self.assertTrue(image.hasAlphaChannel())
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)

    def test_invalid_custom_icon_warns_and_uses_embedded_icon(self):
        with open(self.png_path, "wb") as icon:
            icon.write(b"not an image")
        with self.assertWarnsRegex(RuntimeWarning, "Could not load.*icon.png"):
            self.assertFalse(appicon.create_app_icon().isNull())


class AppStartupTests(unittest.TestCase):
    def test_application_uses_display_name_and_existing_desktop_id(self):
        with (
            patch("PySide6.QtWidgets.QApplication") as app_class,
            patch("umbriel_settings.app_window.AppWindow") as window_class,
            patch("umbriel_settings.appicon.create_app_icon"),
            patch("umbriel_settings.appicon.install_desktop_icon"),
            patch("umbriel_settings.qt6ct_theme.Qt6ctThemeFollower"),
        ):
            app.main(["--no-validate", "/tmp/example.toml"])
        qt_app = app_class.return_value
        qt_app.setApplicationName.assert_called_once_with("Umbriel Settings")
        qt_app.setApplicationDisplayName.assert_called_once_with("Umbriel Settings")
        qt_app.setDesktopFileName.assert_called_once_with("umbriel-settings")
        window_class.assert_called_once_with({"appVersion": __version__, "initialConfig": "/tmp/example.toml",
                                              "validateDefault": False})
        qt_app.exec.assert_called_once_with()

    def test_legacy_flag_is_gone(self):
        with self.assertRaises(SystemExit), patch("sys.stderr"):
            app.parse_args(["--legacy-ui"])


if __name__ == "__main__":
    unittest.main()
