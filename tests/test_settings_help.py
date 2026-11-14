import unittest

from umbriel_config_gui import settings
from umbriel_config_gui.field_defs import F
from umbriel_config_gui.field_widget import FieldWidget
from umbriel_config_gui.setting_help import FIELD_HELP, setting_description
from umbriel_config_gui.settings_layout import form_page


class SettingsHelpTests(unittest.TestCase):
    def test_description_includes_field_help_and_context(self):
        field = F("Enabled", "general.enabled", "bool", False, None, True)

        description = setting_description(field, "General", "Session")

        self.assertIn(FIELD_HELP["Enabled"], description)
        self.assertIn("Applies to: General > Session", description)
        self.assertIn("Config key: general.enabled", description)

    def test_every_window_rule_match_condition_has_its_own_help(self):
        from umbriel_config_gui.field_defs import WINDOW_RULE

        for field in WINDOW_RULE:
            if field.label.startswith("Match "):
                with self.subTest(label=field.label):
                    self.assertIn(field.label, FIELD_HELP)
                    self.assertNotIn("rules rule", setting_description(field, "Window rules", "Match"))

    def test_help_keys_match_existing_labels_and_groups(self):
        """FIELD_HELP is keyed by label, so renaming a field silently orphans its help."""
        from umbriel_config_gui import field_defs
        from umbriel_config_gui.setting_help import GROUP_HELP

        labels, groups = set(), set()

        def visit(value):
            if hasattr(value, "label") and hasattr(value, "path"):
                labels.add(value.label)
            elif isinstance(value, (list, tuple)):
                if len(value) == 2 and isinstance(value[0], str) and isinstance(value[1], list):
                    groups.add(value[0])
                for item in value:
                    visit(item)
            elif isinstance(value, dict):
                for item in value.values():
                    visit(item)

        for name, value in vars(field_defs).items():
            if name.isupper():
                visit(value)
        self.assertEqual(sorted(set(FIELD_HELP) - labels), [])
        self.assertEqual(sorted(set(GROUP_HELP) - groups), [])

    def test_settings_facade_reexports_moved_components(self):
        self.assertIs(settings.FieldWidget, FieldWidget)
        self.assertIs(settings.form_page, form_page)


if __name__ == "__main__":
    unittest.main()
