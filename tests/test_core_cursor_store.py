"""The Pling store client (umbriel_core/cursor_store.py) against a fake API: listing, previews, downloads."""

import hashlib
import io
import json
import os
import unittest
import urllib.error
import urllib.parse
from unittest.mock import patch

from test_core_cursor_download import CURSOR, GOOD, CursorDownloadTestCase, zip_archive
from umbriel_core import cursor_download, cursor_store

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
LINK = "https://files06.pling.com/api/files/download/j/token/{name}"


def item(item_id, files, **extra):
    """A store record; `files` = [(name, data or None for a link-only entry)]."""
    record = {"id": str(item_id), "name": f"<b>Theme</b> {item_id}", "typeid": "107", "personid": "maker",
              "score": 87, "downloads": 1234, "changed": "2024-06-18T04:20:55+00:00", "ghns_excluded": 0,
              "summary": "Nice &amp; <i>smooth</i> [b]cursors[/b]",
              "smallpreviewpic1": f"https://images.pling.com/cache/770x540-4/img/{item_id}.png"}
    for index, (name, data) in enumerate(files, 1):
        record.update({f"downloadname{index}": name, f"downloadlink{index}": LINK.format(name=name),
                       f"downloadsize{index}": (len(data) // 1024 + 1) if data else 1,
                       f"downloadmd5sum{index}": hashlib.md5(data).hexdigest() if data else ""})
    record.update(extra)
    return record


class StoreTestCase(CursorDownloadTestCase):
    def setUp(self):
        super().setUp()
        self.items = {
            1: item(1, [("neat.tar.gz", GOOD), ("neat-Windows.zip", b"x"), ("Neat-Cursor", None)]),
            2: item(2, [("hidden.tar.gz", GOOD)], ghns_excluded=1),
            3: item(3, [("only-Windows.zip", b"x")]),
            4: item(4, [("win.zip", zip_archive([("W/cursors/arrow.cur", b"\0\0\2\0")]))]),
            5: item(5, [("neat.tar.gz", GOOD)], downloadlink1="https://evil.example/neat.tar.gz"),
        }
        self.archives = {}
        for record in self.items.values():
            index = 1
            while f"downloadname{index}" in record:
                name = record[f"downloadname{index}"]
                self.archives[LINK.format(name=name)] = {"neat.tar.gz": GOOD}.get(name, b"x")
                index += 1
        self.archives[LINK.format(name="win.zip")] = zip_archive([("W/cursors/arrow.cur", b"\0\0\2\0")])
        self.requests = []
        patcher = patch.object(cursor_store, "urlopen", self.serve)
        patcher.start()
        self.addCleanup(patcher.stop)

    def serve(self, request, timeout):
        url = request.full_url
        self.requests.append(url)
        parts = urllib.parse.urlsplit(url)
        if url.startswith(cursor_store.API + "?"):
            query = dict(urllib.parse.parse_qsl(parts.query))
            self.query = query
            data = [record for record in self.items.values() if query.get("search", "") in record["name"]]
            return io.BytesIO(json.dumps({"status": "ok", "totalitems": len(data), "data": data}).encode())
        if url.startswith(cursor_store.API + "/"):
            item_id = int(parts.path.rsplit("/", 1)[1])
            data = [self.items[item_id]] if item_id in self.items else []
            return io.BytesIO(json.dumps({"status": "ok", "data": data}).encode())
        if parts.hostname == "images.pling.com":
            return io.BytesIO(PNG if "bad" not in url else b"<html>")
        if url in self.archives:
            return io.BytesIO(self.archives[url])
        raise urllib.error.URLError("not found")


class ListingTests(StoreTestCase):
    def test_rows_leave_out_excluded_windows_only_and_link_only_downloads(self):
        page = cursor_store.listing("rated", " Theme ", 2)
        self.assertEqual(self.query["sortmode"], "high")
        self.assertEqual((self.query["page"], self.query["search"], self.query["categories"]), ("2", "Theme", "107"))
        # 2 is excluded, 3 offers only a Windows zip, 5 links outside pling.com; 4 fails only when unpacked
        self.assertEqual([row["id"] for row in page["rows"]], [1, 4])
        row = page["rows"][0]
        self.assertEqual(row["name"], "Theme 1")
        self.assertEqual(row["summary"], "Nice & smooth cursors")
        self.assertEqual(row["files"], [{"file": 1, "name": "neat.tar.gz", "size": row["files"][0]["size"]}])
        self.assertEqual(row["preview"], "https://images.pling.com/cache/280x171-4/img/1.png")
        self.assertEqual(row["large"], "https://images.pling.com/cache/770x540-4/img/1.png")
        self.assertEqual(row["page"], "https://www.pling.com/p/1")

    def test_icon_themes_are_listed_without_files_and_only_from_their_category(self):
        self.items = {
            10: item(10, [], typeid="132"),  # icon themes are only linked: no archive needed
            11: item(11, [("icons.tar.xz", b"x")], typeid="132", ghns_excluded=1),
            12: item(12, [("neat.tar.gz", GOOD)]),  # a cursor theme
        }
        page = cursor_store.listing(kind="icon")
        self.assertEqual(self.query["categories"], "132")
        self.assertEqual([row["id"] for row in page["rows"]], [10])
        self.assertEqual((page["rows"][0]["files"], page["rows"][0]["page"]), ([], "https://www.pling.com/p/10"))
        self.assertEqual([row["id"] for row in cursor_store.listing()["rows"]], [12], "and not among cursors")

    def test_store_pages_are_built_from_the_item_number(self):
        self.assertEqual(cursor_store.page_url(1166289), "https://www.pling.com/p/1166289/")
        for bad in (0, -3, "1166289", "https://evil.example", True, None):
            with self.assertRaises(cursor_store.StoreError):
                cursor_store.page_url(bad)

    def test_offline_or_a_broken_answer_is_a_readable_error(self):
        with self.assertRaises(cursor_store.StoreError) as offline:
            cursor_store.listing(offline=True)
        self.assertEqual(offline.exception.code, "offline")
        self.assertEqual(self.requests, [])
        with patch.object(cursor_store, "urlopen", lambda request, timeout: io.BytesIO(b"<html>")), \
                self.assertRaisesRegex(cursor_store.StoreError, "isn't JSON"):
            cursor_store.listing()


class PreviewTests(StoreTestCase):
    def test_only_store_images_that_are_png_or_jpeg_are_cached(self):
        good = "https://images.pling.com/cache/280x171-4/img/1.png"
        result = cursor_store.previews(self.data, {"1": good, "2": "https://evil.example/x.png",
                                                   "3": "http://images.pling.com/x.png",
                                                   "4": "https://images.pling.com/bad.png"})
        self.assertEqual(sorted(result["failed"]), ["2", "3", "4"])
        with open(result["paths"]["1"], "rb") as handle:
            self.assertEqual(handle.read(), PNG)
        self.assertEqual(os.stat(result["paths"]["1"]).st_mode & 0o777, 0o600)
        count = len(self.requests)
        self.assertEqual(cursor_store.previews(self.data, {"1": good})["paths"]["1"], result["paths"]["1"])
        self.assertEqual(len(self.requests), count, "cached")
        self.assertEqual(cursor_store.previews(self.data, {"9": good.replace("1.png", "9.png")}, offline=True),
                         {"paths": {}, "failed": []})


class DownloadTests(StoreTestCase):
    def test_a_download_is_read_again_checked_and_cached_once(self):
        self.assertEqual(cursor_store.download(self.data, 1, 1), {"themes": ["Neat"]})
        self.assertEqual(self.requests[0], cursor_store.API + "/1?format=json", "a fresh record first")
        self.assertIn("Neat", cursor_download.cached_themes(self.data))
        record = cursor_download.read_complete(os.path.join(cursor_download.cache_dir(self.data), "pling-1-1"))
        self.assertEqual(record["source"]["store"], "pling")
        count = len(self.requests)
        self.assertEqual(cursor_store.download(self.data, 1, 1, offline=True), {"themes": ["Neat"]})
        self.assertEqual(len(self.requests), count, "cached: no network")

    def test_refusals_write_nothing(self):
        cases = [((1, 2), "isn't offered"),  # the Windows zip
                 ((1, 3), "isn't offered"),  # a link-only entry
                 ((2, 1), "isn't offered"),  # excluded by the store
                 ((5, 1), "isn't offered"),  # a link outside pling.com
                 ((4, 1), "no X11 cursor theme"),  # only Windows cursors inside
                 ((99, 1), "isn't offered")]
        for (item_id, file), message in cases:
            with self.subTest(item=item_id, file=file), self.assertRaisesRegex(cursor_store.StoreError, message):
                cursor_store.download(self.data, item_id, file)
        self.archives[LINK.format(name="neat.tar.gz")] = GOOD[:-1] + b"!"
        with self.assertRaisesRegex(cursor_store.StoreError, "checksum"):
            cursor_store.download(self.data, 1, 1)
        with self.assertRaises(cursor_store.StoreError) as offline:
            cursor_store.download(self.data, 1, 1, offline=True)
        self.assertEqual(offline.exception.code, "offline")
        self.assertEqual(cursor_download.cached_themes(self.data), {})

    def test_an_archive_larger_than_the_store_says_is_refused(self):
        self.items[1]["downloadsize1"] = 1  # KB; the archive is a little larger, plus 64 KB of slack
        self.archives[LINK.format(name="neat.tar.gz")] = GOOD + b"\0" * (200 << 10)
        self.items[1]["downloadmd5sum1"] = hashlib.md5(self.archives[LINK.format(name="neat.tar.gz")]).hexdigest()
        with self.assertRaisesRegex(cursor_store.StoreError, "larger than expected"):
            cursor_store.download(self.data, 1, 1)
        self.assertTrue(CURSOR)


if __name__ == "__main__":
    unittest.main()
