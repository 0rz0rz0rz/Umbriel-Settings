"""File-system helpers in umbriel_core: backups, cursor themes, KDE schemes, launch environment (no Qt)."""

import os
import tempfile
import unittest
from unittest.mock import patch

from umbriel_core import kde, noctalia_theme, paths
from umbriel_core.backups import (
    MAX_BACKUPS,
    create_backup_snapshot,
    delete_backup_snapshots,
    list_backup_snapshots,
    prune_backup_snapshots,
    snapshot_file,
)
from umbriel_core.cursor_themes import installed_cursor_themes
from umbriel_core.launch import child_env
from umbriel_core.legacy import migrate_data_dir


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        self.root = tempdir.name

    def write(self, *parts, text=""):
        path = os.path.join(self.root, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path


class BackupTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.directory = os.path.join(self.root, "backups")
        os.mkdir(self.directory)
        self.config_path = "/config/config.toml"

    def backup(self, name):
        return self.write("backups", name, text="[general]\n")

    def test_lists_only_regular_backups_for_current_config_in_order(self):
        later = self.backup("config.toml.20260102.bak")
        earlier = self.backup("config.toml.20260101.bak")
        self.backup("other.toml.20260101.bak")
        os.mkdir(os.path.join(self.directory, "config.toml.20260103.bak"))
        os.symlink(later, os.path.join(self.directory, "config.toml.20260104.bak"))
        self.assertEqual(list_backup_snapshots(self.directory, self.config_path), [earlier, later])
        self.assertEqual(list_backup_snapshots(os.path.join(self.root, "missing"), self.config_path), [])

    def test_deletes_only_marked_backups_and_rejects_outside_paths(self):
        marked = self.backup("config.toml.20260101.bak")
        unmarked = self.backup("config.toml.20260102.bak")
        outside = self.write("keep.txt", text="keep")
        other = self.backup("other.toml.20260101.bak")
        sneaky = os.path.join(self.directory, "..", "config.toml.20260101.bak")
        deleted, errors = delete_backup_snapshots(self.directory, self.config_path, [marked, outside, other, sneaky])
        self.assertEqual(deleted, [os.path.basename(marked)])
        for path in (unmarked, outside, other):
            self.assertTrue(os.path.exists(path), path)
        self.assertEqual(len(errors), 3)
        self.assertTrue(all("not a valid backup path" in error for error in errors))

    def test_symlinked_backup_is_not_followed(self):
        target = self.write("target.txt", text="keep")
        link = os.path.join(self.directory, "config.toml.20260101.bak")
        os.symlink(target, link)
        deleted, errors = delete_backup_snapshots(self.directory, self.config_path, [link])
        self.assertEqual(deleted, [])
        self.assertIn("not a regular file", errors[0])
        self.assertTrue(os.path.exists(target))


    def test_prune_keeps_the_newest_and_the_protected_backup(self):
        names = [self.backup(f"config.toml.202601{day:02d}.bak") for day in range(1, 14)]
        deleted = prune_backup_snapshots(self.directory, self.config_path, protect=names[0])
        self.assertEqual(deleted, [os.path.basename(name) for name in names[1:4]])
        self.assertEqual(list_backup_snapshots(self.directory, self.config_path), [names[0]] + names[4:])
        self.assertEqual(MAX_BACKUPS, 10)

    def test_new_snapshot_prunes_old_ones(self):
        config = self.write("config.toml", text="[general]\n")
        directory = os.path.join(self.root, "data", "backups")
        for _ in range(MAX_BACKUPS + 2):
            create_backup_snapshot(config, os.path.join(self.root, "data"))
        self.assertEqual(len(list_backup_snapshots(directory, config)), MAX_BACKUPS)

    def test_old_single_backup_is_adopted_as_the_oldest(self):
        source = self.write("mimeapps.list", text="new\n")
        legacy = self.write("data", "backups", "mimeapps.list.bak", text="old\n")
        os.utime(legacy, (0, 86400))
        directory = os.path.join(self.root, "data", "backups")
        migrate_data_dir(os.path.join(self.root, "data"))
        newest = snapshot_file(source, directory)
        snapshots = list_backup_snapshots(directory, source)
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[-1], newest)
        with open(snapshots[0], encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "old\n")
        self.assertFalse(os.path.exists(legacy))
        for _ in range(MAX_BACKUPS + 1):
            snapshot_file(source, directory)
        self.assertEqual(len(list_backup_snapshots(directory, source)), MAX_BACKUPS)


