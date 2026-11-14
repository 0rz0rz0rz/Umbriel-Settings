"""File-system helpers in umbriel_core: backups, cursor themes, KDE schemes, launch environment (no Qt)."""

import os
import tempfile
import unittest
from unittest.mock import patch

from umbriel_core import kde, noctalia_theme, paths, titlebar_apply, titlebar_theme
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

    def test_snapshot_file_adopts_the_old_single_backup_as_the_oldest(self):
        source = self.write("mimeapps.list", text="new\n")
        legacy = self.write("desktop", "mimeapps.list.bak", text="old\n")
        os.utime(legacy, (0, 86400))
        directory = os.path.join(self.root, "desktop")
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


class TitlebarFollowTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch.dict(os.environ, {"XDG_CONFIG_HOME": self.root})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.backups = os.path.join(self.root, "backups")
        self.noctalia = self.write("noctalia", "noctalia-config.toml", text="[shell]\nfont_family = \"Inter\"\n")
        self.write("umbriel-settings", "noctalia-palette.conf",
                   text="primary=#aa0000\nsurface=#101010\nsurface_container=#202020\nprimary_container=#303030\n")
        self.config = self.write("umbriel", "config.toml", text="")

    def test_follow_writes_template_entry_and_current_colors(self):
        state = titlebar_theme.follow(self.config, "background", "kde_header", 0xD7, self.backups)
        self.assertEqual(state["fields"]["background"],
                         {"role": "surface_container", "alpha": "D7", "source": "kde_header", "color": "#202020D7"})
        state = titlebar_theme.follow(self.config, "background_unfocused", "kde", 0x80, self.backups)
        self.assertEqual(set(state["fields"]), {"background", "background_unfocused"}, "the other field is kept")
        with open(titlebar_theme.output_file(), encoding="utf-8") as handle:
            self.assertIn('background = "#202020D7"', handle.read())
        with open(titlebar_theme.template_file(), encoding="utf-8") as handle:
            self.assertIn("{{colors.surface_container.default.hex_stripped}}D7", handle.read())
        import tomllib
        with open(self.noctalia, "rb") as handle:
            entry = tomllib.load(handle)["theme"]["templates"]["user"]["umbriel_titlebar"]
        self.assertEqual(entry["input_path"], "$XDG_CONFIG_HOME/noctalia/templates/umbriel-titlebar.toml")
        self.assertEqual(entry["output_path"], titlebar_theme.output_file())
        self.assertEqual(entry["post_hook"], f"python3 '{titlebar_theme.script_file()}' "
                                             f"'{titlebar_theme.output_file()}'")
        self.assertTrue(os.path.isfile(titlebar_theme.script_file()))
        state = titlebar_theme.follow(self.config, "background", None, 0, self.backups)
        self.assertEqual(set(state["fields"]), {"background_unfocused"})
        state = titlebar_theme.follow(self.config, "background_unfocused", None, 0, self.backups)
        self.assertEqual(state["fields"], {})
        with open(self.noctalia, "rb") as handle:
            user = tomllib.load(handle).get("theme", {}).get("templates", {}).get("user", {})
        self.assertNotIn("umbriel_titlebar", user, "the hook stops once nothing follows")
        self.assertFalse(os.path.exists(titlebar_theme.template_file()))
        self.assertFalse(os.path.exists(titlebar_theme.output_file()))
        with open(self.noctalia, encoding="utf-8") as handle:
            self.assertIn('font_family = "Inter"', handle.read())

    def test_each_config_follows_on_its_own(self):
        other = self.write("other", "config.toml", text="")
        titlebar_theme.follow(self.config, "background", "kde", 0xFF, self.backups)
        state = titlebar_theme.follow(other, "background", "kde_header", 0x80, self.backups)
        self.assertEqual(state["fields"]["background"]["source"], "kde_header")
        self.assertEqual(titlebar_theme.status(self.config)["fields"]["background"]["source"], "kde")
        with open(titlebar_theme.output_file(), encoding="utf-8") as handle:
            rendered = handle.read()
        self.assertEqual(dict(titlebar_apply.rendered_blocks(rendered)),
                         {other: {"background": "#20202080"}, self.config: {"background": "#303030FF"}})
        state = titlebar_theme.follow(self.config, "background", None, 0, self.backups)
        self.assertEqual(state["fields"], {})
        self.assertEqual(set(titlebar_theme.read_all()), {other}, "stopping one config keeps the other")

    def test_a_template_from_before_per_config_following_is_kept(self):
        import tomlkit
        self.write("noctalia", "templates", "umbriel-titlebar.toml", text=(
            '[colors.title_bar]\n'
            'background = "#{{colors.surface_container.default.hex_stripped}}D7"  # source=kde_header\n'))
        with open(self.noctalia, encoding="utf-8") as handle:
            document = tomlkit.parse(handle.read())
        document["theme"] = {"templates": {"user": {"umbriel_titlebar": {
            "post_hook": f"python3 '/x/titlebar_apply.py' '/x/titlebar-colors.toml' '{self.config}'"}}}}
        with open(self.noctalia, "w", encoding="utf-8") as handle:
            handle.write(tomlkit.dumps(document))
        self.assertEqual(titlebar_theme.status(self.config)["fields"]["background"]["source"], "kde_header")
        other = self.write("other", "config.toml", text="")
        titlebar_theme.follow(other, "background", "kde", 0xFF, self.backups)
        self.assertEqual(set(titlebar_theme.read_all()), {self.config, other}, "the old config keeps following")

    def test_follow_rejects_bad_input(self):
        for args in (("title", "kde", 255), ("background", "gtk", 255), ("background", "kde", 256)):
            with self.assertRaises(ValueError):
                titlebar_theme.follow(self.config, *args, self.backups)


