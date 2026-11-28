"""Downloaded cursor themes (from the store, cursor_store.py): kept in the private cache, and copied into the
user's icon folder only by a reviewed save that picks one (ConfigSession.save).

Archives are untrusted data. Only cursor data is kept: `<Theme>/index.theme`, `<Theme>/cursor.theme` and the
Xcursor files (they start with `Xcur`) in `<Theme>/cursors/`, with symlinks only as aliases to another cursor in
the same folder. Nothing from an archive is ever run. Installed themes carry `.umbriel-settings.json` (what this
app wrote) and stay when another theme is picked, or the plugin is disabled or removed: other apps may use them.
A reviewed save can delete any theme in the home search folders and any download (`remove`), never the one the
config picks or Umbriel's default (`protected_themes`); system copies need the package manager.
"""

import hashlib
import json
import os
import re
import shutil
import stat
import tarfile
import tempfile
import zipfile

from .cursor_themes import installed_cursor_themes, read_inherits, search_roots, theme_dirs
from .paths import atomic_write, private_dir, xdg_data_home
from .theme_files import REMOVING, discard, home_roots, safe_name, sweep_leftovers  # noqa: F401 (REMOVING)

CACHE = "cursor-downloads"
COMPLETE = ".complete"
CACHE_VERSION = 2  # raised when extraction changes (2: nested theme copies left out): older downloads are redone
MARKER = ".umbriel-settings.json"
MAX_ARCHIVE = 32 << 20
MAX_MEMBERS = 4000
MAX_FILE = 16 << 20  # Bibata's animated cursors reach 9 MB
MAX_TOTAL = 96 << 20
MAX_DEPTH = 3  # folders above a theme's own inside an archive
PART_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._+-]*")
THEME_FILES = ("index.theme", "cursor.theme")


class CursorError(ValueError):
    """A readable failure (unsafe archive, install refused) for the helper."""


# ------------------------------------------------------------------ archives
def _members(archive, name):
    """(path parts, "file"|"link", size, link target, read()) of the archive's entries; others are left out."""
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                mode = info.external_attr >> 16
                kind = "link" if stat.S_ISLNK(mode) else "dir" if info.is_dir() else "file"
                if kind == "file" and mode and not stat.S_ISREG(mode):
                    continue
                def read(info=info):
                    return _limited(bundle.open(info), MAX_FILE)
                target = read().decode("utf-8", "replace") if kind == "link" and info.file_size < 256 else None
                yield info.filename, kind, info.file_size, target, read
        return
    with tarfile.open(fileobj=archive, mode="r:*") as bundle:
        for info in bundle:
            if info.isreg():
                def read(info=info):
                    return _limited(bundle.extractfile(info), MAX_FILE)
                yield info.name, "file", info.size, None, read
            elif info.issym():
                yield info.name, "link", 0, info.linkname, None
            # directories, hard links, devices and FIFOs are never kept


def _limited(handle, limit):
    with handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise CursorError("A file in the cursor theme archive is too large.")
    return data


def _theme_path(path):
    """(theme folder inside the archive, path inside the theme) for a kept entry, else None."""
    parts = path.strip("/").split("/") if not path.startswith("/") else []
    if parts and parts[0] == ".":
        parts = parts[1:]
    if len(parts) < 2 or not all(PART_RE.fullmatch(part) for part in parts):
        return None  # absolute, "..", odd names
    if parts[-1] in THEME_FILES and len(parts) - 2 <= MAX_DEPTH:
        return "/".join(parts[:-1]), parts[-1]
    if len(parts) >= 3 and parts[-2] == "cursors" and len(parts) - 3 <= MAX_DEPTH:
        return "/".join(parts[:-2]), "cursors/" + parts[-1]
    return None


def _theme_names(folders):
    """{folder in the archive: theme name} for the folders that hold cursors. A theme folder inside another one is
    a copy (a build's `dist/`, say) and is left out; of two folders with the same name the shallower one wins."""
    names, taken = {}, set()
    for folder in sorted(folders, key=lambda path: (path.count("/"), path)):
        if any(folder.startswith(kept + "/") for kept in names):
            continue
        name = folder.rsplit("/", 1)[-1]
        if name not in taken:
            names[folder] = name
            taken.add(name)
    return names


