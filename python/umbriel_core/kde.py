"""Read KDE color schemes (.colors files), such as the one selected in qt6ct."""

import configparser
import os

TITLE_BAR_KEYS = {
    ("colors", "title_bar", "background"): "activeBackground",
    ("colors", "title_bar", "background_unfocused"): "inactiveBackground",
    ("colors", "title_bar", "text"): "activeForeground",
    ("colors", "title_bar", "text_unfocused"): "inactiveForeground",
}

BACKGROUND_KEYS = {
    ("colors", "title_bar", "background"): "Colors:Header",
    ("colors", "title_bar", "background_unfocused"): "Colors:Header][Inactive",
}


def qt6ct_config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "qt6ct", "qt6ct.conf")


def parse_rgb(value):
    """(r, g, b) from a KDE color value "r,g,b" (an alpha part is ignored), or None when it isn't one."""
    parts = value.split(",")
    if len(parts) < 3:
        return None
    try:
        rgb = tuple(int(part.strip()) for part in parts[:3])
    except ValueError:
        return None
    return rgb if all(0 <= component <= 255 for component in rgb) else None


def read_scheme(path):
    """{(section, key): (r, g, b)} for every valid color in a KDE .colors file; {} when it can't be read."""
    parser = configparser.RawConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    try:
        with open(path, encoding="utf-8") as handle:
            parser.read_file(handle)
    except (OSError, UnicodeError, configparser.Error):
        return {}
    colors = {}
    for section in parser.sections():
        for key, value in parser.items(section):
            rgb = parse_rgb(value)
            if rgb is not None:
                colors[(section, key)] = rgb
    return colors


def read_title_bar_rgb(path):
    """Return (title colors, header backgrounds, errors); colors are (r, g, b) tuples keyed by field path."""
    parser = configparser.RawConfigParser(interpolation=None)
    parser.optionxform = str
    with open(path, encoding="utf-8") as handle:
        parser.read_file(handle)

    def read_color(section, key):
        if not parser.has_option(section, key):
            return None
        parts = parser.get(section, key).split(",")
        if len(parts) != 3:
            raise ValueError(f"Invalid [{section}] {key} color")
        try:
            components = [int(part.strip()) for part in parts]
        except ValueError as error:
            raise ValueError(f"Invalid [{section}] {key} color") from error
        if any(component < 0 or component > 255 for component in components):
            raise ValueError(f"Invalid [{section}] {key} color")
        return tuple(components)

    colors, backgrounds, errors = {}, {}, {}
    for kind, entries, output in (
        ("title", ((path, "WM", key) for path, key in TITLE_BAR_KEYS.items()), colors),
        ("background", ((path, section, "BackgroundNormal")
                        for path, section in BACKGROUND_KEYS.items()), backgrounds),
    ):
        for field_path, section, key in entries:
            try:
                color = read_color(section, key)
            except ValueError as error:
                errors[(kind, field_path)] = str(error)
                continue
            if color is not None:
                output[field_path] = color
    if not colors and not backgrounds and not errors:
        raise ValueError("The color scheme has no title-bar or header background colors")
    return colors, backgrounds, errors


def qt6ct_scheme_path(config_path=None):
    """Return the KDE color scheme qt6ct uses; raise ValueError when there is none."""
    config_path = config_path or qt6ct_config_path()
    if not os.path.isfile(config_path):
        raise ValueError("qt6ct configuration not found")
    parser = configparser.RawConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    with open(config_path, encoding="utf-8") as handle:
        parser.read_file(handle)
    if parser.get("Appearance", "custom_palette", fallback="false").strip().lower() != "true":
        raise ValueError("qt6ct custom palette is not enabled")
    scheme = parser.get("Appearance", "color_scheme_path", fallback="").strip().strip('"')
    if not scheme:
        raise ValueError("No qt6ct color scheme is selected")
    scheme = os.path.expanduser(scheme)
    if not os.path.isabs(scheme):
        scheme = os.path.join(os.path.dirname(config_path), scheme)
    return scheme
