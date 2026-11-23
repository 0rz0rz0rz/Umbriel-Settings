---
name: audit-crash-safety
description: "Use before pushing an update to the community-plugins PR, and after changing any code that writes the config or private data, keeps recovery state (Try token, backups, drafts), takes the write lock, or installs files outside the plugin folder: a kill-point audit (SIGTERM, SIGKILL, panel close, disk full, concurrent writer) of every write path, with tests for each gap found."
---

# Kill-point audit

Reading each path and checking what each step does is not enough (that missed PR #1544 rounds 1–3). Walk
the **timeline**: stop the process between every pair of steps and ask what is on disk and who recovers it.

## 1. List the write paths the change touches

Durable state and its owners (details in `core-helper.md`):

| State | Written by | Recovered by |
| --- | --- | --- |
| config | helper `save`, `restore`, `desktop-save`; `titlebar_apply.py` (Noctalia post_hook); Try watcher | backups; Try watcher |
| `trial.json` (Try token) | `trial.arm` → `confirm` (before the write); removed by `claim` (Keep, Go back after its write), `abandon` (failed save), watcher | watcher at deadline; `GIVE_UP` expiry |
| backups `*.bak`, `*.titlebar.bak` | `Session.save`, `restore`, watcher, `titlebar_apply` | Backups page (`delete-backups` keeps `pending_backup`) |
| `draft.json`, sidecars, `run/` files | panel/app, helper | `drafts.restore`; `sweep_run_files` |
| Noctalia template, hook script, rendered file | `titlebar_theme.follow` | `cleanup` (`onExit` disable; uninstall best effort) |

## 2. For each path, number the steps and test every gap

Write the steps out (e.g. `save {trial}`: lock → arm (token, watcher) → apply/validate → backup → confirm →
replace → sidecars → follow intents → read back → reply → unlock). Between each pair, apply each interruption:

| Interruption | What runs | Ask |
| --- | --- | --- |
| SIGTERM (Noctalia helper timeout, logout) | `main` turns it into `SystemExit`: every `except BaseException`/`finally` runs | Does a handler delete or undo recovery state although the protected write may already have happened? |
| SIGKILL, power loss | nothing | Is recovery state already on disk *before* the risky write? Is the write atomic (temp + fsync + replace)? |
| Panel closed / plugin unloaded | the helper runs on; the panel's callback is dropped (`always` only notifies) | Does safety depend on a callback (Keep, Go back, cleanup)? Are flags like `ctx.saving` cleared on `onOpen`? |
| Session end | the detached watcher dies too | Does any promise (README, PR text) claim more? Does stale state expire (`GIVE_UP`)? |
| `OSError` (disk full, EACCES) at each write | normal exception path | Does the failure write nothing, and leave no state that blocks the next attempt (`busy`)? |
| A second writer (app + panel, hook, watcher) | flock on `write.lock` | Does it hold the shared lock and re-check the revision before replacing? |
| User action in between (Backups delete, Save, a second Try) | another helper command | Can it destroy something a pending recovery still needs? |
| Repeated page changes / close + reopen | callbacks dropped, processes keep running | Does anything that can't be stopped (long polls, `wait`) start again each time? Noctalia runs at most 8 commands per plugin; past that every call, Save included, is refused (the harness mirrors the cap). |

Rules that came out of the reviews:
- Persist recovery metadata (backup path, expected revision, deadline) **before** the write it protects.
- An error or interrupt handler decides from **disk state** (hash, existence), never from "an exception
  happened": once the protected write may be done, leave recovery to its owner (`trial.abandon`).
- Remove a claim/token only **after** the write it guards (`restore` claims after writing).
- Private copies are 0600 when first written and when replaced; dirs 0700.
- A file a pending recovery needs is protected under the same lock (`protect_pending`).
- Out-of-tree artifacts start and stop with the reviewed save, are removed on disable, and docs call uninstall
  cleanup best effort.
- A README or PR sentence about safety is a claim: each must match a tested kill point.

## 3. Test each gap with the real mechanism

- Real SIGTERM right after a step: run the helper through a `python -I -c` wrapper that patches the step and
  calls `os.kill(os.getpid(), SIGTERM)` (`SaveTests.interrupted_save` in `noctalia-plugin/tests/test_umbriel_settings.py`).
- Disk full: patch the write to raise `OSError(28, ...)` (same helper, `how="full"`; core: `patch.object`).
- Panel close mid-request: `H.hold(cmd)`, close, `H.release(cmd)` (`outputs_test.lua` "close mid-save").
- Watcher/lock: `tests/test_core_trial.py` (`expire` under a held `paths.write_lock`).
- Each new test must fail before the fix; end Try tests with `trial-end` so no watcher lingers
  (`pgrep -af trial.json`); temp dirs only.

## 4. Report

Give the user a short table, path × kill point → outcome (safe / fixed / accepted + why), before asking to commit or push.
Fix gaps first; list accepted ones in the reply to the reviewer only if they ask.
