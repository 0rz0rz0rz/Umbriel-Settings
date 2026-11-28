"""Entry point of the standalone app (shared Luau UI in a web view)."""

import argparse
import os
import sys
import traceback

from umbriel_core.meta import NOCTALIA_VERSION, UMBRIEL_VERSION
from umbriel_core.paths import normalize_config_path

from . import APP_NAME, __version__

VERSION_TEXT = f"{APP_NAME} {__version__} (Umbriel {UMBRIEL_VERSION}, Noctalia {NOCTALIA_VERSION}+)"


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Edit an Umbriel TOML config file through a graphical interface.")
    parser.add_argument("--version", action="version", version=VERSION_TEXT)
    parser.add_argument("config", nargs="?", help="Path to the Umbriel config TOML file to edit.")
    parser.add_argument("--config", dest="config_option", help="Explicit path to the Umbriel config TOML file to edit.")
    parser.add_argument("--no-validate", action="store_true", help="Start with validation before saving turned off.")
    parser.add_argument("--no-rebuild", action="store_true", help="Never regroup the file layout when saving.")
    parser.add_argument("--check-schema", action="store_true",
                        help="Compare the GUI's fields with `umbriel config schema` and exit.")
    return parser.parse_args(argv)


def check_schema():
    import subprocess

    from umbriel_core.schema import check_schema_coverage, load_umbriel_schema
    try:
        schema = load_umbriel_schema()
    except (FileNotFoundError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"Schema check unavailable: {error}", file=sys.stderr)
        return 2
    missing, stale = check_schema_coverage(schema)
    print(f"Umbriel {schema.get('version', 'unknown version')} ({schema.get('revision') or 'unknown revision'}): "
          f"{len(missing)} unsupported option(s), {len(stale)} stale GUI field(s).")
    for path in missing:
        print(f"Missing GUI field: {path}")
    for path in stale:
        print(f"Stale GUI field: {path}")
    return 1 if missing or stale else 0


def app_options(args):
    options = {"appVersion": __version__}
    path = args.config_option or args.config
    if path:
        options["initialConfig"] = normalize_config_path(path)
    if args.no_validate:
        options["validateDefault"] = False
    if args.no_rebuild:
        options["rebuildDefault"] = False
    return options


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    if args.check_schema:
        return check_schema()
    from PySide6.QtWidgets import QApplication, QMessageBox

    from . import app_window, instance
    from .app_window import AppWindow
    from .appicon import create_app_icon, install_desktop_icon
    from .qt6ct_theme import Qt6ctThemeFollower

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName("umbriel-settings")
    options = app_options(args)
    # A launcher's activation token lets the running window take the focus on Wayland.
    server = instance.claim({"config": options.get("initialConfig", ""),
                             "token": os.environ.get("XDG_ACTIVATION_TOKEN", "")})
    if server is None:
        return 0  # the running app was raised instead
    app.instance_server = server
    app.theme_follower = Qt6ctThemeFollower(app)
    app.theme_follower.start()
    icon = create_app_icon()
    app._umbriel_icon = icon
    app.setWindowIcon(icon)
    try:
        if not icon.isNull():
            install_desktop_icon(icon)
    except OSError as error:
        QMessageBox.warning(None, "Could not install desktop icon",
                            f"The window icon is set, but the desktop entry could not be installed:\n{error}")
    try:
        app.win = AppWindow(options)
    except Exception as error:  # missing files or modules, a Lua error in the UI, unreadable bundled data
        traceback.print_exc()
        QMessageBox.critical(None, "Cannot start Umbriel Settings", str(error))
        return 1
    app_window.quit_on_signals(app, app.win)
    server.activated.connect(app.win.activate_from)
    if app.win.restore_maximized:
        app.win.showMaximized()
    else:
        app.win.show()
    status = app.exec()
    # Python still waits for running helper calls before it exits: a launch meanwhile must open a new window,
    # not hand over to this closing one
    server.server.close()
    return status


if __name__ == "__main__":
    sys.exit(main())
