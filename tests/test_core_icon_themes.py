"""Icon themes (umbriel_core/icon_themes.py) and the GTK/Qt/KDE theme settings (umbriel_core/toolkit_settings.py),
in a temp home: discovery, preview lookup, deleting a theme, and the line-preserving file edits."""

import os
import stat
import sys
import unittest
from unittest.mock import patch

from test_core_files import TempDirTestCase
from umbriel_core import icon_themes, toolkit_settings

INDEX = """[Icon Theme]
Name={label}
Inherits={inherits}
Directories=16x16/places,48x48/places,scalable/places
{extra}
[16x16/places]
Size=16
Type=Fixed

[48x48/places]
Size=48
Type=Fixed

[scalable/places]
Size=48
MinSize=8
MaxSize=512
Type=Scalable
"""


class IconThemeTestCase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.root, "home")
        self.system = os.path.join(self.root, "system")
        env = {"HOME": self.home, "XDG_DATA_HOME": os.path.join(self.home, ".local", "share"),
               "XDG_CONFIG_HOME": os.path.join(self.home, ".config"), "XDG_DATA_DIRS": self.system,
               "GSETTINGS_BACKEND": "memory", "PATH": os.path.join(self.root, "bin")}  # no real gsettings
        patcher = patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def theme(self, where, name, icons=(), label=None, inherits="hicolor", extra=""):
        """An icon theme in `where` ("home": ~/.local/share/icons, "icons": ~/.icons, "system"); `icons` are
        paths inside it (`48x48/places/folder.png`)."""
        base = {"home": os.path.join(self.home, ".local", "share", "icons"), "icons": os.path.join(self.home, ".icons"),
                "system": os.path.join(self.system, "icons")}[where]
        folder = os.path.join(base, name)
        self.write(folder, "index.theme", text=INDEX.format(label=label or name, inherits=inherits, extra=extra))
        for icon in icons:
            self.write(folder, icon, text="x")
        return folder


class DiscoveryTests(IconThemeTestCase):
    def test_themes_icons_and_parents_are_found_and_hicolor_hidden_and_cursor_themes_left_out(self):
        self.theme("system", "hicolor", ["48x48/places/folder.png"])
        parent = self.theme("system", "Parent", ["16x16/places/folder.png", "scalable/places/user-home.svg",
                                                 "48x48/places/user-home.png", "48x48/places/text-x-generic.png"])
        child = self.theme("home", "Child", ["scalable/places/folder.svg"], label="Nice Child", inherits="Parent")
        self.theme("home", "Secret", ["48x48/places/folder.png"], extra="Hidden=true")
        self.write(self.home, ".icons", "Pointer", "index.theme", text="[Icon Theme]\nInherits=Adwaita\n")
        os.makedirs(os.path.join(self.home, ".icons", "Pointer", "cursors"))
        result = icon_themes.previews()
        rows = {row["name"]: row for row in result["themes"]}
        self.assertTrue(result["complete"])
        self.assertEqual(list(rows), ["Child", "Parent"], "no hicolor, Hidden or cursor-only themes")
        self.assertEqual(rows["Child"]["label"], "Nice Child")
        icons = rows["Child"]["icons"]
        self.assertEqual(icons[0], os.path.join(child, "scalable/places/folder.svg"), "its own icon first")
        self.assertEqual(icons[1], os.path.join(parent, "48x48/places/user-home.png"),
                         "from the parent, and a PNG over an SVG at the same fit")
        self.assertIsNone(icons[3], "none anywhere")
        self.assertEqual(icon_themes.protected_themes("Child"), {"Child", "Parent", "hicolor"})

    def test_inherit_cycles_end_and_a_spent_budget_leaves_the_rest(self):
        self.theme("home", "A", inherits="B")
        self.theme("home", "B", inherits="A")
        rows = {row["name"]: row for row in icon_themes.previews()["themes"]}
        self.assertEqual(rows["A"]["icons"], [None] * len(icon_themes.ICONS))
        self.assertFalse(icon_themes.previews(budget=-1)["complete"])


class RemoveTests(IconThemeTestCase):
    def test_only_home_copies_go_and_protected_or_cursor_holding_ones_stay(self):
        mine = self.theme("home", "Mine")
        system = self.theme("system", "Shared")
        shared = self.theme("icons", "Shared")
        both = self.theme("home", "Both")
        os.makedirs(os.path.join(both, "cursors"))
        plan = icon_themes.removal("Shared")
        self.assertEqual((plan["folders"], plan["system"]), ([shared], True))
        icon_themes.remove("Mine")
        icon_themes.remove("Shared")
        self.assertFalse(os.path.exists(mine) or os.path.exists(shared))
        self.assertTrue(os.path.isdir(system), "the system copy needs its package manager")
        with self.assertRaisesRegex(ValueError, "cursor theme"):
            icon_themes.remove("Both")
        with self.assertRaisesRegex(ValueError, "in use"):
            icon_themes.remove("Both", {"Both"})
        self.assertTrue(os.path.isdir(both))
        self.assertEqual(icon_themes.removal("../system")["folders"], [], "unsafe names")
        link = os.path.join(self.home, ".icons", "Link")
        os.symlink(system, link)
        self.assertEqual(icon_themes.removal("Link")["folders"], [], "never through a symlink")


