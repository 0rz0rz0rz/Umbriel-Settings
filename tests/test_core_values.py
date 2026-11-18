"""Field value conversion, defaults, help coverage and keybind checks in umbriel_core (no Qt)."""

import unittest

import tomlkit

from umbriel_core import fields, keybinds
from umbriel_core.fields import F
from umbriel_core.help import FIELD_HELP, GROUP_HELP, setting_help_text
from umbriel_core.tomlops import getp, parse_toml_value
from umbriel_core.values import apply_value, from_ui, to_ui

SIZE = F("Floating size px", "default_floating_size_px", "table",
         {"width": 800, "height": 600}, ("width", "height"), True)
POSITION = F("Position", "position", "table", [0, 0], ("x", "y"), True)


def write(text, field, ui_value, schema_option=None):
    """Apply one UI value to a parsed document like a save does and return the resulting text."""
    doc = tomlkit.parse(text)
    value = None if ui_value is None else from_ui(field, ui_value, schema_option)
    apply_value(doc, field, value, field.default)
    return doc.as_string()


class ParseTomlValueTests(unittest.TestCase):
    def test_accepts_single_values(self):
        self.assertEqual(parse_toml_value("[0.333, 0.5]"), [0.333, 0.5])
        self.assertEqual(parse_toml_value("{ width = 800, height = 600 }"), {"width": 800, "height": 600})
        self.assertEqual(parse_toml_value('"dynamic" # comment'), "dynamic")

    def test_rejects_extra_keys_tables_and_invalid_toml(self):
        for text in ("1\nfoo = 2", "[1]\n[extra]\nkey = 1", "1\n[[window_rule]]", "[1, "):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_toml_value(text)


class FromUiTests(unittest.TestCase):
    def test_raw_field_rejects_trailing_keys_instead_of_dropping_them(self):
        field = F("Position ([x, y])", "position", "raw", [0, 0], None, True)
        with self.assertRaisesRegex(ValueError, "Position"):
            from_ui(field, "[0, 0]\nscale = 2")
        self.assertEqual(from_ui(field, "[10, 20]"), [10, 20])
        self.assertEqual(from_ui(F("Open on workspace", "default_workspace", "raw", 1, None, True), '"music"'),
                         "music")

    def test_numbers_respect_kind_and_schema_bounds(self):
        width = F("Border width", "border_width", "int", 2)
        self.assertEqual(from_ui(width, 4.0), 4)
        self.assertIsInstance(from_ui(width, 4.0), int)
        for bad in (2.5, True, "3", float("nan")):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                from_ui(width, bad)
        with self.assertRaisesRegex(ValueError, "between 0 and 10"):
            from_ui(width, 11, {"min": 0, "max": 10})
        opacity = F("Opacity", "opacity", "float", 1.0)
        self.assertEqual(from_ui(opacity, -0.5, {"min": -1, "max": 1}), -0.5)
        self.assertEqual(from_ui(opacity, 2.0), 2.0)

    def test_colors_choices_and_lists(self):
        color = F("Color", "color", "color", "#112233")
        self.assertEqual(from_ui(color, " #aabbcc80 "), "#AABBCC80")
        for bad in ("aabbcc", "#abc", "#GGHHII"):
            with self.subTest(color=bad), self.assertRaises(ValueError):
                from_ui(color, bad)
        layout = F("Layout", "layout", "choice", "scrolling", fields.LAYOUTS)
        self.assertEqual(from_ui(layout, "master", {"values": fields.LAYOUTS}), "master")
        with self.assertRaisesRegex(ValueError, "choose one of"):
            from_ui(layout, "tiles", {"values": fields.LAYOUTS})
        # Lua encodes an empty list as an empty table, which arrives as {}.
        self.assertEqual(from_ui(F("Files", "files", "list", []), {}), [])
        self.assertEqual(from_ui(F("Files", "files", "list", []), [" a ", "", "b"]), ["a", "b"])
        self.assertEqual(from_ui(F("Run", "run", "command_list", []), [" a b ", "  "]), [" a b "])

    def test_table_fields_keep_integer_keys_and_fill_defaults(self):
        value = from_ui(SIZE, {"width": 1000.0})
        self.assertEqual(value, {"width": 1000, "height": 600})
        self.assertIsInstance(value["width"], int)
        self.assertEqual(from_ui(POSITION, {"x": 1920}), [1920, 0])
        with self.assertRaises(ValueError):
            from_ui(SIZE, {"width": True})


