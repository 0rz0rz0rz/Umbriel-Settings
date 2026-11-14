import unittest

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QEnterEvent, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from unittest.mock import patch

from umbriel_config_gui import state
from umbriel_config_gui.common import MISSING
from umbriel_config_gui.field_defs import F
from umbriel_config_gui.field_widget import FieldWidget
from umbriel_config_gui.widgets import KdeColorControl, SettingRow, SwitchCheckBox, TriStateControl


class SettingsSwitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_clicks_across_switch_toggle_in_both_directions(self):
        switch = SwitchCheckBox()
        switch.resize(switch.sizeHint())
        switch.show()
        self.addCleanup(switch.close)
        self.app.processEvents()

        for x in (4, 10, 17, 25, 30):
            with self.subTest(x=x):
                switch.setChecked(False)
                QTest.mouseClick(switch, Qt.MouseButton.LeftButton, pos=QPoint(x, 11))
                self.assertTrue(switch.isChecked())
                QTest.mouseClick(switch, Qt.MouseButton.LeftButton, pos=QPoint(x, 11))
                self.assertFalse(switch.isChecked())

    def test_release_outside_and_disabled_switch_do_not_toggle(self):
        switch = SwitchCheckBox()
        switch.resize(switch.sizeHint())
        switch.show()
        self.addCleanup(switch.close)
        self.app.processEvents()

        QTest.mousePress(switch, Qt.MouseButton.LeftButton, pos=QPoint(30, 11))
        QTest.mouseRelease(switch, Qt.MouseButton.LeftButton, pos=QPoint(35, 11))
        self.assertFalse(switch.isChecked())
        switch.setEnabled(False)
        QTest.mouseClick(switch, Qt.MouseButton.LeftButton, pos=QPoint(30, 11))
        self.assertFalse(switch.isChecked())

    def test_optional_field_switch_enables_and_disables_editor(self):
        widget = FieldWidget(F("Value", "value", "int", 1, None, True), MISSING)
        widget.show()
        self.addCleanup(widget.close)
        self.app.processEvents()

        switch = widget.check
        self.assertFalse(widget.w.isEnabled())
        QTest.mouseClick(switch, Qt.MouseButton.LeftButton, pos=QPoint(30, 11))
        self.assertTrue(widget.w.isEnabled())
        QTest.keyClick(switch, Qt.Key.Key_Space)
        self.assertFalse(widget.w.isEnabled())

    def test_selected_segments_round_only_the_outer_corners(self):
        for control_type in (TriStateControl, KdeColorControl):
            control = control_type()
            palette = QPalette(control.palette())
            palette.setColor(QPalette.ColorRole.Button, QColor("#202020"))
            palette.setColor(QPalette.ColorRole.Highlight, QColor("#00ff00"))
            control.setPalette(palette)
            control.show()
            self.addCleanup(control.close)
            self.app.processEvents()

            for index in range(3):
                with self.subTest(control=control_type.__name__, index=index):
                    control.setCurrentIndex(index)
                    image = control.grab().toImage()
                    segment = (control.width() - 6) // 3
                    left = 3 + segment * index
                    for y in (4, control.height() - 6):
                        self.assertEqual(image.pixelColor(left + segment // 2, y).name(), "#00ff00")
                        for offset, rounded in ((1, index == 0), (segment - 2, index == 2)):
                            color = image.pixelColor(left + offset, y).name()
                            if rounded:
                                self.assertNotEqual(color, "#00ff00")
                            else:
                                self.assertEqual(color, "#00ff00")
                    for x in (left - 3, left + segment + 2):
                        if 0 <= x < image.width():
                            self.assertNotEqual(image.pixelColor(x, control.height() // 2).name(), "#00ff00")

    def test_tri_state_names_the_schema_default_and_hit_tests_wider_segments(self):
        options = {"effects.in_capture": {"path": "effects.in_capture", "type": "bool", "default": False}}
        with patch.object(state, "ACTIVE_SCHEMA_OPTIONS", options):
            field = FieldWidget(F("Capture", "effects.in_capture", "bool", True, None, True), MISSING)
            rule = FieldWidget(F("Match focused", "match.is_focused", "bool", True, None, True), MISSING)
        self.addCleanup(field.close)
        self.addCleanup(rule.close)
        control = field.w
        self.assertEqual(control.labels, ("default (off)", "on", "off"))
        self.assertEqual(rule.w.labels, ("default", "on", "off"))
        edges = control.segmentEdges()
        self.assertGreater(edges[1] - edges[0], edges[2] - edges[1])
        for index in range(3):
            middle = round((edges[index] + edges[index + 1]) / 2)
            QTest.mouseClick(control, Qt.MouseButton.LeftButton, pos=QPoint(middle, 16))
            self.assertEqual(control.currentIndex(), index)

    def test_switches_and_editors_line_up_across_field_kinds(self):
        fields = [
            F("Tri", "a", "bool", False, None, True),
            F("Text", "b", "str", "", None, True),
            F("Number", "c", "int", 0, (0, 10), True),
            F("Choice", "d", "choice", "x", ["x", "a much longer option value"], True),
            F("Plain", "e", "bool", False),
        ]
        widgets = [FieldWidget(field, MISSING) for field in fields]
        for widget in widgets:
            self.addCleanup(widget.close)
            widget.adjustSize()
        edges = {
            (widget.editor_column.x(), widget.width() - widget.editor_column.geometry().right())
            for widget in widgets
        }
        self.assertEqual(len(edges), 1)
        self.assertEqual({widget.editor_column.width() for widget in widgets}, {FieldWidget.EDITOR_WIDTH})

    def test_every_field_uses_the_shared_editor_column(self):
        from umbriel_config_gui import field_widget
        from umbriel_config_gui.field_defs import OUTPUT_GROUPS, TABS, WINDOW_RULE_GROUPS

        wide = []
        with (
            patch.object(state, "ACTIVE_SCHEMA_OPTIONS", {}),
            patch.object(field_widget, "installed_cursor_themes", return_value=[]),
        ):
            for groups in (*TABS.values(), WINDOW_RULE_GROUPS, OUTPUT_GROUPS):
                for _title, fields in groups:
                    for field in fields:
                        widget = FieldWidget(field, MISSING)
                        widget.show()
                        self.app.processEvents()
                        if widget.editor_column.width() != FieldWidget.EDITOR_WIDTH:
                            wide.append((field.label, field.kind))
                        widget.close()
                        widget.deleteLater()
        # Comma-separated lists and command lists may be wider; everything else must line up.
        self.assertEqual([item for item in wide if item[1] not in ("list", "command_list")], [])

    def test_setting_row_highlights_while_hovered(self):
        row = SettingRow(QLabel("Label"), QLabel("Editor"))
        palette = row.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#000000"))
        palette.setColor(QPalette.ColorRole.Midlight, QColor("#00ff00"))
        row.setPalette(palette)
        row.setAutoFillBackground(True)
        row.resize(300, 40)
        row.show()
        self.addCleanup(row.close)
        self.app.processEvents()

        def center():
            return row.grab().toImage().pixelColor(150, 20).name()

        self.app.sendEvent(row, QEvent(QEvent.Type.Leave))
        self.assertEqual(center(), "#000000")
        point = QPointF(150, 20)
        self.app.sendEvent(row, QEnterEvent(point, point, point))
        self.assertEqual(center(), "#00ff00")
        self.app.sendEvent(row, QEvent(QEvent.Type.Leave))
        self.assertEqual(center(), "#000000")


if __name__ == "__main__":
    unittest.main()
