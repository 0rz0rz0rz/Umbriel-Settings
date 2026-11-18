import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest
import unittest.mock
from pathlib import Path

import support
from support import CONFIG, HELPER, ConfigTestCase

ROOT = Path(__file__).resolve().parents[2]


class HelperTestCase(ConfigTestCase):
    def read(self):
        return self.ok("read", {"config": str(self.config)})

    def save(self, state, **changes):
        return self.ok("save", {"config": str(self.config),
                                "changes": {"revision": state["revision"], **changes}})

    def config_dir(self):
        identity = hashlib.sha256(str(self.config).encode()).hexdigest()[:20]
        return self.root / "data" / "umbriel-settings" / "configs" / identity


class MetaAndReadTests(HelperTestCase):
    def test_meta_files_split_search_text(self):
        out = self.root / "meta"
        response = self.root / "response.json"
        request = self.root / "req.json"
        request.write_text(json.dumps({"out_dir": str(out)}))
        result = subprocess.run(
            [sys.executable, "-B", str(HELPER), "meta", "--request", str(request), "--response", str(response)],
            env=self.env, capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(result.stdout), {"ok": True})
        paths = json.loads(response.read_text())
        meta = json.loads(Path(paths["meta"]).read_text())
        search = dict(json.loads(Path(paths["search"]).read_text()))
        self.assertEqual(meta["fields"]["general.mod_key"]["default"], "Super")
        self.assertEqual(meta["fields"]["appearance.border_width"]["max"], 100)
        self.assertNotIn("search", meta["fields"]["general.mod_key"])
        self.assertIn("modifier", search["general.mod_key"])
        self.assertIn("window_rule:match.app_id", meta["fields"])
        # rule fields have no default; the app's fallback is only the starting value
        floating = meta["fields"]["window_rule:default_floating"]
        self.assertIsNone(floating["default"])
        self.assertTrue(floating["initial"])
        self.assertEqual(meta["pages"]["Effects"]["editors"], ["effect_preset", "effect_pool"])
        self.assertEqual(meta["schema"]["revision"], "r1")
        # the fake schema has three options, all covered; most GUI settings are missing from it
        self.assertEqual(meta["schema"]["missing"], [])
        self.assertIn("layout.gap", meta["schema"]["stale"])
        self.assertNotIn("general.mod_key", meta["schema"]["stale"])

    def test_read_returns_fields_entries_maps_and_keybinds(self):
        state = self.read()
        self.assertEqual(state["fields"]["general.mod_key"], "Super")
        self.assertIsNone(state["fields"]["appearance.border_width"])
        rule = state["editors"]["window_rule"][0]
        self.assertEqual(rule["title"], "1. firefox (app id)")
        self.assertTrue(rule["auto"])
        self.assertEqual(rule["values"]["opacity"], 0.9)
        self.assertEqual(state["maps"]["environment"], [["QT_QPA_PLATFORM", "wayland"]])
        self.assertEqual([r["key"] for r in state["keybinds"]["rows"]], ["super+Return", "super+q"])

    def test_symlinked_config_is_refused(self):
        link = self.root / "link.toml"
        link.symlink_to(self.config)
        reply = self.fails("read", {"config": str(link)})
        self.assertIn("symlink", reply["error"])

    def test_missing_tomlkit_is_reported(self):
        blocker = self.root / "block" / "tomlkit"
        blocker.mkdir(parents=True)
        (blocker / "__init__.py").write_text("raise ImportError('blocked')\n")
        env = {**self.env, "PYTHONPATH": str(blocker.parent)}
        reply = self.fails("read", {"config": str(self.config)}, env)
        self.assertEqual(reply["code"], "missing_dependency")



