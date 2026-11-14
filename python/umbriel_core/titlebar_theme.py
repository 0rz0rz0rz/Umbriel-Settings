"""Title-bar backgrounds that follow Noctalia's palette (Qt-free).

A Noctalia user template renders the chosen colors on every palette change: one line per followed field with the
palette role behind the chosen KDE source and the opacity as a hex byte. Its `post_hook` runs `titlebar_apply.py`,
which copies them into the Umbriel config. An include cannot do this: Noctalia's built-in umbriel template always
moves `noctalia.toml` to the end of `include.optional.files`, and only the config itself is applied after it.
"""

import os
import re
import shutil
from pathlib import Path

from . import noctalia_theme
from .paths import DATA_DIR_NAME
from .xdg_dirs import atomic_write

TEMPLATE_KEY = "umbriel_titlebar"
OLD_INCLUDE = "titlebar.toml"  # earlier versions included the rendered file; Noctalia's include order defeated it
FIELDS = ("background", "background_unfocused")
# Which palette role each KDE button reads from Noctalia's kcolorscheme template.
ROLES = {
    "background": {"kde": "primary_container", "kde_header": "surface_container"},
    "background_unfocused": {"kde": "surface", "kde_header": "surface"},
}
LINE = re.compile(r'^(background(?:_unfocused)?) = "#\{\{colors\.(\w+)\.default\.hex_stripped\}\}([0-9A-F]{2})"'
                  r"\s*# source=(\w+)$", re.M)
ROLE = re.compile(r"\{\{colors\.(\w+)\.default\.hex_stripped\}\}")


def template_file():
    return os.path.join(noctalia_theme.config_home(), "noctalia", "templates", "umbriel-titlebar.toml")


def output_file():
    return os.path.join(noctalia_theme.config_home(), DATA_DIR_NAME, "titlebar-colors.toml")


def script_file():
    return os.path.join(noctalia_theme.config_home(), DATA_DIR_NAME, "titlebar_apply.py")


def _install_script():
    """Copy the standard-library applier to a stable place (the app may run from a temporary AppImage mount)."""
    target = script_file()
    if os.path.islink(target):
        raise ValueError(f"{target} is a symlink; remove it first.")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = target + ".tmp"
    shutil.copyfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "titlebar_apply.py"), tmp)
    os.chmod(tmp, 0o644)
    os.replace(tmp, target)
    return target


def _noctalia_path(path):
    """Write paths under $XDG_CONFIG_HOME the way Noctalia's own entries do."""
    home = noctalia_theme.config_home().rstrip("/") + "/"
    return "$XDG_CONFIG_HOME/" + path[len(home):] if path.startswith(home) else path


def read_follow(path=None):
    """{field: {"source", "role", "alpha"}} from the template, empty when there is none."""
    try:
        with open(path or template_file(), encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return {}
    return {field: {"role": role, "alpha": alpha, "source": source} for field, role, alpha, source in LINE.findall(text)}


def template_text(follow):
    lines = ["# Written by Umbriel Settings: title bar colors follow Noctalia's palette.", "[colors.title_bar]"]
    for field in FIELDS:
        if field in follow:
            item = follow[field]
            lines.append(f'{field} = "#{{{{colors.{item["role"]}.default.hex_stripped}}}}{item["alpha"]}"'
                         f'  # source={item["source"]}')
    return "\n".join(lines) + "\n"


def render(text, roles):
    """Fill the template from palette roles (#rrggbb); None when a role is missing."""
    missing = [name for name in ROLE.findall(text) if name not in roles]
    if missing:
        return None
    return ROLE.sub(lambda match: roles[match.group(1)][1:], text)


def status():
    """What the Colors page needs: followed fields with their current colors, and whether Noctalia is there."""
    follow = read_follow()
    roles, source = noctalia_theme.load_roles()
    fields = {}
    for field, item in follow.items():
        color = roles.get(item["role"]) if source == "noctalia" else None
        fields[field] = {**item, "color": (color.upper() + item["alpha"]) if color else None}
    return {"noctalia": os.path.isfile(noctalia_theme.noctalia_config_file()), "fields": fields,
            "old_include": OLD_INCLUDE, "palette": source == "noctalia"}


def follow(config_path, field, source, alpha, backup_dir):
    """Make one title-bar field follow Noctalia (`source` "kde"/"kde_header", `alpha` 0-255), or stop (source None)."""
    if field not in FIELDS:
        raise ValueError(f"Unknown title bar field: {field}")
    current = read_follow()
    if source is None:
        current.pop(field, None)
    else:
        if source not in ROLES[field]:
            raise ValueError(f"Unknown color source: {source}")
        if not isinstance(alpha, int) or isinstance(alpha, bool) or not 0 <= alpha <= 255:
            raise ValueError("Opacity must be between 0 and 1.")
        current[field] = {"role": ROLES[field][source], "alpha": f"{alpha:02X}", "source": source}
    if not current:  # nothing follows any more: stop the hook; the config keeps the last colors
        noctalia_theme.remove_user_template(TEMPLATE_KEY, template_file(), backup_dir)
        if os.path.isfile(output_file()) and not os.path.islink(output_file()):
            os.remove(output_file())
        return status()
    text = template_text(current)
    config = os.path.abspath(config_path)
    output = output_file()
    script = _install_script()
    if any("'" in path for path in (config, output, script)):
        raise ValueError("Paths with ' cannot be used in Noctalia's post_hook.")
    entry = {"input_path": _noctalia_path(template_file()), "output_path": output,
             "post_hook": f"python3 '{script}' '{output}' '{config}'"}
    noctalia_theme.write_user_template(TEMPLATE_KEY, template_file(), text, entry, backup_dir)
    if os.path.islink(output):
        raise ValueError(f"{output} is a symlink; edit its target directly.")
    roles, palette = noctalia_theme.load_roles()
    rendered = render(text, roles) if palette == "noctalia" else None
    if rendered is not None:  # the UI queues these colors for review; Noctalia refreshes the file later
        atomic_write(Path(output), rendered.encode("utf-8"), 0o644)
    return status()
