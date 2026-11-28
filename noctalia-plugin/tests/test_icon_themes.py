"""The Icon theme page's helper side: `icon-themes`, the `icons` part of `desktop` and `desktop-save` (the theme
written into GNOME settings and the GTK/Qt/KDE files, queued themes deleted), in a temp home with a fake
gsettings."""

import os
import sys
import time
import unittest

from support import HelperTestCase

INDEX = ("[Icon Theme]\nName={name}\nInherits={inherits}\nDirectories=48x48/places\n\n"
         "[48x48/places]\nSize=48\nType=Fixed\n")
GSETTINGS = """import os, sys
state = os.path.join(os.path.dirname(sys.argv[0]), "state")
if sys.argv[1] == "get":
    print("'" + (open(state).read() if os.path.exists(state) else "Gnomish") + "'")
elif sys.argv[3] == "icon-theme":
    open(state, "w").write(sys.argv[4])
"""


class IconThemeHelperTests(HelperTestCase):
    def setUp(self):
        super().setUp()
        self.env["HOME"] = str(self.root)  # $XDG_DATA_HOME/icons lies in the home folder: deletable
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        (bin_dir / "gsettings").write_text(f"#!{sys.executable}\n" + GSETTINGS)
        (bin_dir / "gsettings").chmod(0o755)
        self.env["PATH"] = str(bin_dir)
        self.icons = self.root / "data" / "icons"  # $XDG_DATA_HOME/icons
        self.gtk3 = self.root / "xdg-config" / "gtk-3.0" / "settings.ini"
        self.gtk3.parent.mkdir(parents=True)
        self.gtk3.write_text("[Settings]\ngtk-theme-name=Adw\ngtk-icon-theme-name=Gnomish\n")

    def theme(self, name, inherits="hicolor"):
        folder = self.icons / name
        (folder / "48x48" / "places").mkdir(parents=True)
        (folder / "index.theme").write_text(INDEX.format(name=name, inherits=inherits))
        (folder / "48x48" / "places" / "folder.png").write_bytes(b"png")
        return folder

    def test_listed_with_icons_and_the_current_theme(self):
        self.theme("Base")
        self.theme("Fancy", inherits="Base")
        result = self.ok("icon-themes", {})
        rows = {row["name"]: row for row in result["themes"]}
        self.assertEqual(sorted(rows), ["Base", "Fancy"])
        self.assertTrue(rows["Fancy"]["icons"][0].endswith("Fancy/48x48/places/folder.png"))
        self.assertEqual(rows["Fancy"]["inherits"], ["Base"])
        self.assertTrue(rows["Fancy"]["removable"] and not rows["Fancy"]["system"])
        self.assertEqual(result["theme"], "Gnomish")
        self.assertEqual(result["targets"], ["GNOME settings", "GTK 3"])
        desktop = self.ok("desktop", {})
        self.assertEqual(desktop["icons"]["theme"], "Gnomish")

    def test_save_writes_the_theme_and_deletes_queued_themes_but_not_one_it_builds_on(self):
        self.theme("Base")
        self.theme("Fancy", inherits="Base")
        old = self.theme("Old")
        revision = self.ok("desktop", {})["icons"]["revision"]
        result = self.ok("desktop-save", {"icons": {"revision": revision, "theme": "Fancy",
                                                    "remove": ["Old", "Base"]}})
        self.assertEqual(len(result["icons"]["warnings"]), 1)
        self.assertIn("Base could not be removed", result["icons"]["warnings"][0])
        self.assertFalse(old.exists())
        self.assertTrue((self.icons / "Base").is_dir(), "Fancy inherits it")
        self.assertEqual(self.gtk3.read_text(), "[Settings]\ngtk-theme-name=Adw\ngtk-icon-theme-name=Fancy\n")
        self.assertEqual(self.ok("desktop", {})["icons"], {"theme": "Fancy", "revision": result["icons"]["revision"],
                                                           "targets": ["GNOME settings", "GTK 3"]})
        backups = os.listdir(self.root / "data" / "umbriel-settings" / "backups" / "toolkit" / "gtk3")
        self.assertEqual(len(backups), 1)

    def test_a_change_made_elsewhere_meanwhile_is_not_overwritten(self):
        revision = self.ok("desktop", {})["icons"]["revision"]
        self.gtk3.write_text("[Settings]\ngtk-icon-theme-name=Elsewhere\n")
        error = self.fails("desktop-save", {"icons": {"revision": revision, "theme": "Fancy"}})["error"]
        self.assertIn("changed by another program", error)
        self.assertIn("Elsewhere", self.gtk3.read_text())


class IconStoreHelperTests(HelperTestCase):
    def test_the_store_is_never_asked_offline_and_pages_open_by_number(self):
        self.assertEqual(self.fails("icon-store", {"offline": True})["code"], "offline")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        log = self.root / "opened"
        script = f"#!{sys.executable}\nimport sys\nopen({str(log)!r}, 'a').write(sys.argv[1])\n"
        (bin_dir / "xdg-open").write_text(script)
        (bin_dir / "xdg-open").chmod(0o755)
        env = {**self.env, "PATH": str(bin_dir)}
        self.assertEqual(self.ok("open-store-page", {"id": 1166289}, env), {"url": "https://www.pling.com/p/1166289/"})
        for _ in range(50):  # detached: give it a moment
            if log.exists():
                break
            time.sleep(0.05)
        self.assertEqual(log.read_text(), "https://www.pling.com/p/1166289/")
        self.assertIn("isn't a store item", self.fails("open-store-page", {"id": "https://evil.example"}, env)["error"])


if __name__ == "__main__":
    unittest.main()
