import os
import tempfile
import textwrap
import unittest
from unittest import mock

from umbriel_core import actions, live, xkb
from umbriel_core.included import included_names
from umbriel_core.meta import build_meta

WINDOWS = [
    {"app_id": "firefox", "title": "Docs — Mozilla Firefox", "id": "a"},
    {"app_id": "firefox", "title": "Other tab", "id": "b"},
    {"app_id": "org.gajim.Gajim", "title": "Gajim", "id": "c"},
    {"app_id": "", "title": "no app id", "id": "d"},
]
LAYERS = [
    {"namespace": "noctalia-bar-default", "layer": "top", "output": "DP-1"},
    {"namespace": "noctalia-bar-default", "layer": "top", "output": "HDMI-A-1"},
    {"namespace": "noctalia-wallpaper", "layer": "background", "output": "DP-1"},
]
EVDEV = textwrap.dedent("""\
    ! model
      pc105           Generic 105-key PC

    ! layout
      us              English (US)
      de              German

    ! variant
      intl            us: English (US, intl., with dead keys)
      nodeadkeys      de: German (no dead keys)

    ! option
      grp                  Switching to another layout
      grp:alt_shift_toggle Alt+Shift
      caps                 Caps Lock behavior
      caps:escape          Make Caps Lock an additional Esc
      empty                A group without options
      Compose key          Position of Compose key
      compose:ralt         Right Alt
      compat               Compatibility options
      misc:typo            Enable extra typographic characters
""")


def fake_umbriel(answers):
    return lambda args, timeout: answers[" ".join(args)]


class LiveTests(unittest.TestCase):
    def test_windows_are_one_per_app_with_exact_patterns(self):
        with mock.patch.object(live, "run_umbriel_json", fake_umbriel({"windows --json": WINDOWS})):
            windows = live.open_windows()
        self.assertEqual([w["app_id"] for w in windows], ["firefox", "org.gajim.Gajim"])
        self.assertEqual(windows[0]["count"], 2)
        self.assertEqual(windows[0]["title"], "Docs — Mozilla Firefox")
        self.assertEqual(windows[1]["pattern"], r"^org\.gajim\.Gajim$")

    def test_layers_collect_outputs(self):
        with mock.patch.object(live, "run_umbriel_json", fake_umbriel({"layers --json": LAYERS})):
            layers = live.open_layers()
        self.assertEqual(layers[0], {"namespace": "noctalia-bar-default", "layer": "top",
                                     "outputs": ["DP-1", "HDMI-A-1"], "pattern": "^noctalia-bar-default$"})

    def test_unexpected_shapes_are_errors(self):
        answers = {"windows --json": {"windows": []}, "outputs --json": [{"name": "DP-1"}, {"modes": []}]}
        with mock.patch.object(live, "run_umbriel_json", fake_umbriel(answers)):
            with self.assertRaises(ValueError):
                live.open_windows()
            with self.assertRaises(ValueError):
                live.connected_outputs()

    def test_keyboard_layout_is_a_best_effort_hint(self):
        answer = {"keyboard-layouts --json": {"current_index": 1, "names": ["English (US)", "German"]}}
        with mock.patch.object(live, "run_umbriel_json", fake_umbriel(answer)):
            self.assertEqual(live.keyboard_layout(), "German")
        for index in (-1, 2, True, None):
            answer = {"keyboard-layouts --json": {"current_index": index, "names": ["English (US)", "German"]}}
            with mock.patch.object(live, "run_umbriel_json", fake_umbriel(answer)):
                self.assertIsNone(live.keyboard_layout(), index)
        with mock.patch.object(live, "run_umbriel_json", side_effect=FileNotFoundError):
            self.assertIsNone(live.keyboard_layout())

    def test_regex_literal_escapes_only_shared_metacharacters(self):
        self.assertEqual(live.regex_literal("a-b (x).y*"), r"^a-b \(x\)\.y\*$")


class XkbTests(unittest.TestCase):
    def test_parse_layouts_variants_and_option_groups(self):
        data = xkb.parse(EVDEV)
        self.assertEqual(data["layouts"], [{"name": "us", "desc": "English (US)"}, {"name": "de", "desc": "German"}])
        self.assertEqual(data["variants"]["de"], [{"name": "nodeadkeys", "desc": "German (no dead keys)"}])
        # empty groups dropped; a group name may hold a space and a group may hold other prefixes
        self.assertEqual([g["name"] for g in data["options"]], ["grp", "caps", "Compose key", "compat"])
        self.assertEqual(data["options"][2]["desc"], "Position of Compose key")
        self.assertEqual([i["name"] for i in data["options"][3]["items"]], ["misc:typo"])
        self.assertEqual(data["options"][1]["items"],
                         [{"name": "caps:escape", "desc": "Make Caps Lock an additional Esc"}])

    def test_catalog_reads_xkb_config_root_and_survives_a_missing_file(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "rules"))
            with open(os.path.join(root, "rules", "evdev.lst"), "w", encoding="utf-8") as handle:
                handle.write(EVDEV)
            path = xkb.rules_file({"XKB_CONFIG_ROOT": root})
            self.assertEqual(len(xkb.catalog(path)["layouts"]), 2)
            self.assertEqual(xkb.catalog(os.path.join(root, "missing.lst"))["layouts"], [])