class ApplyValueTests(unittest.TestCase):
    def test_unchanged_partial_table_is_not_rewritten(self):
        text = "default_floating_size_px = {width = 1000}\n"
        current = to_ui(SIZE, getp(tomlkit.parse(text), SIZE.path))
        self.assertEqual(current, {"width": 1000})
        self.assertEqual(write(text, SIZE, {"width": 1000, "height": 700}),
                         "default_floating_size_px = {width = 1000, height = 700}\n")

    def test_enabling_writes_an_inline_table_and_disabling_removes_it(self):
        self.assertEqual(write("", SIZE, {}), "default_floating_size_px = {width = 800, height = 600}\n")
        self.assertEqual(write("default_floating_size_px = {width = 800, height = 600}\n", SIZE, None), "")
        self.assertEqual(write("", POSITION, {"x": 1920}), "position = [1920, 0]\n")

    def test_non_optional_default_is_not_written_and_comments_survive(self):
        width = F("Border width", "general.border_width", "int", 2)
        self.assertEqual(write("", width, 2), "")
        text = "[general]\n# keep me\nborder_width = 2 # inline\n"
        self.assertEqual(write(text, width, 4), "[general]\n# keep me\nborder_width = 4 # inline\n")


class HelpCoverageTests(unittest.TestCase):
    def test_help_text_includes_field_help(self):
        field = F("Enabled", "general.enabled", "bool", False, None, True)
        self.assertIn(FIELD_HELP["Enabled"], setting_help_text(field, "Session"))

    def test_every_window_rule_match_condition_has_its_own_help(self):
        for field in fields.WINDOW_RULE:
            if field.label.startswith("Match "):
                with self.subTest(label=field.label):
                    self.assertIn(field.label, FIELD_HELP)
                    self.assertNotIn("rules rule", setting_help_text(field, "Match"))

    def test_help_keys_match_existing_labels_and_groups(self):
        """FIELD_HELP is keyed by label, so renaming a field silently orphans its help."""
        labels, groups = set(), set()

        def visit(value):
            if isinstance(value, fields.Field):
                labels.add(value.label)
            elif isinstance(value, (list, tuple)):
                if len(value) == 2 and isinstance(value[0], str) and isinstance(value[1], list):
                    groups.add(value[0])
                for item in value:
                    visit(item)
            elif isinstance(value, dict):
                for item in value.values():
                    visit(item)

        for name, value in vars(fields).items():
            if name.isupper():
                visit(value)
        self.assertEqual(sorted(set(FIELD_HELP) - labels), [])
        self.assertEqual(sorted(set(GROUP_HELP) - groups), [])

    def test_labels_carry_no_bracket_notes(self):
        from umbriel_core.help import split_label
        from umbriel_core.meta import build_meta
        meta = build_meta({})
        self.assertEqual([f["label"] for f in meta["fields"].values() if "(" in f["label"]], [])
        self.assertEqual([g["title"] for page in meta["pages"].values() for g in page.get("groups", [])
                          if "(restart)" in g["title"]], [])
        self.assertEqual(split_label("Hide after inactivity (ms, 0 = never)"),
                         ("Hide after inactivity", {"unit": "ms", "special": {"value": 0, "label": "Never"}}))
        self.assertEqual(split_label("app_id (regex or [array])"),
                         ("App ID", {"hint": "regex or list of regexes"}))
        self.assertEqual(split_label("Buttons (comma separated)"), ("Buttons", {}))
        self.assertTrue(meta["fields"]["general.autostart"]["restart"])

    def test_every_group_has_help_that_fits_its_page(self):
        from umbriel_core.meta import build_meta
        meta = build_meta({})
        missing = [(page, group["title"]) for page, info in meta["pages"].items()
                   for group in info.get("groups", []) if not group["help"]]
        missing += [(editor["page"], group["title"]) for editor in meta["editors"].values()
                    for group in editor["groups"] if not group["help"]]
        self.assertEqual(missing, [])
        input_general = next(g for g in meta["pages"]["Input"]["groups"] if g["title"] == "General")
        self.assertNotIn("color", input_general["help"])


class KeybindCheckTests(unittest.TestCase):
    def test_duplicate_shortcuts_are_rejected_ignoring_case_and_spaces(self):
        keybinds.check_shortcut_conflicts(["Super+Q", "Super+W", "", "  "])
        with self.assertRaisesRegex(ValueError, "duplicates"):
            keybinds.check_shortcut_conflicts(["Super+Q", " super+q "])

    def test_incomplete_actions_are_rejected(self):
        keybinds.check_action("Super+Return", "spawn kitty")
        for action in ("spawn", "spawn <cmd...>", "focus <direction>"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                keybinds.check_action("Super+X", action)


if __name__ == "__main__":
    unittest.main()
