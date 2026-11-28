"""Cursor themes from the Pling store (gnome-look.org, store.kde.org; the store KDE's "Get New Cursors" uses), and
its icon themes, which are only listed (each row links to its store page; nothing is downloaded for them).

The network is used only on request: a listing page, preview images and one theme's archive. Uploads are not
reviewed by anyone, so an archive is treated as untrusted data: it must match the item's MD5, only Xcursor files,
index.theme and same-folder aliases are kept (cursor_download.extract), and nothing from it is ever run. Items
KDE excludes from its own store (`ghns_excluded`) are left out.
"""

import hashlib
import html
import io
import json
import os
import re
import time
import urllib.parse

from . import cursor_download, fetch
from .paths import atomic_write, private_dir

API = "https://api.pling.com/ocs/v1/content/data"
CATEGORIES = {"cursor": 107, "icon": 132}  # "X11 Mouse Theme Cursors", "Full Icon Themes"
CATEGORY = CATEGORIES["cursor"]
PAGE = "https://www.pling.com/p/{}/"
SORTS = {"popular": "down", "rated": "high", "new": "new", "name": "alpha"}
LISTING_LIMIT = 2 << 20
LISTING_TIMEOUT = 15
PREVIEW_LIMIT = 1 << 20
PREVIEW_TIMEOUT = 8
PREVIEW_BUDGET = 16  # seconds per request, inside the plugin's 20 s timeout
PREVIEW_BATCH = 12
DOWNLOAD_BUDGET = 50  # inside the plugin's 60 s timeout
ARCHIVES = (".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2", ".tar", ".zip")
PREVIEW_HOST = "images.pling.com"
SMALL, LARGE = "/cache/280x171-4/", "/cache/770x540-4/"  # "-4": scaled to fit, never cropped
MD5_RE = re.compile(r"[0-9a-f]{32}")


class StoreError(ValueError):
    """A readable failure for the helper; `code` is "offline" when nothing may be downloaded."""

    def __init__(self, message, code="error"):
        super().__init__(message)
        self.code = code


def urlopen(request, timeout):  # tests replace this
    return fetch.urlopen(request, timeout)


def _get(url, limit, timeout, deadline=None):
    try:
        return fetch.fetch(url, limit, timeout, deadline, opener=urlopen)
    except fetch.FetchError as error:
        raise StoreError(str(error)) from None


def _https_host(url):
    """The host of an https URL, else None."""
    try:
        parts = urllib.parse.urlsplit(url) if isinstance(url, str) else None
    except ValueError:
        return None
    return parts.hostname if parts and parts.scheme == "https" else None


