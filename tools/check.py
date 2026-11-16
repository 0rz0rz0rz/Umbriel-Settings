#!/usr/bin/env python3
"""Run the checks that cover the current changes and print one line per check.

  python tools/check.py              # pick checks from `git status` (changed + untracked files)
  python tools/check.py core plugin  # run named checks: core, plugin (luac, luau), host, schema, lint (ruff, shellcheck), all
  python tools/check.py test_core_values  # run single test files from tests/ by name
  python tools/check.py -v ...       # also print the full output of passing checks

Failing checks print only their failure blocks (trimmed to --lines), which keeps logs short.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "python"
TESTS = ROOT / "tests"
PLUGIN = ROOT / "noctalia-plugin" / "umbriel-settings"
CORE_TESTS = sorted(p.stem for p in TESTS.glob("test_core*.py"))
HOST_TESTS = sorted(p.stem for p in TESTS.glob("test_*.py") if p.stem not in CORE_TESTS)
ORDER = ["core", "plugin", "host", "schema", "lint"]
TIMEOUT = 900  # seconds per step


def env():
    values = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONDONTWRITEBYTECODE="1",
                  PYTHONPATH=os.pathsep.join([str(PYTHON), str(TESTS)]))
    values.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
    return values


def run(argv, cwd=ROOT):
    started = time.monotonic()
    try:
        result = subprocess.run(argv, cwd=cwd, env=env(), capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired as error:  # e.g. a web view test waiting forever
        output = "".join(part.decode(errors="replace") if isinstance(part, bytes) else part or ""
                         for part in (error.stdout, error.stderr))
        return 124, output + f"\nERROR: timed out after {TIMEOUT} s", time.monotonic() - started
    return result.returncode, result.stdout + result.stderr, time.monotonic() - started


def unittest_summary(output):
    ran = re.search(r"Ran (\d+) tests?", output)
    skipped = re.search(r"skipped=(\d+)", output)
    text = f"{ran.group(1) if ran else '?'} tests"
    return text + (f", {skipped.group(1)} skipped" if skipped else "")


def failure_blocks(output, limit):
    lines = output.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(("=====", "Traceback", "ERROR:", "FAIL:"))), 0)
    picked = [line for line in lines[start:] if not line.startswith("-" * 20)]
    if len(picked) > limit:
        picked = picked[:limit] + [f"... ({len(picked) - limit} more lines; rerun the check with -v)"]
    return "\n".join(picked)


# Exits right after the results: on Python 3.11 PySide6/QtWebEngine can crash in interpreter finalization
# ("bool_dealloc") after every test passed.
RUN_UNITTEST = ("import os, sys, unittest; "
                "result = unittest.main(module=None, argv=['unittest', *sys.argv[1:]], exit=False).result; "
                "sys.stdout.flush(); sys.stderr.flush(); os._exit(0 if result.wasSuccessful() else 1)")


def unittest_modules(modules):
    return [sys.executable, "-c", RUN_UNITTEST, *modules]


CHECKS = {
    "core": [
        ("sync", [sys.executable, str(ROOT / "tools" / "sync_plugin_core.py"), "--check"], None),
        ("tests", unittest_modules(CORE_TESTS), "unittest"),
    ],
    "plugin": [
        ("tests", [sys.executable, "-m", "unittest", "discover", "-s", "noctalia-plugin/tests"], "unittest"),
        ("luac", "luac", None),
        ("luau", "luau-compile", None),
        ("lint", ["noctalia", "plugins", "lint", str(PLUGIN)], None),
    ],
    "host": [("tests", unittest_modules(HOST_TESTS), "unittest")],
    "schema": [("coverage", [sys.executable, "umbriel-settings.py", "--check-schema"], None)],
    "lint": [
        ("ruff", ["ruff", "check", "--quiet", "."], None),
        ("shellcheck", ["shellcheck", "-x", "appimage/build-appimage.sh", "appimage/fetch-pinned.sh",
                        "appimage/recipe/entrypoint.sh"], None),
    ],
}


PARSERS = {"luac": ["luac", "-p", "-o", os.devnull], "luau-compile": ["luau-compile", "--null"]}


def checks_for_paths(paths):
    wanted, files = set(), set()
    for path in paths:
        if path.endswith((".py", ".sh")) or path == "pyproject.toml":
            wanted.add("lint")
        if path.startswith("python/umbriel_core/"):
            wanted |= {"core", "plugin", "host"}
            if path.endswith(("fields.py", "actions.py", "schema.py")):
                wanted.add("schema")
        elif path.startswith("noctalia-plugin/"):
            wanted |= {"plugin", "host"}
        elif path.startswith(("python/umbriel_settings/", ".github/")) or Path(path).stem in HOST_TESTS \
                or path in ("python/umbriel-settings.py", "python/requirements.txt"):
            wanted.add("host")
        elif path.startswith("tests/") and path.endswith(".py"):
            stem = Path(path).stem
            if stem in CORE_TESTS:
                wanted.add("core")
            elif stem.startswith("test_") and (ROOT / path).exists():  # deleted tests show up in git status
                files.add(stem)
        elif path in ("tools/sync_plugin_core.py", "appimage/requirements.lock"):
            wanted.add("core")
    return [name for name in ORDER if name in wanted], sorted(files)


def changed_paths():
    """Changed and untracked paths, or None when git can't tell."""
    try:  # -z: paths as they are (no quoting), NUL-separated; a rename is followed by its old path
        result = subprocess.run(["git", "status", "--porcelain", "-z", "--untracked-files=all"], cwd=ROOT,
                                capture_output=True, text=True)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    paths, entries = [], iter(result.stdout.split("\0"))
    for entry in entries:
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC" or entry[1] in "RC":
            paths.append(next(entries, ""))
    return [path for path in paths if path]