def extract(archive, name, target):
    """Keep the cursor data of an archive (file object; `name` tells its format) in `target`/<Theme>/;
    return the theme names. Raises CursorError past the size caps."""
    files, links, total, count = {}, {}, 0, 0
    try:
        for path, kind, size, link, read in _members(archive, name):
            count += 1
            if count > MAX_MEMBERS:
                raise CursorError("The cursor theme archive has too many files.")
            where = _theme_path(path)
            if where is None or kind == "dir":
                continue
            theme, inner = where
            if kind == "link":
                if inner.startswith("cursors/") and link and PART_RE.fullmatch(link):
                    links[(theme, inner)] = link
                continue
            if size > MAX_FILE:
                raise CursorError("A file in the cursor theme archive is too large.")
            if total + size > MAX_TOTAL:
                raise CursorError("The cursor theme archive unpacks to more than expected.")
            data = read()
            total += len(data)
            if total > MAX_TOTAL:
                raise CursorError("The cursor theme archive unpacks to more than expected.")
            if inner.startswith("cursors/") and not data.startswith(b"Xcur"):
                continue  # not an Xcursor image (a script, an SVG, a Windows cursor): never kept
            files[(theme, inner)] = data
    except (tarfile.TarError, zipfile.BadZipFile, EOFError, OSError, ValueError) as error:
        if isinstance(error, CursorError):
            raise
        raise CursorError(f"The cursor theme archive can't be read: {error}") from None
    names = _theme_names({folder for folder, inner in files if inner.startswith("cursors/")})
    for (folder, inner), data in files.items():
        if folder in names:
            atomic_write(os.path.join(target, names[folder], inner), data, 0o600)
    for (folder, inner), link in links.items():
        resolved, seen = link, set()
        while (folder, "cursors/" + resolved) in links and resolved not in seen:  # alias of an alias
            seen.add(resolved)
            resolved = links[(folder, "cursors/" + resolved)]
        if folder in names and (folder, "cursors/" + resolved) in files:  # dangling or looping ones are dropped
            os.symlink(link, os.path.join(target, names[folder], inner))
    return sorted(names.values())


# ------------------------------------------------------------------ cache
def cache_dir(data_dir):
    return os.path.join(data_dir, CACHE)


def read_complete(folder):
    """The `.complete` record of a finished download ({themes, sha256, source}), else None."""
    try:
        with open(os.path.join(folder, COMPLETE), encoding="utf-8") as handle:
            done = json.load(handle)
    except (OSError, ValueError):
        return None
    if isinstance(done, dict) and done.get("version") == CACHE_VERSION and isinstance(done.get("themes"), list) \
            and isinstance(done.get("source"), dict):
        return done
    return None


def cached_themes(data_dir):
    """{theme: (cache key, folder)} of the finished downloads (the first one of a name wins, by key)."""
    found, root = {}, cache_dir(data_dir)
    try:
        keys = sorted(name for name in os.listdir(root) if not name.startswith("."))
    except OSError:
        return found
    for key in keys:
        folder = os.path.join(root, key)
        for theme in (read_complete(folder) or {}).get("themes", []):
            if isinstance(theme, str) and os.path.isdir(os.path.join(folder, theme, "cursors")):
                found.setdefault(theme, (key, os.path.join(folder, theme)))
    return found


def store_archive(root, key, archive, name, source, sha256):
    """Extract a downloaded archive into the cache as `root/key` (through a `.tmp-` folder renamed last, so the
    folder is either complete or absent); return its theme names ([] = nothing usable, nothing kept)."""
    private_dir(root)
    for entry in os.listdir(root):  # what a killed download left behind
        if entry.startswith(".tmp-"):
            shutil.rmtree(os.path.join(root, entry), ignore_errors=True)
    work = tempfile.mkdtemp(prefix=".tmp-", dir=root)
    try:
        themes = extract(archive, name, work)
        if not themes:
            return []
        atomic_write(os.path.join(work, COMPLETE),
                     json.dumps({"version": CACHE_VERSION, "sha256": sha256, "themes": themes, "source": source}),
                     0o600)
        folder = os.path.join(root, key)
        shutil.rmtree(folder, ignore_errors=True)
        os.replace(work, folder)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return themes


# ------------------------------------------------------------------ install (the reviewed save)
def target_root():
    """Where installs go: `$XDG_DATA_HOME/icons` when the cursor search path has it, else its first folder in
    the home directory."""
    roots = search_roots()
    preferred = os.path.join(xdg_data_home(), "icons")
    if preferred in roots:
        return preferred
    home = os.path.expanduser("~") + os.sep
    for root in roots:
        if root.startswith(home):
            return root
    raise CursorError("XCURSOR_PATH has no folder in your home directory, so the cursor theme can't be installed.")


def _read_marker(path):
    try:
        with open(path, encoding="utf-8") as handle:
            marker = json.load(handle)
    except (OSError, ValueError):
        return None
    return marker if isinstance(marker, dict) and isinstance(marker.get("files"), dict) else None


