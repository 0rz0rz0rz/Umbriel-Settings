"""The watcher that takes back a display Try nobody answered (umbriel_core/trial.py)."""

import os
import time
import unittest
from unittest.mock import patch

from test_core_files import TempDirTestCase
from umbriel_core import backups, paths, trial


class TrialTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.config = self.write("umbriel", "config.toml", text="tried\n")
        self.backup = self.write("configs", "x", "backups", "config.toml.1.bak", text="before\n")
        self.config_dir = os.path.join(self.root, "configs", "x")
        self.lock_dir = os.path.join(self.root, "data")
        self.token = {"id": "abc", "config": self.config, "deadline": 0, "backup": self.backup, "keep": 10,
                      "revision": paths.file_revision(self.config)}

    def read(self, path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def arm(self, token):
        trial._write_json(trial.token_file(self.config_dir), token)
        return trial.token_file(self.config_dir)

    def snapshots(self):
        directory = os.path.dirname(self.backup)
        return sorted(os.path.join(directory, name) for name in os.listdir(directory) if name.endswith(".bak"))

    def test_expire_restores_and_keeps_the_tried_file_private(self):
        os.chmod(self.config, 0o644)
        path = self.arm(self.token)
        self.assertEqual(trial.expire(path, self.lock_dir, "abc"), (True, trial.RESTORED))
        self.assertEqual(self.read(self.config), "before\n")
        self.assertEqual(os.stat(self.config).st_mode & 0o777, 0o644, "the config keeps its mode")
        self.assertFalse(os.path.exists(path))
        tried = [item for item in self.snapshots() if item != self.backup]
        self.assertEqual(len(tried), 1)
        self.assertEqual(self.read(tried[0]), "tried\n")
        self.assertEqual(os.stat(tried[0]).st_mode & 0o777, 0o600, "a copy of the config is owner-only")
        self.assertEqual(trial.STAMP, backups.STAMP)
        self.assertEqual(trial.outcome(self.config_dir, "abc"), {"id": "abc", "restored": True, "reason": "restored"})
        self.assertIn("already restored", trial.describe(trial.outcome(self.config_dir, "abc")))

    def test_the_watcher_prunes_like_the_backups_do(self):
        directory = os.path.dirname(self.backup)
        for index in range(12):
            self.write("configs", "x", "backups", f"config.toml.0000{index:02d}.bak", text="old\n")
        path = self.arm({**self.token, "keep": 5})
        self.assertTrue(trial.expire(path, self.lock_dir, "abc")[0])
        kept = self.snapshots()
        self.assertEqual(len(kept), 5)
        self.assertIn(self.backup, kept, "the backup it restored is never pruned")
        self.assertTrue(any(self.read(os.path.join(directory, item)) == "tried\n" for item in kept))

    def test_a_config_changed_since_the_try_is_left_alone_and_said_so(self):
        path = self.arm(self.token)
        self.write("umbriel", "config.toml", text="edited\n")
        self.assertEqual(trial.expire(path, self.lock_dir, "abc"), (False, trial.CHANGED))
        self.assertEqual(self.read(self.config), "edited\n")
        self.assertIn("changed during the Try", trial.describe(trial.outcome(self.config_dir, "abc")))

    def test_a_missing_backup_is_reported(self):
        os.remove(self.backup)
        path = self.arm(self.token)
        restored, reason = trial.expire(path, self.lock_dir, "abc")
        self.assertFalse(restored)
        self.assertIn("No such file", reason)
        self.assertIn("restore the config from Backups", trial.describe(trial.outcome(self.config_dir, "abc")))

    def test_a_claimed_or_newer_trial_is_not_restored(self):
        path = self.arm(self.token)
        self.assertIsNone(trial.claim(self.config_dir, "other"))
        claimed = trial.claim(self.config_dir, "abc")
        self.assertEqual(claimed["id"], "abc")
        self.assertFalse(trial.expire(path, self.lock_dir, "abc"))
        trial.unclaim(self.config_dir, claimed)  # a failed restore puts it back for the watcher
        self.assertEqual(trial.read_token(path)["id"], "abc")
        self.arm({**self.token, "id": "newer"})
        self.assertFalse(trial.expire(path, self.lock_dir, "abc"))
        self.assertEqual(self.read(self.config), "tried\n")
        self.assertIsNone(trial.outcome(self.config_dir, "abc"))
        self.assertEqual(trial.describe(None), "This Try already ended.")

    def test_expire_waits_while_another_writer_holds_the_lock(self):
        path = self.arm(self.token)
        with paths.write_lock(self.lock_dir), patch.object(trial, "LOCK_TIMEOUT", 0.2):
            self.assertIsNone(trial.expire(path, self.lock_dir, "abc"))
        self.assertTrue(os.path.exists(path))

    def test_the_countdown_starts_once_the_file_is_written(self):
        with patch("subprocess.run"):
            token = trial.arm(self.config, self.config_dir, self.lock_dir, 15)
        self.assertGreater(token["deadline"], time.time() + 15 + trial.GRACE + trial.CONFIRM_WINDOW - 5,
                           "a slow validation can't eat into the countdown")
        before = time.time()
        trial.confirm(self.config_dir, token, self.backup, "rev")
        confirmed = trial.read_token(trial.token_file(self.config_dir))
        self.assertAlmostEqual(confirmed["deadline"], before + 15 + trial.GRACE, delta=2)
        self.assertEqual(os.stat(trial.token_file(self.config_dir)).st_mode & 0o777, 0o600)

    def test_a_waiting_try_refuses_a_second_one(self):
        with patch("subprocess.run"):
            trial.arm(self.config, self.config_dir, self.lock_dir, 15)
            with self.assertRaises(trial.Busy):
                trial.arm(self.config, self.config_dir, self.lock_dir, 15)
            self.arm({**self.token, "deadline": time.time() - 1})  # its watcher died: a new Try may start
            trial.arm(self.config, self.config_dir, self.lock_dir, 15)

    def test_the_watcher_never_runs_on_an_appimage_python(self):
        appdir = os.path.join(self.root, "mount")
        inside = self.write("mount", "usr", "bin", "python3", text="")
        os.chmod(inside, 0o755)
        env = {"APPDIR": appdir, "PATH": os.path.dirname(inside)}
        with self.assertRaisesRegex(OSError, "needs python3"):
            trial.host_python(env)
        outside = self.write("host", "python3", text="")
        os.chmod(outside, 0o755)
        env["PATH"] = os.path.dirname(inside) + os.pathsep + os.path.dirname(outside)
        self.assertEqual(trial.host_python(env), outside)

    def test_the_detached_watcher_restores_without_its_parent_and_notifies(self):
        log = os.path.join(self.root, "notified")
        stub = self.write("bin", "notify-send", text=f"#!/bin/sh\necho \"$@\" > '{log}'\n")
        os.chmod(stub, 0o755)
        with patch.object(trial, "GRACE", 0), \
                patch.dict(os.environ, {"PATH": os.path.dirname(stub) + os.pathsep + os.environ.get("PATH", "")}):
            token = trial.arm(self.config, self.config_dir, self.lock_dir, 1)
            trial.confirm(self.config_dir, token, self.backup, paths.file_revision(self.config))
        deadline = time.monotonic() + 10
        while not os.path.exists(log) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertEqual(self.read(self.config), "before\n")
        self.assertFalse(os.path.exists(trial.token_file(self.config_dir)))
        self.assertIn("previous display settings are back", self.read(log))

    def test_a_watcher_that_cannot_start_leaves_no_token(self):
        with patch("subprocess.run", side_effect=OSError("no python")), self.assertRaisesRegex(OSError, "nothing"):
            trial.arm(self.config, self.config_dir, self.lock_dir, 15)
        self.assertFalse(os.path.exists(trial.token_file(self.config_dir)))


if __name__ == "__main__":
    unittest.main()
