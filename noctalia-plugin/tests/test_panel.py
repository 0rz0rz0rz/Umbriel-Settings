import json
import re
import shutil
import subprocess
import unittest

from support import CONFIG, PLUGIN, PLUGIN_ROOT, ConfigTestCase


class ManifestTests(unittest.TestCase):
    def test_plugin_directory_matches_manifest_id(self):
        manifest = (PLUGIN / "plugin.toml").read_text()
        match = re.search(r'^id\s*=\s*"([^"]+)"', manifest, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1).split("/")[-1], PLUGIN.name)

    def test_manifest_declares_the_bar_widget_and_panel(self):
        manifest = (PLUGIN / "plugin.toml").read_text()
        self.assertRegex(manifest, r'\[\[widget\]\]\s+id\s*=\s*"settings"\s+entry\s*=\s*"bar\.luau"')
        self.assertRegex(manifest, r'\[\[panel\]\]\s+id\s*=\s*"folders"')


@unittest.skipUnless(shutil.which("lua"), "lua is required for the panel harness")
class PanelHarnessTests(ConfigTestCase):
    """Runs the Luau panel under plain Lua with a mocked API; helper replies come from the real helper."""

    def helper(self, command, request):
        return self.ok(command, request)

    def fixtures(self, config_text, saved=True):
        """Write the helper replies the Lua harness serves: meta, search index, state, desktop, save result."""
        self.config.write_text(config_text)
        fixtures = self.root / "fixtures"
        fixtures.mkdir(exist_ok=True)
        meta = self.helper("meta", {})
        (fixtures / "meta.json").write_text(json.dumps(meta["meta"]))
        (fixtures / "search.json").write_text(json.dumps(meta["search"]))
        state = self.helper("read", {"config": str(self.config)})
        (fixtures / "state.json").write_text(json.dumps(state))
        (fixtures / "desktop.json").write_text(json.dumps(self.helper("desktop", {})))
        if saved:
            saved = self.helper("save", {"config": str(self.config), "changes": {
                "revision": state["revision"], "fields": {"general.mod_key": {"value": "Alt"}}}})
        (fixtures / "saved.json").write_text(json.dumps(saved or state))
        return fixtures

    def run_lua(self, script, fixtures, marker, *extra):
        result = subprocess.run(["lua", str(PLUGIN_ROOT / "tests" / script), str(PLUGIN), str(fixtures), *extra],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(marker, result.stdout)
        return result.stdout

    def test_panel_and_app_flows(self):
        fixtures = self.fixtures(CONFIG)
        for script, marker in (("panel_test.lua", "panel ok"), ("state_test.lua", "state ok"),
                               ("app_test.lua", "app ok"), ("outputs_test.lua", "outputs ok")):
            with self.subTest(script=script):
                self.run_lua(script, fixtures, marker)

    def test_callbacks_stay_within_cpu_budget_on_a_large_config(self):
        lines = [f'BUDGET_VAR_{i} = "value {i}"' for i in range(100)]
        text = CONFIG.replace('[environment]\n', '[environment]\n' + "\n".join(lines) + "\n")
        text = text.replace('[keybinds]\n', '[keybinds]\n' + "".join(
            f'"super+shift+alt+k{i}" = "spawn budget-command-{i}"\n' for i in range(400)))
        text += "".join(f'\n[[window_rule]]\nmatch = {{ app_id = "^budget-entry-{i}$" }}\nopacity = 0.9\n'
                        for i in range(300))
        text += "".join(f'\n[[workspace]]\nindex = {i + 1}\n' for i in range(60))
        text += "".join(f'\n[output.BUDGET-{i}]\nscale = 1.0\n' for i in range(50))
        fixtures = self.fixtures(text, saved=False)
        for layout in ("panel", "app"):  # the app also redraws its sidebar with every callback
            with self.subTest(layout=layout):
                output = self.run_lua("budget_test.lua", fixtures, "budget ok", layout)
                self.assertRegex(output, rf"budget {layout}: \d+ callbacks, slowest")

    def test_bar_shows_unsaved_count_and_toggles_panel(self):
        subprocess.run(["lua", str(PLUGIN_ROOT / "tests" / "bar_test.lua"), str(PLUGIN / "bar.luau")], check=True)


if __name__ == "__main__":
    unittest.main()
