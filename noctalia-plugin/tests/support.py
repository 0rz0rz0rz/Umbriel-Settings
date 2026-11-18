"""Shared fixtures for the plugin tests: temp XDG dirs, a fake `umbriel`, and helper calls like the panel's."""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]  # noctalia-plugin/
PLUGIN = PLUGIN_ROOT / "umbriel-settings"
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
    """A temp root holding XDG_DATA_HOME (data/), XDG_CONFIG_HOME (xdg-config/) and XDG_DATA_DIRS (share/)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {
            **os.environ,
            "XDG_DATA_HOME": str(self.root / "data"),
            "XDG_CONFIG_HOME": str(self.root / "xdg-config"),
            "XDG_DATA_DIRS": str(self.root / "share"),  # not the machine's installed apps
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def reply(self, command, request=None, env=None):
        """Run the helper as the panel does and return its whole reply ({ok, result} or {ok, error, code})."""
        args = [sys.executable, "-B", str(HELPER), command]
        if request is not None:
            request_file = self.root / "request.json"
            request_file.write_text(json.dumps(request), encoding="utf-8")
            args += ["--request", str(request_file)]
        result = subprocess.run(args, env=env or self.env, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    call = reply  # desktop tests replace `call` with their own shorthand

    def ok(self, command, request=None, env=None):
        reply = self.reply(command, request, env)
        self.assertTrue(reply["ok"], reply)
        return reply["result"]

    def fails(self, command, request=None, env=None):
        reply = self.reply(command, request, env)
        self.assertFalse(reply["ok"], reply)
        return reply

    def expect(self, command, request, success=True, env=None):
        """The result when `success`, else the error message."""
        return self.ok(command, request, env) if success else self.fails(command, request, env)["error"]


class ConfigTestCase(HelperTestCase):
    """HelperTestCase plus CONFIG at `self.config` and FAKE_UMBRIEL first on PATH."""

    def setUp(self):
        super().setUp()
        self.config = self.root / "umbriel" / "config.toml"
        self.config.parent.mkdir()
        self.config.write_text(CONFIG, encoding="utf-8")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "umbriel"
        fake.write_text(f"#!{sys.executable}\n" + FAKE_UMBRIEL)
        fake.chmod(0o755)
        self.env["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
