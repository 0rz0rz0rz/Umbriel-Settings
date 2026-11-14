"""Field editor widgets and config write-back."""

from .common import (
    MISSING, QColorDialog, QComboBox, QDoubleSpinBox, QFont, QHBoxLayout, QLineEdit,
    QPlainTextEdit, QPushButton, Signal, QSizePolicy, QSpinBox, QToolButton,
    QVBoxLayout, QWidget, WheelSafeComboBox, delp, getp, hexof, putp, py,
    qcolor, tomlkit, totext,
)
from umbriel_core.cursor_themes import installed_cursor_themes
from umbriel_core.tomlops import parse_toml_value

from .schema import field_schema_option
from .kde_titlebar import TITLE_BAR_KEYS
from .widgets import KdeColorControl, SettingSlider, SwitchCheckBox, TriStateControl


class FieldWidget(QWidget):
    """The editor widget for one Field: a spinbox, checkbox, dropdown, text box or color button, plus an optional 'set' checkbox."""
    valueChanged = Signal()
    # Every row's switch and editor start at the same x; see SettingRow.
    EDITOR_WIDTH = 300
    SWITCH_WIDTH = 34

    def __init__(self, field, current, schema_path=None):
        """Create the right widget for the field kind and fill it with the current config value (or the default if the key is missing)."""
        super().__init__()
        self.f = field
        option_path = schema_path or ".".join(field.path)
        self.schema_option = field_schema_option(option_path)
        self.default = (
            self.schema_option["default"]
            if self.schema_option is not None and "default" in self.schema_option
            else field.default
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addStretch(1)
        k, ex = field.kind, field.extra
        if self.schema_option is not None:
            if "values" in self.schema_option and k in ("choice", "combo"):
                ex = self.schema_option["values"]
            if "min" in self.schema_option and "max" in self.schema_option and k in ("int", "float"):
                ex = (self.schema_option["min"], self.schema_option["max"])
        if field.path == ("input", "cursor", "theme"):
            ex = installed_cursor_themes()
        self.tri = k == "bool" and field.opt
        self.raw_single = k == "raw" and not isinstance(field.default, (list, dict))
        if self.tri:
            self.w = TriStateControl()
            self.w.setFixedWidth(self.EDITOR_WIDTH)
            # Only the schema knows what "unset" means; rule match fields have no default.
            if self.schema_option is not None and isinstance(self.schema_option.get("default"), bool):
                default_text = "on" if self.schema_option["default"] else "off"
                self.w.setLabels((f"default ({default_text})", "on", "off"))
                self.w.setToolTip(f"Choose default ({default_text}), on, or off.")
        elif k == "bool":
            self.w = SwitchCheckBox()
        elif k == "int":
            self.w = QSpinBox()
            self.w.setRange(*(ex or (-100000, 100000)))
        elif k == "float":
            self.w = QDoubleSpinBox()
            lo, hi = ex or (-100000.0, 100000.0)
            self.w.setDecimals(3)
            self.w.setRange(lo, hi)
            self.w.setSingleStep(10.0 if hi - lo > 100 else 0.05)
        elif k in ("choice", "combo"):
            self.w = WheelSafeComboBox()
            self.w.addItems(ex or [])
            self.w.setEditable(k == "combo")
            self.w.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            self.w.setMinimumContentsLength(12)
        elif k == "raw":
            if self.raw_single:
                self.w = QLineEdit()
            else:
                self.w = QPlainTextEdit()
                self.w.setMinimumHeight(72)
                self.w.setMaximumHeight(120)
            raw_font = QFont(self.w.font())
            raw_font.setFamily("monospace")
            self.w.setFont(raw_font)
            try:
                example = totext(self.default)
            except (TypeError, ValueError):
                example = ""
            self.w.setPlaceholderText(
                f"TOML value, for example: {example}" if example else "Enter a TOML value"
            )
        elif k == "table":
            self.w = QWidget()
            self.build_table_editors(option_path)
        elif k == "command_list":
            self.w = QWidget()
            self.command_rows = QVBoxLayout(self.w)
            self.command_rows.setContentsMargins(0, 0, 0, 0)
            self.command_rows.setSpacing(6)
            self.add_command_button = QPushButton("Add command")
            self.add_command_button.clicked.connect(self.add_command)
            self.command_rows.addWidget(self.add_command_button)
        elif k == "color":
            self.w = QPushButton()
            self.w.clicked.connect(self.pick_color)
        else:  # str, strorlist, list, raw
            self.w = QLineEdit()
        self.opacity_slider = None
        self.opacity_spin = None
        self.opacity_widget = None
        self.opacity_check = None
        self.opacity_row = None
        self.kde_color = None
        self.kde_background = None
        self.kde_button = None
        self.kde_source = None
        self.kde_messages = ["", ""]
        if field.path in TITLE_BAR_KEYS and field.path not in (
            ("colors", "title_bar", "background"),
            ("colors", "title_bar", "background_unfocused"),
        ):
            self.kde_button = QPushButton("Use KDE color")
            self.kde_button.setEnabled(False)
            self.kde_button.clicked.connect(self.use_kde_color)
        if field.path in (
            ("colors", "title_bar", "background"),
            ("colors", "title_bar", "background_unfocused"),
        ):
            self.kde_source = KdeColorControl()
            self.kde_source.setAccessibleName(f"{field.label} color source")
            self.kde_source.activated.connect(self.select_kde_source)
            self.opacity_slider = SettingSlider()
            self.opacity_slider.setRange(0, 255)
            self.opacity_slider.setPageStep(26)
            self.opacity_slider.setAccessibleName(f"{field.label} opacity")
            self.opacity_spin = QDoubleSpinBox()
            self.opacity_spin.setRange(0.0, 1.0)
            self.opacity_spin.setDecimals(3)
            self.opacity_spin.setSingleStep(0.01)
            self.opacity_spin.setFixedWidth(80)
            self.opacity_spin.setAccessibleName(f"{field.label} opacity")
            self.opacity_slider.valueChanged.connect(self.set_opacity_from_slider)
            self.opacity_spin.valueChanged.connect(self.set_opacity)
        if not self.tri:
            self.w.setMinimumWidth(0)
        self.slider = None
        if k in ("int", "float"):
            self.w.setFixedWidth(105)
            # Slider fills what the spin box leaves of the editor column.
            if ex is not None:
                scale = 1 if k == "int" else 1000
                slider_min = round(self.w.minimum() * scale)
                slider_max = round(self.w.maximum() * scale)
                if (-2147483648 <= slider_min <= slider_max <= 2147483647
                        and slider_max - slider_min <= 2147483647):
                    self.slider = SettingSlider()
                    self.slider.setMaximumWidth(16777215)
                    self.slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                    self.slider.setRange(slider_min, slider_max)
                    self.slider.setPageStep(max(1, (slider_max - slider_min) // 10))
                    self.slider.setAccessibleName(field.label)
                    self.slider.valueChanged.connect(
                        lambda value: self.w.setValue(value / scale if k == "float" else value)
                    )

                    def sync_slider(value):
                        self.slider.blockSignals(True)
                        self.slider.setValue(round(value * scale))
                        self.slider.blockSignals(False)

                    self.w.valueChanged.connect(sync_slider)
        elif k in ("choice", "combo"):
            self.w.setMinimumWidth(120)
            self.w.setMaximumWidth(360)
            self.w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.w.view().setMinimumWidth(240)
        elif k == "color":
            self.w.setMinimumWidth(90)
            self.w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        elif k == "list":
            self.w.setMinimumWidth(420)
            self.w.setMaximumWidth(16777215)
            self.w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        elif k not in ("bool", "command_list", "table"):
            self.w.setMaximumWidth(460)
            self.w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.check = None
        if field.opt and not self.tri:
            self.check = SwitchCheckBox()
            self.check.setToolTip("Tick to write this setting to your config. Unticked = Umbriel's built-in default.")
            if self.kde_button is not None or self.kde_source is not None:
                self.check.setToolTip(
                    "Tick to write this color. When unticked, the KDE color is a preview only; "
                    "Umbriel uses its default or an included config."
                )
                self.check.toggled.connect(self.update_kde_preview)
            if self.kde_source is not None:
                self.check.toggled.connect(self.sync_kde_source)
            self.check.toggled.connect(self.w.setEnabled)
            if self.slider is not None:
                self.check.toggled.connect(self.slider.setEnabled)
            if self.opacity_slider is not None:
                self.check.toggled.connect(self.opacity_slider.setEnabled)
                self.check.toggled.connect(self.opacity_spin.setEnabled)
            self.check.setFixedWidth(self.SWITCH_WIDTH)
            lay.addWidget(self.check)
        else:
            lay.addWidget(self.switch_placeholder())
        self.editor_column = QWidget()
        column = QHBoxLayout(self.editor_column)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        expands = self.w.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
        if self.slider is not None:
            column.addWidget(self.slider, 1)
            expands = True
        if self.opacity_slider is not None:
            column.addWidget(self.kde_source)
            column.addWidget(self.w, 1)
            self.opacity_widget = QWidget()
            opacity_layout = QHBoxLayout(self.opacity_widget)
            opacity_layout.setContentsMargins(0, 0, 0, 0)
            opacity_layout.setSpacing(8)
            if self.check is not None:
                self.opacity_check = SwitchCheckBox()
                self.opacity_check.setFixedWidth(self.SWITCH_WIDTH)
                self.opacity_check.setToolTip("Tick to write this color's opacity. Same switch as the color above.")
                self.check.toggled.connect(self.opacity_check.setChecked)
                self.opacity_check.toggled.connect(self.check.setChecked)
                opacity_layout.addWidget(self.opacity_check)
            else:
                opacity_layout.addWidget(self.switch_placeholder())
            self.opacity_slider.setMaximumWidth(16777215)
            self.opacity_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            opacity_layout.addWidget(self.opacity_slider, 1)
            opacity_layout.addWidget(self.opacity_spin)
            self.opacity_help = QToolButton()
            self.opacity_help.setText("?")
            self.opacity_help.setAutoRaise(True)
            self.opacity_help.setFixedSize(20, 20)
            self.opacity_help.setAccessibleName(f"Help for {field.label} opacity")
            opacity_layout.addWidget(self.opacity_help)
        else:
            if self.kde_button is not None:
                column.addWidget(self.kde_button)
            column.addWidget(self.w, 1 if expands else 0)
        if not expands:
            column.addStretch(1)
        self.editor_column.setMinimumWidth(self.EDITOR_WIDTH)
        if column.minimumSize().width() <= self.EDITOR_WIDTH:
            self.editor_column.setMaximumWidth(self.EDITOR_WIDTH)
        self.editor_column.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        lay.addWidget(self.editor_column)
        self.help_button = QToolButton()
        self.help_button.setText("?")
        self.help_button.setAutoRaise(True)
        self.help_button.setFixedSize(20, 20)
        self.help_button.setAccessibleName(f"Help for {field.label}")
        self.help_button.setToolTip("Setting description")
        lay.addWidget(self.help_button)
        if self.tri:
            self.w.setAccessibleName(field.label)
            self.w.setCurrentIndex(0 if current is MISSING else (1 if py(current) else 2))
            self.w.valueChanged.connect(self.valueChanged)
            return
        if current is MISSING:
            self.set_value(self.default)
            if self.check:
                self.check.setChecked(False)
                self.w.setEnabled(False)
                if self.slider is not None:
                    self.slider.setEnabled(False)
                if self.opacity_slider is not None:
                    self.opacity_slider.setEnabled(False)
                    self.opacity_spin.setEnabled(False)
        else:
            self.set_value(py(current) if k not in ("raw", "strorlist", "table") else current)
            if self.check:
                self.check.setChecked(True)
        if self.slider is not None:
            self.slider.blockSignals(True)
            self.slider.setValue(round(self.w.value() * scale))
            self.slider.blockSignals(False)
        if k == "raw":
            self.w.textChanged.connect(self.update_raw_feedback)
            self.update_raw_feedback()
        if self.check is not None:
            self.check.toggled.connect(self.valueChanged)
        if k == "bool":
            self.w.toggled.connect(self.valueChanged)
        elif k in ("int", "float"):
            self.w.valueChanged.connect(self.valueChanged)
        elif k in ("choice", "combo"):
            self.w.currentTextChanged.connect(self.valueChanged)
        elif k == "raw":
            self.w.textChanged.connect(self.valueChanged)
        elif k not in ("color", "command_list", "table"):
            self.w.textChanged.connect(self.valueChanged)

    def switch_placeholder(self):
        """Reserve the switch slot (a spacer item would skip the layout spacing)."""
        placeholder = QWidget()
        placeholder.setFixedSize(self.SWITCH_WIDTH, 1)
        return placeholder

    def build_table_editors(self, option_path):
        """Edit a small table or [x, y] array with one compact control per key instead of raw TOML."""
        layout = QHBoxLayout(self.w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.table_is_list = isinstance(self.f.default, list)
        self.table_editors = {}
        self.table_shown = None
        self.table_source = None
        for index, key in enumerate(self.f.extra):
            sample = self.f.default[index] if self.table_is_list else self.f.default.get(key)
            if self.table_is_list:
                option = self.schema_option or {}
            else:
                option = field_schema_option(f"{option_path}.{key}") or {}
            values = option.get("values")
            if values or isinstance(sample, str):
                editor = WheelSafeComboBox()
                editor.addItems([str(value) for value in values] if values else [str(sample)])
                editor.setEditable(not values)
                editor.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                editor.setMinimumContentsLength(6)
                editor.currentTextChanged.connect(self.valueChanged)
            else:
                is_float = isinstance(sample, float) or option.get("type") == "float"
                editor = QDoubleSpinBox() if is_float else QSpinBox()
                low = option.get("min", -100000)
                high = option.get("max", 100000)
                if is_float:
                    editor.setDecimals(3)
                    editor.setSingleStep(0.05 if high - low <= 10 else 10.0)
                editor.setRange(low, high)
                editor.setPrefix(f"{key[:1].upper()} ")
                editor.valueChanged.connect(self.valueChanged)
            editor.setMinimumWidth(48)  # 0 would fall back to the range-based size hint
            editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            editor.setToolTip(key)
            editor.setAccessibleName(f"{self.f.label} {key}")
            layout.addWidget(editor, 1)
            self.table_editors[key] = editor
        self.w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def table_values(self):
        values = []
        for editor in self.table_editors.values():
            values.append(editor.currentText() if isinstance(editor, QComboBox) else editor.value())
        return values

    def set_table_value(self, value):
        """Show a table/array value; keys it lacks show the field default."""
        plain = py(value) if value not in (None, "") else None
        for index, (key, editor) in enumerate(self.table_editors.items()):
            if self.table_is_list:
                item = plain[index] if isinstance(plain, list) and index < len(plain) else self.f.default[index]
            else:
                item = plain.get(key, self.f.default.get(key)) if isinstance(plain, dict) else self.f.default.get(key)
            editor.blockSignals(True)
            if isinstance(editor, QComboBox):
                if editor.findText(str(item)) < 0:
                    editor.addItem(str(item))
                editor.setCurrentText(str(item))
            else:
                try:
                    editor.setValue(item)
                except TypeError:
                    pass
            editor.blockSignals(False)
        self.table_shown = self.table_values()
        # Only a value read from the config is kept verbatim; defaults are rebuilt as inline tables.
        self.table_source = value if isinstance(value, tomlkit.items.Item) else None

    def get_table_value(self):
        """Return the original value while untouched so partial tables are not rewritten."""
        values = self.table_values()
        if values == self.table_shown and self.table_source is not None:
            return self.table_source
        if self.table_is_list:
            result = tomlkit.array()
            result.extend(values)
            return result
        result = tomlkit.inline_table()
        for key, value in zip(self.table_editors, values):
            result[key] = value
        return result

    def raw_text(self):
        return (self.w.text() if self.raw_single else self.w.toPlainText()).strip()

    def is_overridden(self):
        """Compare the editable value with its schema or field default."""
        try:
            value = self.get()
        except ValueError:
            return True
        if value is None:
            return False
        if self.f.kind == "color" and self.default is not None:
            try:
                value_color = qcolor(value)
                default_color = qcolor(self.default)
                return value_color != default_color
            except (TypeError, ValueError):
                return py(value) != py(self.default)
        return py(value) != py(self.default)

    def pick_color(self):
        """Open the color dialog (with alpha) and apply the chosen color."""
        c = QColorDialog.getColor(qcolor(self.w.text()), self, "Pick color",
                                  QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if c.isValid():
            self.set_color(hexof(c))
            if self.kde_source is not None:
                self.kde_source.setCurrentIndex(-1)

    def set_color(self, h):
        """Show a color on the button: background in the chosen color, text black or white for readability."""
        self.w.setText(h)
        foreground = '#000' if qcolor(h).lightness() > 128 else '#fff'
        self.w.setStyleSheet(
            f"QPushButton {{ background: {h[:7]}; color: {foreground}; }}"
            "QPushButton:disabled { border: 1px dashed palette(placeholder-text); }"
        )
        if self.opacity_slider is not None:
            alpha = qcolor(h).alpha()
            self.opacity_slider.blockSignals(True)
            self.opacity_slider.setValue(alpha)
            self.opacity_slider.blockSignals(False)
            self.opacity_spin.blockSignals(True)
            self.opacity_spin.setValue(alpha / 255)
            self.opacity_spin.blockSignals(False)
        self.valueChanged.emit()

    def set_opacity(self, value):
        color = qcolor(self.w.text())
        color.setAlpha(round(value * 255))
        self.set_color(hexof(color))

    def set_opacity_from_slider(self, value):
        self.opacity_spin.setValue(value / 255)

    def set_kde_color(self, color, message):
        self.kde_color = color
        if self.kde_source is not None:
            self.kde_source.setSegmentAvailable(1, color is not None)
            self.kde_messages[0] = f"KDE TB: {message}"
            self.update_kde_source_tooltip()
        else:
            self.kde_button.setEnabled(color is not None)
            self.kde_button.setToolTip(
                message if color is not None else message + "; this field was not changed."
            )
        if color is not None and self.check and not self.check.isChecked():
            self.preview_kde_color()

    def preview_kde_color(self):
        color = qcolor(hexof(self.kde_color))
        color.setAlpha(qcolor(self.w.text()).alpha())
        self.set_color(hexof(color))

    def use_kde_color(self):
        if self.kde_color is not None:
            self.preview_kde_color()
            if self.check:
                self.check.setChecked(True)

    def set_kde_background(self, color, message):
        self.kde_background = color
        self.kde_source.setSegmentAvailable(2, color is not None)
        self.kde_messages[1] = f"KDE BG: {message}"
        self.update_kde_source_tooltip()

    def use_kde_background(self):
        if self.kde_background is not None:
            color = qcolor(hexof(self.kde_background))
            color.setAlpha(qcolor(self.w.text()).alpha())
            self.set_color(hexof(color))
            if self.check:
                self.check.setChecked(True)

    def update_kde_preview(self, checked):
        if not checked and self.kde_color is not None:
            self.preview_kde_color()

    def update_kde_source_tooltip(self):
        self.kde_source.setToolTip(
            "Default unsets the override. KDE TB and KDE BG import colors; "
            "no selected segment means a custom override.\n" + "\n".join(self.kde_messages)
        )

    def sync_kde_source(self, checked):
        if not checked:
            self.kde_source.setCurrentIndex(0)
        elif self.kde_source.currentIndex() == 0:
            self.kde_source.setCurrentIndex(-1)

    def select_kde_source(self, index):
        if index == 0:
            if self.check:
                self.check.setChecked(False)
        elif index == 1:
            self.use_kde_color()
        elif index == 2:
            self.use_kde_background()

    def set_value(self, v):
        """Put a value into the widget, converting it to whatever the widget type needs."""
        k = self.f.kind
        if self.tri:
            self.w.setCurrentIndex(0 if v is None else (1 if bool(v) else 2))
            return
        if v is None:
            v = {"bool": False, "int": 0, "float": 0.0, "color": "#000000FF"}.get(k, "")
        if k == "bool":
            self.w.setChecked(bool(v))
        elif k == "int":
            self.w.setValue(int(v))
        elif k == "float":
            self.w.setValue(float(v))
        elif k in ("choice", "combo"):
            if self.w.findText(str(v)) < 0:
                self.w.addItem(str(v))
            self.w.setCurrentText(str(v))
        elif k == "color":
            self.set_color(str(v))
        elif k == "list":
            self.w.setText(", ".join(str(x) for x in v))
        elif k == "command_list":
            while self.command_rows.count() > 1:
                item = self.command_rows.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)
                    item.widget().deleteLater()
            for command in v:
                self.add_command_row(str(command))
        elif k == "table":
            self.set_table_value(v)
        elif k == "raw":
            text = totext(v) if v != "" else ""
            if self.raw_single:
                self.w.setText(text)
            else:
                self.w.setPlainText(text)
        elif k == "strorlist":
            self.w.setText(totext(v) if not isinstance(py(v), str) else str(py(v)))
        else:
            self.w.setText(str(v))

    def get(self):
        """Read the widget back as a TOML-ready value. Returns None when the field is optional and 'set' is unchecked, and raises ValueError on invalid raw TOML."""
        if self.tri:
            i = self.w.currentIndex()
            return None if i == 0 else i == 1
        if self.check and not self.check.isChecked():
            return None
        k = self.f.kind
        if k == "bool":
            return self.w.isChecked()
        if k in ("int", "float"):
            return self.w.value()
        if k in ("choice", "combo"):
            return self.w.currentText()
        if k == "color":
            return self.w.text()
        if k == "list":
            return [s.strip() for s in self.w.text().split(",") if s.strip()]
        if k == "command_list":
            return [
                command.text()
                for command in self.w.findChildren(QLineEdit)
                if command.text().strip()
            ]
        if k == "table":
            return self.get_table_value()
        t = self.raw_text() if k == "raw" else self.w.text().strip()
        if k == "raw" or (k == "strorlist" and t.startswith("[")):
            try:
                return parse_toml_value(t)
            except ValueError as e:
                raise ValueError(f"{self.f.label}: invalid TOML value ({e})") from e
        return t if k == "strorlist" else self.w.text()

    def update_raw_feedback(self):
        """Mark malformed TOML values as the user edits them."""
        text = self.raw_text()
        if not text:
            self.w.setStyleSheet("")
            self.w.setToolTip("Enter a TOML value, for example: [0.333, 0.5, 0.667]")
            return
        try:
            parse_toml_value(text)
        except ValueError as error:
            self.w.setStyleSheet("border: 1px solid #d55;")
            self.w.setToolTip(f"Invalid TOML value: {error}")
        else:
            self.w.setStyleSheet("")
            self.w.setToolTip("Valid TOML value.")

    def add_command_row(self, command=""):
        """Add a case-preserving command entry to the autostart list."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        entry = QLineEdit(command)
        entry.textChanged.connect(self.valueChanged)
        entry.setMinimumWidth(420)
        layout.addWidget(entry, 1)
        remove_button = QPushButton("Remove")
        remove_button.clicked.connect(lambda: self.remove_command_row(row))
        layout.addWidget(remove_button)
        self.command_rows.insertWidget(self.command_rows.count() - 1, row)
        self.valueChanged.emit()

    def add_command(self):
        """Add a blank command entry to the autostart list."""
        self.add_command_row()

    def remove_command_row(self, row):
        """Remove a command entry from the autostart list."""
        self.command_rows.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self.valueChanged.emit()


def apply_fields(c, fws):
    """Write the widget values into `c` (the config or one rule entry). Only changed keys are written; unchecked optional fields are removed."""
    for fw in fws:
        v, p = fw.get(), fw.f.path
        cur = getp(c, p)
        if v is None:
            if cur is not MISSING:
                delp(c, p)
        elif cur is MISSING:
            if fw.f.opt or py(v) != py(fw.default):
                putp(c, p, v)
        elif py(cur) != py(v):
            putp(c, p, v)
