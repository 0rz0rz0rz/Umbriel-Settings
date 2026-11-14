import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "noctalia-plugin" / "Umbriel-GUI-Plugin"
HELPER = PLUGIN / "umbriel_settings.py"

CONFIG = textwrap.dedent("""\
    # my config
    [general]
    mod_key = "Super" # main modifier
    show_cheatsheet = true

    [environment]
    QT_QPA_PLATFORM = "wayland"

    [keybinds]
    # launchers
    "super+Return" = "spawn kitty"
    "super+q" = "window-close"

    [[window_rule]]
    match = { app_id = "^org.mozilla.firefox$" }
    opacity = 0.9
""")

FAKE_UMBRIEL = textwrap.dedent("""\
    import json, os, sys
    if sys.argv[1:3] == ["config", "schema"]:
        print(json.dumps({"version": "test", "revision": "r1", "options": [
            {"path": "general.mod_key", "type": "enum", "default": "Super",
             "values": ["Super", "Alt", "Ctrl", "Shift"]},
            {"path": "appearance.border_width", "type": "int", "default": 5, "min": 0, "max": 100},
            {"path": "general.show_cheatsheet", "type": "bool", "default": True},
        ]}))
        raise SystemExit(0)
    valid = os.environ.get("VALID", "yes") == "yes"
    print(json.dumps({"valid": valid, "diagnostics": [] if valid else
                      [{"severity": "error", "message": "bad value for general.mod_key", "line": 3}]}))
    raise SystemExit(0 if valid else 1)
""")


class HelperTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "umbriel" / "config.toml"
        self.config.parent.mkdir()
        self.config.write_text(CONFIG, encoding="utf-8")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "umbriel"
        fake.write_text(f"#!{sys.executable}\n" + FAKE_UMBRIEL)
        fake.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
            "XDG_DATA_HOME": str(self.root / "data"),
            "XDG_CONFIG_HOME": str(self.root / "xdg-config"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def call(self, command, request=None, env=None):
        args = [sys.executable, "-B", str(HELPER), command]
        if request is not None:
            request_file = self.root / "request.json"
            request_file.write_text(json.dumps(request), encoding="utf-8")
            args += ["--request", str(request_file)]
        result = subprocess.run(args, env=env or self.env, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def ok(self, command, request=None):
        reply = self.call(command, request)
        self.assertTrue(reply["ok"], reply)
        return reply["result"]

    def fails(self, command, request=None, env=None):
        reply = self.call(command, request, env)
        self.assertFalse(reply["ok"], reply)
        return reply

    def read(self):
        return self.ok("read", {"config": str(self.config)})

    def save(self, state, **changes):
        return self.ok("save", {"config": str(self.config),
                                "changes": {"revision": state["revision"], **changes}})

    def config_dir(self):
        identity = hashlib.sha256(str(self.config).encode()).hexdigest()[:20]
        return self.root / "data" / "umbriel-config-gui" / "configs" / identity


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

    def test_vendored_core_matches_source(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "sync_plugin_core.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


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
        env = {**self.env, "VALID": "no"}
        request = self.root / "r.json"
        request.write_text(json.dumps({"config": str(self.config), "changes": {
            "revision": state["revision"], "fields": {"general.mod_key": {"value": "Alt"}}}}))
        out = subprocess.run([sys.executable, "-B", str(HELPER), "save", "--request", str(request)],
                             env=env, capture_output=True, text=True, check=True)
        report = json.loads(out.stdout)["result"]
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


class ConfigPathTests(HelperTestCase):
    def test_uses_the_path_remembered_by_the_app(self):
        saved = self.root / "data" / "umbriel-config-gui" / "gui-config-path"
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
class RealUmbrielTests(unittest.TestCase):
    def test_stock_config_round_trip_validates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "config.toml"
            shutil.copy("/usr/share/umbriel/config.toml", config)
            env = {**os.environ, "XDG_DATA_HOME": str(root / "data"), "PYTHONDONTWRITEBYTECODE": "1"}

            def call(command, request):
                request_file = root / "request.json"
                request_file.write_text(json.dumps(request))
                out = subprocess.run([sys.executable, "-B", str(HELPER), command, "--request", str(request_file)],
                                     env=env, capture_output=True, text=True, check=True)
                reply = json.loads(out.stdout)
                self.assertTrue(reply["ok"], reply)
                return reply["result"]

            state = call("read", {"config": str(config)})
            keybinds = state["keybinds"]["rows"]
            report = call("save", {"config": str(config), "changes": {
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

    def test_desktop_read_and_save(self):
        xdg = self.root / "xdg-config"
        xdg.mkdir()
        (xdg / "user-dirs.dirs").write_text('# keep\nXDG_DESKTOP_DIR="$HOME/Desktop"\n')
        state = self.ok("desktop")
        self.assertEqual(state["userdirs"]["values"], {"DESKTOP": "$HOME/Desktop"})
        result = self.ok("desktop-save", {"userdirs": {
            "revision": state["userdirs"]["revision"], "changes": {"DESKTOP": "$HOME/Schreibtisch"}}})
        self.assertEqual(result["userdirs"]["values"]["DESKTOP"], "$HOME/Schreibtisch")
        self.assertIn("# keep", (xdg / "user-dirs.dirs").read_text())
        self.assertEqual(self.ok("extension", {"extension": "pdf"})["mime"], "application/pdf")


if __name__ == "__main__":
    unittest.main()