def _text(value, limit):
    """Plain text from the store's HTML/BBCode descriptions, cut at `limit`."""
    if not isinstance(value, str):
        return ""
    text = re.sub(r"<[^>]*>|\[/?[a-z*]+(=[^\]]*)?\]", " ", value)
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _number(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _files(item):
    """The item's downloads that may be a Linux cursor theme archive: [{file, name, size, md5, link}]."""
    found, index = [], 1
    while f"downloadname{index}" in item:
        name = item.get(f"downloadname{index}")
        link = item.get(f"downloadlink{index}")
        md5 = item.get(f"downloadmd5sum{index}")
        host = _https_host(link)
        if isinstance(name, str) and name.lower().endswith(ARCHIVES) and "windows" not in name.lower() \
                and isinstance(md5, str) and MD5_RE.fullmatch(md5) and host and host.endswith(".pling.com"):
            found.append({"file": index, "name": name[:120], "size": _number(item.get(f"downloadsize{index}")),
                          "md5": md5, "link": link})
        index += 1
    return found


def _preview(item):
    url = item.get("smallpreviewpic1") or item.get("previewpic1")
    if _https_host(url) != PREVIEW_HOST:
        return None, None
    url = re.sub(r"/cache/\d+x\d+-\d+/", LARGE, url)  # any size the store links to
    return url.replace(LARGE, SMALL), url


def _row(item, kind="cursor"):
    """A listing row, or None for an item that is excluded or (a cursor theme) offers nothing to download. Icon
    themes are only listed and linked, so they need no files."""
    if not isinstance(item, dict) or _number(item.get("ghns_excluded")) \
            or _number(item.get("typeid")) != CATEGORIES[kind]:
        return None
    item_id = _number(item.get("id"))
    files = _files(item) if kind == "cursor" else []
    if item_id <= 0 or (kind == "cursor" and not files):
        return None
    small, large = _preview(item)
    return {
        "id": item_id, "name": _text(item.get("name"), 80) or f"#{item_id}",
        "author": _text(item.get("personid"), 40), "score": max(0, min(100, _number(item.get("score")))),
        "downloads": _number(item.get("downloads")), "updated": str(item.get("changed") or "")[:10],
        "summary": _text(item.get("summary") or item.get("description"), 300),
        "page": f"https://www.pling.com/p/{item_id}", "preview": small, "large": large,
        "files": [{key: value for key, value in f.items() if key in ("file", "name", "size")} for f in files],
    }


def _items(raw):
    try:
        data = json.loads(raw)
    except ValueError:
        raise StoreError("The Pling store answered with something that isn't JSON.") from None
    if not isinstance(data, dict) or data.get("status") != "ok" or not isinstance(data.get("data"), list):
        raise StoreError("The Pling store didn't answer as expected; try again later.")
    return data


def page_url(item_id):
    """The store page of item `item_id` (built from the number, never from text a request brings)."""
    if not isinstance(item_id, int) or isinstance(item_id, bool) or item_id <= 0:
        raise StoreError("That isn't a store item.")
    return PAGE.format(item_id)


def listing(sort="popular", search="", page=0, offline=False, kind="cursor"):
    """One page of cursor or icon themes (`kind`; about 10): {rows, total, page}."""
    if offline:
        raise StoreError("Noctalia is in offline mode, so the store isn't asked.", "offline")
    query = {"categories": CATEGORIES[kind], "format": "json", "sortmode": SORTS.get(sort, "down"),
             "page": max(0, _number(page))}
    if isinstance(search, str) and search.strip():
        query["search"] = search.strip()[:80]
    data = _items(_get(API + "?" + urllib.parse.urlencode(query), LISTING_LIMIT, LISTING_TIMEOUT))
    rows = [row for row in (_row(item, kind) for item in data["data"]) if row]
    return {"rows": rows, "total": _number(data.get("totalitems")), "page": query["page"]}


def _image_kind(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    return None


def previews(data_dir, items, offline=False):
    """{paths: {id: cached image}, failed: [ids]} for {id: preview URL} (images.pling.com only, PNG/JPEG,
    PREVIEW_LIMIT each); what isn't cached is downloaded while PREVIEW_BUDGET allows (not when `offline`)."""
    folder = os.path.join(data_dir, "cursor-store", "previews")
    found, failed, deadline = {}, [], time.monotonic() + PREVIEW_BUDGET
    for key, url in list((items or {}).items())[:PREVIEW_BATCH]:
        if _https_host(url) != PREVIEW_HOST:
            failed.append(key)
            continue
        stem = f"{_number(key)}-{hashlib.sha1(url.encode()).hexdigest()[:12]}"
        cached = [os.path.join(folder, stem + ext) for ext in (".png", ".jpg")]
        hit = next((path for path in cached if os.path.isfile(path)), None)
        if hit:
            found[key] = hit
            continue
        if offline or time.monotonic() > deadline - 1:
            continue
        try:
            data = _get(url, PREVIEW_LIMIT, PREVIEW_TIMEOUT, deadline)
        except StoreError:
            failed.append(key)
            continue
        kind = _image_kind(data)
        if kind is None:
            failed.append(key)
            continue
        private_dir(folder)
        path = os.path.join(folder, f"{stem}.{kind}")
        atomic_write(path, data, 0o600)
        found[key] = path
    return {"paths": found, "failed": failed}


def cache_key(item_id, file):
    return f"pling-{_number(item_id)}-{_number(file)}"


def download(data_dir, item_id, file, offline=False):
    """Download one archive of a store item into the cache (once); return {themes}. The item is read again for
    a fresh link; the archive must match its MD5 and hold an X11 cursor theme."""
    key = cache_key(item_id, file)
    root = cursor_download.cache_dir(data_dir)
    folder = os.path.join(root, key)
    done = cursor_download.read_complete(folder)
    if done is not None:
        return {"themes": done["themes"]}
    if offline:
        raise StoreError("Noctalia is in offline mode, so the cursor theme can't be downloaded.", "offline")
    deadline = time.monotonic() + DOWNLOAD_BUDGET
    data = _items(_get(f"{API}/{_number(item_id)}?format=json", LISTING_LIMIT, LISTING_TIMEOUT, deadline))
    item = data["data"][0] if data["data"] else None
    row = _row(item)
    chosen = next((f for f in _files(item) if f["file"] == _number(file)), None) if row else None
    if chosen is None:
        raise StoreError("That download isn't offered any more (or isn't a Linux cursor theme archive).")
    limit = min(cursor_download.MAX_ARCHIVE, max(chosen["size"], 1) * 1024 + (64 << 10))
    archive = _get(chosen["link"], limit, DOWNLOAD_BUDGET, deadline)
    if hashlib.md5(archive).hexdigest() != chosen["md5"]:  # noqa: S324 - the store's own checksum, not security
        raise StoreError(f"{chosen['name']} doesn't match the store's checksum, so it wasn't used.")
    source = {"store": "pling", "id": row["id"], "file": chosen["file"], "name": row["name"],
              "author": row["author"], "page": row["page"], "archive": chosen["name"]}
    themes = cursor_download.store_archive(root, key, io.BytesIO(archive), chosen["name"], source,
                                           hashlib.sha256(archive).hexdigest())
    if not themes:
        raise StoreError(f"{chosen['name']} has no X11 cursor theme (Windows cursors, or the sources?).")
    return {"themes": themes}