def run_step(name, step, argv, kind, verbose, limit):
    if isinstance(argv, str):  # the shared UI must parse as Lua 5.4 (app) and as Luau (Noctalia)
        if not shutil.which(argv):
            return f"skip {name}:{step} (no {argv})", True
        failures = []
        for path in sorted(PLUGIN.rglob("*.luau")):
            code, output, _ = run([*PARSERS[argv], str(path)])
            if code:
                failures.extend(line for line in output.strip().splitlines() if not line.startswith("Compiled "))
        return (f"ok   {name}:{step}" if not failures else f"FAIL {name}:{step}\n" + "\n".join(failures)), not failures
    if not shutil.which(argv[0]) and not os.path.isabs(argv[0]):
        return f"skip {name}:{step} (no {argv[0]})", True
    if name == "schema" and not shutil.which("umbriel"):  # the coverage check asks the installed Umbriel
        return f"skip {name}:{step} (no umbriel)", True
    cwd = PYTHON if name in ("host", "core", "schema") else ROOT
    code, output, seconds = run(argv, cwd=cwd)
    detail = unittest_summary(output) if kind == "unittest" else (output.strip().splitlines() or [""])[-1][:100]
    line = f"{'ok  ' if code == 0 else 'FAIL'} {name}:{step}  {detail}  {seconds:.1f}s"
    if code != 0:
        line += "\n" + failure_blocks(output, limit)
    elif verbose:
        line += "\n" + output
    return line, code == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("checks", nargs="*", help="check names or test file names from tests/")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--lines", type=int, default=60, help="max failure lines per check")
    args = parser.parse_args()

    names, files = [], []
    for item in args.checks:
        if item == "all":
            names = list(ORDER)
        elif item in CHECKS:
            names.append(item)
        else:
            files.append(Path(item).stem)
    if not args.checks:
        paths = changed_paths()
        if paths is None:
            print("FAIL git status did not work here; name the checks to run (e.g. `check.py all`)")
            return 1
        names, files = checks_for_paths(paths)
        print("checks from git status:", " ".join(names + files) or "none")

    ok = True
    for name in [n for n in ORDER if n in names]:
        for step, argv, kind in CHECKS[name]:
            line, passed = run_step(name, step, argv, kind, args.verbose, args.lines)
            print(line, flush=True)
            ok &= passed
    if files:
        line, passed = run_step("tests", ",".join(files), unittest_modules(files), "unittest", args.verbose, args.lines)
        print(line, flush=True)
        ok &= passed
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
