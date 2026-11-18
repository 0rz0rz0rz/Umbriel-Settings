"""Where the shared Luau UI and the app's own UI data live, and how the app watches files."""

import os

from umbriel_core.paths import default_gui_data_dir

PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLED_UI = os.path.join(PACKAGE_DIR, "ui_shared")  # copied in by the AppImage build
CHECKOUT_UI = os.path.normpath(os.path.join(PACKAGE_DIR, "..", "..", "noctalia-plugin", "umbriel-settings"))


def shared_ui_dir():
    """Return the directory holding app.luau, lib/, ui/, pages/ and umbriel_settings.py."""
    override = os.environ.get("UMBRIEL_SETTINGS_UI_DIR")
    for candidate in (override, BUNDLED_UI, CHECKOUT_UI):
        if candidate and os.path.isfile(os.path.join(candidate, "app.luau")):
            return candidate
    raise FileNotFoundError(
        "The shared UI (app.luau) was not found. Run from a checkout of Umbriel-Settings, or set "
        "UMBRIEL_SETTINGS_UI_DIR to the noctalia-plugin/umbriel-settings directory."
    )


def app_data_dir():
    """Per-user data for the app's UI (drafts, metadata cache); the plugin keeps its own in Noctalia."""
    return os.path.join(default_gui_data_dir(), "app-ui")


def watch_with_parents(watcher, files, prune=False):
    """Watch the existing `files` and their folders on a QFileSystemWatcher; return the paths added.

    Editors and theme tools replace files atomically, which ends a file watch; the folder's change signal
    lets the caller call this again to re-add it. `prune` drops watches on anything else.
    """
    wanted = [path for path in files if os.path.exists(path)]
    wanted += sorted({os.path.dirname(path) for path in files if os.path.isdir(os.path.dirname(path))})
    current = watcher.files() + watcher.directories()
    if prune:
        stale = [path for path in current if path not in wanted]
        if stale:
            watcher.removePaths(stale)
    missing = [path for path in wanted if path not in current]
    if missing:
        watcher.addPaths(missing)
    return missing
