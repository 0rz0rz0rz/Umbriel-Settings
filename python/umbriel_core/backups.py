"""Timestamped backup snapshots (`<file name>.<timestamp>.bak`): create, list, delete.

Used for the Umbriel config (per-config directory) and for the desktop files and Noctalia's config.
"""

import datetime
import os
import shutil
import stat

from .paths import migrate_gui_directory

MAX_BACKUPS = 10
STAMP = "%Y%m%d-%H%M%S-%f"


def backup_dir(config_dir):
    """Return the snapshot directory inside a per-config GUI data directory."""
    return os.path.join(config_dir, "backups")


def create_backup_snapshot(path, config_dir, protect=None):
    """Keep a timestamped, restorable copy under the GUI's data directory; older ones beyond MAX_BACKUPS go,
    except `protect` (the backup being restored)."""
    directory = backup_dir(config_dir)
    migrate_gui_directory(path + ".backups", directory)
    return snapshot_file(path, directory, protect=protect)


def snapshot_file(path, directory, protect=None):
    """Copy `path` into `directory` as `<name>.<timestamp>.bak` and keep the newest MAX_BACKUPS (and `protect`)."""
    os.makedirs(directory, exist_ok=True)
    _adopt_single_backup(path, directory)
    snapshot = os.path.join(directory, f"{os.path.basename(path)}.{datetime.datetime.now().strftime(STAMP)}.bak")
    shutil.copy2(path, snapshot)
    prune_backup_snapshots(directory, path, protect=protect)
    return snapshot


def _adopt_single_backup(path, directory):
    """Earlier versions kept one rolling `<name>.bak`; name it by its time so it sorts and prunes as the oldest."""
    legacy = os.path.join(directory, os.path.basename(path) + ".bak")
    if not os.path.isfile(legacy) or os.path.islink(legacy):
        return
    stamp = datetime.datetime.fromtimestamp(os.path.getmtime(legacy)).strftime(STAMP)
    target = os.path.join(directory, f"{os.path.basename(path)}.{stamp}.bak")
    if not os.path.exists(target):
        os.replace(legacy, target)


def prune_backup_snapshots(directory, config_path, keep=MAX_BACKUPS, protect=None):
    """Delete the oldest snapshots so at most `keep` remain (never `protect`); return the deleted names."""
    protect = os.path.abspath(protect) if protect else None
    snapshots = [item for item in list_backup_snapshots(directory, config_path) if os.path.abspath(item) != protect]
    keep -= 1 if protect and os.path.isfile(protect) else 0
    deleted, _errors = delete_backup_snapshots(directory, config_path, snapshots[:max(0, len(snapshots) - keep)])
    return deleted


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
