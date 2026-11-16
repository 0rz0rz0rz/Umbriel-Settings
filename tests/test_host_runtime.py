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
        # XDG_DATA_DIRS: the desktop page lists installed apps; the machine's own must not decide the result.
        env = patch.dict(os.environ, {"XDG_DATA_HOME": str(root / "data"), "XDG_CONFIG_HOME": str(root / "xdg"),
                                      "XDG_DATA_DIRS": str(root / "share"),
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

    def test_a_second_launch_opens_its_config_unless_edits_would_be_lost(self):
        other = Path(self.temp.name) / "other.toml"
        other.write_text(CONFIG.replace('"Super"', '"Alt"'))
        self.host.call("onRelaunch", str(other))
        self.settle()
        self.assertEqual(self.states.get("umbriel.config"), str(other))
        saved = Path(os.environ["XDG_DATA_HOME"]) / "umbriel-settings" / "gui-config-path"
        self.assertFalse(saved.exists() and str(other) in saved.read_text(), "a launch argument is not remembered")

        self.click("General")
        self.click("Session")
        select = self.find(lambda n: n["props"].get("key") == "f:general.mod_key:select")
        self.host.invoke(select["props"]["onChange"], select["props"]["options"].index("Super"))
        self.settle()
        self.host.call("onRelaunch", str(self.config))
        self.settle()
        self.assertEqual(self.states.get("umbriel.config"), str(other), "unsaved edits keep the config open")
        self.assertIn("Save or discard your changes", self.screen())

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

    def new_app(self, data_dir):
        """A second app instance (fresh Lua state) on the same files, like a restart."""
        from umbriel_settings.host.api import NoctaliaApi
        from umbriel_settings.host.runtime import LuaHost
        host = LuaHost(self.host.ui_dir, on_error=lambda error: None)
        api = NoctaliaApi(host, self.scheduler, data_dir,
                          on_state=lambda key, value: self.states.__setitem__(key, value))
        host.start("app.luau", {"initialConfig": str(self.config)}, api.globals())
        self.host = host
        return api

    def test_a_crashing_helper_shows_an_error_and_try_again_recovers(self):
        from umbriel_settings.host.paths import shared_ui_dir

        class Broken:
            def run(self, argv):
                raise RuntimeError("helper exploded")

        api = self.new_app(str(Path(self.temp.name) / "app-ui-broken"))
        helper = os.path.abspath(os.path.join(shared_ui_dir(), "umbriel_settings.py"))
        api._helpers[helper] = Broken()
        with patch("sys.stderr"):
            self.host.call("onOpen")
            self.settle()
        self.assertIn("helper exploded", self.screen(), "the error is shown instead of loading forever")
        del api._helpers[helper]
        self.click("Try again")
        self.find(lambda n: n["props"].get("key") == "sidebar", "loads after retrying")

    def test_unsaved_user_folder_edits_survive_a_restart(self):
        self.click("User folders")
        field = self.find(lambda n: n["kind"] == "input" and str(n["props"].get("key", "")).startswith("fold-MUSIC-"))
        self.host.invoke(field["props"]["onChange"], "$HOME/Tunes")
        self.settle()
        self.assertEqual(self.states.get("umbriel.pending"), 1)
        self.host.call("onClose")
        self.states.clear()
        self.new_app(str(Path(self.temp.name) / "app-ui"))
        self.host.call("onOpen")
        self.settle()
        self.assertEqual(self.states.get("umbriel.pending"), 1, "the folder edit came back")
        self.assertIn("Restored unsaved user folder and default app edits.", self.screen())

    def test_tree_conversion_and_callbacks(self):
        toggle_page = self.find(lambda n: n["props"].get("key") == "nav-General")
        self.assertIn("$callback", toggle_page["props"]["onClick"])
        self.host.invoke(toggle_page["props"]["onClick"])
        self.settle()
        self.assertIn("Session", self.screen(), "the callback opened the General page")
        from umbriel_settings.host.runtime import as_callback_arg
        self.assertEqual([as_callback_arg(v) for v in (True, False, 2.0, 0.5, None)], ["true", "false", "2", "0.5", ""])

    def test_a_click_from_an_older_tree_runs_what_was_clicked(self):
        """The page can send a click while a newer tree is on its way; ids must not be reused across renders."""
        appearance = self.find(lambda n: n["props"].get("key") == "nav-Appearance")["props"]["onClick"]
        self.host.invoke(self.find(lambda n: n["props"].get("key") == "nav-General")["props"]["onClick"])
        self.settle()
        self.assertNotIn(appearance["$callback"], self.host.callbacks, "ids are unique per render")
        self.host.invoke(appearance)  # still names Appearance, not whatever sits at that position now
        self.settle()
        self.assertIn("Tab bar", self.screen())
        from umbriel_settings.host.runtime import CALLBACK_GENERATIONS
        for _ in range(CALLBACK_GENERATIONS):
            self.host.call("onFrameTick", 16)
        general = self.find(lambda n: n["props"].get("key") == "nav-General")["props"]["onClick"]
        self.host.invoke(appearance)
        self.host.invoke({"$callback": "cb1"})
        self.host.invoke({"$callback": general["$callback"].replace("cb", "cb9999")})
        self.settle()
        self.assertIn("Tab bar", self.screen(), "ids that are too old or unknown do nothing")

    def test_the_ui_cannot_reach_files_processes_or_python(self):
        lua = self.host.lua
        for name in ("io", "python", "package", "debug", "dofile", "loadfile", "load", "require"):
            self.assertIsNone(lua.eval(name), name)
        self.assertEqual(lua.eval("type(os.clock) .. type(os.time) .. type(os.date)"), "functionfunctionfunction")
        for name in ("execute", "remove", "rename", "exit", "getenv", "tmpname"):
            self.assertIsNone(lua.eval("os." + name), name)
        lua.globals().probe = self
        with self.assertRaises(AttributeError):
            lua.eval("probe.temp")
        # The page may only name handlers of the entry script, never a Lua global that the entry can see.
        ran = []
        lua.globals().onProbe = lambda *args: ran.append("global")
        lua.globals().print = lambda *args: ran.append("print")
        for name in ("onProbe", "print", "require", "APP", "tostring"):
            self.assertIsNone(self.host.invoke(name, "x"))
        self.assertEqual(ran, [])
        self.assertIsNotNone(self.host.entry_handler("onOpen"))


if __name__ == "__main__":
    unittest.main()
