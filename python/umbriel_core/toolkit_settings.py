"""The icon and cursor theme of GTK, Qt and KDE apps: gsettings, GTK's settings.ini / .gtkrc-2.0, qt5ct/qt6ct,
kdeglobals, kcminputrc and the X11 default cursor (`~/.icons/default/index.theme`).

Only the theme keys change: every other line stays as it was. Files are written only where they already exist
(GTK 3's settings.ini is created when no GTK file exists), each backed up first (`backups.snapshot_file`, its own
folder per file) and replaced atomically; a symlinked file is refused. Each file stands alone: a failure is a
warning for that file and the others are still written (a kill halfway leaves some files on the new theme, each
of them whole; the next save writes the rest).
"""

import hashlib
import json
import os
import re
import shutil
import subprocess

from .backups import snapshot_file
from .launch import child_env
from .paths import atomic_write, xdg_config_home

GSETTINGS_SCHEMA = "org.gnome.desktop.interface"
NAME_RE = re.compile(r"[^\s\"'=\[\]\\]+(?: [^\s\"'=\[\]\\]+)*")  # theme folder names (spaces inside allowed)


class Target:
    """One file (or gsettings): its keys for the icon theme and the cursor theme/size, in `section` (None for
    .gtkrc-2.0, which has no sections and quotes strings)."""

    def __init__(self, key, label, path, section, icon=None, cursor=None, size=None, create=False):
        self.key, self.label, self.path, self.section = key, label, path, section
        self.icon, self.cursor, self.size, self.create = icon, cursor, size, create

    def keys(self, kind):
        return [key for key in ((self.icon,) if kind == "icon" else (self.cursor, self.size)) if key]


def targets():
    config, home = xdg_config_home(), os.path.expanduser("~")
    return [
        Target("gtk3", "GTK 3", os.path.join(config, "gtk-3.0", "settings.ini"), "Settings", "gtk-icon-theme-name",
               "gtk-cursor-theme-name", "gtk-cursor-theme-size", create=True),
        Target("gtk4", "GTK 4", os.path.join(config, "gtk-4.0", "settings.ini"), "Settings", "gtk-icon-theme-name",
               "gtk-cursor-theme-name", "gtk-cursor-theme-size"),
        Target("gtk2", "GTK 2", os.path.join(home, ".gtkrc-2.0"), None, "gtk-icon-theme-name",
               "gtk-cursor-theme-name", "gtk-cursor-theme-size"),
        Target("qt6ct", "qt6ct", os.path.join(config, "qt6ct", "qt6ct.conf"), "Appearance", "icon_theme"),
        Target("qt5ct", "qt5ct", os.path.join(config, "qt5ct", "qt5ct.conf"), "Appearance", "icon_theme"),
        Target("kde", "KDE", os.path.join(config, "kdeglobals"), "Icons", "Theme"),
        Target("kdeinput", "KDE input", os.path.join(config, "kcminputrc"), "Mouse", None, "cursorTheme",
               "cursorSize"),
        Target("xcursor", "X11 default cursor", os.path.join(home, ".icons", "default", "index.theme"),
               "Icon Theme", None, "Inherits"),
    ]


# ------------------------------------------------------------------ text edits
def _key_re(key):
    return re.compile(r"^\s*" + re.escape(key) + r"\s*=\s*(.*?)\s*$")


def _section_of(line):
    match = re.fullmatch(r"\s*\[([^\]]*)\]\s*", line)
    return match.group(1) if match else None


def get_value(text, section, key):
    """The value of `key` in `section` (None: a file without sections), quotes of .gtkrc strings dropped."""
    current, pattern = None, _key_re(key)
    for line in text.splitlines():
        header = _section_of(line)
        if header is not None:
            current = header
            continue
        if section is not None and current != section:
            continue
        match = pattern.match(line)
        if match:
            value = match.group(1)
            return value[1:-1] if len(value) >= 2 and value[0] == value[-1] == '"' else value
    return None


def set_values(text, section, values, quote=False):
    """`text` with each key of `values` set in `section` (a missing key goes at the section's end, a missing
    section at the file's end); everything else stays. `quote`: strings in double quotes (.gtkrc-2.0)."""
    def line_for(key, value):
        shown = f'"{value}"' if quote and isinstance(value, str) else str(value)
        return f"{key}={shown}\n"

    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    todo = dict(values)
    current, start, end = None, None, None  # the wanted section's header line and the index after its last line
    if section is None:
        start, end = -1, len(lines)
    for index, line in enumerate(lines):
        header = _section_of(line)
        if header is not None:
            if current == section and start is not None and end is None:
                end = index
            current = header
            if header == section and start is None:
                start = index
            continue
        if section is not None and current != section:
            continue
        for key in list(todo):
            if _key_re(key).match(line):
                lines[index] = line_for(key, todo.pop(key))
    if not todo:
        return "".join(lines)
    if start is None:  # no such section yet
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.append(f"[{section}]\n")
        lines.extend(line_for(key, value) for key, value in todo.items())
        return "".join(lines)
    end = len(lines) if end is None else end
    insert = end
    while insert > start + 1 and not lines[insert - 1].strip():
        insert -= 1  # after the section's last non-blank line
    lines[insert:insert] = [line_for(key, value) for key, value in todo.items()]
    return "".join(lines)


# ------------------------------------------------------------------ gsettings
def gsettings():
    """The gsettings command, or None (then GNOME settings aren't read or written)."""
    return shutil.which("gsettings")


