"""Title bars that follow Noctalia: the user template (titlebar_theme) and its post_hook (titlebar_apply)."""

import os
import unittest
from unittest.mock import patch

from test_core_files import TempDirTestCase
from umbriel_core import paths, titlebar_apply, titlebar_theme


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
        self.assertFalse(os.path.exists(titlebar_theme.script_file()), "nothing of the hook is left")
        with open(self.noctalia, encoding="utf-8") as handle:
            self.assertIn('font_family = "Inter"', handle.read())

    def test_status_only_reads_and_names_the_palette_colors(self):
        script = self.write("umbriel-settings", "titlebar_apply.py", text="# old\n")
        state = titlebar_theme.status(self.config)
        with open(script, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "# old\n", "a read command writes nothing")
        self.assertEqual(state["sources"]["background"], {"kde": "#303030", "kde_header": "#202020"})
        self.assertEqual(state["sources"]["background_unfocused"], {"kde": "#101010", "kde_header": "#101010"})

    def test_refresh_replaces_only_older_scripts(self):
        script = self.write("umbriel-settings", "titlebar_apply.py", text="# old, no version\n")
        titlebar_theme.refresh_script()
        with open(script, encoding="utf-8") as handle:
            self.assertIn(f"SCRIPT_VERSION = {titlebar_apply.SCRIPT_VERSION}", handle.read())
        newer = f"SCRIPT_VERSION = {titlebar_apply.SCRIPT_VERSION + 1}\n"
        self.write("umbriel-settings", "titlebar_apply.py", text=newer)
        titlebar_theme.refresh_script()
        with open(script, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), newer, "a newer copy (another install) stays")
        os.remove(script)
        titlebar_theme.refresh_script()
        self.assertFalse(os.path.exists(script), "nothing is installed while nothing follows")

    def test_stopping_and_cleanup_remove_the_hook_and_its_backups(self):
        titlebar_theme.follow(self.config, "background", "kde", 0xFF, self.backups)
        backup = self.write("umbriel-settings", "config.toml.1234abcd.titlebar.bak", text="secret\n")
        titlebar_theme.follow(self.config, "background", None, 0, self.backups)
        self.assertFalse(os.path.exists(backup), "copies of the config go with the hook")
        palette = os.path.join(self.root, "umbriel-settings", "noctalia-palette.conf")
        self.assertTrue(os.path.exists(palette), "other files in the folder stay")
        titlebar_theme.follow(self.config, "background", "kde", 0xFF, self.backups)
        os.remove(palette)
        self.assertTrue(titlebar_theme.cleanup(self.backups))
        import tomllib
        with open(self.noctalia, "rb") as handle:
            user = tomllib.load(handle).get("theme", {}).get("templates", {}).get("user", {})
        self.assertNotIn("umbriel_titlebar", user)
        self.assertFalse(os.path.exists(titlebar_theme.template_file()))
        self.assertFalse(os.path.exists(os.path.join(self.root, "umbriel-settings")), "the empty folder goes")
        self.assertFalse(titlebar_theme.cleanup(self.backups), "a second cleanup finds nothing")

    def test_a_symlinked_noctalia_config_is_refused_before_anything_is_removed(self):
        titlebar_theme.follow(self.config, "background", "kde", 0xFF, self.backups)
        with open(self.noctalia, encoding="utf-8") as handle:
            real = self.write("elsewhere", "noctalia-config.toml", text=handle.read())
        os.remove(self.noctalia)
        os.symlink(real, self.noctalia)
        with self.assertRaisesRegex(ValueError, "symlink"):
            titlebar_theme.follow(self.config, "background", None, 0, self.backups)
        self.assertTrue(os.path.exists(titlebar_theme.template_file()))
        self.assertTrue(os.path.exists(titlebar_theme.script_file()), "the hook keeps working")

    def test_the_script_is_in_place_before_noctalia_is_told_to_run_it(self):
        """Stopped between the two writes, Noctalia must never run a hook whose script is missing."""
        from umbriel_core import noctalia_theme
        real, seen = noctalia_theme.write_user_template, []

        def spy(*args):
            seen.append(os.path.exists(titlebar_theme.script_file()))
            return real(*args)

        with patch.object(noctalia_theme, "write_user_template", spy):
            titlebar_theme.follow(self.config, "background", "kde", 0xFF, self.backups)
        self.assertEqual(seen, [True])

    def test_cleanup_stops_the_hook_even_when_noctalias_config_cant_change(self):
        """Disable must never leave a hook that rewrites configs: the script and the copies go first."""
        for broken in ("symlink", "no tomlkit"):
            titlebar_theme.follow(self.config, "background", "kde", 0xFF, self.backups)
            backup = self.write("umbriel-settings", "config.toml.1234abcd.titlebar.bak", text="secret\n")
            with open(self.noctalia, encoding="utf-8") as handle:
                text = handle.read()
            with patch.dict("sys.modules", {"tomlkit": None} if broken == "no tomlkit" else {}):
                if broken == "symlink":
                    real = self.write("elsewhere", "noctalia-config.toml", text=text)
                    os.remove(self.noctalia)
                    os.symlink(real, self.noctalia)
                with self.assertRaisesRegex(ValueError, r"umbriel_titlebar.*by hand"):
                    titlebar_theme.cleanup(self.backups)
            for path in (titlebar_theme.script_file(), titlebar_theme.output_file(), backup):
                self.assertFalse(os.path.exists(path), f"{broken}: {path}")
            os.remove(self.noctalia)
            self.noctalia = self.write("noctalia", "noctalia-config.toml", text=text)
            titlebar_theme.cleanup(self.backups)

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

    def test_a_symlinked_output_is_refused_before_anything_is_written(self):
        os.makedirs(os.path.dirname(titlebar_theme.output_file()), exist_ok=True)
        os.symlink(self.config, titlebar_theme.output_file())
        with open(self.noctalia, encoding="utf-8") as handle:
            before = handle.read()
        with self.assertRaisesRegex(ValueError, "symlink"):
            titlebar_theme.follow(self.config, "background", "kde", 255, self.backups)
        with open(self.noctalia, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), before)
        self.assertFalse(os.path.exists(titlebar_theme.template_file()))
        self.assertFalse(os.path.exists(titlebar_theme.script_file()))

    def test_follow_rejects_bad_input(self):
        for args in (("title", "kde", 255), ("background", "gtk", 255), ("background", "kde", 256)):
            with self.assertRaises(ValueError):
                titlebar_theme.follow(self.config, *args, self.backups)


