"""Previews of the installed cursor themes: a strip of common shapes per theme as a PNG in the private cache.

Xcursor files are read directly (no Qt, no libXcursor): the image nearest the preview size, first frame only.
Shapes missing from a theme are looked up in the themes it inherits from, like libXcursor does.
"""

import array
import hashlib
import os
import struct
import sys
import time
import zlib

from . import cursor_download
from .cursor_themes import installed_cursor_themes, read_inherits, theme_dirs
from .paths import atomic_write, private_dir

VERSION = 2  # part of every cache name: raise it when the drawing changes (2: 60 px cells)
CELL = 60  # pixels per shape; the UI shows them at half size (sharp on HiDPI)
# Each shape by its CSS name, then the X11 names older themes use.
SHAPES = (
    ("default", "left_ptr", "arrow"),
    ("pointer", "hand2", "hand"),
    ("text", "xterm", "ibeam"),
    ("progress", "left_ptr_watch", "half-busy"),
    ("wait", "watch"),
    ("grab", "openhand", "hand1"),
    ("move", "fleur", "all-scroll"),
    ("crosshair", "cross", "tcross"),
)
MAX_FILE = 8 << 20
MAX_TOC = 1024
MAX_SIDE = 512
IMAGE_TYPE = 0xFFFD0002
MAX_DEPTH = 8
BUDGET = 12  # seconds per request: inside the helper's 20 s read timeout; the rest come with the next request


def read_xcursor(path, size=CELL):
    """(width, height, pixels) of the first frame nearest `size` (pixels: premultiplied ARGB, one int each),
    or None for anything that isn't a readable Xcursor file."""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > MAX_FILE:
            return None
        with open(path, "rb") as handle:
            header = handle.read(16)
            if len(header) < 16 or header[:4] != b"Xcur":
                return None
            header_size, _, count = struct.unpack("<III", header[4:16])
            if count > MAX_TOC or header_size < 16:
                return None
            handle.seek(header_size)
            toc = handle.read(12 * count)
            if len(toc) < 12 * count:
                return None
            images = [struct.unpack_from("<III", toc, 12 * i) for i in range(count)]
            images = [(subtype, position) for kind, subtype, position in images if kind == IMAGE_TYPE]
            if not images:
                return None
            # the smallest nominal size that reaches `size`, else the largest; the first frame of that size
            bigger = [nominal for nominal, _ in images if nominal >= size]
            nominal = min(bigger) if bigger else max(nominal for nominal, _ in images)
            position = next(position for subtype, position in images if subtype == nominal)
            handle.seek(position)
            chunk = handle.read(36)
            if len(chunk) < 36:
                return None
            chunk_size, kind, _, _, width, height = struct.unpack("<IIIIII", chunk[:24])
            if kind != IMAGE_TYPE or chunk_size != 36 or not 0 < width <= MAX_SIDE or not 0 < height <= MAX_SIDE:
                return None
            data = handle.read(4 * width * height)
    except OSError:
        return None
    if len(data) < 4 * width * height:
        return None
    pixels = array.array("I")
    pixels.frombytes(data)
    if sys.byteorder == "big":
        pixels.byteswap()
    return width, height, pixels


