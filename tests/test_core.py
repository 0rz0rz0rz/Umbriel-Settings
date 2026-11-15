import collections
import os
import subprocess
import sys
import tempfile
import textwrap
import tomllib
import unittest

import tomlkit

from umbriel_core import entries, entry_ops, kde, keybinds, paths, schema
from umbriel_core.layout import BANNER_RE, rebuild_config
from umbriel_core.tomlops import MISSING, getp

PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(entries.__file__)))
ROOT = os.path.dirname(PYTHON_DIR)
CORE_MODULES = sorted(
    name[:-3] for name in os.listdir(os.path.join(PYTHON_DIR, "umbriel_core"))
    if name.endswith(".py") and name != "__init__.py"
)
# Modules the desktop-only plugin helpers import; they must work without tomlkit.
TOMLKIT_FREE = {"actions", "backups", "cursor_themes", "fields", "help", "kde", "launch", "mimeapps", "paths",
                "schema", "xdg_dirs"}


def import_blocked(modules, blocked):
    """Import `modules` in a fresh interpreter where the `blocked` packages cannot be imported."""
    code = textwrap.dedent(f"""
        import importlib, sys
        for name in {blocked!r}:
            sys.modules[name] = None
        for name in {modules!r}:
            importlib.import_module("umbriel_core." + name)
    """)
    return subprocess.run(
        [sys.executable, "-B", "-c", code], cwd=PYTHON_DIR, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": PYTHON_DIR},
    )


