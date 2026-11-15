"""Entry point of the standalone app (shared Luau UI in a web view)."""

import argparse
import os
import sys

from . import APP_NAME, __version__


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Edit an Umbriel TOML config file through a graphical interface.")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
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
        options["initialConfig"] = os.path.abspath(os.path.expanduser(path))
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

    from .app_window import AppWindow
    from .appicon import create_app_icon, install_desktop_icon
    from .qt6ct_theme import Qt6ctThemeFollower

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName("umbriel-settings")
    app.theme_follower = Qt6ctThemeFollower(app)
    app.theme_follower.start()
    icon = create_app_icon()
    app._umbriel_icon = icon
    app.setWindowIcon(icon)
    try:
        install_desktop_icon(icon)
    except OSError as error:
        QMessageBox.warning(None, "Could not install desktop icon",
                            f"The window icon is set, but the desktop entry could not be installed:\n{error}")
    try:
        app.win = AppWindow(app_options(args))
    except (FileNotFoundError, ImportError) as error:
        QMessageBox.critical(None, "Cannot start Umbriel Settings", str(error))
        return 1
    if app.win.restore_maximized:
        app.win.showMaximized()
    else:
        app.win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
