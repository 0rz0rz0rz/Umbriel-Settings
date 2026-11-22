"""ConfigSession saves on hand-written config shapes: nothing invalid is written, no raw crashes (no Qt)."""

import hashlib
import os
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from umbriel_core import keybinds, layout
from umbriel_core.session import ConfigSession

ROWS = [{"key": "super+q", "action": "window-close", "group": "Windows"}]


class SessionTestCase(unittest.TestCase):
    def setUp(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        self.path = os.path.join(tempdir.name, "config.toml")
        self.data = os.path.join(tempdir.name, "data")

    def session(self, text):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return ConfigSession(self.path, self.data)

    def save(self, text, **changes):
        """Save without the umbriel CLI, as on a machine where it is not installed."""
        session = self.session(text)
        report = session.save({"revision": session.read()["revision"], **changes}, validate=False,
                              backup=lambda path, config_dir: None)
        with open(self.path, encoding="utf-8") as handle:
            return report, handle.read()

    def groups(self, text):
        return self.save(text, keybinds={"rows": ROWS, "groups": ["Windows"], "locks": []})


class KeybindGroupTests(SessionTestCase):
    def test_indented_or_spaced_header_gets_no_second_table(self):
        for header in ("  [keybinds]", "[ keybinds ]", '["keybinds"]  # binds'):
            report, text = self.groups(f'{header}\n"super+q" = "window-close"\n')
            self.assertTrue(report["saved"], header)
            self.assertEqual(tomllib.loads(text), {"keybinds": {"super+q": "window-close"}}, header)
            lines = text.splitlines()
            self.assertEqual(lines[0], header)
            self.assertTrue(lines[1].startswith(keybinds.KEYBIND_GROUPS_MARKER), text)

    def test_dotted_and_inline_keybinds_keep_the_file_valid(self):
        for source in ('keybinds."super+q" = "window-close"\n', 'keybinds = { "super+q" = "window-close" }\n'):
            report, text = self.groups(source)
            self.assertTrue(report["saved"], source)
            self.assertEqual(tomllib.loads(text), {"keybinds": {"super+q": "window-close"}}, source)
            self.assertNotIn(keybinds.KEYBIND_GROUPS_MARKER, text)
            self.assertTrue(any("Groups not stored" in item["label"] for item in report["summary"]), source)

    def test_groups_start_a_table_when_there_are_no_keybinds(self):
        report, text = self.save("[general]\n", keybinds={"rows": [], "groups": ["Windows"], "locks": []})
        self.assertTrue(report["saved"])
        self.assertIn("[keybinds]\n" + keybinds.KEYBIND_GROUPS_MARKER, text)

    def test_keybinds_that_are_not_a_table_are_refused(self):
        with self.assertRaisesRegex(ValueError, "keybinds is not a table"):
            self.groups('keybinds = "x"\n')


class HandWrittenShapeTests(SessionTestCase):
    def test_scalar_where_a_table_is_expected_is_a_readable_error(self):
        with self.assertRaisesRegex(ValueError, "layout is not a table"):
            self.save('layout = "x"\n', fields={"layout.gap": {"value": 4}})
        with open(self.path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), 'layout = "x"\n')

    def test_a_match_that_is_not_a_table_does_not_break_other_saves(self):
        report, text = self.save('[general]\n[[window_rule]]\nmatch = "x"\n',
                                 fields={"general.mod_key": {"value": "Alt"}})
        self.assertTrue(report["saved"])
        self.assertIn('mod_key = "Alt"', text)
        for rules in ({"window_rule": {"match": 1}}, {"window_rule": [1]}, {}):
            layout.inline_window_rule_matches(rules)  # shapes read() already refuses; still no crash here

    def test_text_that_lost_a_setting_is_never_written(self):
        source = '[keybinds]\n"super+q" = "window-close"\n'
        for broken in ("[keybinds]\n", '[keybinds]\n[keybinds]\n"super+q" = "window-close"\n'):
            with patch.object(keybinds, "write_keybind_groups", return_value=broken), \
                    self.assertRaisesRegex(ValueError, "Nothing was written"):
                self.groups(source)
            with open(self.path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), source)

    def test_labels_count_indented_and_spaced_rule_headers(self):
        text = "  [[window_rule]]\nopacity = 1\n[[ window_rule ]]\nopacity = 0.5\n"
        named = layout.add_entry_name_comments(text, {"window_rule": ["", "Second"]})
        self.assertEqual(named, "  [[window_rule]]\nopacity = 1\n# GUI rule name: Second\n"
                                "[[ window_rule ]]\nopacity = 0.5\n")


class LabelFileTests(SessionTestCase):
    def test_a_labels_file_with_the_wrong_shapes_still_reads_and_saves(self):
        text = "[[window_rule]]\nopacity = 1\n\n[output.DP-1]\nscale = 1.0\n"
        session = self.session(text)
        os.makedirs(session.config_dir, exist_ok=True)
        with open(os.path.join(session.config_dir, "gui-labels.json"), "w", encoding="utf-8") as handle:
            handle.write('{"window_rule": {"a": "b"}, "output": ["Rule label"]}')
        state = session.read()
        self.assertEqual(state["editors"]["output"][0]["label"], "")
        _, saved = self.save(text, fields={"general.xwayland_primary_output": {"value": "DP-1"}})
        self.assertIn('xwayland_primary_output = "DP-1"', saved)


class LockFileTests(SessionTestCase):
    def test_a_lock_file_that_is_not_a_list_locks_nothing(self):
        session = self.session("")
        os.makedirs(session.config_dir, exist_ok=True)
        for content, expected in (('"abc"', set()), ('{"a": 1}', set()), ('["super+q", 3]', {"super+q"})):
            with open(session.lock_path(), "w", encoding="utf-8") as handle:
                handle.write(content)
            self.assertEqual(keybinds.load_locked(session.config_dir), expected, content)


class BeforeWriteTests(SessionTestCase):
    def test_before_write_sees_the_new_revision_and_can_stop_the_write(self):
        seen = []
        session = self.session("[general]\nmod_key = \"Super\"\n")
        changes = {"revision": session.read()["revision"], "fields": {"general.mod_key": {"value": "Alt"}}}
        session.save(changes, validate=False, backup=lambda path, config_dir: "snap",
                     before_write=lambda backup, revision: seen.append((backup, revision)))
        with open(self.path, "rb") as handle:
            self.assertEqual(seen, [("snap", hashlib.sha256(handle.read()).hexdigest())])

        def fail(backup, revision):
            raise OSError("disk full")
        session = self.session("[general]\nmod_key = \"Super\"\n")
        changes = {"revision": session.read()["revision"], "fields": {"general.mod_key": {"value": "Alt"}}}
        with self.assertRaises(OSError):
            session.save(changes, validate=False, backup=lambda path, config_dir: "snap", before_write=fail)
        with open(self.path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "[general]\nmod_key = \"Super\"\n")


if __name__ == "__main__":
    unittest.main()
