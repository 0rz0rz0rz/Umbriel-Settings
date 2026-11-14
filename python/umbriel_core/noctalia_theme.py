"""Follow the Noctalia shell's colors, font and corner radius in the standalone app (Qt-free).

Sources, first available wins:
1. A palette file written by a Noctalia user template (exact Material roles, see PALETTE_TEMPLATE).
2. The KDE color scheme Noctalia writes for qt6ct (roles mapped from its sections).
3. Nothing: the host falls back to the Qt palette.
"""

import configparser
import os
import re
import stat
import tomllib
from pathlib import Path

from .paths import DATA_DIR_NAME, LEGACY_DIR_NAME
from .xdg_dirs import atomic_write

ROLES = (
    "primary", "on_primary", "primary_container", "on_primary_container", "secondary", "on_secondary",
    "secondary_container", "tertiary", "on_tertiary", "error", "on_error", "surface", "on_surface",
    "on_surface_variant", "surface_container_lowest", "surface_container_low", "surface_container",
    "surface_container_high", "surface_container_highest", "outline", "outline_variant", "hover", "on_hover",
)

# Noctalia template (TemplateEngine syntax) that writes every color role as name=#rrggbb.
PALETTE_TEMPLATE = """\
# Written by Noctalia for Umbriel Settings; regenerated on every theme change.
<* for name, value in colors *>
{{ name }}={{ value.default.hex }}
<* endfor *>
"""


ROLE_NAME = re.compile(r"[a-z][a-z0-9_]*")  # role names become CSS custom properties


def config_home():
    return os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")


def palette_file():
    """Where Noctalia writes the palette; templates set up before the rename still write to the old directory."""
    path = os.path.join(config_home(), DATA_DIR_NAME, "noctalia-palette.conf")
    legacy = os.path.join(config_home(), LEGACY_DIR_NAME, "noctalia-palette.conf")
    return legacy if not os.path.exists(path) and os.path.exists(legacy) else path


def template_file():
    return os.path.join(config_home(), "noctalia", "templates", "umbriel-settings-palette.conf")


def noctalia_config_file():
    return os.path.join(config_home(), "noctalia", "noctalia-config.toml")


def _hex(value):
    value = value.strip().strip('"')
    if value.startswith("#") and len(value) in (7, 9):
        try:
            int(value[1:], 16)
        except ValueError:
            return None
        return value[:7].lower()
    return None


def parse_palette(text):
    """Parse name=#rrggbb lines into {role: '#rrggbb'}."""
    roles = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, color = name.strip(), _hex(value)
        if color and ROLE_NAME.fullmatch(name):
            roles[name] = color
    return roles


def _rgb(text):
    parts = [part.strip() for part in text.split(",")[:3]]
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return "#" + "".join(f"{min(255, int(part)):02x}" for part in parts)


# KDE scheme (section, key) → role. Missing roles are derived later by fill_roles.
KDE_ROLES = {
    "surface": ("Colors:Window", "BackgroundNormal"),
    "on_surface": ("Colors:Window", "ForegroundNormal"),
    "on_surface_variant": ("Colors:Window", "ForegroundInactive"),
    "surface_container_low": ("Colors:View", "BackgroundNormal"),
    "surface_container": ("Colors:Button", "BackgroundNormal"),
    "surface_container_high": ("Colors:Header", "BackgroundNormal"),
    "primary": ("Colors:Selection", "BackgroundNormal"),
    "on_primary": ("Colors:Selection", "ForegroundNormal"),
    "secondary": ("Colors:View", "ForegroundLink"),
    "tertiary": ("Colors:View", "ForegroundPositive"),
    "error": ("Colors:View", "ForegroundNegative"),
}


def palette_from_kde_scheme(path):
    parser = configparser.RawConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    try:
        with open(path, encoding="utf-8") as handle:
            parser.read_file(handle)
    except (OSError, UnicodeError, configparser.Error):
        return {}
    roles = {}
    for role, (section, key) in KDE_ROLES.items():
        if parser.has_option(section, key):
            color = _rgb(parser.get(section, key))
            if color:
                roles[role] = color
    return roles


def qt6ct_scheme(config_dir=None):
    path = os.path.join(config_dir or config_home(), "qt6ct", "qt6ct.conf")
    parser = configparser.RawConfigParser(strict=False, interpolation=None)
    try:
        with open(path, encoding="utf-8") as handle:
            parser.read_file(handle)
    except (OSError, UnicodeError, configparser.Error):
        return None
    scheme = parser.get("Appearance", "color_scheme_path", fallback="").strip().strip('"')
    if not scheme:
        return None
    scheme = os.path.expanduser(scheme)
    return scheme if os.path.isabs(scheme) else os.path.join(os.path.dirname(path), scheme)