class SaveTests(HelperTestCase):
    def test_field_edit_keeps_comments_and_backs_up(self):
        state = self.read()
        report = self.save(state, fields={"general.mod_key": {"value": "Alt"},
                                          "general.show_cheatsheet": {"unset": True},
                                          "appearance.border_width": {"value": 8.0}})
        self.assertTrue(report["saved"])
        text = self.config.read_text()
        self.assertIn('mod_key = "Alt" # main modifier', text)
        self.assertNotIn("show_cheatsheet", text)
        self.assertIn("border_width = 8\n", text)
        self.assertEqual(Path(report["backup"]).read_text(), CONFIG)
        self.assertEqual(report["state"]["fields"]["general.mod_key"], "Alt")
        labels = {(item["label"], item["new"]) for item in report["summary"]}
        self.assertIn(("Mod key", "Alt"), labels)

    def test_saves_wait_for_another_writer_but_reads_do_not(self):
        state = self.read()
        sys.path.insert(0, str(HELPER.parent))
        self.addCleanup(sys.path.remove, str(HELPER.parent))
        from umbriel_core import paths

        held = threading.Event()

        def other_writer():
            with paths.write_lock(str(self.root / "data" / "umbriel-settings")):
                held.set()
                time.sleep(0.6)
        writer = threading.Thread(target=other_writer)
        writer.start()
        self.addCleanup(writer.join)
        held.wait(5)
        started = time.monotonic()
        self.read()
        self.assertLess(time.monotonic() - started, 0.6, "a read does not take the write lock")
        report = self.save(state, fields={"general.mod_key": {"value": "Alt"}})
        self.assertTrue(report["saved"])
        self.assertFalse(writer.is_alive(), "the save waited until the other writer was done")

    def test_failures_after_the_write_are_warnings(self):
        state = self.read()
        remembered = self.root / "data" / "umbriel-settings" / "gui-config-path"
        remembered.mkdir(parents=True)  # a directory where the remembered path goes: that write fails
        report = self.ok("save", {"config": str(self.config), "remember_path": True,
                                  "changes": {"revision": state["revision"],
                                              "fields": {"general.mod_key": {"value": "Alt"}}}})
        self.assertTrue(report["saved"])
        self.assertIn("could not be remembered", report["warnings"][0])
        self.assertEqual(report["state"]["fields"]["general.mod_key"], "Alt")

    def test_save_removes_stale_temporary_files(self):
        old = self.config.parent / ".config.toml.abc123.tmp"
        fresh = self.config.parent / ".umbriel-settings-xyz.toml"
        for path in (old, fresh):
            path.write_text("x")
        os.utime(old, (time.time() - 3600, time.time() - 3600))
        self.save(self.read(), fields={"general.mod_key": {"value": "Alt"}})
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists(), "a recent one may belong to a running save")

    def test_preview_does_not_write(self):
        state = self.read()
        report = self.ok("preview", {"config": str(self.config), "changes": {
            "revision": state["revision"], "fields": {"general.mod_key": {"value": "Ctrl"}}}})
        self.assertTrue(report["changed"])
        self.assertIn("[general]", [section["title"] for section in report["sections"]])
        self.assertTrue(report["validation"]["valid"])
        self.assertEqual(self.config.read_text(), CONFIG)

    def test_invalid_values_and_conflicts_write_nothing(self):
        state = self.read()
        reply = self.fails("save", {"config": str(self.config), "changes": {
            "revision": state["revision"], "fields": {"appearance.border_width": {"value": 500}}}})
        self.assertIn("between 0 and 100", reply["error"])
        self.config.write_text(CONFIG + "\n# edited elsewhere\n")
        reply = self.fails("save", {"config": str(self.config), "changes": {
            "revision": state["revision"], "fields": {"general.mod_key": {"value": "Alt"}}}})
        self.assertIn("Reload", reply["error"])

    def test_validation_errors_block_the_save(self):
        state = self.read()
        report = self.ok("save", {"config": str(self.config), "changes": {
            "revision": state["revision"], "fields": {"general.mod_key": {"value": "Alt"}}}},
            env={**self.env, "VALID": "no"})
        self.assertFalse(report["saved"])
        self.assertEqual(report["validation"]["diagnostics"][0]["field"], "general.mod_key")
        self.assertEqual(self.config.read_text(), CONFIG)

    def test_entry_operations_labels_and_maps(self):
        state = self.read()
        report = self.save(state, entries=[
            {"editor": "window_rule", "op": "add"},
            {"editor": "window_rule", "op": "set", "index": 1, "field": "match.app_id", "value": "^kitty$"},
            {"editor": "window_rule", "op": "label", "index": 1, "text": "Terminal"},
            {"editor": "window_rule", "op": "move", "index": 1, "to": 0},
            {"editor": "output", "op": "add", "name": "DP-1"},
            {"editor": "output", "op": "set", "index": 0, "field": "scale", "value": 1.5},
        ], maps=[
            {"editor": "environment", "op": "set", "name": "EDITOR", "value": "nvim"},
            {"editor": "beziers", "op": "set", "name": "soft", "value": "[0.2, 0, 0, 1]"},
        ])
        text = self.config.read_text()
        self.assertLess(text.index("# GUI rule name: Terminal"), text.index("firefox"))
        self.assertIn('app_id = "^kitty$"', text)
        self.assertIn("[output.DP-1]", text)
        self.assertIn('EDITOR = "nvim"', text)
        rules = report["state"]["editors"]["window_rule"]
        self.assertEqual([r["title"] for r in rules], ["1. Terminal", "2. firefox (app id)"])
        labels = json.loads((self.config_dir() / "gui-labels.json").read_text())
        self.assertEqual(labels, {"window_rule": ["Terminal", ""]})

    def test_bad_map_values_are_rejected(self):
        state = self.read()
        for op, message in (
            ({"editor": "environment", "op": "set", "name": "WAYLAND_DISPLAY", "value": "x"}, "owned by Umbriel"),
            ({"editor": "beziers", "op": "set", "name": "b", "value": "[2, 0, 0, 1]"}, "between 0 and 1"),
        ):
            reply = self.fails("save", {"config": str(self.config), "changes": {
                "revision": state["revision"], "maps": [op]}})
            self.assertIn(message, reply["error"])

    def test_keybinds_respect_locks_and_groups(self):
        lock_dir = self.config_dir()
        lock_dir.mkdir(parents=True)
        (lock_dir / "gui-locked-keybinds.json").write_text('["super+q"]')
        state = self.read()
        self.assertTrue(state["keybinds"]["rows"][1]["locked"])
        rows = [{"key": "super+Return", "action": "spawn foot", "group": "Apps"},
                {"key": "super+d", "action": "spawn fuzzel", "opts": {"repeat": False}}]
        report = self.save(state, keybinds={"rows": rows, "groups": ["Apps"], "locks": ["super+q"]})
        text = self.config.read_text()
        self.assertIn('"super+Return" = "spawn foot"', text)
        self.assertIn('"super+q" = "window-close"', text)  # locked, so not removed
        self.assertIn("# Additional keybinds", text)
        self.assertIn('"groups":["Apps"]', text)
        self.assertEqual(report["state"]["keybinds"]["groups"], ["Apps"])
        state = report["state"]
        reply = self.fails("save", {"config": str(self.config), "changes": {
            "revision": state["revision"],
            "keybinds": {"rows": [{"key": "super+q", "action": "spawn x"}], "groups": [], "locks": ["super+q"]}}})
        self.assertIn("locked", reply["error"])
        reply = self.fails("save", {"config": str(self.config), "changes": {
            "revision": state["revision"],
            "keybinds": {"rows": [{"key": "super+a", "action": "spawn"}], "groups": [], "locks": []}}})
        self.assertIn("command after", reply["error"])

    def test_sorted_keybinds_are_written_in_list_order(self):
        """The keybinds page sends rows in display order (groups in order); the file follows, comments stay."""
        state = self.read()
        rows = [{"key": "super+q", "action": "window-close", "group": "Windows"},
                {"key": "super+Return", "action": "spawn kitty", "group": "Apps"}]
        report = self.save(state, keybinds={"rows": rows, "groups": ["Windows", "Apps"], "locks": []})
        text = self.config.read_text()
        section = text[text.index("[keybinds]"):text.index("[[window_rule]]")]
        self.assertLess(section.index('"super+q"'), section.index('"super+Return"'), section)
        self.assertIn("# launchers", section)
        self.assertIn('"groups":["Windows","Apps"]', section)
        self.assertEqual([row["key"] for row in report["state"]["keybinds"]["rows"]], ["super+q", "super+Return"])
        self.assertEqual(report["state"]["keybinds"]["groups"], ["Windows", "Apps"])