class TitlebarApplyTests(TempDirTestCase):
    """The post_hook script that copies followed colors into the config."""

    def setUp(self):
        super().setUp()
        self.backup = os.path.join(self.root, "config.toml.titlebar.bak")
        patcher = patch.object(titlebar_apply, "backup_file", return_value=self.backup)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_replaces_only_the_two_keys_and_keeps_the_rest(self):
        text = ('# mine\n[colors.title_bar]  # bar\nbackground = "#1F1F1FD7"  # old\ntext = "#FFFFFFFF"\n\n'
                '[appearance]\nbackground = "keep"\n')
        updated = titlebar_apply.apply(text, {"background": "#202020CC", "background_unfocused": "#101010CC"})
        self.assertEqual(updated, '# mine\n[colors.title_bar]  # bar\nbackground_unfocused = "#101010CC"\n'
                                  'background = "#202020CC"\ntext = "#FFFFFFFF"\n\n[appearance]\nbackground = "keep"\n')
        self.assertEqual(titlebar_apply.apply(updated, {"background": "#202020CC"}), updated, "unchanged stays")

    def test_adds_the_table_when_missing(self):
        self.assertEqual(titlebar_apply.apply("[general]\n", {"background": "#202020CC"}),
                         '[general]\n\n[colors.title_bar]\nbackground = "#202020CC"\n')

    def test_keeps_crlf_and_other_keys(self):
        text = '[colors.title_bar]\r\ntext = "#FFFFFFFF"\r\nbackground = "#000000FF"\r\n[general]\r\n'
        self.assertEqual(titlebar_apply.apply(text, {"background": "#112233CC", "background_unfocused": "#000000CC"}),
                         '[colors.title_bar]\r\nbackground_unfocused = "#000000CC"\r\ntext = "#FFFFFFFF"\r\n'
                         'background = "#112233CC"\r\n[general]\r\n')

    def test_main_never_writes_invalid_toml(self):
        rendered = self.write("colors.toml", text='background = "#112233CC"\n')
        for text in ('[colors]\ntitle_bar.background = "#000000FF"\n',
                     '[colors]\ntitle_bar = { background = "#000000FF" }\n'):
            config = self.write("config.toml", text=text)
            with patch("sys.stderr"):
                self.assertEqual(titlebar_apply.main([rendered, config]), 1, text)
            with open(config, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), text)

    def test_main_keeps_crlf_on_disk(self):
        rendered = self.write("colors.toml", text='background = "#112233CC"\n')
        config = os.path.join(self.root, "crlf.toml")
        with open(config, "wb") as handle:
            handle.write(b'[colors.title_bar]\r\nbackground = "#000000FF"\r\n')
        self.assertEqual(titlebar_apply.main([rendered, config]), 0)
        with open(config, "rb") as handle:
            self.assertEqual(handle.read(), b'[colors.title_bar]\r\nbackground = "#112233CC"\r\n')

    def test_main_backs_up_the_previous_config(self):
        rendered = self.write("colors.toml", text='background = "#112233CC"\n')
        config = self.write("config.toml", text="[colors.title_bar]\n")
        self.assertEqual(titlebar_apply.main([rendered, config]), 0)
        with open(self.backup, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "[colors.title_bar]\n")

    def test_main_applies_each_config_block_and_continues_after_a_failure(self):
        first = self.write("a", "config.toml", text="[colors.title_bar]\n")
        missing = os.path.join(self.root, "gone", "config.toml")
        second = self.write("b", "config.toml", text="")
        rendered = self.write("colors.toml", text=(
            f'# header\n# config: {first}\nbackground = "#112233CC"  # source=kde\n'
            f'# config: {missing}\nbackground = "#000000FF"  # source=kde\n'
            f'# config: {second}\nbackground_unfocused = "#445566FF"  # source=kde\n'))
        with patch("sys.stderr"):
            self.assertEqual(titlebar_apply.main([rendered]), 1, "the missing config is reported")
        with open(first, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), '[colors.title_bar]\nbackground = "#112233CC"\n')
        with open(second, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), '[colors.title_bar]\nbackground_unfocused = "#445566FF"\n')

    def test_main_reads_rendered_file_and_refuses_symlinks(self):
        rendered = self.write("colors.toml", text='[colors.title_bar]\nbackground = "#2f2322cc"  # source=kde\n')
        config = self.write("config.toml", text="[colors.title_bar]\n")
        self.assertEqual(titlebar_apply.main([rendered, config]), 0)
        with open(config, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), '[colors.title_bar]\nbackground = "#2F2322CC"\n')
        link = os.path.join(self.root, "link.toml")
        os.symlink(config, link)
        with patch("sys.stderr"):
            self.assertEqual(titlebar_apply.main([rendered, link]), 1)


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
