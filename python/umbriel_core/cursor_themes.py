"""Installed cursor theme discovery."""

import configparser
import os
import warnings

from .paths import xdg_data_dirs, xdg_data_home


def search_roots():
    """Folders holding cursor themes, in libXcursor's order; `XCURSOR_PATH` replaces them."""
    cursor_path = os.environ.get("XCURSOR_PATH")
    if cursor_path is not None:
        roots = cursor_path.split(os.pathsep)
    else:
        roots = [
            os.path.expanduser("~/.icons"),
            os.path.join(xdg_data_home(), "icons"),
            *(os.path.join(directory, "icons") for directory in xdg_data_dirs()),
            "/usr/share/pixmaps",
        ]
    return [os.path.expanduser(root) for root in roots if root]


def read_inherits(folder):
    """The themes `folder/index.theme` inherits from ([Icon Theme] Inherits); None when it can't be read."""
    index_path = os.path.join(folder, "index.theme")
    try:
        with open(index_path, encoding="utf-8") as index_file:
            index = configparser.ConfigParser(interpolation=None, strict=False)
            index.read_file(index_file)
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, configparser.Error) as error:
        warnings.warn(f"Could not read cursor theme index {index_path}: {error}", RuntimeWarning, stacklevel=2)
        return None
    inherited = index.get("Icon Theme", "Inherits", fallback="")
    return [name.strip() for name in inherited.split(",") if name.strip()]


def theme_dirs():
    """({name: [folders with cursors/, search order]}, {alias: inherited names}): themes, and the folders that
    only hold an index.theme inheriting from others (like `default`)."""
    themes, aliases = {}, {}
    for root in search_roots():
        try:
            entries = list(os.scandir(root))
        except FileNotFoundError:
            continue
        except OSError as error:
            warnings.warn(f"Could not scan cursor theme directory {root}: {error}", RuntimeWarning, stacklevel=2)
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            if os.path.isdir(os.path.join(entry.path, "cursors")):
                themes.setdefault(entry.name, []).append(entry.path)
                continue
            try:
                with os.scandir(entry.path) as children:
                    if any(child.is_dir() for child in children):
                        continue
            except OSError:
                continue
            inherited = read_inherits(entry.path)
            if inherited is not None:
                aliases.setdefault(entry.name, set()).update(inherited)
    return themes, aliases


def installed_cursor_themes():
    """Find cursor themes and inheritance-only aliases in cursor search paths."""
    found, aliases = theme_dirs()
    themes = set(found)
    while True:
        inherited_themes = {name for name, parents in aliases.items() if parents & themes}
        new_themes = inherited_themes - themes
        if not new_themes:
            break
        themes.update(new_themes)
    return sorted(themes, key=lambda name: (name.casefold(), name))