def _draw(canvas, canvas_width, left, top, image):
    """Copy an Xcursor image into the RGBA canvas at (left, top), scaled down to fit CELL (nearest pixel), and
    turned from premultiplied ARGB into straight RGBA."""
    width, height, pixels = image
    scale = max(width, height) / CELL if max(width, height) > CELL else 1
    shown_w, shown_h = int(width / scale), int(height / scale)
    left += (CELL - shown_w) // 2
    top += (CELL - shown_h) // 2
    for y in range(shown_h):
        source_row = int(y * scale) * width
        target = ((top + y) * canvas_width + left) * 4
        for x in range(shown_w):
            pixel = pixels[source_row + int(x * scale)]
            alpha = pixel >> 24
            if alpha:
                r, g, b = (pixel >> 16) & 255, (pixel >> 8) & 255, pixel & 255
                if alpha < 255:
                    r, g, b = min(255, r * 255 // alpha), min(255, g * 255 // alpha), min(255, b * 255 // alpha)
                canvas[target:target + 4] = bytes((r, g, b, alpha))
            target += 4


def png(width, height, rgba):
    """A PNG file (8-bit RGBA) of `rgba` rows."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    stride = width * 4
    raw = b"".join(b"\x00" + bytes(rgba[y * stride:(y + 1) * stride]) for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


class _Lookup:
    """Finds a theme's cursor files, following Inherits like libXcursor (cycle-safe, MAX_DEPTH deep)."""

    def __init__(self, extra=None):
        self.themes, self.aliases = theme_dirs()
        for name, folders in (extra or {}).items():  # downloaded themes, not installed yet
            self.themes.setdefault(name, []).extend(folders)
        self.inherits = {}

    def parents(self, theme):
        if theme not in self.inherits:
            if theme in self.aliases:
                found = sorted(self.aliases[theme])
            else:
                found = []
                for folder in self.themes.get(theme, []):
                    found += [name for name in read_inherits(folder) or [] if name not in found]
            self.inherits[theme] = found
        return self.inherits[theme]

    def find(self, theme, names, seen=None, depth=0):
        for folder in self.themes.get(theme, []):
            for name in names:
                path = os.path.join(folder, "cursors", name)
                if os.path.isfile(path):
                    return path
        seen = seen if seen is not None else {theme}
        if depth >= MAX_DEPTH:
            return None
        for parent in self.parents(theme):
            if parent not in seen:
                seen.add(parent)
                found = self.find(parent, names, seen, depth + 1)
                if found:
                    return found
        return None


def _cache_name(theme, files):
    digest = hashlib.sha1(f"{VERSION}\0{theme}".encode())
    for path in files:
        try:
            info = os.stat(path)
            digest.update(f"\0{path}\0{info.st_mtime_ns}\0{info.st_size}".encode())
        except OSError:
            digest.update(f"\0{path}\0-".encode())
    return digest.hexdigest()[:20]


def _render(lookup, theme, folder, made):
    """(strip path, arrow path) for `theme`, from the cache or drawn now; (None, None) without any shape."""
    files = [lookup.find(theme, names) for names in SHAPES]
    if not any(files):
        return None, None
    name = _cache_name(theme, [path for path in files if path])
    strip_path, arrow_path = (os.path.join(folder, f"{name}-{part}.png") for part in ("strip", "arrow"))
    made.update((os.path.basename(strip_path), os.path.basename(arrow_path)))
    if os.path.isfile(strip_path) and os.path.isfile(arrow_path):
        return strip_path, arrow_path
    images = [read_xcursor(path) if path else None for path in files]
    if not any(images):
        return None, None
    strip = bytearray(CELL * len(SHAPES) * CELL * 4)
    for index, image in enumerate(images):
        if image:
            _draw(strip, CELL * len(SHAPES), index * CELL, 0, image)
    arrow = bytearray(CELL * CELL * 4)
    first = next(image for image in images if image)
    _draw(arrow, CELL, 0, 0, first)
    private_dir(folder)
    atomic_write(strip_path, png(CELL * len(SHAPES), CELL, strip), 0o600)
    atomic_write(arrow_path, png(CELL, CELL, arrow), 0o600)
    return strip_path, arrow_path


def previews(data_dir, budget=BUDGET):
    """{"themes": [{name, preview, arrow, downloaded, ours, removable, system, protected}], "complete"}: every
    installed theme and every downloaded one that isn't installed yet (`downloaded`: a save picking it installs
    it), by name; `ours` = put into the icon folder by this app; `removable` = a save can delete it (a copy in a
    home search folder or a download), `system` = only system copies (needs the package manager), `protected` =
    Umbriel's default (`cursor_download.protected_themes`; the UI adds the theme in use). `preview` is the strip
    of SHAPES and `arrow` the first shape alone (PNG paths, None when the theme has none of them or it wasn't
    drawn within `budget` seconds: then `complete` is false and the next request draws the rest)."""
    folder = os.path.join(data_dir, "cursor-previews")
    cursor_download.prune_stale(data_dir)  # downloads of an older extraction: never listed, so never removable
    installed = installed_cursor_themes()
    cached = {name: [path] for name, (_, path) in cursor_download.cached_themes(data_dir).items()
              if name not in installed}
    names = sorted([*installed, *cached], key=lambda name: (name.casefold(), name))
    lookup, made, rows, deadline = _Lookup(cached), set(), [], time.monotonic() + budget
    downloads, protected = cursor_download.download_index(data_dir), cursor_download.protected_themes()
    complete = True
    for theme in names:
        strip = arrow = None
        if time.monotonic() < deadline:
            try:
                strip, arrow = _render(lookup, theme, folder, made)
            except (OSError, ValueError):  # one broken theme never hides the others
                strip = arrow = None
        else:
            complete = False
        plan = cursor_download.removal(theme, data_dir, downloads)
        removable = bool(plan["folders"] or plan["downloads"])
        rows.append({"name": theme, "preview": strip, "arrow": arrow, "downloaded": theme in cached,
                     "ours": theme not in cached and cursor_download.installed_by_us(theme),
                     "removable": removable, "system": plan["system"] and not removable,
                     "protected": theme in protected})
    if complete:  # themes removed or changed since: their old pictures go
        try:
            for entry in os.scandir(folder):
                if entry.name.endswith(".png") and entry.name not in made:
                    os.unlink(entry.path)
        except OSError:
            pass
    return {"themes": rows, "complete": complete}