class IncludedNamesTests(unittest.TestCase):
    def test_names_come_from_includes_and_their_includes(self):
        with tempfile.TemporaryDirectory() as root:
            def write(name, text):
                with open(os.path.join(root, name), "w", encoding="utf-8") as handle:
                    handle.write(textwrap.dedent(text))
            write("effects.toml", """\
                [include]
                files = ["curves.toml", "effects.toml"]  # includes itself: read once
                [effects.preset.pulse]
                kind = "border"
                [effects.pool.borders]
                kind = "border"
            """)
            write("curves.toml", "[animation.beziers]\nsoft = [0.1, 0.9, 0.2, 1.0]\n")
            write("broken.toml", "this is = = not toml")
            config = {"include": {"files": ["effects.toml", "broken.toml"], "optional": {"files": ["missing.toml"]}}}
            names = included_names(config, root)
        self.assertEqual(names, {"effect_preset": ["pulse"], "effect_pool": ["borders"], "beziers": ["soft"],
                                 "springs": []})

    def test_a_fifo_include_is_skipped_without_blocking(self):
        with tempfile.TemporaryDirectory() as root:
            os.mkfifo(os.path.join(root, "pipe.toml"))
            self.assertEqual(included_names({"include": {"files": ["pipe.toml"]}}, root)["effect_preset"], [])

    def test_no_includes(self):
        self.assertEqual(included_names({}, "/nowhere")["effect_preset"], [])


class RunActionTests(unittest.TestCase):
    def test_blocked_actions(self):
        for action in ("session-quit", "session-quit skip-confirmation", "window-close", "window-kill abc",
                       "dpms-off", "submap resize", "spawn noctalia msg session lock", "",
                       '"session-quit"', "'window-close'", "spawn noctalia msg 'session' lock",
                       "spawn sh -c 'noctalia  msg session lock'"):
            self.assertIsNotNone(actions.run_block_reason(action), action)
        for action in ("window-focus-left", "submap reset", "spawn kitty", "overview-toggle"):
            self.assertIsNone(actions.run_block_reason(action), action)

    def test_msg_argv_keeps_the_spawn_command_as_one_word(self):
        self.assertEqual(actions.msg_argv("spawn kitty --title 'a b'"), ["msg", "spawn", "kitty --title 'a b'"])
        self.assertEqual(actions.msg_argv("workspace-focus --name 'my ws'"),
                         ["msg", "workspace-focus", "--name", "my ws"])
        self.assertEqual(actions.msg_argv("spawn\tkitty --hold"), ["msg", "spawn", "kitty --hold"])
        self.assertEqual(actions.msg_argv("spawn"), ["msg", "spawn", ""])


class MetaPickerTests(unittest.TestCase):
    def test_curve_effect_and_keyboard_fields_are_flagged(self):
        schema = {
            "animation.windows_in.curve": {"type": "string", "format": "curve"},
            "animation.windows_in.effect": {"type": "string", "format": "effect", "default": ""},
            "window_rule[].border_effect": {"type": "string", "format": "effect"},
        }
        meta = build_meta(schema)
        fields = meta["fields"]
        self.assertEqual(fields["animation.windows_in.curve"]["names_from"], "curve")
        effect = fields["animation.windows_in.effect"]
        self.assertEqual((effect["kind"], effect["choices"], effect["names_from"]), ("combo", [""], "effect"))
        self.assertEqual(fields["window_rule:border_effect"]["names_from"], "effect")
        self.assertEqual(fields["input.keyboard.variant"]["xkb"], "variant")
        self.assertEqual(fields["input_device:options"]["picker"], "xkb")
        self.assertNotIn("picker", fields["input.keyboard.model"])
        self.assertEqual(meta["actions"]["blocked"]["heads"]["session-quit"], actions.RUN_BLOCKED["session-quit"])

    def test_output_fields_offer_names_and_path_fields_a_file_chooser(self):
        schema = {
            "general.xwayland_primary_output": {"type": "string", "default": ""},
            "window_rule[].default_output": {"type": "string"},
        }
        fields = build_meta(schema)["fields"]
        primary = fields["general.xwayland_primary_output"]
        self.assertEqual((primary["kind"], primary["choices"], primary["names_from"]), ("combo", [""], "output"))
        rule = fields["window_rule:default_output"]
        self.assertEqual((rule["kind"], rule["choices"]), ("combo", []))  # no key = "Not set", not a "" choice
        self.assertEqual(fields["effect_preset:shader"]["file"]["relative"], True)
        self.assertEqual(fields["output:color_profile"]["picker"], "file")
        self.assertEqual(fields["output:mode"]["picker"], "mode")  # Resolution + Refresh rate dropdowns
        self.assertEqual(fields["include.optional.files"]["file"]["filter"], ["TOML files", "*.toml"])
        self.assertEqual(fields["general.autostart"]["picker"], "file")  # Browse… next to Add
        self.assertTrue(fields["general.autostart"]["file"]["command"])

    def test_without_a_schema_effect_fields_stay_text(self):
        self.assertEqual(build_meta({})["fields"]["animation.windows_in.effect"]["kind"], "str")


if __name__ == "__main__":
    unittest.main()
