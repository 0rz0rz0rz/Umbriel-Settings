"""Move files left by earlier versions into the current layout, once.

Earlier versions kept GUI files next to the config (`<config>.gui-labels.json`, `gui-locked-keybinds.json`,
`<config>.backups/`) and single rolling `<name>.bak` backups. A marker file makes each migration run only once:
per config in its data directory, and once for the shared backup directory.
"""

import datetime
import os
import re
import shutil

from .backups import STAMP
from .paths import LABELS_FILE_NAME, LOCK_FILE_NAME

MARKER = ".migrated-v1"
TIMESTAMPED = re.compile(r"\.\d{8}-\d{6}-\d{6}\.bak$")


def migrate_config(config_path, config_dir):
    """Move one config's old sidecars into `config_dir`; an OSError leaves the marker unwritten (retried later)."""
    marker = os.path.join(config_dir, MARKER)
    if os.path.exists(marker):
        return
    config_path = os.path.abspath(config_path)
    try:
        _move_file(config_path + ".gui-labels.json", os.path.join(config_dir, LABELS_FILE_NAME))
        _move_file(os.path.join(os.path.dirname(config_path), LOCK_FILE_NAME), os.path.join(config_dir, LOCK_FILE_NAME))
        backups = os.path.join(config_dir, "backups")
        _move_directory(config_path + ".backups", backups)
        _adopt_single_backups(backups)
        _write_marker(marker)
    except OSError:
        pass


def migrate_data_dir(data_dir):
    """Give old rolling backups in the shared backup directory (desktop files, Noctalia's config) a timestamp."""
    marker = os.path.join(data_dir, MARKER)
    if os.path.exists(marker):
        return
    try:
        _adopt_single_backups(os.path.join(data_dir, "backups"))
        _write_marker(marker)
    except OSError:
        pass


def _write_marker(marker):
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    with open(marker, "w", encoding="utf-8"):
        pass


def _move_file(legacy_path, new_path):
    if os.path.isfile(legacy_path) and not os.path.exists(new_path):
        os.makedirs(os.path.dirname(new_path), exist_ok=True)
        os.replace(legacy_path, new_path)


def _move_directory(legacy_path, new_path):
    if not os.path.isdir(legacy_path):
        return
    os.makedirs(new_path, exist_ok=True)
    for name in os.listdir(legacy_path):
        destination = os.path.join(new_path, name)
        if not os.path.exists(destination):
            shutil.move(os.path.join(legacy_path, name), destination)
    try:
        os.rmdir(legacy_path)
    except OSError:
        pass


def _adopt_single_backups(directory):
    """Name each old `<name>.bak` by its time, so it sorts and is pruned as that file's oldest snapshot."""
    try:
        names = os.listdir(directory)
    except FileNotFoundError:
        return
    for name in names:
        legacy = os.path.join(directory, name)
        if not name.endswith(".bak") or TIMESTAMPED.search(name) or not os.path.isfile(legacy) \
                or os.path.islink(legacy):
            continue
        stamp = datetime.datetime.fromtimestamp(os.path.getmtime(legacy)).strftime(STAMP)
        target = os.path.join(directory, f"{name[:-len('.bak')]}.{stamp}.bak")
        if not os.path.exists(target):
            os.replace(legacy, target)