class ToolkitSettingsTests(IconThemeTestCase):
    def config(self, *parts):
        return os.path.join(self.home, ".config", *parts)

    def test_set_values_keeps_every_other_line(self):
        text = "# mine\n[Settings]\ngtk-theme-name=Foo\ngtk-icon-theme-name = old\n\n[Other]\nx=1\n"
        self.assertEqual(toolkit_settings.set_values(text, "Settings", {"gtk-icon-theme-name": "new", "size": 24}),
                         "# mine\n[Settings]\ngtk-theme-name=Foo\ngtk-icon-theme-name=new\nsize=24\n\n[Other]\nx=1\n")
        self.assertEqual(toolkit_settings.set_values("a=1", "Icons", {"Theme": "x"}), "a=1\n\n[Icons]\nTheme=x\n")
        self.assertEqual(toolkit_settings.set_values('gtk-icon-theme-name="a"\n', None,
                                                     {"gtk-icon-theme-name": "b", "gtk-cursor-theme-size": 24},
                                                     quote=True),
                         'gtk-icon-theme-name="b"\ngtk-cursor-theme-size=24\n')
        self.assertEqual(toolkit_settings.get_value('gtk-icon-theme-name="b"\n', None, "gtk-icon-theme-name"), "b")

    def test_icon_theme_goes_into_the_files_that_exist_backed_up_and_a_symlink_is_refused(self):
        gtk3 = self.write(self.config("gtk-3.0", "settings.ini"), text="[Settings]\ngtk-icon-theme-name=old\n")
        qt6 = self.write(self.config("qt6ct", "qt6ct.conf"), text="[Appearance]\nstyle=Fusion\n")
        real = self.write(self.root, "dotfiles", "kdeglobals", text="[Icons]\nTheme=old\n")
        os.symlink(real, self.config("kdeglobals"))
        before = toolkit_settings.read()
        self.assertEqual((before["theme"], before["icon"]["gtk3"]), ("old", "old"))
        self.assertNotIn("gtk4", before["icon"], "only files that exist")
        backups = os.path.join(self.root, "backups")
        result = toolkit_settings.set_icon_theme("Nice", backups)
        self.assertEqual(result["written"], ["GTK 3", "qt6ct"])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("symlink", result["warnings"][0])
        with open(gtk3, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "[Settings]\ngtk-icon-theme-name=Nice\n")
        with open(qt6, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "[Appearance]\nstyle=Fusion\nicon_theme=Nice\n")
        with open(real, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "[Icons]\nTheme=old\n", "not through the symlink")
        snapshot = os.listdir(os.path.join(backups, "gtk3"))
        self.assertEqual(len(snapshot), 1)
        mode = os.stat(os.path.join(backups, "gtk3", snapshot[0])).st_mode
        self.assertEqual(stat.S_IMODE(mode), 0o600)
        self.assertNotEqual(toolkit_settings.read()["revision"], before["revision"])
        with self.assertRaisesRegex(ValueError, "isn't a theme name"):
            toolkit_settings.set_icon_theme('bad"name', backups)

    def test_without_gtk_files_gtk3_is_created_and_the_cursor_goes_everywhere_it_is_named(self):
        xcursor = self.write(self.home, ".icons", "default", "index.theme",
                             text="[Icon Theme]\nName=Default\nInherits=old_cursors\n")
        self.assertTrue(toolkit_settings.cursor_differs("Neat", 32))
        result = toolkit_settings.set_cursor_theme("Neat", 32, os.path.join(self.root, "backups"))
        self.assertEqual(result, {"written": ["GTK 3", "X11 default cursor"], "warnings": []})
        with open(self.config("gtk-3.0", "settings.ini"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "[Settings]\ngtk-cursor-theme-name=Neat\ngtk-cursor-theme-size=32\n")
        with open(xcursor, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "[Icon Theme]\nName=Default\nInherits=Neat\n")
        self.assertFalse(toolkit_settings.cursor_differs("Neat", 32))
        self.assertFalse(os.path.exists(self.config("gtk-4.0")), "only GTK 3 is created")

    def test_gsettings_is_written_when_it_exists(self):
        log = os.path.join(self.root, "gsettings.log")
        self.write(self.root, "bin", "gsettings", text=f"#!{sys.executable}\nimport sys\n"
                   f"open({log!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
                   "print(\"'Old'\" if sys.argv[1] == 'get' else '')\n")
        os.chmod(os.path.join(self.root, "bin", "gsettings"), 0o755)
        self.assertEqual(toolkit_settings.read()["theme"], "Old")
        result = toolkit_settings.set_icon_theme("Nice", os.path.join(self.root, "backups"))
        self.assertEqual(result["written"][0], "GNOME settings")
        with open(log, encoding="utf-8") as handle:
            self.assertIn("set org.gnome.desktop.interface icon-theme Nice", handle.read())


if __name__ == "__main__":
    unittest.main()
