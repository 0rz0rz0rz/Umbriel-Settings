#!/usr/bin/env python3
"""Run Noctalia's official plugin validator (community profile) on noctalia-plugin/umbriel-settings.

The validator is `$NOCTALIA_VALIDATOR` (a validate-plugins.py, as CI downloads it), else the copy in the
official-plugins source Noctalia keeps locally. Without `langdetect` the English check is stubbed out (CI
installs it). Exit code 2 with "no validator": tools/check.py reports a skip.
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL_SOURCE = Path.home() / ".local/state/noctalia/plugins/sources/official/repo"
VALIDATOR_PATH = ".github/actions/validate-plugins/validate-plugins.py"
NO_VALIDATOR = 2

STUB = {
    "__init__.py": ("class DetectorFactory:\n    seed = 0\n\n\nclass _English:\n    lang = 'en'\n    prob = 1.0\n\n\n"
                    "def detect_langs(text):\n    return [_English()]\n"),
    "lang_detect_exception.py": "class LangDetectException(Exception):\n    pass\n",
}


def find_validator(temp):
    configured = os.environ.get("NOCTALIA_VALIDATOR")
    if configured:
        return Path(configured)
    try:
        source = subprocess.run(["git", "-C", str(OFFICIAL_SOURCE), "show", f"HEAD:{VALIDATOR_PATH}"],
                                capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    path = temp / "validate-plugins.py"
    path.write_text(source, encoding="utf-8")
    return path


def main():
    with tempfile.TemporaryDirectory() as name:
        temp = Path(name)
        validator = find_validator(temp)
        if validator is None or not validator.is_file():
            print("no validator: set NOCTALIA_VALIDATOR or add Noctalia's official plugin source", flush=True)
            return NO_VALIDATOR
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        if importlib.util.find_spec("langdetect") is None:
            stub = temp / "stub" / "langdetect"
            stub.mkdir(parents=True)
            for file, text in STUB.items():
                (stub / file).write_text(text, encoding="utf-8")
            env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(stub.parent), env.get("PYTHONPATH")]))
            print("language check skipped (langdetect is not installed)", flush=True)
        result = subprocess.run([sys.executable, str(validator), "--profile", "community",
                                 "--root", str(ROOT / "noctalia-plugin")], env=env)
        return result.returncode


if __name__ == "__main__":
    sys.exit(main())
