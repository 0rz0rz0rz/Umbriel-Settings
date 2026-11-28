"""Downloaded cursor themes (umbriel_core/cursor_download.py): safe extraction, the cache, install on save."""

import hashlib
import io
import json
import os
import stat
import tarfile
import unittest
import zipfile
from unittest.mock import patch

from test_core_files import TempDirTestCase, xcursor
from umbriel_core import cursor_download, cursor_preview, toolkit_settings
from umbriel_core.session import ConfigSession

CURSOR = xcursor((24, 4, 4, 0xFFFFFFFF))


def tar_archive(entries, mode="w:gz"):
    """entries: (name, bytes) files, (name, "->target") symlinks, (name, "hard->target"), (name, "fifo")."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode=mode) as bundle:
        for name, content in entries:
            info = tarfile.TarInfo(name)
            if isinstance(content, bytes):
                info.size = len(content)
                bundle.addfile(info, io.BytesIO(content))
                continue
            if content.startswith("->"):
                info.type, info.linkname = tarfile.SYMTYPE, content[2:]
            elif content.startswith("hard->"):
                info.type, info.linkname = tarfile.LNKTYPE, content[6:]
            elif content == "fifo":
                info.type = tarfile.FIFOTYPE
            elif content == "dev":
                info.type, info.devmajor, info.devminor = tarfile.CHRTYPE, 1, 3
            bundle.addfile(info)
    return buffer.getvalue()


def zip_archive(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, content in entries:
            info = zipfile.ZipInfo(name)
            if isinstance(content, str) and content.startswith("->"):
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                bundle.writestr(info, content[2:])
            else:
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                bundle.writestr(info, content)
    return buffer.getvalue()


GOOD = tar_archive([
    ("Neat/index.theme", b"[Icon Theme]\nName=Neat\n"),
    ("Neat/cursor.theme", b"[Icon Theme]\nInherits=Neat\n"),
    ("Neat/cursors/left_ptr", CURSOR),
    ("Neat/cursors/not-xcursor", b"#!/bin/sh\necho hi\n"),  # in cursors/, but no Xcursor image
    ("Neat/cursors/default", "->left_ptr"),
    ("Neat/cursors/arrow", "->default"),  # an alias of an alias
    ("Neat/cursors/gone", "->missing"),  # dangling
    ("Neat/cursors/escape", "->../../../../etc/passwd"),
    ("Neat/cursors_scalable/left_ptr.svg", b"<svg/>"),
    ("Neat/install.sh", b"#!/bin/sh\nrm -rf ~\n"),
    ("../evil/cursors/x", CURSOR),
    ("/abs/cursors/x", CURSOR),
    ("Neat/cursors/hard", "hard->Neat/cursors/left_ptr"),
    ("Neat/cursors/fifo", "fifo"),
    ("Neat/cursors/dev", "dev"),
])


class CursorDownloadTestCase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.root, "home")
        self.data = os.path.join(self.root, "data", "umbriel-settings")
        env = {"HOME": self.home, "XDG_DATA_HOME": os.path.join(self.home, ".local", "share"),
               "XDG_CONFIG_HOME": os.path.join(self.home, ".config"), "GSETTINGS_BACKEND": "memory",
               "XDG_DATA_DIRS": os.path.join(self.root, "system")}
        patcher = patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("XCURSOR_PATH", None)

    def cache(self, data=GOOD, name="neat.tar.gz", key="pling-1-1"):
        """Put an archive into the cache as a finished download; return its themes."""
        return cursor_download.store_archive(cursor_download.cache_dir(self.data), key, io.BytesIO(data), name,
                                             {"store": "test", "id": 1}, hashlib.sha256(data).hexdigest())

    def icons(self, *parts):
        return os.path.join(self.home, ".local", "share", "icons", *parts)


class ExtractTests(CursorDownloadTestCase):
    def test_only_cursor_data_is_kept_and_nothing_leaves_the_target(self):
        self.assertEqual(self.cache(), ["Neat"])
        folder = os.path.join(self.data, "cursor-downloads", "pling-1-1", "Neat")
        self.assertEqual(sorted(os.listdir(folder)), ["cursor.theme", "cursors", "index.theme"])
        self.assertEqual(sorted(os.listdir(os.path.join(folder, "cursors"))), ["arrow", "default", "left_ptr"],
                         "only Xcursor images and aliases that resolve")
        self.assertEqual(os.readlink(os.path.join(folder, "cursors", "arrow")), "default")
        self.assertFalse(os.path.exists(os.path.join(self.root, "evil")))
        self.assertEqual(os.stat(os.path.join(folder, "cursors", "left_ptr")).st_mode & 0o777, 0o600)
        self.assertEqual(cursor_download.cached_themes(self.data), {"Neat": ("pling-1-1", folder)})

    def test_a_copy_inside_a_theme_folder_is_no_second_theme(self):
        data = tar_archive([("Layan-cursors/index.theme", b"[Icon Theme]\n"),
                            ("Layan-cursors/cursors/left_ptr", CURSOR),
                            ("Layan-cursors/dist/index.theme", b"[Icon Theme]\n"),
                            ("Layan-cursors/dist/cursors/left_ptr", CURSOR),
                            ("pack/a/Twin/cursors/left_ptr", CURSOR),  # two folders of one name: the shallower
                            ("pack/Twin/cursors/default", CURSOR)])
        self.assertEqual(self.cache(data, "layan.tar.xz", "pling-5-1"), ["Layan-cursors", "Twin"])
        twin = os.path.join(self.data, "cursor-downloads", "pling-5-1", "Twin", "cursors")
        self.assertEqual(os.listdir(twin), ["default"], "never mixed")

    def test_zip_archives_keep_their_aliases(self):
        data = zip_archive([("z/Zed/cursors/left_ptr", CURSOR), ("z/Zed/cursors/default", "->left_ptr"),
                            ("z/Zed/index.theme", b"[Icon Theme]\n")])
        self.assertEqual(self.cache(data, "zed.zip", "pling-2-1"), ["Zed"])
        cursors = os.path.join(self.data, "cursor-downloads", "pling-2-1", "Zed", "cursors")
        self.assertEqual(os.readlink(os.path.join(cursors, "default")), "left_ptr")

    def test_windows_cursors_or_a_bomb_leave_nothing(self):
        windows = zip_archive([("Win/cursors/arrow.cur", b"\0\0\2\0"), ("Win/install.inf", b"[x]")])
        self.assertEqual(self.cache(windows, "win.zip", "pling-3-1"), [])
        bomb = tar_archive([(f"Big/cursors/c{i}", CURSOR + b"\0" * 4096) for i in range(10)])
        with patch.object(cursor_download, "MAX_TOTAL", 8192), \
                self.assertRaisesRegex(cursor_download.CursorError, "more than expected"):
            self.cache(bomb, "big.tar.gz", "pling-4-1")
        self.assertEqual(cursor_download.cached_themes(self.data), {})
        self.assertEqual(os.listdir(os.path.join(self.data, "cursor-downloads")), [], "no half-written theme")

    def test_downloads_from_an_older_extraction_are_redone(self):
        self.cache()
        complete = os.path.join(self.data, "cursor-downloads", "pling-1-1", cursor_download.COMPLETE)
        with open(complete, encoding="utf-8") as handle:
            record = json.load(handle)
        record.pop("version")
        with open(complete, "w", encoding="utf-8") as handle:
            json.dump(record, handle)
        self.assertEqual(cursor_download.cached_themes(self.data), {})

    def test_a_killed_extraction_is_redone(self):
        with patch.object(cursor_download.os, "replace", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.cache()
        self.assertEqual(cursor_download.cached_themes(self.data), {})
        self.assertEqual(self.cache(), ["Neat"])
        self.assertIn("Neat", cursor_download.cached_themes(self.data))


class InstallTests(CursorDownloadTestCase):
    def test_install_writes_the_marker_first_and_keeps_aliases(self):
        self.cache()
        order = []
        real = cursor_download.atomic_write
        with patch.object(cursor_download, "atomic_write",
                          side_effect=lambda path, *a, **k: (order.append(os.path.basename(path)),
                                                              real(path, *a, **k))):
            dest = cursor_download.install("Neat", self.data)
        self.assertEqual(dest, self.icons("Neat"))
        self.assertEqual(order[0], cursor_download.MARKER)
        self.assertEqual(os.readlink(self.icons("Neat", "cursors", "default")), "left_ptr")
        self.assertEqual(os.stat(self.icons("Neat", "cursors", "left_ptr")).st_mode & 0o777, 0o644)
        with open(self.icons("Neat", cursor_download.MARKER), encoding="utf-8") as handle:
            marker = json.load(handle)
        self.assertEqual(marker["source"], "pling-1-1")
        self.assertIn("cursors/left_ptr", marker["files"])
        self.assertTrue(cursor_download.installed_by_us("Neat"))
        rows = {row["name"]: row for row in cursor_preview.previews(self.data)["themes"]}
        self.assertTrue(rows["Neat"]["ours"] and not rows["Neat"]["downloaded"])
        cursor_download.install("Neat", self.data)  # again: a no-op over matching files

    def test_install_refuses_a_foreign_folder_a_symlink_or_no_home_folder_to_use(self):
        self.cache()
        os.makedirs(self.icons("Neat", "cursors"))
        with self.assertRaisesRegex(cursor_download.CursorError, "wasn't installed by Umbriel Settings"):
            cursor_download.install("Neat", self.data)
        os.rmdir(self.icons("Neat", "cursors"))
        os.rmdir(self.icons("Neat"))
        os.makedirs(os.path.join(self.root, "elsewhere"))
        os.symlink(os.path.join(self.root, "elsewhere"), self.icons("Neat"))
        with self.assertRaisesRegex(cursor_download.CursorError, "symlink"):
            cursor_download.install("Neat", self.data)
        os.unlink(self.icons("Neat"))
        with patch.dict(os.environ, {"XCURSOR_PATH": os.path.join(self.root, "system", "icons")}), \
                self.assertRaisesRegex(cursor_download.CursorError, "XCURSOR_PATH"):
            cursor_download.install("Neat", self.data)
        self.assertEqual(os.listdir(os.path.join(self.root, "elsewhere")), [])

    def test_a_downloaded_theme_is_listed_with_its_preview_before_it_is_installed(self):
        self.cache()
        rows = {row["name"]: row for row in cursor_preview.previews(self.data)["themes"]}
        self.assertTrue(rows["Neat"]["downloaded"])
        self.assertIsNotNone(rows["Neat"]["preview"])


class SaveTests(CursorDownloadTestCase):
    def session(self, text):
        path = os.path.join(self.root, "config.toml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return ConfigSession(path, self.data)

    def save(self, session, **extra):
        return session.save({"revision": session.read()["revision"],
                             "fields": {"input.cursor.theme": {"value": "Neat"}}}, validate=False,
                            backup=lambda path, config_dir: None, **extra)

    def test_the_save_that_picks_a_downloaded_theme_installs_it_before_the_config(self):
        self.cache()
        session = self.session("[input.cursor]\nsize = 24\n")
        preview = session.preview({"revision": session.read()["revision"],
                                   "fields": {"input.cursor.theme": {"value": "Neat"}}}, validate=False)
        self.assertIn("Install cursor theme: Neat (into ~/.local/share/icons)",
                      [item["label"] for item in preview["summary"]])
        seen = []
        report = self.save(session, before_write=lambda backup, sha: seen.append(
            os.path.isfile(self.icons("Neat", "cursors", "left_ptr"))))
        self.assertTrue(report["saved"])
        self.assertEqual(seen, [True], "installed before the config is written")

    def test_the_save_gives_gtk_and_qt_apps_the_cursor_theme_when_syncing(self):
        self.cache()
        gtk3 = os.path.join(self.home, ".config", "gtk-3.0", "settings.ini")
        session = self.session("[input.cursor]\nsize = 32\n")
        change = {"revision": session.read()["revision"], "fields": {"input.cursor.theme": {"value": "Neat"}}}
        with patch.object(toolkit_settings, "gsettings", return_value=None):
            labels = [item["label"] for item in session.preview(change, validate=False)["summary"]]
            self.assertFalse([label for label in labels if "other apps" in label], "off unless the helper asks")
            self.save(session)
            self.assertFalse(os.path.exists(gtk3))
            session.sync_toolkit = True
            labels = [item["label"] for item in session.preview(
                {"revision": session.read()["revision"], "fields": {"input.cursor.size": {"value": 32}}},
                validate=False)["summary"]]
            self.assertIn("Cursor theme for other apps: Neat, 32 px (GTK 3)", labels)
            report = session.save({"revision": session.read()["revision"],
                                   "fields": {"input.cursor.size": {"value": 40}}}, validate=False,
                                  backup=lambda path, config_dir: None)
            self.assertNotIn("warnings", report)
            with open(gtk3, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "[Settings]\ngtk-cursor-theme-name=Neat\ngtk-cursor-theme-size=40\n")
            unset = self.session("[input.cursor]\nsize = 24\n")
            unset.sync_toolkit = True
            labels = [item["label"] for item in unset.preview(
                {"revision": unset.read()["revision"], "fields": {"input.cursor.size": {"value": 30}}},
                validate=False)["summary"]]
            self.assertFalse([label for label in labels if "other apps" in label], "Umbriel default: theirs stays")

    def test_a_failed_install_writes_nothing(self):
        self.cache()
        os.makedirs(self.icons("Neat"))  # someone else's folder
        session = self.session("[input.cursor]\nsize = 24\n")
        with self.assertRaisesRegex(ValueError, "wasn't installed by Umbriel Settings"):
            self.save(session)
        with open(session.path, encoding="utf-8") as handle:
            self.assertNotIn("Neat", handle.read())


class RemoveTests(CursorDownloadTestCase):
    def installed(self):
        self.cache()
        return cursor_download.install("Neat", self.data)

    def test_remove_deletes_only_its_unchanged_files_and_the_download(self):
        dest = self.installed()
        self.assertEqual(cursor_download.remove("Neat", self.data), [])
        self.assertFalse(os.path.lexists(dest))
        self.assertEqual(cursor_download.cached_themes(self.data), {}, "the cached download goes too")

    def test_files_changed_or_added_by_hand_stay(self):
        dest = self.installed()
        with open(os.path.join(dest, "cursors", "left_ptr"), "ab") as handle:
            handle.write(b"edited")
        with open(os.path.join(dest, "cursors", "mine"), "wb") as handle:
            handle.write(CURSOR)
        self.assertEqual(cursor_download.remove("Neat", self.data), ["cursors/left_ptr"])
        self.assertEqual(sorted(os.listdir(os.path.join(dest, "cursors"))), ["left_ptr", "mine"])
        self.assertFalse(os.path.exists(os.path.join(dest, cursor_download.MARKER)))

    def theme(self, *parts, files=("cursors/left_ptr", "index.theme")):
        folder = os.path.join(self.home, *parts)
        for inner in files:
            os.makedirs(os.path.dirname(os.path.join(folder, inner)), exist_ok=True)
            with open(os.path.join(folder, inner), "wb") as handle:
                handle.write(CURSOR if inner.startswith("cursors/") else b"[Icon Theme]\nInherits=Adwaita\n")
        return folder

    def test_a_theme_it_didnt_install_goes_whole_unless_it_is_an_icon_theme_too(self):
        other = self.theme(".icons", "Other", files=("cursors/left_ptr", "index.theme", "README"))
        bundle = self.theme(".local", "share", "icons", "Bundle",
                            files=("cursors/left_ptr", "cursor.theme", "index.theme", "apps/16/a.png"))
        alias = self.theme(".icons", "Alias", files=("index.theme",))
        icons = self.theme(".icons", "Icons", files=("index.theme", "apps/16/a.png"))
        system = os.path.join(self.root, "system", "icons", "Other", "cursors")
        os.makedirs(system)
        plan = cursor_download.removal("Other", self.data)
        self.assertEqual((plan["folders"], plan["system"]), ([(other, "whole")], True))
        self.assertEqual(cursor_download.removal("Bundle", self.data)["folders"], [(bundle, "cursors")])
        self.assertEqual(cursor_download.removal("Icons", self.data)["folders"], [], "no cursor theme there")
        for theme in ("Other", "Bundle", "Alias"):
            self.assertEqual(cursor_download.remove(theme, self.data), [])
        self.assertFalse(os.path.lexists(other) or os.path.lexists(alias))
        self.assertEqual(sorted(os.listdir(bundle)), ["apps", "index.theme"], "the icons stay")
        self.assertTrue(os.path.isdir(system) and os.path.isdir(icons), "system copies and icon themes stay")
        self.assertFalse([name for name in os.listdir(os.path.join(self.home, ".icons"))
                          if name.startswith(cursor_download.REMOVING)], "nothing hidden left behind")

    def test_a_killed_removal_leaves_nothing_a_lookup_finds_and_is_swept(self):
        self.theme(".icons", "Other")
        with patch.object(cursor_download.shutil, "rmtree"):  # killed right after the rename
            cursor_download.remove("Other", self.data)
        names = os.listdir(os.path.join(self.home, ".icons"))
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].startswith(cursor_download.REMOVING))
        self.assertNotIn("Other", cursor_preview.installed_cursor_themes())
        cursor_download.prune_stale(self.data)
        self.assertEqual(os.listdir(os.path.join(self.home, ".icons")), [])

    def test_symlinks_unsafe_names_and_protected_themes_are_left_alone(self):
        target = self.theme("elsewhere", "Real")
        os.makedirs(os.path.join(self.home, ".icons"))
        os.symlink(target, os.path.join(self.home, ".icons", "Linked"))
        self.assertEqual(cursor_download.removal("Linked", self.data)["folders"], [])
        self.assertEqual(cursor_download.removal("../elsewhere/Real", self.data)["folders"], [])
        self.theme(".icons", "default", files=("index.theme",))  # inherits Adwaita
        self.assertEqual(cursor_download.protected_themes("Mine"), {"default", "Adwaita", "Mine"})
        with self.assertRaisesRegex(cursor_download.CursorError, "default cursor theme"):
            cursor_download.remove("default", self.data, cursor_download.protected_themes())
        self.assertTrue(os.path.isdir(target) and os.path.isdir(os.path.join(self.home, ".icons", "default")))

    def test_a_download_goes_alone_and_older_extractions_are_pruned(self):
        data = tar_archive([("A/cursors/left_ptr", CURSOR), ("B/cursors/left_ptr", CURSOR)])
        self.assertEqual(self.cache(data, "ab.tar.gz", "pling-3-1"), ["A", "B"])
        self.assertEqual(cursor_download.remove("A", self.data), [])
        self.assertEqual(sorted(cursor_download.cached_themes(self.data)), ["B"], "the archive's other theme stays")
        self.cache()
        complete = os.path.join(self.data, "cursor-downloads", "pling-1-1", cursor_download.COMPLETE)
        with open(complete, encoding="utf-8") as handle:
            record = json.load(handle)
        record.pop("version")
        with open(complete, "w", encoding="utf-8") as handle:
            json.dump(record, handle)
        rows = {row["name"]: row for row in cursor_preview.previews(self.data)["themes"]}
        self.assertNotIn("Neat", rows)
        self.assertEqual(sorted(os.listdir(cursor_download.cache_dir(self.data))), ["pling-3-1"], "pruned")
        self.assertTrue(rows["B"]["removable"] and not rows["B"]["system"] and not rows["B"]["protected"])


class RemoveOnSaveTests(SaveTests):
    def change(self, session, **fields):
        return {"revision": session.read()["revision"], "cursor_remove": ["Neat"],
                "fields": {fid: {"value": value} for fid, value in fields.items()}}

    def test_the_save_removes_it_after_review_lists_it(self):
        self.cache()
        cursor_download.install("Neat", self.data)
        session = self.session("[input.cursor]\nsize = 24\n")
        preview = session.preview(self.change(session), validate=False)
        self.assertIn("Remove cursor theme: Neat (from ~/.local/share/icons/Neat)",
                      [item["label"] for item in preview["summary"]])
        report = session.save(self.change(session), validate=False, backup=lambda path, config_dir: None)
        self.assertTrue(report["saved"])
        self.assertNotIn("warnings", report)
        self.assertFalse(os.path.lexists(self.icons("Neat")))

    def test_a_theme_already_gone_is_nothing_to_do(self):
        session = self.session("[input.cursor]\nsize = 24\n")
        preview = session.preview(self.change(session), validate=False)
        self.assertFalse([item for item in preview["summary"] if "Remove cursor theme" in item["label"]])
        report = session.save(self.change(session), validate=False, backup=lambda path, config_dir: None)
        self.assertTrue(report["saved"])
        self.assertNotIn("warnings", report)

    def test_the_picked_theme_or_umbriels_default_is_refused(self):
        self.cache()
        cursor_download.install("Neat", self.data)
        session = self.session('[input.cursor]\ntheme = "Neat"\n')
        with self.assertRaisesRegex(ValueError, "pick another before removing it"):
            session.preview(self.change(session), validate=False)
        session = self.session("[input.cursor]\nsize = 24\n")
        with self.assertRaisesRegex(ValueError, "pick another before removing it"):
            session.save(self.change(session, **{"input.cursor.theme": "Neat"}), validate=False,
                         backup=lambda path, config_dir: None)
        self.assertTrue(os.path.isdir(self.icons("Neat")), "nothing removed")
        os.makedirs(os.path.join(self.home, ".icons", "default"))
        with open(os.path.join(self.home, ".icons", "default", "index.theme"), "w", encoding="utf-8") as handle:
            handle.write("[Icon Theme]\nInherits=Neat\n")
        with self.assertRaisesRegex(ValueError, "Umbriel's default cursor theme"):
            session.preview(self.change(session), validate=False)

    def test_a_theme_it_didnt_install_or_a_download_is_deleted_by_the_save(self):
        os.makedirs(os.path.join(self.home, ".icons", "Neat", "cursors"))
        self.cache(tar_archive([("Spare/cursors/left_ptr", CURSOR)]), "spare.tar.gz", "pling-4-1")
        session = self.session("[input.cursor]\nsize = 24\n")
        change = {**self.change(session), "cursor_remove": ["Neat", "Spare"]}
        labels = [item["label"] for item in session.preview(change, validate=False)["summary"]]
        self.assertIn("Delete cursor theme: Neat (~/.icons/Neat, for good)", labels)
        self.assertIn("Delete downloaded cursor theme: Spare", labels)
        report = session.save(change, validate=False, backup=lambda path, config_dir: None)
        self.assertNotIn("warnings", report)
        self.assertFalse(os.path.lexists(os.path.join(self.home, ".icons", "Neat")))
        self.assertEqual(cursor_download.cached_themes(self.data), {})


if __name__ == "__main__":
    unittest.main()
