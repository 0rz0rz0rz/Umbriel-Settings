"""Timestamped config backup snapshots: create, list, delete."""

import datetime
import os
import shutil
import stat

from .paths import migrate_gui_directory


def backup_dir(config_dir):
    """Return the snapshot directory inside a per-config GUI data directory."""
    return os.path.join(config_dir, "backups")


def create_backup_snapshot(path, config_dir):
    """Keep a timestamped, restorable copy under the GUI's data directory."""
    directory = backup_dir(config_dir)
    migrate_gui_directory(path + ".backups", directory)
    os.makedirs(directory, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    snapshot = os.path.join(directory, f"{os.path.basename(path)}.{stamp}.bak")
    shutil.copy2(path, snapshot)
    return snapshot


def list_backup_snapshots(directory, config_path):
    """Return regular backup files belonging to the selected config."""
    prefix = os.path.basename(config_path) + "."
    try:
        with os.scandir(directory) as entries:
            return sorted(
                os.path.join(directory, entry.name)
                for entry in entries
                if entry.name.startswith(prefix)
                and entry.name.endswith(".bak")
                and entry.is_file(follow_symlinks=False)
            )
    except FileNotFoundError:
        return []


def delete_backup_snapshots(directory, config_path, snapshots):
    """Delete only marked regular backup files directly inside the backup directory."""
    directory = os.path.abspath(directory)
    prefix = os.path.basename(config_path) + "."
    deleted = []
    errors = []
    for snapshot in snapshots:
        path = os.path.abspath(snapshot)
        name = os.path.basename(path)
        if (
            os.path.dirname(path) != directory
            or not name.startswith(prefix)
            or not name.endswith(".bak")
        ):
            errors.append(f"{name}: not a valid backup path")
            continue
        try:
            if not stat.S_ISREG(os.lstat(path).st_mode):
                raise OSError("not a regular file")
            os.remove(path)
            deleted.append(name)
        except OSError as error:
            errors.append(f"{name}: {error}")
    return deleted, errors