class ConfigPathTests(HelperTestCase):
    def test_uses_the_path_remembered_by_the_app(self):
        saved = self.root / "data" / "umbriel-settings" / "gui-config-path"
        saved.parent.mkdir(parents=True)
        saved.write_text(str(self.config) + "\n")
        self.assertEqual(self.ok("read")["path"], str(self.config))

    def test_set_config_remembers_the_choice(self):
        other = self.root / "other.toml"
        other.write_text("[general]\n")
        state = self.ok("set-config", {"config": str(other)})
        self.assertEqual(state["path"], str(other))
        self.assertEqual(self.ok("read")["path"], str(other))
        self.assertIn("does not exist", self.fails("read", {"config": str(self.root / "nope.toml")})["error"])


@unittest.skipUnless(shutil.which("umbriel") and os.path.isfile("/usr/share/umbriel/config.toml"),
                     "needs the installed umbriel CLI and its stock config")
class RealUmbrielTests(support.HelperTestCase):  # no fake: the installed `umbriel` validates
    def test_stock_config_round_trip_validates(self):
        config = self.root / "config.toml"
        shutil.copy("/usr/share/umbriel/config.toml", config)
        state = self.ok("read", {"config": str(config)})
        keybinds = state["keybinds"]["rows"]
        report = self.ok("save", {"config": str(config), "changes": {
            "revision": state["revision"],
            "fields": {"appearance.border_width": {"value": 3}},
            "keybinds": {"rows": keybinds + [{"key": "Mod+Shift+F12", "action": "spawn true"}],
                         "groups": ["Test"], "locks": []},
        }})
        self.assertTrue(report["saved"], report)
        self.assertTrue(report["validation"]["valid"], report["validation"])
        text = config.read_text()
        self.assertIn("border_width = 3", text)
        self.assertIn('"Mod+Shift+F12" = "spawn true"', text)


