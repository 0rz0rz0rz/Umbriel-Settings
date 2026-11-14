import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_umbriel_settings import CONFIG, FAKE_UMBRIEL

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "umbriel-settings"
HELPER = PLUGIN / "umbriel_settings.py"


@unittest.skipUnless(shutil.which("lua"), "lua is required for the panel harness")
class PanelHarnessTests(unittest.TestCase):
    """Runs the Luau panel under plain Lua with a mocked API; helper replies come from the real helper."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "umbriel"
        fake.write_text(f"#!{sys.executable}\n" + FAKE_UMBRIEL)
        fake.chmod(0o755)
        self.config = self.root / "config.toml"
        self.config.write_text(CONFIG)
        self.env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
                    "XDG_DATA_HOME": str(self.root / "data"), "XDG_CONFIG_HOME": str(self.root / "xdg"),
                    "PYTHONDONTWRITEBYTECODE": "1"}

    def helper(self, command, request):
        request_file = self.root / "request.json"
        request_file.write_text(json.dumps(request))
        result = subprocess.run([sys.executable, "-B", str(HELPER), command, "--request", str(request_file)],
                                env=self.env, capture_output=True, text=True, check=True)
        reply = json.loads(result.stdout)
        self.assertTrue(reply["ok"], reply)
        return reply["result"]

    def test_panel_and_app_flows(self):
        fixtures = self.root / "fixtures"
        fixtures.mkdir()
        meta = self.helper("meta", {})
        (fixtures / "meta.json").write_text(json.dumps(meta["meta"]))
        (fixtures / "search.json").write_text(json.dumps(meta["search"]))
        state = self.helper("read", {"config": str(self.config)})
        (fixtures / "state.json").write_text(json.dumps(state))
        (fixtures / "desktop.json").write_text(json.dumps(self.helper("desktop", {})))
        saved = self.helper("save", {"config": str(self.config), "changes": {
            "revision": state["revision"], "fields": {"general.mod_key": {"value": "Alt"}}}})
        (fixtures / "saved.json").write_text(json.dumps(saved))
        for script, marker in (("panel_test.lua", "panel ok"), ("app_test.lua", "app ok")):
            with self.subTest(script=script):
                result = subprocess.run(["lua", str(ROOT / "tests" / script), str(PLUGIN), str(fixtures)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(marker, result.stdout)

    def test_bar_shows_unsaved_count_and_toggles_panel(self):
        manifest = (PLUGIN / "plugin.toml").read_text()
        self.assertRegex(manifest, r'\[\[widget\]\]\s+id\s*=\s*"settings"\s+entry\s*=\s*"bar\.luau"')
        self.assertRegex(manifest, r'\[\[panel\]\]\s+id\s*=\s*"folders"')
        subprocess.run(["lua", str(ROOT / "tests" / "bar_test.lua"), str(PLUGIN / "bar.luau")], check=True)


if __name__ == "__main__":
    unittest.main()
