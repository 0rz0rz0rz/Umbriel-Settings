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

    def test_a_try_confirmed_but_never_written_is_already_back(self):
        self.write("umbriel", "config.toml", text="before\n")  # the save stopped between confirm and the write
        path = self.arm(self.token)
        self.assertEqual(trial.expire(path, self.lock_dir, "abc"), (True, trial.RESTORED))
        self.assertEqual(self.read(self.config), "before\n")
        self.assertEqual(self.snapshots(), [self.backup], "nothing was written, so no copy of a tried file")

    def test_the_pending_backup_is_the_confirmed_one_until_its_watcher_is_surely_gone(self):
        self.assertIsNone(trial.pending_backup(self.config_dir))
        pending = {**self.token, "deadline": time.time() + 30}
        self.arm({**pending, "backup": None})
        self.assertIsNone(trial.pending_backup(self.config_dir), "armed, not confirmed yet")
        self.arm(pending)
        self.assertEqual(trial.pending_backup(self.config_dir), self.backup)
        other = os.path.join(os.path.dirname(self.backup), "config.toml.0.bak")
        self.assertEqual(trial.protect_pending(self.config_dir, [self.backup, other, 7]), (
            [other, 7], ["config.toml.1.bak: kept until the running Try ends (it is its rollback)"]))
        # a watcher killed with the session (logout, reboot) left its token behind: it protects nothing
        self.arm({**pending, "deadline": time.time() - trial.GIVE_UP - 1})
        self.assertIsNone(trial.pending_backup(self.config_dir))
        self.assertEqual(trial.protect_pending(self.config_dir, [self.backup]), ([self.backup], []))

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
        self.arm({**self.token, "id": "newer"})
        self.assertFalse(trial.expire(path, self.lock_dir, "abc"))
        self.assertEqual(self.read(self.config), "tried\n")
        self.assertIsNone(trial.outcome(self.config_dir, "abc"))
        self.assertEqual(trial.describe(None), "This Try already ended.")

    def test_a_failed_save_leaves_a_written_try_to_the_watcher(self):
        path = self.arm(self.token)  # the config holds the tried file: only the watcher may end this trial
        trial.abandon(self.config_dir, "other")
        trial.abandon(self.config_dir, "abc")
        self.assertTrue(os.path.exists(path))
        self.assertEqual(trial.expire(path, self.lock_dir, "abc"), (True, trial.RESTORED))
        self.assertEqual(self.read(self.config), "before\n")
        for token in ({**self.token, "revision": "not the config's"},  # confirmed, never written
                      {key: value for key, value in self.token.items() if key not in ("backup", "revision")}):
            path = self.arm(token)
            trial.abandon(self.config_dir, "abc")
            self.assertFalse(os.path.exists(path), token)

    def test_expire_waits_while_another_writer_holds_the_lock(self):
        path = self.arm(self.token)
        with paths.write_lock(self.lock_dir), patch.object(trial, "LOCK_TIMEOUT", 0.2):
            self.assertIsNone(trial.expire(path, self.lock_dir, "abc"))
        self.assertTrue(os.path.exists(path))

    def test_a_failed_confirm_says_nothing_was_tried(self):
        with patch.object(trial, "_write_json", side_effect=OSError("No space left on device")):
            with self.assertRaisesRegex(OSError, r"could not be set up \(No space left on device\), so nothing "
                                                 "was tried"):
                trial.confirm(self.config_dir, self.token, self.backup, "rev")

    def test_the_countdown_starts_right_before_the_write(self):
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

    def test_a_result_file_that_cannot_be_written_still_restores_and_answers(self):
        path = self.arm(self.token)
        with patch.object(trial, "_write_json", side_effect=OSError("disk full")):
            self.assertEqual(trial.expire(path, self.lock_dir, "abc"), (True, trial.RESTORED))
        self.assertEqual(self.read(self.config), "before\n")


if __name__ == "__main__":
    unittest.main()