class TitlebarApplyTests(TempDirTestCase):
    """The post_hook script that copies followed colors into the config."""

    def setUp(self):
        super().setUp()
        self.backup = os.path.join(self.root, "config.toml.titlebar.bak")
        self.data = os.path.join(self.root, "data")
        for patcher in (patch.object(titlebar_apply, "backup_file", return_value=self.backup),
                        patch.dict(os.environ, {"XDG_DATA_HOME": self.data})):
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

    def test_the_backup_is_owner_only_also_when_replacing_one(self):
        rendered = self.write("colors.toml", text='background = "#112233CC"\n')
        config = self.write("config.toml", text="[colors.title_bar]\n")
        os.chmod(config, 0o644)
        self.write("config.toml.titlebar.bak", text="older\n")
        os.chmod(self.backup, 0o644)
        self.assertEqual(titlebar_apply.main([rendered, config]), 0)
        self.assertEqual(os.stat(self.backup).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(config).st_mode & 0o777, 0o644, "the config keeps its own mode")

    def test_main_waits_for_the_write_lock(self):
        rendered = self.write("colors.toml", text='background = "#112233CC"\n')
        config = self.write("config.toml", text="[colors.title_bar]\n")
        self.assertEqual(titlebar_apply.lock_dir(), paths.default_gui_data_dir(), "the app's and the panel's lock")
        with paths.write_lock(titlebar_apply.lock_dir()), patch.object(titlebar_apply, "LOCK_TIMEOUT", 0.2), \
                patch("sys.stderr"):
            self.assertEqual(titlebar_apply.main([rendered, config]), 1, "a save holds the lock")
        with open(config, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "[colors.title_bar]\n")
        self.assertEqual(titlebar_apply.main([rendered, config]), 0)

    def test_the_rendered_colors_are_read_under_the_lock(self):
        rendered = self.write("colors.toml", text='background = "#112233CC"\n')
        config = self.write("config.toml", text="[colors.title_bar]\n")
        held = []
        real_open = open

        def spy(path, *args, **kwargs):
            if path == rendered:  # another writer can't get the lock now (flock: a second open file waits)
                try:
                    with patch.object(titlebar_apply, "LOCK_TIMEOUT", 0.1), titlebar_apply.write_lock():
                        held.append(False)
                except TimeoutError:
                    held.append(True)
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", spy):
            self.assertEqual(titlebar_apply.main([rendered, config]), 0)
        self.assertEqual(held, [True])

    def test_temporary_files_are_hidden_and_cleaned_up(self):
        config = self.write("config.toml", text="x\n")
        names = []
        real = titlebar_apply.tempfile.mkstemp

        def spy(**kwargs):
            handle, tmp = real(**kwargs)
            names.append(os.path.basename(tmp))
            return handle, tmp

        with patch.object(titlebar_apply.tempfile, "mkstemp", spy):
            titlebar_apply.write(config, "y\n")
        self.assertTrue(names[0].startswith(".config.toml.") and names[0].endswith(".tmp"), names)

    def test_a_config_saved_meanwhile_is_read_again(self):
        rendered = self.write("colors.toml", text='background = "#112233CC"\n')
        config = self.write("config.toml", text="[colors.title_bar]\n")
        real_read, reads = titlebar_apply.read, []

        def read(path):
            reads.append(path)
            if len(reads) == 2:  # between the first read and the write, someone else saves
                with open(config, "w", encoding="utf-8") as handle:
                    handle.write("[general]\n\n[colors.title_bar]\n")
            return real_read(path)

        with patch.object(titlebar_apply, "read", read):
            self.assertEqual(titlebar_apply.main([rendered, config]), 0)
        with open(config, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), '[general]\n\n[colors.title_bar]\nbackground = "#112233CC"\n')

    def test_main_applies_each_config_block_and_continues_after_a_failure(self):
        first = self.write("a", "config.toml", text="[colors.title_bar]\n")
        missing = os.path.join(self.root, "gone", "config.toml")
        garbled = os.path.join(self.root, "garbled.toml")
        with open(garbled, "wb") as handle:
            handle.write(b"\xff\xfe not utf-8\n")
        second = self.write("b", "config.toml", text="")
        rendered = self.write("colors.toml", text=(
            f'# header\n# config: {first}\nbackground = "#112233CC"  # source=kde\n'
            f'# config: {missing}\nbackground = "#000000FF"  # source=kde\n'
            f'# config: {garbled}\nbackground = "#000000FF"  # source=kde\n'
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


if __name__ == "__main__":
    unittest.main()
