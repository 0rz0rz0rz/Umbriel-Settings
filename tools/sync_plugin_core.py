#!/usr/bin/env python3
"""Copy python/umbriel_core into the Noctalia plugin, which must be self-contained when installed.

Usage: tools/sync_plugin_core.py [--check]
--check exits 1 (and changes nothing) when the plugin copy differs from the source.
"""
import filecmp
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "python", "umbriel_core")
TARGET = os.path.join(ROOT, "noctalia-plugin", "Umbriel-GUI-Plugin", "umbriel_core")


def source_files(directory):
    """Return relative paths of the package's .py files, ignoring caches."""
    found = []
    for base, dirs, files in os.walk(directory):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        found.extend(
            os.path.relpath(os.path.join(base, name), directory)
            for name in sorted(files) if name.endswith(".py")
        )
    return found


def differences():
    """Return relative paths that are missing, extra or different in the plugin copy."""
    wanted = set(source_files(SOURCE))
    present = set(source_files(TARGET)) if os.path.isdir(TARGET) else set()
    changed = {
        name for name in wanted & present
        if not filecmp.cmp(os.path.join(SOURCE, name), os.path.join(TARGET, name), shallow=False)
    }
    return sorted((wanted ^ present) | changed)


def sync():
    if os.path.isdir(TARGET):
        shutil.rmtree(TARGET)
    shutil.copytree(SOURCE, TARGET, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def main(argv):
    diff = differences()
    if "--check" in argv:
        if diff:
            print("Plugin core is out of date: " + ", ".join(diff), file=sys.stderr)
            return 1
        return 0
    if diff:
        sync()
        print("Synced: " + ", ".join(diff))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
