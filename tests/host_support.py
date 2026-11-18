"""Shared fixtures for the app host tests: a small config and a fake `umbriel` in temporary XDG dirs."""

import os
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch

try:
    import lupa  # noqa: F401
except ImportError:  # pragma: no cover - lupa is a runtime dependency of the app
    lupa = None

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


def isolated_home(test):
    """Temp root with CONFIG at root/config.toml, FAKE_UMBRIEL first on PATH and XDG dirs inside the root
    (XDG_DATA_DIRS too: the desktop page lists installed apps, and the machine's own must not decide results).
    Everything is undone by `test`'s cleanups. Returns (root, config path)."""
    temp = tempfile.TemporaryDirectory()
    test.addCleanup(temp.cleanup)
    root = Path(temp.name)
    config = root / "config.toml"
    config.write_text(CONFIG)
    bin_dir = root / "bin"
    bin_dir.mkdir()
    (bin_dir / "umbriel").write_text(f"#!{sys.executable}\n" + FAKE_UMBRIEL)
    (bin_dir / "umbriel").chmod(0o755)
    env = patch.dict(os.environ, {"XDG_DATA_HOME": str(root / "data"), "XDG_CONFIG_HOME": str(root / "xdg"),
                                  "XDG_DATA_DIRS": str(root / "share"),
                                  "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]})
    env.start()
    test.addCleanup(env.stop)
    return root, config
