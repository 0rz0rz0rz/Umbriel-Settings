"""Read and update XDG user folder paths (user-dirs.dirs)."""

import hashlib
import re
from pathlib import Path

from .backups import snapshot_file
from .paths import atomic_write, xdg_config_home

ENTRY = re.compile(r'^\s*XDG_([A-Z]+)_DIR\s*=\s*"(.*)"\s*$')
KEY = re.compile(r"^[A-Z]+$")


def config_path():
    return Path(xdg_config_home()) / "user-dirs.dirs"


def read_document(path):
    try:
        contents = path.read_bytes()
    except FileNotFoundError:
        return "", "missing"
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{path} is not UTF-8 text ({error.reason} at byte {error.start}).") from None
    return text, hashlib.sha256(contents).hexdigest()


def snapshot(text, revision):
    values = {}
    for line in text.splitlines():
        match = ENTRY.fullmatch(line)
        if match:
            values[match.group(1)] = match.group(2)
    return {"values": values, "revision": revision}


def validate_changes(changes):
    if not isinstance(changes, dict):
        raise ValueError("Changes must be an object.")
    for key, value in changes.items():
        if not isinstance(key, str) or not KEY.fullmatch(key) or not isinstance(value, str):
            raise ValueError("Invalid folder name or path.")
        if not value:
            continue
        if not (value.startswith("/") or value == "$HOME" or value.startswith("$HOME/")):
            raise ValueError(f"{key}: use an absolute path or $HOME/path.")
        remainder = value[5:] if value.startswith("$HOME") else value
        if any(char in remainder for char in '$`"\\\r\n') or "\0" in value:
            raise ValueError(f"{key}: path contains unsupported shell characters.")


def save(path, backup_dir, expected_revision, changes):
    validate_changes(changes)
    if path.is_symlink():
        raise ValueError("User folders file is a symlink; edit its target directly.")
    text, revision = read_document(path)
    if revision != expected_revision:
        raise ValueError("User folders changed externally. Reload before saving.")
    output = []
    seen = set()
    for line in text.splitlines(keepends=True):
        match = ENTRY.fullmatch(line.rstrip("\r\n"))
        if match and match.group(1) in changes:
            key = match.group(1)
            seen.add(key)
            if changes[key]:
                output.append(f'XDG_{key}_DIR="{changes[key]}"\n')
        else:
            output.append(line)
    for key, value in changes.items():
        if key not in seen and value:
            if output and not output[-1].endswith(("\n", "\r")):
                output[-1] += "\n"
            output.append(f'XDG_{key}_DIR="{value}"\n')
    updated = "".join(output).encode("utf-8")
    if revision != "missing":
        snapshot_file(str(path), str(backup_dir))
    atomic_write(path, updated)
    return {"revision": hashlib.sha256(updated).hexdigest()}
