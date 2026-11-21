import unittest

from support import DesktopTestCase


class DefaultAppsPluginTests(DesktopTestCase):
    FILE, PART = "mimeapps.list", "apps"

    def setUp(self):
        super().setUp()
        self.env["XDG_DATA_DIRS"] = str(self.root / "system")

    def test_role_and_mime_changes_preserve_fallbacks_and_unrelated_sections(self):
        self.path.parent.mkdir()
        original = (
            "# comment\n[Default Applications]\n"
            "text/html=old.desktop;fallback.desktop;\napplication/json=json.desktop;\n"
            "[Added Associations]\ntext/html=other.desktop;\n"
        )
        self.path.write_text(original)
        loaded = self.read()
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
        self.assertEqual(saved, {"revision": self.read()["revision"]}, "a save only returns the new revision")

    def test_file_types_list_their_extensions(self):
        self.path.parent.mkdir()
        self.path.write_text("[Default Applications]\napplication/json=viewer.desktop;\n"
                             "x-scheme-handler/x=a.desktop;\n")
        extensions = self.read()["extensions"]
        self.assertIn(".json", extensions["application/json"].split())
        self.assertEqual(extensions["x-scheme-handler/x"], "")

    def test_external_changes_and_invalid_updates_are_rejected(self):
        loaded = self.read()
        self.path.parent.mkdir()
        self.path.write_text("# external\n")
        changes = [{"kind": "role", "key": "Web browser", "value": "test.desktop"}]
        self.assertIn("changed externally", self.save(loaded["revision"], changes, success=False))
        loaded = self.read()
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
        loaded = self.read()
        self.assertEqual(loaded["apps"], [{"id": "example.desktop", "name": "Example"}])
        self.assertEqual(self.ok("extension", {"extension": ".pdf"})["mime"], "application/pdf")
        self.fails("extension", {"extension": "bad/extension"})

    def test_app_command_is_the_exec_line_of_the_installed_app(self):
        appdir = self.root / "data" / "applications"
        (appdir / "kde").mkdir(parents=True)
        (appdir / "term.desktop").write_text("[Desktop Entry]\nName=Term\nExec=term --login %F\n")
        (appdir / "kde" / "sub.desktop").write_text("[Desktop Entry]\nName=Sub\nExec=sub\n")
        (appdir / "noexec.desktop").write_text("[Desktop Entry]\nName=None\n")
        self.assertEqual(self.ok("app-command", {"id": "term.desktop"})["command"], "term --login")
        self.assertEqual(self.ok("app-command", {"id": "kde-sub.desktop"})["command"], "sub")
        for app_id in ("noexec.desktop", "missing.desktop", "../term.desktop", "term"):
            self.assertEqual(self.fails("app-command", {"id": app_id})["code"], "no_command", app_id)

    def test_only_the_desktop_entry_group_counts_and_broken_files_are_skipped(self):
        appdir = self.root / "data" / "applications"
        (appdir / "kde").mkdir(parents=True)
        system = self.root / "system" / "applications"
        system.mkdir(parents=True)
        files = {
            appdir / "good.desktop": "# c\n[Desktop Entry]\nName=Good\nExec=good %U\n"
                                     "[Desktop Action new]\nName=New window\nNoDisplay=true\n",
            appdir / "kde" / "sub.desktop": "[Desktop Entry]\nName = Spaced\n",
            appdir / "nodisplay.desktop": "[Desktop Entry]\nName=Gone\nNoDisplay=True\n",
            appdir / "link.desktop": "[Desktop Entry]\nType=Link\nName=Link\n",
            appdir / "tryexec.desktop": "[Desktop Entry]\nName=Missing\nTryExec=no-such-program-xyz\n",
            appdir / "noname.desktop": "[Desktop Entry]\nExec=x\n",
            appdir / "garbage.desktop": "[Desktop Entry]\nName=Broken\nthis line has no equals sign\n",
            appdir / "other.desktop": "[Other]\nName=Other\n",
            system / "good.desktop": "[Desktop Entry]\nName=System copy\n",
            system / "system.desktop": "[Desktop Entry]\nName=System\n",
        }
        for path, text in files.items():
            path.write_text(text)
        (appdir / "latin1.desktop").write_bytes(b"[Desktop Entry]\nName=Caf\xe9\n")
        self.env.update(LC_ALL="", LC_MESSAGES="", LANG="C", XDG_CURRENT_DESKTOP="")
        self.assertEqual(self.read()["apps"], [
            {"id": "good.desktop", "name": "Good"},
            {"id": "noname.desktop", "name": "noname"},
            {"id": "kde-sub.desktop", "name": "Spaced"},
            {"id": "system.desktop", "name": "System"},
        ])

    def test_hidden_default_apps_still_get_their_names(self):
        appdir = self.root / "data" / "applications"
        appdir.mkdir(parents=True)
        (appdir / "userapp-Mail-ABC.desktop").write_text("[Desktop Entry]\nName=Mail\nNoDisplay=true\n")
        self.path.parent.mkdir(parents=True)
        self.path.write_text("[Default Applications]\nx-scheme-handler/mailto=userapp-Mail-ABC.desktop\n"
                             "text/x-example=gone.desktop\n")
        apps = self.read()
        self.assertNotIn("userapp-Mail-ABC.desktop", [app["id"] for app in apps["apps"]])
        self.assertEqual(apps["names"], {"userapp-Mail-ABC.desktop": "Mail"})

    def test_app_names_follow_the_locale_and_desktop_filters_apply(self):
        appdir = self.root / "data" / "applications"
        appdir.mkdir(parents=True)
        (appdir / "files.desktop").write_text("[Desktop Entry]\nName=Files\nName[de]=Dateien\n")
        (appdir / "kde.desktop").write_text("[Desktop Entry]\nName=KDE only\nOnlyShowIn=KDE;\n")
        (appdir / "notgnome.desktop").write_text("[Desktop Entry]\nName=Not GNOME\nNotShowIn=GNOME;\n")
        self.env.update(LC_ALL="", LC_MESSAGES="", LANG="de_AT.UTF-8", XDG_CURRENT_DESKTOP="Umbriel:GNOME")
        self.assertEqual(self.read()["apps"], [{"id": "files.desktop", "name": "Dateien"}])
        self.env.update(LANG="C.UTF-8", XDG_CURRENT_DESKTOP="KDE")
        self.assertEqual([app["name"] for app in self.read()["apps"]], ["Files", "KDE only", "Not GNOME"])

    def test_symlink_is_not_replaced(self):
        self.path.parent.mkdir()
        target = self.root / "target"
        target.write_text("[Default Applications]\n")
        self.path.symlink_to(target)
        loaded = self.read()
        changes = [{"kind": "role", "key": "File manager", "value": "files.desktop"}]
        self.assertIn("symlink", self.save(loaded["revision"], changes, success=False))
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(target.read_text(), "[Default Applications]\n")


if __name__ == "__main__":
    unittest.main()
