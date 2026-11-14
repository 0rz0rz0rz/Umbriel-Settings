import unittest

from PySide6.QtWidgets import QApplication

from umbriel_config_gui.common import MISSING, tomlkit
from umbriel_config_gui.field_defs import F
from umbriel_config_gui.field_widget import FieldWidget, apply_fields, parse_toml_value


class ParseTomlValueTests(unittest.TestCase):
    def test_accepts_single_values(self):
        self.assertEqual(parse_toml_value("[0.333, 0.5]"), [0.333, 0.5])
        self.assertEqual(parse_toml_value("{ width = 800, height = 600 }"), {"width": 800, "height": 600})
        self.assertEqual(parse_toml_value('"dynamic" # comment'), "dynamic")

    def test_rejects_extra_keys_and_tables(self):
        for text in ("1\nfoo = 2", "[1]\n[extra]\nkey = 1", "1\n[[window_rule]]"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_toml_value(text)

    def test_rejects_invalid_toml(self):
        with self.assertRaises(ValueError):
            parse_toml_value("[1, ")


class RawFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_raw_field_rejects_trailing_keys_instead_of_dropping_them(self):
        field = FieldWidget(F("Position ([x, y])", "position", "raw", [0, 0], None, True), [0, 0])
        self.addCleanup(field.close)
        field.w.setPlainText("[0, 0]\nscale = 2")

        with self.assertRaisesRegex(ValueError, "Position"):
            field.get()

        field.w.setPlainText("[10, 20]")
        self.assertEqual(field.get(), [10, 20])

    def test_scalar_raw_field_uses_a_single_line(self):
        field = FieldWidget(F("Open on workspace", "default_workspace", "raw", 1, None, True), MISSING)
        self.addCleanup(field.close)
        field.check.setChecked(True)
        field.w.setText('"music"')
        self.assertEqual(field.get(), "music")


class TableFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def size_field(self, current):
        field = F("Floating size px", "default_floating_size_px", "table",
                  {"width": 800, "height": 600}, ("width", "height"), True)
        widget = FieldWidget(field, current)
        self.addCleanup(widget.close)
        return widget

    def test_untouched_partial_table_is_not_rewritten(self):
        doc = tomlkit.parse("default_floating_size_px = {width = 1000}\n")
        widget = self.size_field(doc["default_floating_size_px"])
        self.assertEqual([editor.value() for editor in widget.table_editors.values()], [1000, 600])
        apply_fields(doc, [widget])
        self.assertEqual(doc.as_string(), "default_floating_size_px = {width = 1000}\n")

        widget.table_editors["height"].setValue(700)
        apply_fields(doc, [widget])
        self.assertEqual(doc.as_string(), "default_floating_size_px = {width = 1000, height = 700}\n")

    def test_enabling_writes_an_inline_table_and_disabling_removes_it(self):
        doc = tomlkit.document()
        widget = self.size_field(MISSING)
        self.assertIsNone(widget.get())
        widget.check.setChecked(True)
        apply_fields(doc, [widget])
        self.assertEqual(doc.as_string(), "default_floating_size_px = {width = 800, height = 600}\n")
        widget.check.setChecked(False)
        apply_fields(doc, [widget])
        self.assertEqual(doc.as_string(), "")

    def test_array_field_writes_one_value_per_key(self):
        doc = tomlkit.document()
        widget = FieldWidget(F("Position", "position", "table", [0, 0], ("x", "y"), True), MISSING)
        self.addCleanup(widget.close)
        widget.check.setChecked(True)
        widget.table_editors["x"].setValue(1920)
        apply_fields(doc, [widget])
        self.assertEqual(doc.as_string(), "position = [1920, 0]\n")


if __name__ == "__main__":
    unittest.main()
