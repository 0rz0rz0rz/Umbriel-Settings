import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
import threading
import time
import unittest
import unittest.mock
from pathlib import Path

from support import CONFIG, HELPER, ConfigTestCase, HelperTestCase

ROOT = Path(__file__).resolve().parents[2]


class ConfigHelperTestCase(ConfigTestCase):
    def read(self):
        return self.ok("read", {"config": str(self.config)})

    def save(self, state, **changes):
        return self.ok("save", {"config": str(self.config),
                                "changes": {"revision": state["revision"], **changes}})

    def config_dir(self):
        identity = hashlib.sha256(str(self.config).encode()).hexdigest()[:20]
        return self.root / "data" / "umbriel-settings" / "configs" / identity


class MetaAndReadTests(ConfigHelperTestCase):
    def test_old_run_files_of_dropped_callbacks_are_swept(self):
        run = self.root / "run"
        run.mkdir()
        old = [run / "titlebar-cleanup-1795278892897-1.req.json", run / "wait-live-1795276748361-10.res.json"]
        kept = [run / "outputs-1795276748361-9.res.json", run / "notes.json"]  # recent, not a run file
        for path in old + kept:
            path.write_text("{}")
        for path in old + kept[1:]:
            os.utime(path, (time.time() - 3600,) * 2)
        request, response = run / "about-1-1.req.json", run / "about-1-1.res.json"
        request.write_text("{}")
        result = subprocess.run(
            [sys.executable, "-B", str(HELPER), "about", "--request", str(request), "--response", str(response)],
            env=self.env, capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(result.stdout), {"ok": True})
        self.assertEqual(sorted(path.name for path in run.iterdir()),
                         sorted([request.name, response.name] + [path.name for path in kept]))

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



