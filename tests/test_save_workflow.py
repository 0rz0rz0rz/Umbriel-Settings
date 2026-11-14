import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import tomlkit

from PySide6.QtWidgets import QApplication

from umbriel_config_gui import common, desktop, settings_layout, state
from umbriel_config_gui.field_widget import FieldWidget
from umbriel_config_gui.window import Window


class SaveWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.config_path = os.path.join(self.tempdir.name, "config.toml")
        with open(self.config_path, "w", encoding="utf-8") as config:
            config.write("[general]\nmod_key = 'Super'\n")
        self.path_patch = patch.object(state, "PATH", self.config_path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

        self.userdirs = Mock(changed=False)
        self.defaultapps = Mock(changed=False)
        self.window = SimpleNamespace(
            confirm_external_change=Mock(return_value=True),
            confirm_save_diff=Mock(return_value=False),
            side_tabs=Mock(),
            _editor_page_names=(),
            fws=[],
            editors=[self.userdirs, self.defaultapps],
            userdirs=self.userdirs,
            defaultapps=self.defaultapps,
            doc=tomlkit.parse("[general]\nmod_key = 'Alt'\n"),
            rebuild_box=Mock(),
            diff_box=Mock(),
            validate_box=Mock(),
            status=Mock(),
            _dirty=True,
        )
        self.window.rebuild_box.isChecked.return_value = False
        self.window.diff_box.isChecked.return_value = True
        self.window.validate_box.isChecked.return_value = False
        from umbriel_config_gui.common import config_fingerprint

        self.window._disk_fingerprint = config_fingerprint(self.config_path)

    def test_canceling_diff_does_not_save_desktop_settings(self):
        self.assertFalse(Window.save(self.window))
        self.userdirs.commit.assert_not_called()
        self.defaultapps.commit.assert_not_called()
        with open(self.config_path, encoding="utf-8") as config:
            self.assertEqual(config.read(), "[general]\nmod_key = 'Super'\n")

    def test_desktop_save_error_is_reported(self):
        self.window.confirm_save_diff.return_value = True
        self.userdirs.commit.side_effect = OSError("permission denied")
        with patch("umbriel_config_gui.window.QMessageBox.critical") as critical:
            self.assertFalse(Window.save(self.window))
        critical.assert_called_once()
        self.defaultapps.commit.assert_not_called()
        self.assertTrue(self.window._dirty)

    def test_confirmed_save_writes_config_and_desktop_settings(self):
        self.window.confirm_save_diff.return_value = True
        with (
            patch("umbriel_config_gui.window.create_backup_snapshot"),
            patch("umbriel_config_gui.window.config_gui_data_dir", return_value=self.tempdir.name),
        ):
            self.assertTrue(Window.save(self.window))
        self.userdirs.commit.assert_called_once()
        self.defaultapps.commit.assert_called_once()
        with open(self.config_path, encoding="utf-8") as config:
            self.assertEqual(config.read(), "[general]\nmod_key = 'Alt'\n")
        self.assertFalse(self.window._dirty)

    def test_desktop_only_change_does_not_require_config_diff(self):
        self.window.doc = tomlkit.parse("[general]\nmod_key = 'Super'\n")
        self.userdirs.changed = True
        self.assertTrue(Window.save(self.window))
        self.window.confirm_save_diff.assert_not_called()
        self.userdirs.commit.assert_called_once()
        self.defaultapps.commit.assert_called_once()
        self.window.status.setText.assert_called_with("Saved user folders.")

    def test_config_error_reports_desktop_settings_were_saved(self):
        self.window.confirm_save_diff.return_value = True
        self.userdirs.changed = True
        with (
            patch("umbriel_config_gui.window.create_backup_snapshot", side_effect=OSError("disk full")),
            patch("umbriel_config_gui.window.QMessageBox.critical") as critical,
        ):
            self.assertFalse(Window.save(self.window))
        self.assertIn("Desktop settings were already saved", critical.call_args.args[2])
        self.assertTrue(self.window._dirty)


class SaveButtonStateTests(unittest.TestCase):
    """Save is only enabled while there are edits, so browsing must never mark the window dirty."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_browsing_keeps_save_disabled_and_an_edit_enables_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.toml")
            with open(path, "w", encoding="utf-8") as config:
                config.write(
                    "[general]\n[[window_rule]]\nmatch.app_id = \"a\"\nopen_floating = true\n"
                    "[[window_rule]]\nmatch.title = \"b\"\n"
                    "default_floating_size_px = {width = 10, height = 20}\n"
                )
            with (
                patch.object(state, "PATH", path),
                patch.object(state, "ACTIVE_SCHEMA_OPTIONS", {}),
                patch.object(common, "GUI_DATA_DIR", os.path.join(directory, "data")),
                patch.object(settings_layout, "_GROUP_EXPANSION_PATH", os.path.join(directory, "state.json")),
                patch.object(settings_layout, "_group_expansion_states", {}),
                patch.object(desktop, "USER_DIRS", os.path.join(directory, "user-dirs.dirs")),
                patch.object(desktop, "MIMEAPPS_PATH", os.path.join(directory, "mimeapps.list")),
                patch.object(desktop, "installed_desktop_apps", return_value=[]),
                patch("umbriel_config_gui.window.load_umbriel_schema", side_effect=FileNotFoundError("test")),
            ):
                window = Window(path)
                self.addCleanup(window.deleteLater)
                window.show()
                self.addCleanup(setattr, window, "_dirty", False)
                self.app.processEvents()
                self.assertEqual(
                    [action.text() for action in window.save_options_btn.menu().actions()],
                    [window.rebuild_box.text(), window.diff_box.text(), window.validate_box.text()],
                )
                for name, row in window.side_tabs.page_rows.items():
                    with self.subTest(page=name):
                        window.side_tabs.nav.setCurrentRow(row)
                        self.app.processEvents()
                        self.app.processEvents()
                        self.assertFalse(window._dirty)
                rules = window.side_tabs.page_widgets["Window rules"]
                for row in (1, 0, 1):
                    rules.list.setCurrentRow(row)
                    self.app.processEvents()
                self.assertFalse(window._dirty)
                self.assertFalse(window.save_btn.isEnabled())
                self.assertFalse(window.isWindowModified())

                size = next(field for field in rules.findChildren(FieldWidget)
                            if field.f.path == ("default_floating_size_px",))
                size.table_editors["height"].setValue(30)
                self.assertTrue(window.save_btn.isEnabled())
                self.assertTrue(window.isWindowModified())


if __name__ == "__main__":
    unittest.main()