class PrivateFilesTests(TempDirTestCase):
    """Copies of the user's files are owner-only, whatever the original's mode (PR #1544 review)."""

    def mode(self, path):
        return os.stat(path).st_mode & 0o777

    def test_snapshots_are_owner_only_from_the_first_byte(self):
        config = self.write("config.toml", text="[environment]\nTOKEN = \"x\"\n")
        os.chmod(config, 0o644)
        directory = os.path.join(self.root, "data", "backups")
        os.makedirs(directory, mode=0o755)
        os.chmod(directory, 0o755)
        modes = []
        real = paths.atomic_write

        def spy(path, data, mode=None):  # the copy is never written with another mode first
            modes.append(mode)
            return real(path, data, mode)

        with patch("umbriel_core.backups.atomic_write", spy):
            snapshot = snapshot_file(config, directory)
        self.assertEqual(modes, [0o600])
        self.assertEqual(self.mode(snapshot), 0o600)
        self.assertEqual(self.mode(directory), 0o700, "an existing 0755 folder is tightened")
        new_dir = os.path.join(self.root, "data", "configs", "abc", "backups")
        self.assertEqual(self.mode(os.path.dirname(create_backup_snapshot(config, os.path.dirname(new_dir)))),
                         0o700)

    def test_the_data_directory_is_kept_owner_only(self):
        data = os.path.join(self.root, "umbriel-settings")
        os.makedirs(data)
        os.chmod(data, 0o755)
        with patch.dict(os.environ, {"XDG_DATA_HOME": self.root}):
            self.assertEqual(paths.default_gui_data_dir(), data)
        self.assertEqual(self.mode(data), 0o700)

    def test_sidecars_are_owner_only(self):
        from umbriel_core import keybinds
        directory = os.path.join(self.root, "configs", "x")
        keybinds.save_locked({"Super+Q"}, directory)
        self.assertEqual(self.mode(keybinds.lock_file(directory)), 0o600)

    def test_files_of_earlier_versions_become_owner_only_once(self):
        data = os.path.join(self.root, "data")
        backup = self.write("data", "configs", "x", "backups", "config.toml.20260101-000000-000000.bak", text="a")
        labels = self.write("data", "configs", "x", "gui-labels.json", text="{}")
        hook_backup = self.write("xdg", "umbriel-settings", "config.toml.12345678.titlebar.bak", text="a")
        script = self.write("xdg", "umbriel-settings", "titlebar_apply.py", text="")
        for path in (backup, labels, hook_backup, script):
            os.chmod(path, 0o644)
        os.chmod(os.path.dirname(backup), 0o755)
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": os.path.join(self.root, "xdg")}):
            migrate_data_dir(data)
        self.assertEqual([self.mode(path) for path in (backup, labels, hook_backup)], [0o600] * 3)
        self.assertEqual(self.mode(os.path.dirname(backup)), 0o700)
        self.assertEqual(self.mode(script), 0o644, "the hook script stays readable; only its backups are private")
        self.assertTrue(os.path.exists(os.path.join(data, ".private-v1")))