def mix(a, b, amount):
    """Blend two #rrggbb colors; amount 0 keeps a, 1 gives b."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(ca, cb, strict=True))


def fill_roles(roles):
    """Derive missing roles from the ones a source provided, like a Material palette would."""
    r = dict(roles)
    r.setdefault("surface", "#1d1b20")
    r.setdefault("on_surface", "#e6e0e9")
    r.setdefault("primary", "#d0bcff")
    surface, text, primary = r["surface"], r["on_surface"], r["primary"]
    r.setdefault("on_surface_variant", mix(text, surface, 0.3))
    r.setdefault("surface_container_lowest", mix(surface, "#000000", 0.25))
    r.setdefault("surface_container_low", mix(surface, text, 0.04))
    r.setdefault("surface_container", mix(surface, text, 0.08))
    r.setdefault("surface_container_high", mix(surface, text, 0.12))
    r.setdefault("surface_container_highest", mix(surface, text, 0.17))
    r.setdefault("on_primary", surface)
    r.setdefault("primary_container", mix(surface, primary, 0.3))
    r.setdefault("on_primary_container", text)
    r.setdefault("secondary", mix(primary, text, 0.3))
    r.setdefault("on_secondary", surface)
    r.setdefault("secondary_container", mix(surface, r["secondary"], 0.3))
    r.setdefault("tertiary", mix(primary, "#7fd1ae", 0.5))
    r.setdefault("on_tertiary", surface)
    r.setdefault("error", "#f2b8b5")
    r.setdefault("on_error", surface)
    r.setdefault("outline", mix(text, surface, 0.5))
    r.setdefault("outline_variant", mix(text, surface, 0.75))
    r.setdefault("hover", r["tertiary"])
    r.setdefault("on_hover", r["on_tertiary"])
    return r


def load_roles(fallback=None):
    """Return (roles, source) from the palette file, the qt6ct KDE scheme or `fallback` (a dict)."""
    try:
        with open(palette_file(), encoding="utf-8") as handle:
            roles = parse_palette(handle.read())
        if "primary" in roles and "surface" in roles:
            return fill_roles(roles), "noctalia"
    except (OSError, UnicodeError):
        pass
    scheme = qt6ct_scheme()
    if scheme:
        roles = palette_from_kde_scheme(scheme)
        if "surface" in roles:
            return fill_roles(roles), "qt6ct"
    return fill_roles(fallback or {}), "qt"


def shell_style(path=None):
    """Font family and corner radius scale from Noctalia's [shell] settings (defaults when absent)."""
    try:
        with open(path or noctalia_config_file(), "rb") as handle:
            shell = tomllib.load(handle).get("shell", {})
    except (OSError, tomllib.TOMLDecodeError):
        shell = {}
    family = shell.get("font_family") if isinstance(shell.get("font_family"), str) else None
    scale = shell.get("corner_radius_scale")
    scale = float(scale) if isinstance(scale, (int, float)) and 0 <= scale <= 4 else 1.0
    return {"font_family": family, "radius_scale": scale}


def _css_string(text):
    """Quote text as a CSS string; control characters are dropped."""
    text = "".join(char for char in text if char.isprintable())
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def css_variables(roles, style):
    """CSS custom properties for the web renderer: --<role>, --font, --radius-scale."""
    lines = [f"--{name}: {color};" for name, color in sorted(roles.items()) if ROLE_NAME.fullmatch(name)]
    family = style.get("font_family")
    fonts = (f"{_css_string(family)}, " if family else "") + "system-ui, sans-serif"
    lines.append(f"--font: {fonts};")
    lines.append(f"--radius-scale: {style.get('radius_scale', 1.0)};")
    return ":root {\n  " + "\n  ".join(lines) + "\n}\n"


TEMPLATE_KEY = "umbriel_settings"  # [theme.templates.user.<key>] in noctalia-config.toml
TEMPLATE_ENTRY = {
    "input_path": "$XDG_CONFIG_HOME/noctalia/templates/umbriel-settings-palette.conf",
    "output_path": f"$XDG_CONFIG_HOME/{DATA_DIR_NAME}/noctalia-palette.conf",
}


def template_status(config=None):
    """Whether Noctalia is set up to write the palette the app follows."""
    config = config or noctalia_config_file()
    entry = False
    try:
        with open(config, "rb") as handle:
            user = tomllib.load(handle).get("theme", {}).get("templates", {}).get("user", {})
        entry = isinstance(user, dict) and isinstance(user.get(TEMPLATE_KEY), dict)
    except (OSError, tomllib.TOMLDecodeError, AttributeError):
        pass
    return {
        "noctalia": os.path.isfile(config),
        "template": os.path.isfile(template_file()),
        "entry": entry,
        "palette": load_roles()[1] == "noctalia",
    }


def install_template(backup_dir, config=None):
    """Write the palette template and add its user-template entry to Noctalia's config (backed up first)."""
    import tomlkit

    config = config or noctalia_config_file()
    template = template_file()
    for path in (config, template):
        if os.path.islink(path):
            raise ValueError(f"{path} is a symlink; edit its target directly.")
    if not os.path.isfile(config):
        raise ValueError(f"Noctalia's config was not found: {config}")
    with open(config, encoding="utf-8") as handle:
        text = handle.read()
    document = tomlkit.parse(text)
    node = document
    for key in ("theme", "templates", "user"):
        if key not in node:
            node[key] = tomlkit.table(is_super_table=True)
        node = node[key]
        if not isinstance(node, dict):
            raise ValueError(f"Noctalia's config: [{key}] is not a table.")
    atomic_write(Path(template), PALETTE_TEMPLATE.encode("utf-8"), 0o644)
    os.makedirs(os.path.join(config_home(), DATA_DIR_NAME), exist_ok=True)
    if TEMPLATE_KEY not in node:
        entry = tomlkit.table()
        entry.update(TEMPLATE_ENTRY)
        node[TEMPLATE_KEY] = entry
        updated = tomlkit.dumps(document)
        tomllib.loads(updated)
        os.makedirs(backup_dir, exist_ok=True)
        atomic_write(Path(backup_dir) / "noctalia-config.toml.bak", text.encode("utf-8"))
        atomic_write(Path(config), updated.encode("utf-8"), stat.S_IMODE(os.stat(config).st_mode))
    return template_status(config)
