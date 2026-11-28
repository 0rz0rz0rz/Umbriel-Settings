"""Helper commands for the cursor theme store and the kill points of the save that installs a downloaded theme (a
real SIGTERM, a full disk). No network: the cache is filled first, as after Download."""

import json
import os
import struct
import subprocess
import sys
import textwrap
import time
import unittest

from support import HELPER, ConfigTestCase

KEY, THEME = "pling-1411743-1", "WhiteSur-cursors"
IMAGE = struct.pack("<9I", 36, 0xFFFD0002, 24, 1, 2, 2, 0, 0, 0) + struct.pack("<I", 0xFFFFFFFF) * 4
CURSOR = b"Xcur" + struct.pack("<III", 16, 0x10000, 1) + struct.pack("<III", 0xFFFD0002, 24, 28) + IMAGE


class CursorDownloadHelperTests(ConfigTestCase):
    def setUp(self):
        super().setUp()
        self.env.update({"HOME": str(self.root), "XDG_DATA_HOME": str(self.root / "data")})
        self.env.pop("XCURSOR_PATH", None)
        cached = self.root / "data" / "umbriel-settings" / "cursor-downloads" / KEY
        (cached / THEME / "cursors").mkdir(parents=True)
        (cached / THEME / "index.theme").write_text("[Icon Theme]\nName=Nordzy\n")
        for name in ("left_ptr", "pointer", "text"):
            (cached / THEME / "cursors" / name).write_bytes(CURSOR)
        os.symlink("left_ptr", cached / THEME / "cursors" / "default")
        (cached / ".complete").write_text(json.dumps({"version": 2, "sha256": "0" * 64, "themes": [THEME], "source": {
            "store": "pling", "id": 1411743, "file": 1, "name": "WhiteSur cursors"}}))
        self.installed = self.root / "data" / "icons" / THEME

    def request(self, **extra):
        state = self.ok("read", {"config": str(self.config)})
        return {"config": str(self.config), "changes": {"revision": state["revision"], "fields": {
            "input.cursor.theme": {"value": THEME}, **extra}}}

    def interrupted_save(self, how):
        """`save` killed by SIGTERM right after the marker (`marker`) or the config (`config`) was written, or with
        a full disk at the first theme file (`full`)."""
        wrapper = textwrap.dedent("""\
            import importlib.util, os, signal, sys
            helper, how, config = sys.argv[1:4]
            spec = importlib.util.spec_from_file_location("umbriel_settings_under_test", helper)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            from umbriel_core import cursor_download, session
            real_write, real_config = cursor_download.atomic_write, session.write_text_file
            def write(path, data, mode=None):
                if how == "full" and not path.endswith(cursor_download.MARKER):
                    raise OSError(28, "No space left on device")
                real_write(path, data, mode)
                if how == "marker":
                    os.kill(os.getpid(), signal.SIGTERM)
            def write_config(path, text, *rest):
                real_config(path, text, *rest)
                if how == "config" and os.path.abspath(path) == config:
                    os.kill(os.getpid(), signal.SIGTERM)
            cursor_download.atomic_write, session.write_text_file = write, write_config
            sys.exit(module.main(sys.argv[4:]))
        """)
        request_file = self.root / "request.json"
        request_file.write_text(json.dumps(self.request()), encoding="utf-8")
        return subprocess.run([sys.executable, "-I", "-c", wrapper, str(HELPER), how, str(self.config), "save",
                               "--request", str(request_file)], env=self.env, capture_output=True, text=True,
                              check=False)

    def test_the_store_is_never_asked_in_offline_mode(self):
        self.assertEqual(self.fails("cursor-store", {"offline": True})["code"], "offline")
        self.assertEqual(self.fails("cursor-store-download", {"id": 1, "file": 1, "offline": True})["code"], "offline")
        self.assertEqual(self.ok("cursor-store-download", {"id": 1411743, "file": 1, "offline": True}),
                         {"themes": [THEME]}, "a finished download needs no network")
        self.assertEqual(self.ok("cursor-store-previews", {"items": {"1": "https://evil.example/x.png"}}),
                         {"paths": {}, "failed": ["1"]})

    def test_the_save_that_picks_it_installs_it_and_review_says_so(self):
        themes = {row["name"]: row for row in self.ok("cursor-themes", {})["themes"]}
        self.assertTrue(themes[THEME]["downloaded"])
        preview = self.ok("preview", self.request())
        self.assertIn({"page": "Input", "label": f"Install cursor theme: {THEME} (into ~/data/icons)"},
                      preview["summary"])
        self.assertTrue(self.ok("save", self.request())["saved"])
        self.assertEqual((self.installed / "cursors" / "left_ptr").read_bytes(), CURSOR)
        self.assertEqual(os.readlink(self.installed / "cursors" / "default"), "left_ptr")

    def test_a_queued_removal_is_reviewed_and_done_by_the_save(self):
        self.assertTrue(self.ok("save", self.request())["saved"])
        state = self.ok("read", {"config": str(self.config)})
        picked = {"config": str(self.config), "changes": {"revision": state["revision"], "cursor_remove": [THEME]}}
        self.assertIn("pick another", self.fails("preview", picked)["error"], "not the theme in use")
        request = {"config": str(self.config), "changes": {"revision": state["revision"], "cursor_remove": [THEME],
                                                          "fields": {"input.cursor.theme": {"value": ""}}}}
        preview = self.ok("preview", request)
        self.assertIn({"page": "Input", "label": f"Remove cursor theme: {THEME} (from ~/data/icons/{THEME})"},
                      preview["summary"])
        report = self.ok("save", request)
        self.assertTrue(report["saved"])
        self.assertFalse(self.installed.exists(), "removed after the config was written")

    def test_any_theme_in_a_home_folder_can_go_but_not_umbriels_default(self):
        mine = self.root / ".icons" / "Mine"
        (mine / "cursors").mkdir(parents=True)
        (mine / "cursors" / "left_ptr").write_bytes(CURSOR)
        (self.root / ".icons" / "default").mkdir()
        (self.root / ".icons" / "default" / "index.theme").write_text("[Icon Theme]\nInherits=Mine\n")
        rows = {row["name"]: row for row in self.ok("cursor-themes", {})["themes"]}
        self.assertTrue(rows["Mine"]["removable"] and rows["Mine"]["protected"], "inherited by default")
        self.assertTrue(rows[THEME]["removable"] and not rows[THEME]["protected"], "a download")
        state = self.ok("read", {"config": str(self.config)})
        request = {"config": str(self.config), "changes": {"revision": state["revision"], "cursor_remove": ["Mine"]}}
        self.assertIn("Umbriel's default", self.fails("save", request)["error"])
        (self.root / ".icons" / "default" / "index.theme").write_text("[Icon Theme]\nInherits=Adwaita\n")
        preview = self.ok("preview", request)
        self.assertIn({"page": "Input", "label": "Delete cursor theme: Mine (~/.icons/Mine, for good)"},
                      preview["summary"])
        self.assertTrue(self.ok("save", request)["saved"])
        self.assertFalse(mine.exists())
        self.assertNotIn("Mine", {row["name"] for row in self.ok("cursor-themes", {})["themes"]})

    def test_the_folder_opens_in_the_file_manager_once_it_exists(self):
        self.assertEqual(self.fails("open-cursor-folder", {})["code"], "missing", "never made by the button")
        self.assertFalse((self.root / "data" / "icons").exists())
        (self.root / "data" / "icons").mkdir()
        tools = self.root / "tools"
        tools.mkdir()
        log = self.root / "xdg-open.log"
        (tools / "xdg-open").write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {log}\n")
        (tools / "xdg-open").chmod(0o755)
        env = {**self.env, "PATH": str(tools) + os.pathsep + self.env["PATH"]}
        self.assertEqual(self.ok("open-cursor-folder", {}, env=env)["folder"], str(self.root / "data" / "icons"))
        for _ in range(50):
            if log.exists():
                break
            time.sleep(0.05)
        self.assertEqual(log.read_text().strip(), str(self.root / "data" / "icons"))

    def test_sigterm_after_the_marker_leaves_known_files_and_no_config_change(self):
        result = self.interrupted_save("marker")
        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertNotIn(THEME, self.config.read_text(), "the config wasn't written")
        marker = json.loads((self.installed / ".umbriel-settings.json").read_text())
        self.assertIn("cursors/left_ptr", marker["files"], "every file it may write is known")
        self.assertTrue(self.ok("save", self.request())["saved"], "the next save finishes the install")
        self.assertTrue((self.installed / "cursors" / "pointer").is_file())

    def test_sigterm_after_the_config_write_finds_the_theme_installed(self):
        result = self.interrupted_save("config")
        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertIn(THEME, self.config.read_text())
        self.assertTrue((self.installed / "cursors" / "left_ptr").is_file(), "installed before the config")

    def test_a_full_disk_fails_the_save_and_leaves_no_half_files(self):
        result = self.interrupted_save("full")
        self.assertIn("No space left on device", json.loads(result.stdout)["error"])
        self.assertNotIn(THEME, self.config.read_text())
        self.assertEqual(list(self.installed.glob("**/*.tmp")), [], "atomic writes leave no temp files")
        self.assertTrue(self.ok("save", self.request())["saved"], "the next attempt works")


if __name__ == "__main__":
    unittest.main()