class AtomicWriteTests(TempDirTestCase):
    def test_keeps_the_mode_and_leaves_no_temporary_files(self):
        path = self.write("dir", "file.txt", text="old")
        os.chmod(path, 0o640)
        paths.atomic_write(path, "new")
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o640)
        paths.atomic_write(os.path.join(self.root, "dir", "fresh.txt"), b"x")
        self.assertEqual(os.stat(os.path.join(self.root, "dir", "fresh.txt")).st_mode & 0o777, 0o644)
        paths.atomic_write(path, "private", 0o600)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, "dir"))), ["file.txt", "fresh.txt"])

    def test_failed_write_keeps_the_old_file(self):
        path = self.write("file.txt", text="old")
        with patch("umbriel_core.paths.os.replace", side_effect=OSError("disk full")), \
                self.assertRaises(OSError):
            paths.atomic_write(path, "new")
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "old")
        self.assertEqual(os.listdir(self.root), ["file.txt"])

    def test_write_text_file_writes_through_a_symlinked_sidecar(self):
        target = self.write("real.json", text="{}")
        link = os.path.join(self.root, "link.json")
        os.symlink(target, link)
        paths.write_text_file(link, "[]")
        self.assertTrue(os.path.islink(link))
        with open(target, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "[]")


class WriteLockTests(TempDirTestCase):
    def test_a_held_lock_times_out_and_is_released_after_errors(self):
        directory = os.path.join(self.root, "data")
        with paths.write_lock(directory), self.assertRaisesRegex(TimeoutError, "still saving"), \
                paths.write_lock(directory, timeout=0.1):
            pass
        with self.assertRaises(RuntimeError), paths.write_lock(directory):
            raise RuntimeError("a failing save")
        with paths.write_lock(directory, timeout=0.1):  # free again
            pass


class CursorThemeTests(TempDirTestCase):
    def test_discovers_themes_in_xdg_and_legacy_locations(self):
        home = self.root
        data_home = os.path.join(home, "data")
        data_dir = os.path.join(home, "system")
        for root, name in (
            (os.path.join(home, ".icons"), "Legacy"),
            (os.path.join(data_home, "icons"), "User"),
            (os.path.join(data_dir, "icons"), "System"),
            (os.path.join(data_dir, "icons"), "User"),
        ):
            os.makedirs(os.path.join(root, name, "cursors"))
        os.makedirs(os.path.join(data_dir, "icons", "IconOnly", "scalable"))
        self.write("data", "icons", "default", "index.theme", text="[Icon Theme]\nInherits=User\n")
        os.symlink(os.path.join(data_home, "icons", "User"), os.path.join(data_home, "icons", "Linked"))
        env = {"HOME": home, "XDG_DATA_HOME": data_home, "XDG_DATA_DIRS": data_dir}
        with patch.dict(os.environ, env, clear=True):
            themes = installed_cursor_themes()
        self.assertEqual(
            [name for name in themes if name in {"default", "Legacy", "Linked", "System", "User", "IconOnly"}],
            ["default", "Legacy", "Linked", "System", "User"],
        )

    def test_xcursor_path_overrides_standard_locations(self):
        home = self.root
        os.makedirs(os.path.join(home, "custom", "Custom", "cursors"))
        os.makedirs(os.path.join(home, ".icons", "Ignored", "cursors"))
        env = {"HOME": home, "XCURSOR_PATH": os.pathsep.join(["~/custom", os.path.join(home, "missing")])}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(installed_cursor_themes(), ["Custom"])