def _gsettings(*args):
    command = gsettings()
    if not command:
        return None
    result = subprocess.run([command, *args], capture_output=True, text=True, timeout=5, env=child_env(),
                            check=False)
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or f"gsettings exited with {result.returncode}")
    return result.stdout.strip()


def _gsettings_get(key):
    try:
        value = _gsettings("get", GSETTINGS_SCHEMA, key)
    except (OSError, subprocess.SubprocessError):
        return None
    if value is None:
        return None
    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] == "'" else value


# ------------------------------------------------------------------ read / write
def _read(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        return None


def read():
    """{"icon": {target: value}, "cursor": {target: value}, "theme": the icon theme apps use (GNOME settings,
    else the first file that names one), "targets": {"icon": [labels], "cursor": [labels]} that a save writes,
    "revision"} (the revision covers every value, so a change made elsewhere is noticed)."""
    result = {"icon": {}, "cursor": {}, "targets": {"icon": [], "cursor": []}}
    if gsettings():
        result["icon"]["gnome"] = _gsettings_get("icon-theme")
        result["cursor"]["gnome"] = _gsettings_get("cursor-theme")
        for kind in ("icon", "cursor"):
            result["targets"][kind].append("GNOME settings")
    gtk_files = False
    for target in targets():
        try:
            text = None if os.path.islink(target.path) else _read(target.path)
        except (OSError, UnicodeError):
            text = None
        if text is None:
            continue
        gtk_files = gtk_files or target.key.startswith("gtk")
        for kind in ("icon", "cursor"):
            keys = target.keys(kind)
            if keys:
                result[kind][target.key] = get_value(text, target.section, keys[0])
                result["targets"][kind].append(target.label)
    if not gtk_files:  # a save creates GTK 3's settings.ini
        for kind in ("icon", "cursor"):
            result["targets"][kind].insert(1 if gsettings() else 0, "GTK 3")
    result["theme"] = next((value for value in result["icon"].values() if value), "")
    result["revision"] = hashlib.sha256(json.dumps([result["icon"], result["cursor"]], sort_keys=True)
                                        .encode("utf-8")).hexdigest()
    return result


def _check_name(name):
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ValueError(f"{name!r} isn't a theme name.")


def _write(kind, values_by_key, backup_dir):
    """Write `values_by_key` (target key → {file key: value}) into each target that exists (or may be created);
    returns {"written": [labels], "warnings": [texts]}."""
    written, warnings, every = [], [], targets()
    gtk_present = any(target.key.startswith("gtk") and os.path.lexists(target.path) for target in every)
    for target in every:
        values = values_by_key.get(target.key)
        if not values or not (os.path.lexists(target.path) or (target.create and not gtk_present)):
            continue
        try:
            if os.path.islink(target.path) or os.path.islink(os.path.dirname(target.path)):
                raise ValueError("it is a symlink; edit its target directly")
            text = _read(target.path)
            updated = set_values(text or "", target.section, values, quote=target.section is None)
            if updated == text:
                continue
            if text is not None:
                snapshot_file(target.path, os.path.join(backup_dir, target.key))
            atomic_write(target.path, updated)
            written.append(target.label)
        except (OSError, UnicodeError, ValueError) as error:
            warnings.append(f"The {kind} theme wasn't set for {target.label} ({target.path}): {error}.")
    return {"written": written, "warnings": warnings}


def _write_gsettings(pairs, kind, result):
    if not gsettings():
        return
    try:
        for key, value in pairs:
            _gsettings("set", GSETTINGS_SCHEMA, key, str(value))
        result["written"].insert(0, "GNOME settings")
    except (OSError, subprocess.SubprocessError) as error:
        result["warnings"].insert(0, f"The {kind} theme wasn't set in GNOME settings: {error}.")


def set_icon_theme(name, backup_dir):
    """Make `name` the icon theme of GTK, Qt and KDE apps (see the module doc)."""
    _check_name(name)
    result = _write("icon", {target.key: {target.icon: name} for target in targets() if target.icon}, backup_dir)
    _write_gsettings([("icon-theme", name)], "icon", result)
    return result


def set_cursor_theme(name, size, backup_dir):
    """Make `name` (at `size` px) the cursor theme of GTK, Qt and KDE apps and of X11 apps without a setting."""
    _check_name(name)
    if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= 512:
        raise ValueError("The cursor size must be 1–512.")
    values = {}
    for target in targets():
        if target.cursor:
            values[target.key] = {target.cursor: name, **({target.size: size} if target.size else {})}
    result = _write("cursor", values, backup_dir)
    _write_gsettings([("cursor-theme", name), ("cursor-size", size)], "cursor", result)
    return result


def cursor_differs(name, size):
    """Whether any target names another cursor theme or size than `name`/`size` (then a save writes them)."""
    for target in targets():
        if not target.cursor or os.path.islink(target.path):
            continue
        try:
            text = _read(target.path)
        except (OSError, UnicodeError):
            continue
        if text is None:
            if target.create and not any(os.path.lexists(other.path) for other in targets()
                                         if other.key.startswith("gtk")):
                return True
            continue
        if get_value(text, target.section, target.cursor) != name:
            return True
        if target.size and get_value(text, target.section, target.size) not in (None, str(size)):
            return True
    if gsettings():
        return _gsettings_get("cursor-theme") not in (None, name) \
            or _gsettings_get("cursor-size") not in (None, str(size))
    return False
