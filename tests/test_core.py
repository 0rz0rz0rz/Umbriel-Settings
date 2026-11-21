import collections
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
import tomllib
import unittest
import unittest.mock

import tomlkit

from umbriel_core import entry_ops, kde, keybinds, paths, schema
from umbriel_core.layout import BANNER_RE, rebuild_config
from umbriel_core.tomlops import MISSING, getp

PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(entry_ops.__file__)))
ROOT = os.path.dirname(PYTHON_DIR)
CORE_MODULES = sorted(
    name[:-3] for name in os.listdir(os.path.join(PYTHON_DIR, "umbriel_core"))
    if name.endswith(".py") and name != "__init__.py"
)
# Modules the desktop-only plugin helpers import; they must work without tomlkit.
TOMLKIT_FREE = {"actions", "backups", "cursor_themes", "fields", "help", "kde", "launch", "legacy", "mimeapps",
                "paths", "schema", "xdg_dirs"}


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

    def test_versions_agree(self):
        """One MAJOR.MINOR.PATCH for app and plugin; the Umbriel/Noctalia targets match plugin_api and every README."""
        from umbriel_core.meta import NOCTALIA_VERSION, UMBRIEL_VERSION, build_meta
        noctalia_for_api = {43: "5.4.0", 53: "5.5.0", 56: "5.6.0"}  # first release with each API (noctalia-plugin.md)
        with open(os.path.join(PYTHON_DIR, "umbriel_settings", "__init__.py"), encoding="utf-8") as handle:
            app_version = re.search(r'^__version__ = "([^"]+)"', handle.read(), re.M).group(1)
        with open(os.path.join(ROOT, "noctalia-plugin", "umbriel-settings", "plugin.toml"), "rb") as handle:
            plugin = tomllib.load(handle)
        self.assertRegex(app_version, r"^\d+\.\d+\.\d+$")
        self.assertEqual(plugin["version"], app_version)
        self.assertEqual(noctalia_for_api.get(plugin["plugin_api"]), NOCTALIA_VERSION)
        self.assertEqual(build_meta({})["targets"], {"umbriel": UMBRIEL_VERSION, "noctalia": NOCTALIA_VERSION})
        wanted = [f"`{app_version}`", f"| Made for Umbriel | `{UMBRIEL_VERSION}` |",
                  f"`{NOCTALIA_VERSION}` or newer (plugin API {plugin['plugin_api']})"]
        for readme in ("README.md", "noctalia-plugin/README.md", "noctalia-plugin/umbriel-settings/README.md"):
            with open(os.path.join(ROOT, readme), encoding="utf-8") as handle:
                text = handle.read()
            self.assertEqual([item for item in wanted if item not in text], [], readme)

    def test_appimage_lock_matches_the_requirements(self):
        """The build installs only hashed wheels from appimage/requirements.lock; a version bump needs new pins."""
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
        self.assertEqual(entry_ops.entry_label_info(first, 0), (
            "1. firefox (app id)", 'match.app_id = "^org.mozilla.firefox$"', True))
        self.assertEqual(entry_ops.entry_label_info(first, 0, "Browser")[0], "1. Browser")
        self.assertEqual(entry_ops.entry_label_info(second, 1)[:3:2], ("2. Chat", False))
        self.assertEqual(entry_ops.entry_label_info(doc["workspace"][0], 0)[0], "1. Workspace 3")
        self.assertEqual(entry_ops.entry_label_info(tomlkit.table(), 4)[0], "5. (matches everything)")


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

    def test_locked_keybinds_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = paths.config_gui_data_dir(os.path.join(tmp, "config.toml"), os.path.join(tmp, "data"))
            keybinds.save_locked({"b", "a"}, config_dir)
            self.assertEqual(keybinds.load_locked(config_dir), {"a", "b"})


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
    def test_entry_labels_ignore_malformed_sidecar_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = os.path.join(tmp, "gui")
            os.makedirs(config_dir)
            with open(os.path.join(config_dir, "gui-labels.json"), "w", encoding="utf-8") as handle:
                json.dump({"window_rule": ["A", 3], "scratchpad": "junk"}, handle)
            self.assertEqual(paths.load_all_entry_labels(config_dir), {"window_rule": ["A", ""]})

    def test_schema_option_lookup_uses_wildcards(self):
        options = schema.schema_options_by_path({"options": [
            {"path": "output.*.scale", "default": 1.0}, {"path": "general.mod_key"}, "junk",
        ]})
        self.assertEqual(schema.field_schema_option(options, "output.<name>.scale")["default"], 1.0)
        self.assertIsNone(schema.field_schema_option(options, "general.missing"))
        self.assertIs(getp(tomlkit.document(), ("a",)), MISSING)

    def test_schema_coverage_matching_rules(self):
        catalog = [
            ("general.mod_key", "choice"),
            ("general.gaps", "int"),               # stale: Umbriel has no such option
            ("output.<name>.scale", "float"),
            ("window_rule[].match", "raw"),        # raw covers everything below it
            ("decoration.blur", "table"),
            ("keybinds.<name>", "custom"),
            ("input.device[].accel", "float"),
        ]
        document = {"options": [
            {"path": "general.mod_key", "type": "enum"},
            {"path": "general.layout", "type": "enum"},            # missing
            {"path": "general", "type": "table"},                  # tables are never missing
            {"path": "output.<name>.scale", "type": "float"},
            {"path": "output.<name>.mode", "type": "string"},      # missing
            {"path": "output.*.scale", "type": "float"},           # a literal "*" matches <name> too
            {"path": "window_rule[].match.app_id", "type": "string"},
            {"path": "window_rule[].opacity", "type": "float"},    # missing
            {"path": "workspace[].match", "type": "string"},       # [] only matches the same array
            {"path": "decoration.blur.size", "type": "int"},
            {"path": "decoration.shadow.size", "type": "int"},     # missing: a prefix of another field
            {"path": "keybinds.<name>", "type": "string"},
            {"path": "input.device[].accel", "type": "float"},
            {"path": "input.device[].accel.extra", "type": "float"},  # longer than a plain field: missing
            {"path": "<name>.x", "type": "int"},                   # odd first segments do not crash
            "junk",
        ]}
        with unittest.mock.patch.object(schema, "schema_field_catalog", return_value=catalog):
            missing, stale = schema.check_schema_coverage(document)
        self.assertEqual(missing, ["<name>.x", "decoration.shadow.size", "general.layout",
                                   "input.device[].accel.extra", "output.<name>.mode",
                                   "window_rule[].opacity", "workspace[].match"])
        self.assertEqual(stale, ["general.gaps"])

    def test_schema_coverage_stays_fast_on_a_large_schema(self):
        # Every catalog path plus thousands of unknown options: the old pairwise fnmatch scan took seconds here.
        options = [{"path": path.replace("<name>", "*"), "type": "int"} for path, _ in schema.schema_field_catalog()]
        options += [{"path": f"section{i % 40}.group{i}.option", "type": "string"} for i in range(3000)]
        started = time.perf_counter()
        missing, stale = schema.check_schema_coverage({"options": options})
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertEqual((len(missing), stale), (3000, []))


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
