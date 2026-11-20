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
        icon_patch = patch.object(appicon, "APP_ICON_PATH", self.png_path)
        icon_patch.start()
        self.addCleanup(icon_patch.stop)

    def write_png(self, color):
        image = QImage(256, 256, QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        painter.fillRect(64, 64, 128, 128, QColor(color))
        painter.end()
        self.assertTrue(image.save(self.png_path, "PNG"))

    def icon(self):
        self.write_png("blue")
        return appicon.create_app_icon()

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

    def test_icon_keeps_transparency_in_window_and_desktop_icon(self):
        self.write_png("blue")
        icon = appicon.create_app_icon()
        image = icon.pixmap(128, 128).toImage()
        self.assertEqual(image.pixelColor(2, 2).alpha(), 0)
        self.assertGreater(image.pixelColor(64, 64).blue(), 240)
        entry = self.install(icon)
        desktop_icon = QImage(os.path.join(
            self.tempdir.name, "icons", "hicolor", "128x128", "apps", "umbriel-settings.png"
        ))
        self.assertEqual((desktop_icon.width(), desktop_icon.height()), (128, 128))
        self.assertEqual(desktop_icon.pixelColor(2, 2).alpha(), 0)
        self.assertGreater(desktop_icon.pixelColor(64, 64).blue(), 240)
        self.assertIn("Name=Umbriel Settings\n", entry)
        self.assertIn(appicon.desktop_entry_quote(appicon.LAUNCHER_PATH), entry)

    def test_entry_and_icon_from_before_the_rename_are_removed(self):
        applications = os.path.join(self.tempdir.name, "applications")
        icons = os.path.join(self.tempdir.name, "icons", "hicolor", "128x128", "apps")
        os.makedirs(applications)
        os.makedirs(icons)
        for path in (os.path.join(applications, "umbriel-config-gui.desktop"),
                     os.path.join(icons, "umbriel-config-gui.png")):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("old")
        self.assertIn("StartupWMClass=umbriel-settings\n", self.install(self.icon()))
        self.assertEqual(sorted(os.listdir(applications)), ["umbriel-settings.desktop"])
        self.assertEqual(sorted(os.listdir(icons)), ["umbriel-settings.png"])

    def test_appimage_desktop_entry_runs_the_appimage_with_quoting(self):
        entry = self.install(self.icon(), APPIMAGE='/opt/My "Apps"/100%.AppImage')
        self.assertIn('Exec="/opt/My \\"Apps\\"/100%%.AppImage"\n', entry)

    def test_bundled_icon_is_a_transparent_png(self):
        image = QImage(os.path.join(os.path.dirname(appicon.__file__), "assets", "icon.png"))
        self.assertFalse(image.isNull())
        self.assertTrue(image.hasAlphaChannel())
        self.assertEqual(image.pixelColor(0, 0).alpha(), 0)

    def test_missing_or_invalid_icon_warns_and_gives_a_null_icon(self):
        with self.assertWarnsRegex(RuntimeWarning, "Could not load.*icon.png"):
            self.assertTrue(appicon.create_app_icon().isNull())
        with open(self.png_path, "wb") as icon:
            icon.write(b"not an image")
        with self.assertWarnsRegex(RuntimeWarning, "Could not load.*icon.png"):
            self.assertTrue(appicon.create_app_icon().isNull())


class AppStartupTests(unittest.TestCase):
    def test_application_uses_display_name_and_existing_desktop_id(self):
        with (
            patch("PySide6.QtWidgets.QApplication") as app_class,
            patch("umbriel_settings.app_window.AppWindow") as window_class,
            patch("umbriel_settings.app_window.quit_on_signals") as quit_on_signals,
            patch("umbriel_settings.appicon.create_app_icon"),
            patch("umbriel_settings.appicon.install_desktop_icon"),
            patch("umbriel_settings.qt6ct_theme.Qt6ctThemeFollower"),
            patch("umbriel_settings.instance.claim") as claim,
            patch.dict(os.environ, {"XDG_ACTIVATION_TOKEN": "token-1"}),
        ):
            app.main(["--no-validate", "/tmp/example.toml"])
        claim.assert_called_once_with({"config": "/tmp/example.toml", "token": "token-1"})
        claim.return_value.activated.connect.assert_called_once_with(window_class.return_value.activate_from)
        qt_app = app_class.return_value
        qt_app.setApplicationName.assert_called_once_with("Umbriel Settings")
        qt_app.setApplicationDisplayName.assert_called_once_with("Umbriel Settings")
        qt_app.setDesktopFileName.assert_called_once_with("umbriel-settings")
        window_class.assert_called_once_with({"appVersion": __version__, "initialConfig": "/tmp/example.toml",
                                              "validateDefault": False})
        qt_app.exec.assert_called_once_with()
        quit_on_signals.assert_called_once_with(qt_app, window_class.return_value)

    def test_a_ui_that_fails_to_start_shows_a_dialog(self):
        with (
            patch("PySide6.QtWidgets.QApplication") as app_class,
            patch("PySide6.QtWidgets.QMessageBox") as message_box,
            patch("umbriel_settings.app_window.AppWindow", side_effect=RuntimeError("app.luau:3: syntax error")),
            patch("umbriel_settings.appicon.create_app_icon"),
            patch("umbriel_settings.appicon.install_desktop_icon"),
            patch("umbriel_settings.qt6ct_theme.Qt6ctThemeFollower"),
            patch("umbriel_settings.instance.claim"),
            patch("sys.stderr"),
        ):
            self.assertEqual(app.main([]), 1)
        self.assertIn("syntax error", message_box.critical.call_args.args[2])
        app_class.return_value.exec.assert_not_called()

    def test_a_second_launch_hands_over_and_exits_without_a_window(self):
        with (
            patch("PySide6.QtWidgets.QApplication") as app_class,
            patch("umbriel_settings.app_window.AppWindow") as window_class,
            patch("umbriel_settings.appicon.install_desktop_icon") as install,
            patch("umbriel_settings.instance.claim", return_value=None),
        ):
            self.assertEqual(app.main([]), 0)
        window_class.assert_not_called()
        install.assert_not_called()
        app_class.return_value.exec.assert_not_called()

    def test_an_unchanged_desktop_entry_is_not_rewritten(self):
        from PySide6.QtGui import QIcon, QPixmap
        from PySide6.QtWidgets import QApplication
        self.qt_app = QApplication.instance() or QApplication([])
        pixmap = QPixmap(8, 8)
        pixmap.fill()
        with tempfile.TemporaryDirectory() as data_home, patch.object(appicon.sys, "platform", "linux"), \
                patch.dict(os.environ, {"XDG_DATA_HOME": data_home}):
            os.environ.pop("APPIMAGE", None)
            appicon.install_desktop_icon(QIcon(pixmap))
            with patch.object(appicon, "write_text_file") as write:
                appicon.install_desktop_icon(QIcon(pixmap))
            write.assert_not_called()

    def test_legacy_flag_is_gone(self):
        with self.assertRaises(SystemExit), patch("sys.stderr"):
            app.parse_args(["--legacy-ui"])


if __name__ == "__main__":
    unittest.main()