class KdeSchemeTests(TempDirTestCase):
    def test_missing_header_returns_only_title_colors(self):
        scheme = self.write("scheme.colors", text="[WM]\nactiveBackground=1,2,3\ninactiveBackground=4,5,6\n")
        colors, backgrounds, errors = kde.read_title_bar_rgb(scheme)
        self.assertEqual(colors, {("colors", "title_bar", "background"): (1, 2, 3),
                                  ("colors", "title_bar", "background_unfocused"): (4, 5, 6)})
        self.assertEqual((backgrounds, errors), ({}, {}))

    def test_repeated_keys_are_read_and_broken_files_are_value_errors(self):
        scheme = self.write("twice.colors", text="[WM]\nactiveBackground=1,2,3\nactiveBackground=7,8,9\n")
        colors, _, _ = kde.read_title_bar_rgb(scheme)
        self.assertEqual(colors[("colors", "title_bar", "background")], (7, 8, 9))
        with self.assertRaises(ValueError):
            kde.read_title_bar_rgb(self.write("broken.colors", text="activeBackground=1,2,3\n"))

    def test_invalid_colors_are_reported_per_key(self):
        scheme = self.write("bad.colors", text="[WM]\nactiveBackground=999,0,0\nactiveForeground=1,2\n"
                                               "[Colors:Header]\nBackgroundNormal=1,2,3\n")
        colors, backgrounds, errors = kde.read_title_bar_rgb(scheme)
        self.assertEqual(colors, {})
        self.assertEqual(backgrounds, {("colors", "title_bar", "background"): (1, 2, 3)})
        self.assertEqual(set(errors), {("title", ("colors", "title_bar", "background")),
                                       ("title", ("colors", "title_bar", "text"))})
        self.assertTrue(all("Invalid" in message for message in errors.values()))

    def test_scheme_without_any_title_colors_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "no title-bar"):
            kde.read_title_bar_rgb(self.write("empty.colors", text="[General]\nName=Empty\n"))

    def test_qt6ct_scheme_path_requires_a_custom_palette(self):
        config = os.path.join(self.root, "qt6ct", "qt6ct.conf")
        with self.assertRaisesRegex(ValueError, "not found"):
            kde.qt6ct_scheme_path(config)
        self.write("qt6ct", "qt6ct.conf", text="[Appearance]\ncustom_palette=false\ncolor_scheme_path=/x.colors\n")
        with self.assertRaisesRegex(ValueError, "not enabled"):
            kde.qt6ct_scheme_path(config)
        self.write("qt6ct", "qt6ct.conf", text="[Appearance]\ncustom_palette=true\n")
        with self.assertRaisesRegex(ValueError, "No qt6ct color scheme"):
            kde.qt6ct_scheme_path(config)
        self.write("qt6ct", "qt6ct.conf", text='[Appearance]\ncustom_palette=true\ncolor_scheme_path="mine.colors"\n')
        self.assertEqual(kde.qt6ct_scheme_path(config), os.path.join(self.root, "qt6ct", "mine.colors"))


class NoctaliaThemeTests(unittest.TestCase):
    def test_palette_names_and_font_cannot_escape_css_values(self):
        roles = noctalia_theme.parse_palette("primary=#112233\nx;} body{display:none=#445566\nBad=#000000\n")
        self.assertEqual(roles, {"primary": "#112233"})
        css = noctalia_theme.css_variables({"primary": "#112233", "a}b": "#000000"},
                                           {"font_family": 'Evil"; } body { x: \\\n', "radius_scale": 1.0})
        self.assertNotIn("a}b", css)
        self.assertIn('--font: "Evil\\"; } body { x: \\\\", system-ui, sans-serif;', css)

    def test_corner_radius_scale_is_clamped_like_noctalia(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {
                "XDG_CONFIG_HOME": root, "XDG_STATE_HOME": os.path.join(root, "state"), "NOCTALIA_STATE_HOME": ""}):
            os.makedirs(os.path.join(root, "noctalia"))
            for text, expected in (("3.0", 2.0), ("-1", 0.0), ("0.5", 0.5), ('"big"', 1.0), ("true", 1.0)):
                with open(noctalia_theme.noctalia_config_file(), "w", encoding="utf-8") as handle:
                    handle.write(f"[shell]\ncorner_radius_scale = {text}\n")
                self.assertEqual(noctalia_theme.shell_style()["radius_scale"], expected, text)
            os.remove(noctalia_theme.noctalia_config_file())
            self.assertEqual(noctalia_theme.shell_style()["radius_scale"], 1.0)

    def test_settings_window_overrides_win_over_the_config(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {
                "XDG_CONFIG_HOME": root, "XDG_STATE_HOME": os.path.join(root, "state"), "NOCTALIA_STATE_HOME": ""}):
            os.makedirs(os.path.join(root, "noctalia"))
            with open(noctalia_theme.noctalia_config_file(), "w", encoding="utf-8") as handle:
                handle.write('[shell]\ncorner_radius_scale = 2.0\nfont_family = "Fira Code"\n')
            self.assertEqual(noctalia_theme.shell_style()["radius_scale"], 2.0)
            os.makedirs(os.path.dirname(noctalia_theme.noctalia_settings_file()))
            with open(noctalia_theme.noctalia_settings_file(), "w", encoding="utf-8") as handle:
                handle.write("[shell]\ncorner_radius_scale = 0.0\n")
            self.assertEqual(noctalia_theme.shell_style(), {"font_family": "Fira Code", "radius_scale": 0.0})
            with patch.dict(os.environ, {"NOCTALIA_STATE_HOME": os.path.join(root, "other")}):
                self.assertEqual(noctalia_theme.shell_style()["radius_scale"], 2.0)


class PaletteTemplateTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch.dict(os.environ, {"XDG_CONFIG_HOME": self.root})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.backups = os.path.join(self.root, "backups")

    def test_install_adds_one_entry_and_keeps_the_rest(self):
        original = ("# my shell\n[theme]\nmode = \"dark\"  # keep\n\n    [theme.templates.user.other]\n"
                    "    input_path = \"a\"\n    output_path = \"b\"\n")
        config = self.write("noctalia", "noctalia-config.toml", text=original)
        status = noctalia_theme.template_status()
        self.assertEqual((status["noctalia"], status["template"], status["entry"]), (True, False, False))
        status = noctalia_theme.install_template(self.backups)
        self.assertEqual((status["template"], status["entry"], status["palette"]), (True, True, False))
        with open(config, encoding="utf-8") as handle:
            text = handle.read()
        self.assertTrue(text.startswith(original))
        self.assertIn('[theme.templates.user.umbriel_settings]', text)
        snapshots = list_backup_snapshots(self.backups, config)
        self.assertEqual(len(snapshots), 1)
        with open(snapshots[0], encoding="utf-8") as handle:
            self.assertEqual(handle.read(), original)
        with open(noctalia_theme.template_file(), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), noctalia_theme.PALETTE_TEMPLATE)
        noctalia_theme.install_template(self.backups)
        with open(config, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), text, "a second install changes nothing")

    def test_install_creates_missing_template_tables(self):
        config = self.write("noctalia", "noctalia-config.toml", text="[shell]\nfont_family = \"Inter\"\n")
        noctalia_theme.install_template(self.backups)
        import tomllib
        with open(config, "rb") as handle:
            data = tomllib.load(handle)
        self.assertEqual(data["shell"], {"font_family": "Inter"})
        self.assertEqual(data["theme"]["templates"]["user"]["umbriel_settings"], noctalia_theme.TEMPLATE_ENTRY)

    def test_install_refuses_symlinks_and_missing_config(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            noctalia_theme.install_template(self.backups)
        target = self.write("real.toml", text="")
        os.makedirs(os.path.join(self.root, "noctalia"))
        os.symlink(target, os.path.join(self.root, "noctalia", "noctalia-config.toml"))
        with self.assertRaisesRegex(ValueError, "symlink"):
            noctalia_theme.install_template(self.backups)

    def test_a_config_saved_meanwhile_is_not_overwritten(self):
        config = self.write("noctalia", "noctalia-config.toml", text="[shell]\n")
        real = noctalia_theme.snapshot_file

        def settings_window_saves(path, directory):  # Noctalia's settings window writes between read and write
            with open(config, "w", encoding="utf-8") as handle:
                handle.write("[shell]\nfont_family = \"Inter\"\n")
            return real(path, directory)

        with patch("umbriel_core.noctalia_theme.tomllib.loads", side_effect=lambda text: settings_window_saves(
                config, self.backups) and {}), self.assertRaisesRegex(ValueError, "changed meanwhile"):
            noctalia_theme.install_template(self.backups)
        with open(config, encoding="utf-8") as handle:
            self.assertIn("Inter", handle.read())


class RenameMigrationTests(TempDirTestCase):
    """Data and palette locations from before the rename (umbriel-config-gui) keep working."""

    def test_legacy_data_directory_moves_once(self):
        legacy = self.write("umbriel-config-gui", "configs", "abc", "gui-labels.json", text="{}")
        self.write("umbriel-config-gui", "gui-config-path", text="/cfg/config.toml")
        with patch.dict(os.environ, {"XDG_DATA_HOME": self.root}):
            moved = paths.default_gui_data_dir()
            self.assertEqual(moved, os.path.join(self.root, "umbriel-settings"))
            self.assertFalse(os.path.exists(legacy))
            with open(os.path.join(moved, "gui-config-path"), encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "/cfg/config.toml")
            # A later legacy directory (an old AppImage still running) is left alone.
            self.write("umbriel-config-gui", "stray", text="x")
            self.assertEqual(paths.default_gui_data_dir(), moved)
            self.assertTrue(os.path.exists(os.path.join(self.root, "umbriel-config-gui", "stray")))

    def test_new_installs_use_the_new_directory(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": self.root}):
            self.assertEqual(paths.default_gui_data_dir(), os.path.join(self.root, "umbriel-settings"))

    def test_failed_move_keeps_using_the_legacy_directory(self):
        self.write("umbriel-config-gui", "gui-config-path", text="/cfg/config.toml")
        with patch.dict(os.environ, {"XDG_DATA_HOME": self.root}), \
                patch("umbriel_core.paths.os.rename", side_effect=OSError("busy")):
            self.assertEqual(paths.default_gui_data_dir(), os.path.join(self.root, "umbriel-config-gui"))

    def test_palette_written_by_an_old_template_is_still_read(self):
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": self.root}):
            self.assertEqual(noctalia_theme.palette_file(),
                             os.path.join(self.root, "umbriel-settings", "noctalia-palette.conf"))
            legacy = self.write("umbriel-config-gui", "noctalia-palette.conf", text="primary=#112233\n")
            self.assertEqual(noctalia_theme.palette_file(), legacy)
            new = self.write("umbriel-settings", "noctalia-palette.conf", text="primary=#445566\n")
            self.assertEqual(noctalia_theme.palette_file(), new)
            self.assertIn("umbriel-settings/noctalia-palette.conf", noctalia_theme.TEMPLATE_ENTRY["output_path"])


class ChildEnvTests(unittest.TestCase):
    def test_outside_appimage_environment_is_unchanged(self):
        environ = {"PYTHONPATH": "/host", "HOME": "/home/user"}
        self.assertEqual(child_env(environ), environ)

    def test_appimage_restores_host_python_variables(self):
        environ = {
            "UMBRIEL_SETTINGS_APPIMAGE_ENV": "1",
            "PYTHONPATH": "/tmp/.mount_app",
            "PYTHONNOUSERSITE": "1",
            "UMBRIEL_SETTINGS_HOST_PYTHONPATH": "/host/lib",
            "HOME": "/home/user",
        }
        env = child_env(environ)
        self.assertEqual(env["PYTHONPATH"], "/host/lib")
        self.assertNotIn("PYTHONNOUSERSITE", env)
        self.assertEqual(env["HOME"], "/home/user")
        self.assertFalse(any(name.startswith("UMBRIEL_SETTINGS_") for name in env))


if __name__ == "__main__":
    unittest.main()
