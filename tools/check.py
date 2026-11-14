#!/usr/bin/env python3
"""Run the checks that cover the current changes and print one line per check.

  python tools/check.py              # pick checks from `git status` (changed + untracked files)
  python tools/check.py core plugin  # run named checks: core, plugin, host, app, schema, all
  python tools/check.py test_sidebar # run single app test files by name
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
HOST_TESTS = ["test_host_runtime", "test_host_bridge"]
CORE_TESTS = ["test_core"]
ORDER = ["core", "plugin", "host", "app", "schema"]


def app_tests():
    skip = set(HOST_TESTS + CORE_TESTS)
    return sorted(p.stem for p in TESTS.glob("test_*.py") if p.stem not in skip)


def env():
    values = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONDONTWRITEBYTECODE="1",
                  PYTHONPATH=os.pathsep.join([str(PYTHON), str(TESTS)]))
    values.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
    return values


def run(argv, cwd=ROOT):
    started = time.monotonic()
    result = subprocess.run(argv, cwd=cwd, env=env(), capture_output=True, text=True)
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


def unittest_modules(modules):
    return [sys.executable, "-m", "unittest", *modules]


CHECKS = {
    "core": [
        ("sync", [sys.executable, str(ROOT / "tools" / "sync_plugin_core.py"), "--check"], None),
        ("tests", unittest_modules(CORE_TESTS), "unittest"),
    ],
    "plugin": [
        ("tests", [sys.executable, "-m", "unittest", "discover", "-s", "noctalia-plugin/tests"], "unittest"),
        ("luac", "luac", None),
        ("lint", ["noctalia", "plugins", "lint", str(PLUGIN)], None),
    ],
    "host": [("tests", unittest_modules(HOST_TESTS), "unittest")],
    "app": [("tests", None, "unittest")],  # filled with app_tests() at run time
    "schema": [("coverage", [sys.executable, "umbriel-config-gui.py", "--check-schema"], None)],
}


def checks_for_paths(paths):
    wanted, files = set(), set()
    for path in paths:
        if path.startswith("python/umbriel_core/"):
            wanted |= {"core", "plugin", "host", "app"}
            if path.endswith(("fields.py", "actions.py", "schema.py")):
                wanted.add("schema")
        elif path.startswith("noctalia-plugin/"):
            wanted |= {"plugin", "host"}
        elif path.startswith(("python/umbriel_config_gui/host/", "python/umbriel_config_gui/app")) \
                or Path(path).stem in HOST_TESTS:
            wanted.add("host")
        elif path.startswith("tests/") and path.endswith(".py"):
            stem = Path(path).stem
            if stem in CORE_TESTS:
                wanted.add("core")
            elif stem.startswith("test_"):
                files.add(stem)
        elif path.startswith("python/") and path.endswith(".py"):
            wanted.add("app")
        elif path == "tools/sync_plugin_core.py":
            wanted.add("core")
    if "app" in wanted:
        files.clear()
    return [name for name in ORDER if name in wanted], sorted(files)


def changed_paths():
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT,
                         capture_output=True, text=True).stdout
    paths = []
    for line in out.splitlines():
        entry = line[3:]
        paths.extend(part.strip().strip('"') for part in entry.split(" -> "))
    return paths


def run_step(name, step, argv, kind, verbose, limit):
    if argv == "luac":
        if not shutil.which("luac"):
            return f"skip {name}:{step} (no luac)", True
        failures = []
        for path in sorted(PLUGIN.rglob("*.luau")):
            code, output, _ = run(["luac", "-p", "-o", os.devnull, str(path)])
            if code:
                failures.append(output.strip())
        return (f"ok   {name}:{step}" if not failures else f"FAIL {name}:{step}\n" + "\n".join(failures)), not failures
    if not shutil.which(argv[0]) and not os.path.isabs(argv[0]):
        return f"skip {name}:{step} (no {argv[0]})", True
    cwd = PYTHON if name in ("host", "app", "core", "schema") else ROOT
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
    parser.add_argument("checks", nargs="*", help="check names or app test file names")
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
        names, files = checks_for_paths(changed_paths())
        print("checks from git status:", " ".join(names + files) or "none")

    ok = True
    for name in [n for n in ORDER if n in names]:
        for step, argv, kind in CHECKS[name]:
            if argv is None:
                argv = unittest_modules(app_tests())
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