class SaveTests(ConfigHelperTestCase):
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

    def test_check_validates_an_unchanged_config(self):
        unchanged = {"config": str(self.config), "changes": {"revision": self.read()["revision"]}}
        self.assertFalse(self.ok("preview", unchanged)["validation"]["ran"])
        report = self.ok("preview", {**unchanged, "check": True}, env={**self.env, "VALID": "no"})
        self.assertFalse(report["changed"])
        self.assertEqual((report["validation"]["ran"], report["validation"]["valid"]), (True, False))

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

    def try_request(self, state, value="Alt"):
        return {"config": str(self.config), "trial": 15,
                "changes": {"revision": state["revision"], "fields": {"general.mod_key": {"value": value}}}}

    def test_a_try_arms_a_rollback_that_keep_ends(self):
        token = self.config_dir() / "trial.json"
        report = self.ok("save", self.try_request(self.read()))
        armed = json.loads(token.read_text())
        self.assertEqual((armed["id"], armed["backup"]), (report["trial"], report["backup"]))
        self.assertEqual(armed["revision"], report["state"]["revision"]["config"])
        self.assertEqual(token.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.fails("save", self.try_request(report["state"], "Ctrl"))["code"], "busy",
                         "a second Try waits for the first")
        self.assertEqual(self.ok("trial-end", {"config": str(self.config), "trial": "other"}),
                         {"ended": False, "message": "This Try already ended."})
        self.assertIn("trial", self.fails("trial-end", {"config": str(self.config)})["error"])
        self.assertEqual(self.ok("trial-end", {"config": str(self.config), "trial": report["trial"]}), {"ended": True})
        self.assertFalse(token.exists())
        # a rejected try arms nothing
        self.ok("save", self.try_request(report["state"], "Ctrl"), env={**self.env, "VALID": "no"})
        self.assertFalse(token.exists())
        self.assertEqual(self.fails("save", {**self.try_request(report["state"]), "trial": 0})["error"],
                         "trial must be a number of seconds from 1 to 120.")

    def interrupted_save(self, request, how):
        """Run `save` as the panel does, but with the config write either followed by a SIGTERM (Noctalia's
        helper timeout) or failing (a full disk)."""
        wrapper = textwrap.dedent("""\
            import importlib.util, os, signal, sys
            helper, how, config = sys.argv[1:4]
            spec = importlib.util.spec_from_file_location("umbriel_settings_under_test", helper)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            from umbriel_core import session
            real = session.write_text_file
            def write(path, text, *rest):
                if os.path.abspath(path) != config:
                    return real(path, text, *rest)
                if how == "full":
                    raise OSError(28, "No space left on device")
                real(path, text, *rest)
                os.kill(os.getpid(), signal.SIGTERM)
            session.write_text_file = write
            sys.exit(module.main(sys.argv[4:]))
        """)
        request_file = self.root / "request.json"
        request_file.write_text(json.dumps(request), encoding="utf-8")
        return subprocess.run([sys.executable, "-I", "-c", wrapper, str(HELPER), how, str(self.config), "save",
                               "--request", str(request_file)], env=self.env, capture_output=True, text=True,
                              check=False)

    def test_an_interrupted_try_is_left_to_the_watcher(self):
        token = self.config_dir() / "trial.json"
        state = self.read()
        result = self.interrupted_save(self.try_request(state), "kill")
        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertIn('mod_key = "Alt"', self.config.read_text())
        armed = json.loads(token.read_text())  # the watcher still goes back
        self.assertEqual(armed["revision"], hashlib.sha256(self.config.read_bytes()).hexdigest())
        self.assertEqual(Path(armed["backup"]).read_text(), CONFIG)
        self.ok("trial-end", {"config": str(self.config), "trial": armed["id"]})
        # nothing written: no trial is left that would make the next Try wait
        result = self.interrupted_save(self.try_request(self.read(), "Ctrl"), "full")
        self.assertIn("No space left on device", json.loads(result.stdout)["error"])
        self.assertIn('mod_key = "Alt"', self.config.read_text())
        self.assertFalse(token.exists())

    def test_go_back_claims_the_trial_and_finds_the_watchers_result(self):
        token = self.config_dir() / "trial.json"
        report = self.ok("save", self.try_request(self.read()))
        restore = {"config": str(self.config), "snapshot": report["backup"], "revision": report["state"]["revision"],
                   "validate": False, "trial": report["trial"]}
        Path(report["backup"]).write_text("not = [toml")  # the restore fails: the watcher must still go back
        self.assertIn("not valid TOML", self.fails("restore", restore)["error"])
        self.assertTrue(token.exists())
        Path(report["backup"]).write_text(CONFIG)
        self.ok("restore", restore)
        self.assertFalse(token.exists())
        self.assertEqual(self.config.read_text(), CONFIG)
        reply = self.fails("restore", {**restore, "revision": self.read()["revision"]})
        self.assertEqual(reply["code"], "trial_over")
        # the watcher went back first: the panel's countdown, with the tried revision, learns that, not "conflict"
        report = self.ok("save", self.try_request(self.read()))
        token.unlink()
        (self.config_dir() / "trial.result.json").write_text(json.dumps(
            {"id": report["trial"], "restored": True, "reason": "restored"}))
        self.config.write_text(CONFIG)
        reply = self.fails("restore", {"config": str(self.config), "snapshot": report["backup"], "validate": False,
                                       "revision": report["state"]["revision"], "trial": report["trial"]})
        self.assertEqual((reply["code"], reply["error"]),
                         ("trial_over", "The previous display settings were already restored."))

    def test_backups_keep_a_pending_trys_rollback(self):
        older = self.save(self.read(), fields={"general.mod_key": {"value": "Ctrl"}})
        report = self.ok("save", self.try_request(older["state"]))
        request = {"config": str(self.config), "snapshots": [report["backup"], older["backup"]]}
        reply = self.ok("delete-backups", request)
        self.assertEqual(reply["deleted"], [os.path.basename(older["backup"])])
        self.assertEqual(reply["errors"], [f"{os.path.basename(report['backup'])}: kept until the running Try ends "
                                           "(it is its rollback)"])
        self.assertTrue(Path(report["backup"]).exists())
        self.ok("trial-end", {"config": str(self.config), "trial": report["trial"]})
        reply = self.ok("delete-backups", {**request, "snapshots": [report["backup"]]})
        self.assertEqual((reply["deleted"], reply["errors"]), ([os.path.basename(report["backup"])], []))

    def test_entry_operations_labels_and_maps(self):
        state = self.read()
        report = self.save(state, entries=[
            {"editor": "window_rule", "op": "add"},
            {"editor": "window_rule", "op": "set", "index": 1, "field": "match.app_id", "value": "^kitty$"},
            {"editor": "window_rule", "op": "label", "index": 1, "text": "Terminal"},
            {"editor": "window_rule", "op": "move", "index": 1, "to": 0},
            {"editor": "output", "op": "add", "name": "DP-1"},
            {"editor": "output", "op": "set", "index": 0, "field": "scale", "value": 1.5},
            {"editor": "output", "op": "label", "index": 0, "text": "  Desk   left "},
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
        self.assertEqual(labels, {"window_rule": ["Terminal", ""], "output": {"DP-1": "Desk left"}})
        self.assertEqual(report["state"]["editors"]["output"][0]["label"], "Desk left")
        self.assertNotIn("Desk", text)  # GUI-only, never in the config
        # removing the output drops its name; clearing a name drops it too
        state = self.read()
        self.save(state, entries=[{"editor": "output", "op": "remove", "index": 0}])
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


class ConfigPathTests(ConfigHelperTestCase):
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
class RealUmbrielTests(HelperTestCase):  # no fake: the installed `umbriel` validates
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


class BackupAndDesktopTests(ConfigHelperTestCase):
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
        reply = self.reply("open-config", {"config": str(self.config)}, env)
        self.assertTrue(reply["ok"], reply)
        deadline = time.monotonic() + 5
        while not record.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        lines = record.read_text().splitlines()
        self.assertIn("PYTHONPATH=/host/lib", lines)
        self.assertFalse([line for line in lines if line.startswith(("PYTHONNOUSERSITE=", "UMBRIEL_SETTINGS_"))])


class EditorAndAboutTests(ConfigHelperTestCase):
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
        self.assertEqual(self.ok("set-editor", {"editor": " my-editor --new-window "}),
                         {"editor": "my-editor --new-window"})
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


class TitlebarFollowTests(ConfigHelperTestCase):
    """Following Noctalia's palette starts and stops with the save that carries the intent, never before."""

    def setUp(self):
        super().setUp()
        self.noctalia = self.root / "xdg-config" / "noctalia" / "noctalia-config.toml"
        self.noctalia.parent.mkdir(parents=True)
        self.noctalia.write_text("")
        palette = self.root / "xdg-config" / "umbriel-settings" / "noctalia-palette.conf"
        palette.parent.mkdir(parents=True)
        palette.write_text("primary=#aa0000\nsurface=#101010\nsurface_container=#202020\nprimary_container=#303030\n")

    def save_follow(self, state, follow, value="#202020D6"):
        return self.ok("save", {"config": str(self.config), "changes": {"revision": state["revision"], "fields": {
            "colors.title_bar.background": {"value": value, "follow": follow}}}})

    def test_follow_starts_and_stops_with_the_save(self):
        state = self.ok("titlebar", {"config": str(self.config)})
        self.assertEqual(state["fields"], {})
        self.assertEqual(state["sources"]["background"], {"kde": "#303030", "kde_header": "#202020"})
        self.assertNotIn("post_hook", self.noctalia.read_text(), "reading writes nothing")
        intent = {"source": "kde_header", "alpha": "D6"}
        preview = self.ok("preview", {"config": str(self.config), "changes": {"revision": self.read()["revision"],
                          "fields": {"colors.title_bar.background": {"value": "#202020D6", "follow": intent}}}})
        self.assertIn("follows Noctalia (KDE header)", json.dumps(preview["summary"]))
        self.assertNotIn("post_hook", self.noctalia.read_text(), "a preview installs nothing")
        report = self.save_follow(self.read(), intent)
        self.assertNotIn("warnings", report)
        self.assertIn("post_hook", self.noctalia.read_text())
        self.assertEqual(self.ok("titlebar", {"config": str(self.config)})["fields"]["background"]["alpha"], "D6")
        other = self.root / "other" / "config.toml"
        other.parent.mkdir()
        other.write_text("")
        self.assertEqual(self.ok("titlebar", {"config": str(other)})["fields"], {}, "following is per config")
        self.save_follow(report["state"], False)
        self.assertNotIn("umbriel_titlebar", self.noctalia.read_text())
        self.assertFalse((self.root / "xdg-config" / "umbriel-settings" / "titlebar_apply.py").exists())

    def test_bad_intents_and_a_missing_noctalia_are_reported(self):
        state = self.read()
        self.assertIn("follow needs", self.fails("save", {"config": str(self.config), "changes": {
            "revision": state["revision"], "fields": {"colors.title_bar.background": {
                "value": "#202020D6", "follow": {"source": "gtk", "alpha": "D6"}}}}})["error"])
        self.assertIn("can't follow", self.fails("save", {"config": str(self.config), "changes": {
            "revision": state["revision"], "fields": {"general.mod_key": {"value": "Alt", "follow": False}}}})["error"])
        self.assertEqual(self.config.read_text(), CONFIG, "nothing is written for a bad intent")
        self.noctalia.unlink()
        report = self.save_follow(state, {"source": "kde", "alpha": "FF"}, "#303030FF")
        self.assertTrue(report["saved"])
        self.assertIn("could not follow Noctalia", " ".join(report["warnings"]))

    def test_cleanup_removes_every_following_config(self):
        self.save_follow(self.read(), {"source": "kde", "alpha": "FF"}, "#303030FF")
        self.assertEqual(self.ok("titlebar-cleanup", {}), {"followed": True})
        self.assertNotIn("umbriel_titlebar", self.noctalia.read_text())
        self.assertEqual(self.ok("titlebar", {"config": str(self.config)})["fields"], {})
        self.assertIn("colors.title_bar", self.config.read_text(), "the config keeps its last colors")


class LauncherTests(HelperTestCase):
    """`launch-app`: the standalone app started through its desktop entry."""

    def test_standalone_launcher_checks_entry_and_reports_errors(self):
        data = self.root / "data with spaces"
        desktop = data / "applications" / "umbriel-settings.desktop"
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        log = self.root / "launch-args"
        env = {
            **self.env, "XDG_DATA_HOME": str(data), "PATH": str(bin_dir),
            "LAUNCH_LOG": str(log),
        }

        def launch(**extra_env):
            return self.reply("launch-app", env={**env, **extra_env})

        reply = launch()
        self.assertIn("desktop entry not found", reply["error"])
        desktop.parent.mkdir(parents=True)
        desktop.write_text("[Desktop Entry]\n")
        self.assertIn("gio is not installed", launch()["error"])
        gio = bin_dir / "gio"
        gio.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$LAUNCH_LOG"\nexit "${LAUNCH_EXIT:-0}"\n')
        gio.chmod(0o755)
        self.assertEqual(launch(), {"ok": True, "result": {}})
        self.assertEqual(log.read_text().splitlines(), ["launch", str(desktop)])
        self.assertIn("exit code 9", launch(LAUNCH_EXIT="9")["error"])

    @unittest.skipUnless(shutil.which("gio"), "gio is required for the launcher integration test")
    def test_standalone_launcher_detaches_app_output(self):
        data = self.root / "data"
        desktop = data / "applications" / "umbriel-settings.desktop"
        desktop.parent.mkdir(parents=True)
        marker = self.root / "app-ran"
        app = self.root / "fake-app"
        app.write_text('#!/bin/sh\nsleep 0.3\nprintf "app output\\n" >&2\nprintf ready > "$LAUNCH_LOG"\n')
        app.chmod(0o755)
        desktop.write_text(f"[Desktop Entry]\nType=Application\nName=Test\nExec={app}\n")
        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        env = {
            **self.env, "HOME": str(self.root), "XDG_DATA_HOME": str(data),
            "XDG_RUNTIME_DIR": str(runtime), "DBUS_SESSION_BUS_ADDRESS": "unix:path=/nonexistent",
            "DISPLAY": "", "WAYLAND_DISPLAY": "", "LAUNCH_LOG": str(marker),
        }
        result = subprocess.run(
            [sys.executable, "-B", str(HELPER), "launch-app"],
            env=env, text=True, capture_output=True, timeout=5, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        deadline = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(marker.read_text(), "ready")


class LiveTests(ConfigHelperTestCase):
    def test_windows_and_layers_from_the_running_umbriel(self):
        windows = self.ok("windows")["windows"]
        self.assertEqual([(w["app_id"], w["count"], w["pattern"]) for w in windows],
                         [("firefox", 2, "^firefox$"), ("org.gajim.Gajim", 1, r"^org\.gajim\.Gajim$")])
        self.assertEqual(self.ok("layers")["layers"][0]["pattern"], "^noctalia-bar-default$")
        env = {**self.env, "PATH": str(self.root / "nowhere")}
        self.assertEqual(self.fails("windows", env=env)["code"], "missing_umbriel")

    def test_focused_window_gives_exact_patterns(self):
        window = self.ok("focused-window")["window"]
        self.assertEqual((window["pattern"], window["title_pattern"]), (r"^org\.gajim\.Gajim$", r"^Gajim \(2\)$"))

    def test_wait_live_answers_on_a_change_that_a_page_shows(self):
        env = {**self.env, "SUB_CHANGE": "windows"}
        # a title change is no change to the window list; a new app id is
        self.assertEqual(self.ok("wait-live", {"events": ["outputs", "windows"], "timeout": 10}, env=env),
                         {"event": "windows"})
        started = time.monotonic()
        self.assertEqual(self.ok("wait-live", {"events": ["outputs"], "timeout": 1}), {"event": None})
        self.assertLess(time.monotonic() - started, 5, "the umbriel subscribe process is stopped")
        self.assertIn("events must list", self.fails("wait-live", {"events": ["theme"]})["error"])
        missing = self.fails("wait-live", {"events": ["outputs"]}, env={**self.env, "PATH": str(self.root / "nowhere")})
        self.assertEqual(missing["code"], "missing_umbriel")

    def test_xkb_lists_layouts_with_the_active_one(self):
        rules = self.root / "xkb" / "rules"
        rules.mkdir(parents=True)
        (rules / "evdev.lst").write_text("! layout\n  de  German\n! variant\n  nodeadkeys  de: German (nd)\n")
        data = self.ok("xkb", env={**self.env, "XKB_CONFIG_ROOT": str(self.root / "xkb")})
        self.assertEqual((data["layouts"], data["current"]), ([{"name": "de", "desc": "German"}], "German"))
        missing = self.fails("xkb", env={**self.env, "XKB_CONFIG_ROOT": str(self.root / "none")})
        self.assertEqual(missing["code"], "missing_xkb")

    def test_run_action_sends_allowed_actions_only(self):
        log = self.root / "msg.log"
        env = {**self.env, "MSG_LOG": str(log)}
        self.ok("run-action", {"action": "spawn kitty --title 'a b'"}, env=env)
        self.ok("run-action", {"action": "window-focus-left"}, env=env)
        blocked = self.fails("run-action", {"action": "session-quit"}, env=env)
        self.assertEqual(blocked["code"], "blocked")
        self.assertEqual([json.loads(line) for line in log.read_text().splitlines()],
                         [["spawn", "kitty --title 'a b'"], ["window-focus-left"]])
        failed = self.fails("run-action", {"action": "nonsense"}, env={**env, "MSG_FAIL": "1"})
        self.assertEqual(failed["error"], "unknown action: nonsense")


class FileBrowserTests(ConfigHelperTestCase):
    """`list-dir` (the UI's file browser) and `pick-file` / `pick-folder`, which map the path it chose."""

    def pick(self, request, chosen):
        return self.ok("pick-file", {**request, "chosen": chosen})["path"]

    def test_pick_file_writes_paths_relative_to_the_config_when_asked(self):
        inside = str(self.config.parent / "shaders" / "glow.frag")
        request = {"config": str(self.config), "relative": True}
        self.assertEqual(self.pick(request, inside), "shaders/glow.frag")
        self.assertEqual(self.pick({**request, "relative": False}, inside), inside)
        self.assertEqual(self.pick(request, "/usr/share/x.frag"), "/usr/share/x.frag")
        self.assertEqual(self.ok("pick-file", request), {"cancelled": True})
        self.assertEqual(self.ok("pick-folder", {}), {"cancelled": True})

    def test_pick_file_is_relative_through_a_symlinked_config_folder(self):
        real = self.root / "dotfiles"
        (real / "shaders").mkdir(parents=True)
        (real / "shaders" / "glow.frag").write_text("")
        (real / "config.toml").write_text("")
        linked = self.root / "linked-config"
        linked.symlink_to(real)
        request = {"config": str(linked / "config.toml"), "relative": True}
        self.assertEqual(self.pick(request, str(real / "shaders" / "glow.frag")), "shaders/glow.frag")

    def test_pick_file_for_a_command_writes_an_apps_exec_line_or_the_quoted_program(self):
        apps = self.root / "apps"
        apps.mkdir()
        (apps / "foo.desktop").write_text("[Desktop Entry]\nName=Foo\nExec=foo  --new %U --pct=50%%\n"
                                          "[Desktop Action x]\nExec=foo --other\n")
        (apps / "empty.desktop").write_text("[Desktop Entry]\nName=Empty\n")
        request = {"command": True, "relative": True, "config": str(self.config)}
        self.assertEqual(self.pick(request, str(apps / "foo.desktop")), "foo --new --pct=50%")
        program = str(self.config.parent / "my tools" / "start.sh")  # quoted, and never relative
        self.assertEqual(self.pick(request, program), f"'{program}'")
        self.assertEqual(self.pick(request, "/usr/bin/kitty"), "/usr/bin/kitty")
        failed = self.fails("pick-file", {**request, "chosen": str(apps / "empty.desktop")})
        self.assertEqual(failed["code"], "no_command")

    def test_pick_folder_writes_home_as_a_variable(self):
        home = self.env.get("HOME") or os.path.expanduser("~")
        env = {**self.env, "HOME": home}
        self.assertEqual(self.ok("pick-folder", {"chosen": home + "/Music"}, env=env)["path"], "$HOME/Music")
        self.assertEqual(self.ok("pick-folder", {"chosen": "/srv/media"}, env=env)["path"], "/srv/media")

    def test_list_dir_lists_folders_then_matching_files_without_hidden_ones(self):
        folder = self.root / "browse"
        (folder / "Sub").mkdir(parents=True)
        (folder / ".hidden").mkdir()
        for name in ("b.ICC", "a.icm", "notes.txt", ".secret.icc"):
            (folder / name).write_text("")
        listing = self.ok("list-dir", {"path": str(folder), "filter": ["ICC profiles", "*.icc *.icm"]})
        self.assertEqual((listing["path"], listing["parent"]), (str(folder), str(self.root)))
        self.assertEqual((listing["folders"], listing["files"]), (["Sub"], ["a.icm", "b.ICC"]))
        self.assertEqual(self.ok("list-dir", {"path": str(folder), "folders": True})["files"], [])
        self.assertEqual(len(self.ok("list-dir", {"path": str(folder)})["files"]), 3)
        # no path: where the browser opens (start, else the config's folder)
        self.assertEqual(self.ok("list-dir", {"start": str(folder / "missing"), "config": str(self.config)})["path"],
                         str(self.config.parent))
        self.assertIsNone(self.ok("list-dir", {"path": "/"})["parent"])
        self.assertEqual(self.fails("list-dir", {"path": str(folder / "notes.txt")})["code"], "not_folder")


if __name__ == "__main__":
    unittest.main()