class BackupAndDesktopTests(HelperTestCase):
    def test_backups_list_restore_and_delete(self):
        state = self.read()
        report = self.save(state, fields={"general.mod_key": {"value": "Alt"}})
        listing = self.ok("backups", {"config": str(self.config)})
        self.assertEqual([b["path"] for b in listing["backups"]], [report["backup"]])
        diff = self.ok("backup-diff", {"config": str(self.config), "snapshot": report["backup"]})["diff"]
        self.assertIn('+mod_key = "Super"', diff)
        restored = self.ok("restore", {"config": str(self.config), "snapshot": report["backup"],
                                       "revision": report["state"]["revision"]})
        self.assertEqual(self.config.read_text(), CONFIG)
        self.assertEqual(len(restored["backups"]["backups"]), 2)
        deleted = self.ok("delete-backups", {"config": str(self.config),
                                             "snapshots": [report["backup"], "/etc/passwd"]})
        self.assertEqual(len(deleted["deleted"]), 1)
        self.assertEqual(len(deleted["errors"]), 1)
        self.assertTrue(os.path.exists("/etc/passwd"))

    def test_restore_keeps_the_restored_backup_when_pruning(self):
        state = self.read()
        report = self.save(state, fields={"general.mod_key": {"value": "Alt"}})
        directory = os.path.dirname(report["backup"])
        for index in range(12):
            with open(os.path.join(directory, f"config.toml.29990101-{index:02d}.bak"), "w") as handle:
                handle.write(CONFIG)
        listing = self.ok("backups", {"config": str(self.config)})["backups"]
        oldest = min(item["path"] for item in listing)
        self.assertEqual(oldest, report["backup"])
        restored = self.ok("restore", {"config": str(self.config), "snapshot": oldest,
                                       "revision": self.read()["revision"]})
        kept = [item["path"] for item in restored["backups"]["backups"]]
        self.assertEqual(len(kept), 10)
        self.assertIn(oldest, kept, "the restored backup is never pruned")

    def test_desktop_read_and_save(self):
        xdg = self.root / "xdg-config"
        xdg.mkdir()
        (xdg / "user-dirs.dirs").write_text('# keep\nXDG_DESKTOP_DIR="$HOME/Desktop"\n')
        state = self.ok("desktop")
        self.assertEqual(state["userdirs"]["values"], {"DESKTOP": "$HOME/Desktop"})
        result = self.ok("desktop-save", {"userdirs": {
            "revision": state["userdirs"]["revision"], "changes": {"DESKTOP": "$HOME/Schreibtisch"}}})
        reread = self.ok("desktop")["userdirs"]
        self.assertEqual(reread["values"]["DESKTOP"], "$HOME/Schreibtisch")
        self.assertEqual(result["userdirs"], {"revision": reread["revision"]})
        self.assertIn("# keep", (xdg / "user-dirs.dirs").read_text())
        self.assertEqual(self.ok("extension", {"extension": "pdf"})["mime"], "application/pdf")

    def test_desktop_save_keeps_the_part_that_was_written(self):
        xdg = self.root / "xdg-config"
        xdg.mkdir()
        (xdg / "user-dirs.dirs").write_text('XDG_DESKTOP_DIR="$HOME/Desktop"\n')
        target = self.root / "real-mimeapps.list"
        target.write_text("[Default Applications]\n")
        (xdg / "mimeapps.list").symlink_to(target)
        state = self.ok("desktop")
        result = self.ok("desktop-save", {
            "userdirs": {"revision": state["userdirs"]["revision"], "changes": {"DESKTOP": "$HOME/Tisch"}},
            "apps": {"revision": state["apps"]["revision"],
                     "changes": [{"kind": "mime", "key": "application/example", "value": "a.desktop"}]}})
        self.assertIn("symlink", result["errors"]["apps"])
        self.assertEqual(result["userdirs"]["revision"], self.ok("desktop")["userdirs"]["revision"])
        self.assertIn("Tisch", (xdg / "user-dirs.dirs").read_text())
        self.assertEqual(target.read_text(), "[Default Applications]\n")

    def test_unreadable_user_dirs_do_not_hide_default_apps(self):
        xdg = self.root / "xdg-config"
        xdg.mkdir()
        (xdg / "user-dirs.dirs").write_bytes(b'XDG_DESKTOP_DIR="\xff"\n')
        state = self.ok("desktop")
        self.assertIn("user-dirs.dirs is not UTF-8", state["userdirs"]["error"])
        self.assertIn("roles", state["apps"])

    def test_restore_reports_an_invalid_backup_but_restores_it(self):
        state = self.read()
        report = self.save(state, fields={"general.mod_key": {"value": "Alt"}})
        restored = self.ok("restore", {"config": str(self.config), "snapshot": report["backup"],
                                       "revision": report["state"]["revision"]}, env={**self.env, "VALID": "no"})
        self.assertIn("Umbriel reports problems", restored["warnings"][0])
        self.assertEqual(self.config.read_text(), CONFIG)
        self.assertIsNotNone(restored["state"])

    def test_wrongly_shaped_desktop_requests_are_rejected(self):
        for request in ({"userdirs": "x"}, {"apps": ["x"]}):
            self.assertEqual(self.fails("desktop-save", request)["code"], "error", request)

    def test_unexpected_errors_still_answer(self):
        """A helper bug must still produce a reply, or the app's UI would wait for it forever."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("umbriel_settings_under_test", HELPER)
        module = importlib.util.module_from_spec(spec)
        saved = list(sys.path)
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = saved

        def broken(request):
            raise RuntimeError("boom")
        module.COMMANDS["about"] = broken
        with unittest.mock.patch("sys.stderr"):
            reply = json.loads(module.run(["about"]))
        self.assertEqual((reply["ok"], reply["code"]), (False, "internal"))
        self.assertIn("RuntimeError: boom", reply["error"])

    def test_wrongly_shaped_sections_are_reported_not_crashed(self):
        self.config.write_text(CONFIG + '\n[[output]]\nname = "DP-1"\n')
        reply = self.fails("read", {"config": str(self.config)})
        self.assertIn("[output.NAME]", reply["error"])

    def test_launched_programs_get_the_host_python_environment_back(self):
        """Inside the AppImage the app runs this helper in-process; xdg-open must not see the bundled Python."""
        record = self.root / "xdg-open.env"
        opener = self.root / "bin" / "xdg-open"
        opener.write_text(f'#!/bin/sh\nenv > "{record}.tmp" && mv "{record}.tmp" "{record}"\n')
        opener.chmod(0o755)
        env = {**self.env, "UMBRIEL_SETTINGS_APPIMAGE_ENV": "1", "PYTHONNOUSERSITE": "1",
               "UMBRIEL_SETTINGS_HOST_PYTHONPATH": "/host/lib"}
        reply = self.call("open-config", {"config": str(self.config)}, env)
        self.assertTrue(reply["ok"], reply)
        deadline = time.monotonic() + 5
        while not record.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        lines = record.read_text().splitlines()
        self.assertIn("PYTHONPATH=/host/lib", lines)
        self.assertFalse([line for line in lines if line.startswith(("PYTHONNOUSERSITE=", "UMBRIEL_SETTINGS_"))])


class EditorAndAboutTests(HelperTestCase):
    def wait_for(self, path):
        deadline = time.monotonic() + 5
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        return path.read_text()

    def test_open_config_uses_the_saved_editor_command(self):
        record = self.root / "editor.args"
        editor = self.root / "bin" / "my-editor"
        editor.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{record}.tmp" && mv "{record}.tmp" "{record}"\n')
        editor.chmod(0o755)
        self.assertEqual(self.ok("about")["editor"], "")
        self.assertEqual(self.ok("set-editor", {"editor": " my-editor --new-window "}), {"editor": "my-editor --new-window"})
        self.assertEqual(self.ok("about")["editor"], "my-editor --new-window")
        self.ok("open-config", {"config": str(self.config)})
        self.assertEqual(self.wait_for(record).splitlines(), ["--new-window", str(self.config)])
        self.assertEqual(self.ok("set-editor", {"editor": ""}), {"editor": ""})
        self.assertEqual(self.ok("about")["editor"], "")

    def test_set_editor_rejects_unknown_programs_and_bad_quoting(self):
        self.assertEqual(self.fails("set-editor", {"editor": "no-such-editor-xyz"})["code"], "missing_editor")
        self.assertIn("quotation", self.fails("set-editor", {"editor": "my 'editor"})["error"])
        self.fails("set-editor", {"editor": "sh\nrm"})
        self.assertEqual(self.ok("about")["editor"], "")

    def test_about_reports_and_sets_up_the_palette_template(self):
        self.assertFalse(self.ok("about")["palette"]["noctalia"])
        self.assertIn("not found", self.fails("palette-template", {})["error"])
        config = self.root / "xdg-config" / "noctalia" / "noctalia-config.toml"
        config.parent.mkdir(parents=True)
        config.write_text("# mine\n[shell]\nfont_family = \"Inter\"\n")
        palette = self.ok("palette-template", {})["palette"]
        self.assertEqual((palette["template"], palette["entry"], palette["palette"]), (True, True, False))
        self.assertTrue(config.read_text().startswith("# mine\n"))
        backups = self.root / "data" / "umbriel-settings" / "noctalia-backups"
        self.assertEqual(len(list(backups.glob("noctalia-config.toml.*.bak"))), 1)


class TitlebarFollowTests(HelperTestCase):
    def test_follow_converts_opacity_and_reports_state(self):
        self.assertEqual(self.ok("titlebar", {"config": str(self.config)})["fields"], {})
        noctalia = self.root / "xdg-config" / "noctalia" / "noctalia-config.toml"
        noctalia.parent.mkdir(parents=True)
        noctalia.write_text("")
        state = self.ok("titlebar-follow", {"config": str(self.config), "field": "background",
                                            "source": "kde_header", "opacity": 0.84})
        self.assertEqual(state["fields"]["background"]["alpha"], "D6")
        self.assertEqual(state["old_include"], "titlebar.toml")
        self.assertIn("post_hook", noctalia.read_text())
        self.assertIn("Opacity", self.fails("titlebar-follow", {"config": str(self.config), "field": "background",
                                                                "source": "kde", "opacity": 2})["error"])
        other = self.root / "other" / "config.toml"
        other.parent.mkdir()
        other.write_text("")
        self.assertEqual(self.ok("titlebar", {"config": str(other)})["fields"], {}, "following is per config")
        self.assertIn("background", self.ok("titlebar", {"config": str(self.config)})["fields"])
        self.assertIn("choose a title bar field", self.fails("titlebar-follow", {"config": str(self.config),
                      "source": "kde"})["error"].lower())


if __name__ == "__main__":
    unittest.main()