def installed_by_us(theme):
    """Whether `theme` in the install folder was put there by this app."""
    try:
        return _read_marker(os.path.join(target_root(), theme, MARKER)) is not None
    except CursorError:
        return False


def _entries(folder):
    """{path in the theme: sha256 or "link:<target>"} of a cached theme."""
    found = {}
    for name in THEME_FILES:
        path = os.path.join(folder, name)
        if os.path.isfile(path) and not os.path.islink(path):
            found[name] = _sha(path)
    cursors = os.path.join(folder, "cursors")
    for name in sorted(os.listdir(cursors)):
        path = os.path.join(cursors, name)
        if os.path.islink(path):
            found["cursors/" + name] = "link:" + os.readlink(path)
        elif os.path.isfile(path):
            found["cursors/" + name] = _sha(path)
    return found


def _sha(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def needs_install(theme, data_dir):
    """Whether a save picking `theme` would install it: cached, and not installed, or installed by this app but
    not completely (a save killed after writing the marker)."""
    cached = cached_themes(data_dir).get(theme) if theme else None
    if cached is None:
        return False
    if theme not in installed_cursor_themes():
        return True
    if not installed_by_us(theme):
        return False
    dest = os.path.join(target_root(), theme)
    return any(not os.path.lexists(os.path.join(dest, inner)) for inner in _entries(cached[1]))


def install(theme, data_dir):
    """Copy a cached theme into the icon folder (under the write lock, before the config that names it is
    written). The marker listing every file goes first, so what a killed install leaves is known; files that
    already match are kept. Returns the theme's folder."""
    cached = cached_themes(data_dir).get(theme)
    if cached is None:
        raise CursorError(f"The cursor theme {theme} isn't downloaded; download it again.")
    source_id, folder = cached
    root = target_root()
    dest = os.path.join(root, theme)
    for path in (dest, os.path.join(dest, "cursors"), os.path.join(dest, MARKER)):
        if os.path.islink(path):
            raise CursorError(f"{path} is a symlink; Umbriel Settings doesn't write through symlinks.")
    marker_path = os.path.join(dest, MARKER)
    marker = _read_marker(marker_path)
    if os.path.lexists(dest) and marker is None:
        raise CursorError(f"{dest} already exists and wasn't installed by Umbriel Settings; move it away first.")
    entries = _entries(folder)
    os.makedirs(os.path.join(dest, "cursors"), 0o755, exist_ok=True)
    known = dict(marker["files"]) if marker else {}
    known.update(entries)
    atomic_write(marker_path, json.dumps({"version": 1, "source": source_id, "files": known}, indent=1,
                                         sort_keys=True), 0o644)
    for inner, sha in entries.items():
        path = os.path.join(dest, inner)
        if sha.startswith("link:"):
            target = sha[5:]
            if os.path.islink(path) and os.readlink(path) == target:
                continue
            if os.path.lexists(path):
                os.unlink(path)
            os.symlink(target, path)
        else:
            if os.path.islink(path):
                os.unlink(path)
            elif os.path.isfile(path) and _sha(path) == sha:
                continue
            with open(os.path.join(folder, inner), "rb") as handle:
                atomic_write(path, handle.read(), 0o644)
    return dest


def _remove_ours(dest):
    """Delete a copy this app installed: only the files its marker lists that are unchanged since, then the
    marker and empty folders. Returns the files kept (changed or added by hand); the folder then stays."""
    marker_path = os.path.join(dest, MARKER)
    marker = _read_marker(marker_path)
    kept = []
    for inner, sha in sorted(marker["files"].items()):
        if not isinstance(inner, str) or not all(PART_RE.fullmatch(part) for part in inner.split("/")):
            continue
        path = os.path.join(dest, inner)
        if isinstance(sha, str) and sha.startswith("link:"):
            if os.path.islink(path) and os.readlink(path) == sha[5:]:
                os.unlink(path)
        elif os.path.isfile(path) and not os.path.islink(path):
            if _sha(path) == sha:
                os.unlink(path)
            else:
                kept.append(inner)
    os.unlink(marker_path)
    for folder in (os.path.join(dest, "cursors"), dest):
        try:
            os.rmdir(folder)
        except OSError:
            pass  # not empty: files that weren't ours
    return kept


def _drop_download(folder, theme):
    """Forget `theme` in one cached download: the record first (an archive may hold several themes), then its
    files; the whole download when nothing else is left in it."""
    record = read_complete(folder)
    others = [name for name in (record or {}).get("themes", []) if name != theme]
    if not others:
        shutil.rmtree(folder, ignore_errors=True)
        return
    atomic_write(os.path.join(folder, COMPLETE), json.dumps({**record, "themes": others}), 0o600)
    shutil.rmtree(os.path.join(folder, theme), ignore_errors=True)


def remove(theme, data_dir, protected=()):
    """Delete `theme` (a reviewed save asked for it) from the home search folders and the download cache: a copy
    this app installed loses only its unchanged files (`_remove_ours`), another copy its whole folder, or only
    `cursors/` and `cursor.theme` when it is an icon theme too. Copies outside the home folder (system packages)
    stay. Returns the files kept; a theme already gone is nothing to do."""
    if theme in protected:
        raise CursorError(f"{theme} is in use or Umbriel's default cursor theme, so it isn't removed.")
    plan = removal(theme, data_dir)
    kept = []
    for folder, kind in plan["folders"]:
        root = os.path.dirname(folder)
        if kind == "ours":
            kept += _remove_ours(folder)
        elif kind == "whole":
            discard(folder, root, theme)
        else:  # an icon theme with cursors: the icons stay
            discard(os.path.join(folder, "cursors"), root, theme)
            try:
                os.unlink(os.path.join(folder, "cursor.theme"))
            except FileNotFoundError:
                pass
    for folder in plan["downloads"]:
        _drop_download(folder, theme)
    return kept


# ------------------------------------------------------------------ what can be removed
def _theme_kind(folder):
    """How deleting a theme's real (not symlinked) folder works: "ours" (this app's marker), "whole" (no other
    subfolder than `cursors/`, or an inherit-only alias like `default`), "cursors" (an icon theme that also has
    cursors: only those go), or None (no cursor theme there)."""
    if os.path.islink(folder) or not os.path.isdir(folder):
        return None
    if _read_marker(os.path.join(folder, MARKER)) is not None:
        return "ours"
    try:
        with os.scandir(folder) as entries:
            folders = {entry.name for entry in entries if entry.is_dir(follow_symlinks=False)}
    except OSError:
        return None
    if "cursors" in folders:
        return "whole" if folders == {"cursors"} else "cursors"
    if not folders and read_inherits(folder) is not None:
        return "whole"
    return None


def download_index(data_dir):
    """{theme: [cache folders]} of every download whose record names it, finished or from an older extraction."""
    found, root = {}, cache_dir(data_dir)
    try:
        keys = sorted(name for name in os.listdir(root) if not name.startswith("."))
    except OSError:
        return found
    for key in keys:
        folder = os.path.join(root, key)
        try:
            with open(os.path.join(folder, COMPLETE), encoding="utf-8") as handle:
                record = json.load(handle)
        except (OSError, ValueError):
            continue
        themes = record.get("themes") if isinstance(record, dict) else None
        for theme in themes if isinstance(themes, list) else []:
            if isinstance(theme, str):
                found.setdefault(theme, []).append(folder)
    return found


def removal(theme, data_dir, downloads=None):
    """What deleting `theme` takes: {"folders": [(folder, kind)] in the home search folders (`_theme_kind`),
    "downloads": [cache folders], "system": whether a copy outside the home folder stays (needs root)}."""
    plan = {"folders": [], "downloads": [], "system": False}
    if not safe_name(theme):
        return plan
    home = home_roots(search_roots())
    for root in search_roots():
        folder = os.path.join(root, theme)
        if root in home:
            kind = _theme_kind(folder)
            if kind:
                plan["folders"].append((folder, kind))
        elif not plan["system"] and os.path.isdir(folder) and (
                os.path.isdir(os.path.join(folder, "cursors")) or read_inherits(folder) is not None):
            plan["system"] = True
    plan["downloads"] = list((download_index(data_dir) if downloads is None else downloads).get(theme, []))
    return plan


def protected_themes(picked=""):
    """Themes never removed: the one the config picks and Umbriel's default (`default`, the theme an unset
    `input.cursor.theme` falls back to, and the themes it inherits)."""
    themes, aliases = theme_dirs()
    names = {"default", *aliases.get("default", ())}
    for folder in themes.get("default", []):
        names.update(read_inherits(folder) or [])
    if picked:
        names.add(picked)
    return names


def prune_stale(data_dir):
    """Delete downloads an older extraction left (their record has another version: never listed, never used)
    and the leftovers of a killed removal."""
    root = cache_dir(data_dir)
    try:
        keys = [name for name in os.listdir(root) if not name.startswith(".")]
    except OSError:
        keys = []
    for key in keys:
        folder = os.path.join(root, key)
        if os.path.isdir(folder) and not os.path.islink(folder) and read_complete(folder) is None:
            shutil.rmtree(folder, ignore_errors=True)
    sweep_leftovers(search_roots())
