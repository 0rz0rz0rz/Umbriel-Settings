import unittest

from support import DesktopTestCase


class UserFoldersPluginTests(DesktopTestCase):
    FILE, PART = "user-dirs.dirs", "userdirs"

    def test_save_preserves_other_entries_and_makes_backup(self):
        self.path.parent.mkdir()
        original = '# User folders\nXDG_DOCUMENTS_DIR="$HOME/Documents"\nXDG_CUSTOM_DIR="/old"\n'
        self.path.write_text(original)
        loaded = self.read()
        self.assertEqual(loaded["values"]["DOCUMENTS"], "$HOME/Documents")
        saved = self.save(loaded["revision"], {
            "DOCUMENTS": "$HOME/Work",
            "MUSIC": "/data/My Music",
        })
        self.assertEqual(saved["revision"], self.read()["revision"])
        self.assertEqual(
            self.path.read_text(),
            '# User folders\nXDG_DOCUMENTS_DIR="$HOME/Work"\nXDG_CUSTOM_DIR="/old"\n'
            'XDG_MUSIC_DIR="/data/My Music"\n',
        )
        backups = sorted(self.backup.glob("user-dirs.dirs.*.bak"))
        self.assertEqual([path.read_text() for path in backups], [original])
        self.save(saved["revision"], {"MUSIC": ""})
        self.assertNotIn("XDG_MUSIC_DIR", self.path.read_text())

    def test_missing_file_and_external_change_detection(self):
        loaded = self.read()
        self.assertEqual(loaded["revision"], "missing")
        self.save(loaded["revision"], {"DOWNLOAD": "$HOME/Downloads"})
        self.assertEqual(self.path.read_text(), 'XDG_DOWNLOAD_DIR="$HOME/Downloads"\n')
        self.assertFalse(self.backup.exists())
        loaded = self.read()
        self.path.write_text("# external edit\n")
        error = self.save(loaded["revision"], {"DOWNLOAD": "/other"}, success=False)
        self.assertIn("changed externally", error)
        self.assertEqual(self.path.read_text(), "# external edit\n")

    def test_rejects_unsafe_values_without_writing(self):
        loaded = self.read()
        for value in ("relative", '/tmp/$(touch bad)', '/tmp/"bad', "/tmp/`bad`", "/tmp/bad\n"):
            with self.subTest(value=value):
                self.save(loaded["revision"], {"MUSIC": value}, success=False)
                self.assertFalse(self.path.exists())

    def test_refuses_to_replace_symlink(self):
        self.path.parent.mkdir()
        target = self.root / "linked-dirs"
        target.write_text('XDG_MUSIC_DIR="/old"\n')
        self.path.symlink_to(target)
        loaded = self.read()
        error = self.save(loaded["revision"], {"MUSIC": "/new"}, success=False)
        self.assertIn("symlink", error)
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(target.read_text(), 'XDG_MUSIC_DIR="/old"\n')


if __name__ == "__main__":
    unittest.main()
