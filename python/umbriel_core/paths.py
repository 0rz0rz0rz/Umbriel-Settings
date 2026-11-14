"""GUI data locations, atomic file writes and config snapshots shared by the app and the plugin."""

import hashlib
import json
import os
import shutil

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.config/umbriel/config.toml")


def default_gui_data_dir():
    """Return `$XDG_DATA_HOME/umbriel-config-gui`, the data directory shared by the app and the plugin."""
    return os.path.join(
        os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "umbriel-config-gui"
    )


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
    except OSError:
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


def write_text_file(path, text):
    """Write text atomically so file watchers never see a partially written file."""
    real = os.path.realpath(path)
    directory = os.path.dirname(real)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = real + ".gui-tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())  # make sure the data is on disk before it replaces the old file
        try:
            shutil.copymode(real, tmp)
        except OSError:
            pass
        os.replace(tmp, real)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def config_fingerprint(path):
    """Return a content hash used to detect edits made outside this program."""
    with open(path, "rb") as config_file:
        data = config_file.read()
    return hashlib.sha256(data).hexdigest()


def read_config_state(path):
    """Read config text and its matching content hash from the same file snapshot."""
    with open(path, "rb") as config_file:
        data = config_file.read()
    return data.decode("utf-8"), hashlib.sha256(data).hexdigest()


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
