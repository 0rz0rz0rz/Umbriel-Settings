import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / "umbriel-settings" / "umbriel_settings.py"


class DefaultAppsPluginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "config" / "mimeapps.list"
        self.backup = self.root / "data" / "umbriel-settings" / "backups"
        self.env = {
            **os.environ,
            "XDG_CONFIG_HOME": str(self.path.parent),
            "XDG_DATA_HOME": str(self.root / "data"),
            "XDG_DATA_DIRS": str(self.root / "system"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def call(self, command, request, success=True):
        request_file = self.root / "request.json"
        request_file.write_text(json.dumps(request))
        result = subprocess.run(
            [sys.executable, "-B", str(HELPER), command, "--request", str(request_file)],
            env=self.env, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        reply = json.loads(result.stdout)
        self.assertEqual(reply["ok"], success, reply)
        return reply["result"] if success else reply["error"]

    def helper(self, *args, success=True):
        if args[0] == "extension":
            return self.call("extension", {"extension": args[1]}, success)
        return self.call("desktop", {}, success)["apps"]

    def save(self, revision, changes, success=True):
        result = self.call("desktop-save", {"apps": {"revision": revision, "changes": changes}}, success)
        return result["apps"] if success else result

    def test_role_and_mime_changes_preserve_fallbacks_and_unrelated_sections(self):
        self.path.parent.mkdir()
        original = (
            "# comment\n[Default Applications]\n"
            "text/html=old.desktop;fallback.desktop;\napplication/json=json.desktop;\n"
            "[Added Associations]\ntext/html=other.desktop;\n"
        )
        self.path.write_text(original)
        loaded = self.helper("read")
        self.assertEqual(loaded["roles"]["Web browser"], "<multiple>")
        self.assertEqual(loaded["mimes"]["application/json"], "json.desktop")
        saved = self.save(loaded["revision"], [
            {"kind": "role", "key": "Web browser", "value": "new.desktop"},
            {"kind": "mime", "key": "application/json", "value": ""},
            {"kind": "mime", "key": "application/example", "value": "example.desktop"},
        ])
        text = self.path.read_text()
        self.assertIn("text/html=new.desktop;old.desktop;fallback.desktop;", text)
        self.assertIn("application/example=example.desktop;", text)
        self.assertNotIn("application/json=", text)
        self.assertIn("[Added Associations]\ntext/html=other.desktop;", text)
        backups = sorted(self.backup.glob("mimeapps.list.*.bak"))
        self.assertEqual([path.read_text() for path in backups], [original])
        self.assertEqual(saved["roles"]["Web browser"], "new.desktop")

    def test_file_types_list_their_extensions(self):
        self.path.parent.mkdir()
        self.path.write_text("[Default Applications]\napplication/json=viewer.desktop;\nx-scheme-handler/x=a.desktop;\n")
        extensions = self.helper("read")["extensions"]
        self.assertIn(".json", extensions["application/json"].split())
        self.assertEqual(extensions["x-scheme-handler/x"], "")

    def test_external_changes_and_invalid_updates_are_rejected(self):
        loaded = self.helper("read")
        self.path.parent.mkdir()
        self.path.write_text("# external\n")
        changes = [{"kind": "role", "key": "Web browser", "value": "test.desktop"}]
        self.assertIn("changed externally", self.save(loaded["revision"], changes, success=False))
        loaded = self.helper("read")
        for change in (
            {"kind": "mime", "key": "text/html", "value": "test.desktop"},
            {"kind": "mime", "key": "bad", "value": "test.desktop"},
            {"kind": "mime", "key": "application/json", "value": "bad;id"},
        ):
            self.save(loaded["revision"], [change], success=False)
        self.assertEqual(self.path.read_text(), "# external\n")

    def test_discovers_apps_and_resolves_extensions(self):
        appdir = self.root / "data" / "applications"
        appdir.mkdir(parents=True)
        (appdir / "example.desktop").write_text("[Desktop Entry]\nType=Application\nName=Example\n")
        (appdir / "hidden.desktop").write_text("[Desktop Entry]\nName=Hidden\nHidden=true\n")
        loaded = self.helper("read")
        self.assertEqual(loaded["apps"], [{"id": "example.desktop", "name": "Example"}])
        self.assertEqual(self.helper("extension", ".pdf")["mime"], "application/pdf")
        self.helper("extension", "bad/extension", success=False)

    def test_app_names_follow_the_locale_and_desktop_filters_apply(self):
        appdir = self.root / "data" / "applications"
        appdir.mkdir(parents=True)
        (appdir / "files.desktop").write_text("[Desktop Entry]\nName=Files\nName[de]=Dateien\n")
        (appdir / "kde.desktop").write_text("[Desktop Entry]\nName=KDE only\nOnlyShowIn=KDE;\n")
        (appdir / "notgnome.desktop").write_text("[Desktop Entry]\nName=Not GNOME\nNotShowIn=GNOME;\n")
        self.env.update(LC_ALL="", LC_MESSAGES="", LANG="de_AT.UTF-8", XDG_CURRENT_DESKTOP="Umbriel:GNOME")
        self.assertEqual(self.helper("read")["apps"], [{"id": "files.desktop", "name": "Dateien"}])
        self.env.update(LANG="C.UTF-8", XDG_CURRENT_DESKTOP="KDE")
        self.assertEqual([app["name"] for app in self.helper("read")["apps"]], ["Files", "KDE only", "Not GNOME"])

    def test_symlink_is_not_replaced(self):
        self.path.parent.mkdir()
        target = self.root / "target"
        target.write_text("[Default Applications]\n")
        self.path.symlink_to(target)
        loaded = self.helper("read")
        changes = [{"kind": "role", "key": "File manager", "value": "files.desktop"}]
        self.assertIn("symlink", self.save(loaded["revision"], changes, success=False))
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(target.read_text(), "[Default Applications]\n")


if __name__ == "__main__":
    unittest.main()
