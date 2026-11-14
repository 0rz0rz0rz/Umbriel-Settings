"""Where the shared Luau UI and the app's own UI data live."""

import os

PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLED_UI = os.path.join(PACKAGE_DIR, "ui_shared")  # copied in by the AppImage build
CHECKOUT_UI = os.path.normpath(os.path.join(PACKAGE_DIR, "..", "..", "noctalia-plugin", "Umbriel-GUI-Plugin"))


def shared_ui_dir():
    """Return the directory holding app.luau, lib/, ui/, pages/ and umbriel_settings.py."""
    override = os.environ.get("UMBRIEL_SETTINGS_UI_DIR")
    for candidate in (override, BUNDLED_UI, CHECKOUT_UI):
        if candidate and os.path.isfile(os.path.join(candidate, "app.luau")):
            return candidate
    raise FileNotFoundError(
        "The shared UI (app.luau) was not found. Run from a checkout of Umbriel-GUI, or set "
        "UMBRIEL_SETTINGS_UI_DIR to the noctalia-plugin/Umbriel-GUI-Plugin directory."
    )


def app_data_dir():
    """Per-user data for the app's UI (drafts, metadata cache); the plugin keeps its own in Noctalia."""
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "umbriel-config-gui", "app-ui")
