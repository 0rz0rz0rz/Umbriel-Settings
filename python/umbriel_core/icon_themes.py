"""Installed icon themes (freedesktop Icon Theme spec): discovery, a few preview icons per theme, and deleting a
theme from the home folder. Stdlib only: the previews are the theme's own files (PNG or SVG), nothing is drawn.
"""

import configparser
import os
import time
import warnings

from .paths import xdg_data_dirs, xdg_data_home
from .theme_files import discard, home_roots, safe_name, sweep_leftovers

# Each preview icon by its spec name, then names older themes use.
ICONS = (
    ("folder",),
    ("user-home", "folder-home"),
    ("text-x-generic",),
    ("image-x-generic",),
    ("utilities-terminal", "terminal"),
    ("web-browser", "internet-web-browser", "applications-internet"),
)
SIZE = 48  # the wanted icon size; the UI shows them smaller (sharp on HiDPI)
EXTENSIONS = (".png", ".svg")  # at the same fit a PNG wins: it's drawn as the theme made it for that size
MAX_DEPTH = 6
BUDGET = 8  # seconds per request; the rest come with the next one (`complete: false`)
HIDDEN = {"hicolor"}  # the spec's fallback theme: never a theme to pick
SHOWN = {"Adwaita"}  # Hidden=true, yet GTK's default and a fine pick (GNOME's own tools list it too)


def search_roots():
    """Folders holding icon themes, in the spec's order."""
    roots = [os.path.expanduser("~/.icons"), os.path.join(xdg_data_home(), "icons"),
             *(os.path.join(directory, "icons") for directory in xdg_data_dirs())]
    return list(dict.fromkeys(os.path.expanduser(root) for root in roots if root))


def read_index(folder):
    """The parsed `folder/index.theme` of an icon theme ([Icon Theme] with Directories), else None."""
    path = os.path.join(folder, "index.theme")
    index = configparser.ConfigParser(interpolation=None, strict=False)
    index.optionxform = str  # keys are case-sensitive (Size, MinSize, …)
    try:
        with open(path, encoding="utf-8") as handle:
            index.read_file(handle)
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, configparser.Error) as error:
        warnings.warn(f"Could not read icon theme index {path}: {error}", RuntimeWarning, stacklevel=2)
        return None
    if not index.has_section("Icon Theme") or not index.get("Icon Theme", "Directories", fallback="").strip():
        return None  # a cursor theme or an alias: no icons
    return index


def _split(value):
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def theme_folders():
    """{name: [folders, search order]} of every icon theme (the first folder's index.theme counts)."""
    found = {}
    for root in search_roots():
        try:
            entries = sorted(os.scandir(root), key=lambda entry: entry.name)
        except FileNotFoundError:
            continue
        except OSError as error:
            warnings.warn(f"Could not scan icon theme directory {root}: {error}", RuntimeWarning, stacklevel=2)
            continue
        for entry in entries:
            if entry.name.startswith(".") or not entry.is_dir():
                continue
            if entry.name in found or read_index(entry.path) is not None:
                found.setdefault(entry.name, []).append(entry.path)
    return found


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class _Theme:
    """One theme's index: label, Inherits and its icon directories sorted by how well they fit SIZE."""

    def __init__(self, name, folders):
        self.name, self.folders = name, folders
        index = read_index(folders[0])
        info = index["Icon Theme"]
        self.label = info.get("Name", name).strip() or name
        self.hidden = info.get("Hidden", "").strip().lower() == "true"
        self.inherits = [parent for parent in _split(info.get("Inherits")) if parent != name]
        dirs = []
        for subdir in _split(info.get("Directories")) + _split(info.get("ScaledDirectories")):
            if not index.has_section(subdir):
                continue
            section = index[subdir]
            if _int(section.get("Scale"), 1) != 1:
                continue
            size = _int(section.get("Size"), 0)
            kind = section.get("Type", "Threshold").strip()
            if kind == "Fixed":
                low = high = size
            elif kind == "Scalable":
                low, high = _int(section.get("MinSize"), size), _int(section.get("MaxSize"), size)
            else:
                threshold = _int(section.get("Threshold"), 2)
                low, high = size - threshold, size + threshold
            distance = low - SIZE if SIZE < low else (SIZE - high if SIZE > high else 0)
            dirs.append((distance, subdir))
        self.dirs = [subdir for _, subdir in sorted(dirs, key=lambda item: item[0])]

    def find(self, names):
        for subdir in self.dirs:
            for folder in self.folders:
                base = os.path.join(folder, subdir)
                for name in names:
                    for extension in EXTENSIONS:
                        path = os.path.join(base, name + extension)
                        if os.path.isfile(path):
                            return path
        return None


