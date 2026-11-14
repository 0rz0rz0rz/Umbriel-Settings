import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import lupa  # noqa: F401
except ImportError:  # pragma: no cover - lupa is a runtime dependency of the app
    lupa = None

ROOT = Path(__file__).resolve().parents[1]
CONFIG = textwrap.dedent("""\
    # my config
    [general]
    mod_key = "Super" # main modifier

    [keybinds]
    "Mod+Return" = "spawn kitty"

    [[window_rule]]
    match = { app_id = "^org.mozilla.firefox$" }
""")
FAKE_UMBRIEL = textwrap.dedent("""\
    import json, sys
    if sys.argv[1:3] == ["config", "schema"]:
        print(json.dumps({"version": "test", "revision": "r1", "options": [
            {"path": "general.mod_key", "type": "enum", "default": "Super", "values": ["Super", "Alt"]}]}))
        raise SystemExit(0)
    print(json.dumps({"valid": True, "diagnostics": []}))
""")


def walk(node, visit):
    if node is None:
        return None
    if visit(node):
        return node
    for child in node["children"]:
        found = walk(child, visit)
        if found:
            return found
    return None


@unittest.skipIf(lupa is None, "lupa is required for the app UI host")
class HostRuntimeTests(unittest.TestCase):
    def setUp(self):
        from umbriel_settings.host.api import ManualScheduler, NoctaliaApi
        from umbriel_settings.host.paths import shared_ui_dir
        from umbriel_settings.host.runtime import LuaHost

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.config = root / "config.toml"
        self.config.write_text(CONFIG)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        (bin_dir / "umbriel").write_text(f"#!{sys.executable}\n" + FAKE_UMBRIEL)
        (bin_dir / "umbriel").chmod(0o755)
        env = patch.dict(os.environ, {"XDG_DATA_HOME": str(root / "data"), "XDG_CONFIG_HOME": str(root / "xdg"),
                                      "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]})
        env.start()
        self.addCleanup(env.stop)
        self.scheduler = ManualScheduler()
        self.host = LuaHost(shared_ui_dir(), on_error=lambda error: None)
        self.states = {}
        api = NoctaliaApi(self.host, self.scheduler, str(root / "app-ui"),
                          on_state=lambda key, value: self.states.__setitem__(key, value))
        self.host.start("app.luau", {"initialConfig": str(self.config)}, api.globals())
        self.host.call("onOpen")
        self.settle()

    def settle(self):
        while self.scheduler.drain():
            pass
        self.assertEqual(self.host.errors, [])

    def find(self, predicate, message="node not found"):
        node = walk(self.host.tree, predicate)
        self.assertIsNotNone(node, message + "\n" + self.screen())
        return node

    def screen(self):
        texts = []
        walk(self.host.tree, lambda n: texts.append(str(n["props"].get("text"))) if "text" in n["props"] else None)
        return " | ".join(texts)

    def click(self, text):
        node = self.find(lambda n: "onClick" in n["props"] and walk(n, lambda c: c["props"].get("text") == text),
                         f"nothing clickable shows {text}")
        self.host.invoke(node["props"]["onClick"])
        self.settle()

    def test_sidebar_search_edit_and_save_round_trip(self):
        self.find(lambda n: n["props"].get("key") == "sidebar", "sidebar")
        self.assertIn("Appearance", self.screen())
        search = self.find(lambda n: n["kind"] == "input" and str(n["props"].get("key", "")).startswith("search:"))
        self.host.invoke(search["props"]["onChange"], "modifier")
        self.settle()
        self.click("Mod key")
        select = self.find(lambda n: n["props"].get("key") == "f:general.mod_key:select")
        self.host.invoke(select["props"]["onChange"], select["props"]["options"].index("Alt"))
        self.settle()
        self.assertEqual(self.states.get("umbriel.pending"), 1)
        self.click("Review & save")
        self.assertIn("Umbriel accepts the new config.", self.screen())
        self.click("Save")
        self.assertIn('mod_key = "Alt" # main modifier', self.config.read_text())
        self.assertEqual(self.states.get("umbriel.pending"), 0)

    def test_loading_the_helper_does_not_shadow_the_app_package(self):
        """The helper file is umbriel_settings.py, like this package; its sys.path change must not leak."""
        import importlib

        from umbriel_settings.host.api import ManualScheduler, NoctaliaApi
        from umbriel_settings.host.paths import shared_ui_dir

        before = list(sys.path)
        api = NoctaliaApi(self.host, ManualScheduler(), self.temp.name)
        helper = api._helper(os.path.join(shared_ui_dir(), "umbriel_settings.py"))
        self.assertTrue(hasattr(helper, "run"))
        self.assertEqual(sys.path, before)
        self.assertTrue(hasattr(importlib.import_module("umbriel_settings"), "APP_NAME"))

    def test_starts_without_a_config_argument(self):
        saved = Path(os.environ["XDG_DATA_HOME"]) / "umbriel-settings" / "gui-config-path"
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_text(str(self.config))
        from umbriel_settings.host.api import NoctaliaApi
        from umbriel_settings.host.runtime import LuaHost
        host = LuaHost(self.host.ui_dir, on_error=lambda error: None)
        api = NoctaliaApi(host, self.scheduler, str(Path(self.temp.name) / "app-ui-2"))
        host.start("app.luau", {}, api.globals())
        host.call("onOpen")
        while self.scheduler.drain():
            pass
        self.assertEqual(host.errors, [])
        texts = []
        walk(host.tree, lambda n: texts.append(str(n["props"].get("text", ""))) and False)
        self.assertNotIn("The request must be a JSON object.", texts)
        self.assertIn("General", texts)
        self.assertIn(str(self.config), texts)

    def test_tree_conversion_and_callbacks(self):
        toggle_page = self.find(lambda n: n["props"].get("key") == "nav-General")
        self.assertIn("$callback", toggle_page["props"]["onClick"])
        self.host.invoke(toggle_page["props"]["onClick"])
        self.settle()
        toggle = self.find(lambda n: n["kind"] == "button" and str(n["props"].get("key", "")).endswith(":tri:2")
                           or n["kind"] == "toggle")
        self.assertIn(toggle["kind"], ("button", "toggle"))
        from umbriel_settings.host.runtime import as_callback_arg
        self.assertEqual([as_callback_arg(v) for v in (True, False, 2.0, 0.5, None)], ["true", "false", "2", "0.5", ""])


if __name__ == "__main__":
    unittest.main()