class CoreIsolationTests(unittest.TestCase):
    def test_core_never_imports_qt(self):
        result = import_blocked(CORE_MODULES, ["PySide6"])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_desktop_modules_do_not_need_tomlkit(self):
        result = import_blocked(sorted(TOMLKIT_FREE), ["PySide6", "tomlkit"])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_plugin_copy_matches_source(self):
        result = subprocess.run(
            [sys.executable, "-B", os.path.join(ROOT, "tools", "sync_plugin_core.py"), "--check"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr + "\nRun tools/sync_plugin_core.py.")

    def test_app_and_plugin_share_one_version(self):
        """App `<Umbriel version>-<NNN>`; plugin `<major>.<minor>.<NNN>` (Noctalia needs plain semver)."""
        import re
        import tomllib
        with open(os.path.join(PYTHON_DIR, "umbriel_settings", "__init__.py"), encoding="utf-8") as handle:
            app_version = re.search(r'^__version__ = "([^"]+)"', handle.read(), re.M).group(1)
        with open(os.path.join(ROOT, "noctalia-plugin", "umbriel-settings", "plugin.toml"), "rb") as handle:
            plugin_version = tomllib.load(handle)["version"]
        match = re.fullmatch(r"(\d+)\.(\d+)\.\d+-(\d{3})", app_version)
        self.assertTrue(match, app_version)
        self.assertEqual(plugin_version, f"{match[1]}.{match[2]}.{int(match[3])}")

    def test_appimage_lock_matches_the_requirements(self):
        """The build installs only hashed wheels from appimage/requirements.lock; a version bump needs new pins."""
        import re
        with open(os.path.join(PYTHON_DIR, "requirements.txt"), encoding="utf-8") as handle:
            wanted = {line.split("#")[0].strip().lower().replace("_", "-") for line in handle} - {""}
        with open(os.path.join(ROOT, "appimage", "requirements.lock"), encoding="utf-8") as handle:
            text = handle.read()
        locked = {name.lower().replace("_", "-") for name in re.findall(r"^(\S+==\S+) \\$", text, re.M)}
        self.assertLessEqual(wanted, locked, "Run tools/update_appimage_pins.py.")
        self.assertNotRegex(text, r"(?m)^\S+==\S+$", "every locked package has hashes")


class CoreEntryTests(unittest.TestCase):
    def test_entry_names_prefer_custom_then_name_then_match(self):
        doc = tomlkit.parse(textwrap.dedent("""
            [[window_rule]]
            match = { app_id = "^org.mozilla.firefox$" }
            [[window_rule]]
            name = "Chat"
            [[workspace]]
            index = 3
        """))
        first, second = doc["window_rule"]
        self.assertEqual(entries.entry_label_info(first, 0), (
            "1. firefox (app id)", 'match.app_id = "^org.mozilla.firefox$"', True))
        self.assertEqual(entries.entry_label_info(first, 0, "Browser")[0], "1. Browser")
        self.assertEqual(entries.entry_label_info(second, 1)[:3:2], ("2. Chat", False))
        self.assertEqual(entries.entry_label_info(doc["workspace"][0], 0)[0], "1. Workspace 3")
        self.assertEqual(entries.entry_label_info(tomlkit.table(), 4)[0], "5. (matches everything)")


    def test_wrongly_shaped_entry_sections_raise_readable_errors(self):
        doc = tomlkit.parse('window_rule = { opacity = 1 }\n[[output]]\nname = "DP-1"\n')
        with self.assertRaisesRegex(ValueError, r"Window rules: .*\[\[window_rule\]\]"):
            entry_ops.entries(doc, "window_rule")
        with self.assertRaisesRegex(ValueError, r"Outputs: .*\[output.NAME\]"):
            entry_ops.entries(doc, "output")
        valid = tomlkit.parse('window_rule = [{ opacity = 1 }]\n[output.DP-1]\nscale = 1.0\n')
        self.assertEqual(len(entry_ops.entries(valid, "window_rule")), 1)
        self.assertEqual(entry_ops.entries(valid, "output")[0][0], "DP-1")


class CoreKeybindTests(unittest.TestCase):
    def test_apply_bindings_keeps_comments_locks_and_order(self):
        doc = tomlkit.parse(textwrap.dedent("""\
            [keybinds]
            # launchers
            "super+Return" = "spawn kitty"
            "super+q" = "window-close" # close
            "super+l" = "spawn noctalia msg session lock"
        """))
        original = keybinds.read_bindings(doc)
        rows = {
            "super+l": original["super+l"],
            "super+Return": ("spawn foot", {}),
            "super+d": ("spawn fuzzel", {"repeat": False}),
        }
        keybinds.apply_bindings(doc, rows, original, locked={"super+q"})
        text = doc.as_string()
        self.assertIn("# launchers", text)
        self.assertIn('"super+q" = "window-close" # close', text)
        self.assertIn('"super+Return" = "spawn foot"', text)
        self.assertIn('"super+d" = {action = "spawn fuzzel", repeat = false}', text)
        self.assertEqual(list(doc["keybinds"])[:2], ["super+l", "super+Return"])

    def test_validation_messages(self):
        keybinds.check_shortcut_conflicts(["super+a", "", "super+b"])
        with self.assertRaisesRegex(ValueError, "duplicates"):
            keybinds.check_shortcut_conflicts(["Super+A", " super+a "])
        with self.assertRaisesRegex(ValueError, "command after"):
            keybinds.check_action("super+x", "spawn")
        with self.assertRaisesRegex(ValueError, "needs its argument"):
            keybinds.check_action("super+x", "workspace-switch <n>")
        keybinds.check_action("super+x", "spawn kitty")

    def test_locks_migrate_from_next_to_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = os.path.join(tmp, "config.toml")
            config_dir = paths.config_gui_data_dir(config, os.path.join(tmp, "data"))
            with open(os.path.join(tmp, keybinds.LOCK_FILE_NAME), "w", encoding="utf-8") as f:
                f.write('["super+q"]')
            self.assertEqual(keybinds.load_locked(config, config_dir), {"super+q"})
            keybinds.save_locked({"b", "a"}, config_dir)
            self.assertEqual(keybinds.load_locked(config, config_dir), {"a", "b"})


class CoreLayoutTests(unittest.TestCase):
    """"Tidy file layout" regroups the whole file: it must keep every value and comment and be stable."""

    CASES = {
        "multiline string with a table header inside": (
            '[general]\nx = 1\n\n[environment]\nA = """\n[window_rule]\nmatch\n"""\n'),
        "CRLF line ends": "[general]\r\nx = 1\r\n\r\n[input]\r\nrepeat = 2\r\n",
        "arrays of tables before plain tables": (
            '[[window_rule]]\nmatch.app_id = "a"\n\n[[window_rule]]\nmatch.app_id = "b"\n\n[general]\nx = 1\n'),
        "dotted keys at the top": "general.x = 1\ninput.repeat = 2\n",
        "inline keybind tables": (
            '[keybinds]\n# launchers\n"Mod+A" = "spawn x"\n"Mod+B" = { action = "spawn y", locked = true }\n'),
        "comment that looks like a banner": "# ==========\n# Fake\n# ==========\n[general]\nx = 1  # mine\n",
    }

    @staticmethod
    def content_lines(text):
        """Non-empty lines other than section banners, which the rebuild adds or replaces."""
        return collections.Counter(line.strip() for line in text.splitlines()
                                   if line.strip() and not BANNER_RE.match(line) and not line.startswith("# ---"))

    def check(self, name, text):
        rebuilt = rebuild_config(text)
        self.assertEqual(tomllib.loads(rebuilt), tomllib.loads(text), name)
        self.assertEqual(rebuild_config(rebuilt), rebuilt, f"{name}: a second rebuild changes nothing")
        missing = self.content_lines(text) - self.content_lines(rebuilt)
        self.assertFalse(missing, f"{name}: lost {list(missing)}")

    def test_rebuild_keeps_values_comments_and_is_stable(self):
        for name, text in self.CASES.items():
            self.check(name, text)

    def test_rebuild_of_the_stock_config(self):
        stock = "/usr/share/umbriel/config.toml"
        if not os.path.isfile(stock):
            self.skipTest("Umbriel's stock config is not installed")
        with open(stock, encoding="utf-8") as handle:
            self.check("stock config", handle.read())


class CorePathTests(unittest.TestCase):
    def test_entry_labels_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = os.path.join(tmp, "config.toml")
            config_dir = os.path.join(tmp, "gui")
            paths.save_entry_labels(config, "window_rule", ["A", ""], config_dir)
            paths.save_entry_labels(config, "scratchpad", ["", ""], config_dir)
            self.assertEqual(paths.load_all_entry_labels(config, config_dir), {"window_rule": ["A", ""]})
            self.assertEqual(paths.load_entry_labels(config, "layer_rule", config_dir), [])

    def test_schema_option_lookup_uses_wildcards(self):
        options = schema.schema_options_by_path({"options": [
            {"path": "output.*.scale", "default": 1.0}, {"path": "general.mod_key"}, "junk",
        ]})
        self.assertEqual(schema.field_schema_option(options, "output.<name>.scale")["default"], 1.0)
        self.assertIsNone(schema.field_schema_option(options, "general.missing"))
        self.assertIs(getp(tomlkit.document(), ("a",)), MISSING)


class CoreKdeTests(unittest.TestCase):
    def test_reads_scheme_from_qt6ct(self):
        with tempfile.TemporaryDirectory() as tmp:
            scheme = os.path.join(tmp, "Theme.colors")
            with open(scheme, "w", encoding="utf-8") as f:
                f.write("[WM]\nactiveBackground=1,2,3\ninactiveForeground=300,0,0\n"
                        "[Colors:Header]\nBackgroundNormal=4,5,6\n")
            conf = os.path.join(tmp, "qt6ct.conf")
            with open(conf, "w", encoding="utf-8") as f:
                f.write("[Appearance]\ncustom_palette=true\ncolor_scheme_path=Theme.colors\n")
            self.assertEqual(kde.qt6ct_scheme_path(conf), scheme)
            colors, backgrounds, errors = kde.read_title_bar_rgb(scheme)
            self.assertEqual(colors, {("colors", "title_bar", "background"): (1, 2, 3)})
            self.assertEqual(backgrounds, {("colors", "title_bar", "background"): (4, 5, 6)})
            self.assertEqual(list(errors), [("title", ("colors", "title_bar", "text_unfocused"))])
            with open(conf, "w", encoding="utf-8") as f:
                f.write("[Appearance]\ncustom_palette=false\n")
            with self.assertRaisesRegex(ValueError, "not enabled"):
                kde.qt6ct_scheme_path(conf)


if __name__ == "__main__":
    unittest.main()