class _Lookup:
    """Finds icons through a theme and the themes it inherits (cycle-safe, MAX_DEPTH deep)."""

    def __init__(self, folders):
        self.folders, self.themes = folders, {}

    def theme(self, name):
        if name not in self.themes:
            try:
                self.themes[name] = _Theme(name, self.folders[name]) if name in self.folders else None
            except (KeyError, IndexError, TypeError):
                self.themes[name] = None
        return self.themes[name]

    def find(self, name, names, seen=None, depth=0):
        theme = self.theme(name)
        if theme is None:
            return None
        found = theme.find(names)
        if found or depth >= MAX_DEPTH:
            return found
        seen = seen if seen is not None else {name}
        for parent in theme.inherits:
            if parent not in seen:
                seen.add(parent)
                found = self.find(parent, names, seen, depth + 1)
                if found:
                    return found
        return None

    def chain(self, name):
        """`name` and every theme it inherits, transitively."""
        found, todo = set(), [name]
        while todo:
            current = todo.pop()
            if current in found or not current:
                continue
            found.add(current)
            theme = self.theme(current)
            todo.extend(theme.inherits if theme else [])
        return found


def removal(name, folders=None):
    """What deleting theme `name` takes: {"folders": [its real folders in home search folders], "system": a copy
    outside the home folder stays (needs root), "cursors": a home copy also holds a cursor theme (not deleted
    here)}."""
    plan = {"folders": [], "system": False, "cursors": False}
    if not safe_name(name):
        return plan
    roots = search_roots()
    home = home_roots(roots)
    for root in roots:
        folder = os.path.join(root, name)
        if root in home:
            if os.path.islink(folder) or not os.path.isdir(folder) or read_index(folder) is None:
                continue
            plan["folders"].append(folder)
            plan["cursors"] = plan["cursors"] or os.path.isdir(os.path.join(folder, "cursors"))
        elif not plan["system"] and os.path.isdir(folder) and read_index(folder) is not None:
            plan["system"] = True
    return plan


def protected_themes(current):
    """Themes never deleted: `current` (the one the desktop uses after the save), all it inherits, and hicolor."""
    return {"hicolor", *_Lookup(theme_folders()).chain(current)}


def remove(name, protected=()):
    """Delete theme `name` from the home search folders (a reviewed save asked for it); system copies stay."""
    if name in protected:
        raise ValueError(f"{name} is the icon theme in use or one it builds on, so it isn't removed.")
    plan = removal(name)
    if plan["cursors"]:
        raise ValueError(f"{name} also holds a cursor theme; remove that from the cursor list instead.")
    for folder in plan["folders"]:
        discard(folder, os.path.dirname(folder), name)
    sweep_leftovers(search_roots())


def previews(budget=BUDGET):
    """{"themes": [{name, label, inherits, icons, removable, system, cursors}], "complete"}: every installed icon
    theme (not hicolor, not Hidden) by name; `icons` = paths of the ICONS (None where the theme and its parents
    have none, or past `budget` seconds: then `complete` is false and the next request finds the rest)."""
    folders = theme_folders()
    lookup, rows, complete = _Lookup(folders), [], True
    deadline = time.monotonic() + budget
    for name in sorted(folders, key=lambda name: (name.casefold(), name)):
        theme = lookup.theme(name)
        if theme is None or (theme.hidden and name not in SHOWN) or name in HIDDEN:
            continue
        icons = []
        for names in ICONS:
            if time.monotonic() < deadline:
                try:
                    icons.append(lookup.find(name, names))
                except OSError:
                    icons.append(None)
            else:
                complete = False
                icons.append(None)
        plan = removal(name)
        rows.append({"name": name, "label": theme.label, "inherits": theme.inherits, "icons": icons,
                     "removable": bool(plan["folders"]) and not plan["cursors"],
                     "system": plan["system"] and not plan["folders"], "cursors": plan["cursors"]})
    return {"themes": rows, "complete": complete}
