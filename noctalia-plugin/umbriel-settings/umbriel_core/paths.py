"""GUI data locations, atomic file writes and config snapshots shared by the app and the plugin."""

import hashlib
import json
import os
import shutil
import stat
import tempfile

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.config/umbriel/config.toml")
DATA_DIR_NAME = "umbriel-settings"
LEGACY_DIR_NAME = "umbriel-config-gui"  # data, config and desktop-entry name before the rename to Umbriel Settings


def default_gui_data_dir():
    """Return `$XDG_DATA_HOME/umbriel-settings`, the data directory shared by the app and the plugin.

    The pre-rename `umbriel-config-gui` directory (backups, labels, locks, last config) is moved there once;
    if that move fails the old directory keeps being used so nothing appears lost.
    """
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(base, DATA_DIR_NAME)
    legacy = os.path.join(base, LEGACY_DIR_NAME)
    if not os.path.lexists(path) and os.path.isdir(legacy) and not os.path.islink(legacy):
        try:
            os.rename(legacy, path)
        except OSError:
            return legacy
    return path


def normalize_config_path(path, default=DEFAULT_CONFIG_PATH):
    """Normalize a config path and return an absolute version suitable for the GUI."""
    if not path:
        return default
    return os.path.abspath(os.path.expanduser(path.strip()))


def config_gui_data_dir(config_path, data_dir):
    """Return a private GUI-data directory associated with one config path."""
    identity = hashlib.sha256(
        os.path.abspath(config_path).encode("utf-8")
    ).hexdigest()[:20]
    return os.path.join(data_dir, "configs", identity)


def load_saved_config_path(saved_file, default_path):
    """Return the config path stored in `saved_file`, or `default_path` when there is none."""
    if not os.path.exists(saved_file):
        return default_path
    try:
        with open(saved_file, encoding="utf-8") as f:
            saved = f.read().strip()
        if saved:
            return normalize_config_path(saved)
    except (OSError, UnicodeError):
        pass
    return default_path


def migrate_gui_file(legacy_path, new_path):
    """Move a GUI-owned file from its former location into the application data directory."""
    if os.path.isfile(legacy_path) and not os.path.exists(new_path):
        os.makedirs(os.path.dirname(new_path), exist_ok=True)
        os.replace(legacy_path, new_path)


def migrate_gui_directory(legacy_path, new_path):
    """Move GUI-owned files from a former directory into the application data directory."""
    if not os.path.isdir(legacy_path):
        return
    os.makedirs(new_path, exist_ok=True)
    for name in os.listdir(legacy_path):
        source = os.path.join(legacy_path, name)
        destination = os.path.join(new_path, name)
        if not os.path.exists(destination):
            shutil.move(source, destination)
    try:
        os.rmdir(legacy_path)
    except OSError:
        pass


def atomic_write(path, data, mode=None):
    """Replace `path` with `data` (str or bytes) so readers and file watchers never see a partial file.

    The data goes to a unique temporary file in the same directory and reaches the disk before it replaces the
    old file. `mode` defaults to the replaced file's permissions, else 0o644. A symlink at `path` is replaced
    itself; callers that must refuse symlinks check first.
    """
    path = os.fspath(path)
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    if mode is None:
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
        except OSError:
            mode = 0o644
    handle, tmp = tempfile.mkstemp(dir=directory, prefix=f".{os.path.basename(path)}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_text_file(path, text):
    """Write text atomically; a symlinked GUI file is written through to its target."""
    atomic_write(os.path.realpath(path), text)


def labels_file(config_path, config_dir):
    """Return the GUI-only entry label sidecar, migrating it from next to the config if needed."""
    sidecar = os.path.join(config_dir, "gui-labels.json")
    migrate_gui_file(os.path.abspath(config_path) + ".gui-labels.json", sidecar)
    return sidecar


def load_all_entry_labels(config_path, config_dir):
    """Return every stored entry label list keyed by entry path, e.g. {"window_rule": ["Foo", ""]}."""
    try:
        with open(labels_file(config_path, config_dir), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        key: [label if isinstance(label, str) else "" for label in labels]
        for key, labels in data.items()
        if isinstance(labels, list)
    }


def load_entry_labels(config_path, entry_path, config_dir):
    """Load GUI-only entry labels for one entry path."""
    return load_all_entry_labels(config_path, config_dir).get(entry_path, [])


def save_entry_labels(config_path, entry_path, labels, config_dir):
    """Save GUI-only entry labels without adding unsupported keys to the Umbriel config."""
    sidecar = labels_file(config_path, config_dir)
    try:
        with open(sidecar, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    if any(labels):
        data[entry_path] = labels
    else:
        data.pop(entry_path, None)
    write_text_file(sidecar, json.dumps(data, indent=2))
