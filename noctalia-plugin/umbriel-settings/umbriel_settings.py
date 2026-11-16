"""Single helper behind the Umbriel Settings panel.

Usage: umbriel_settings.py COMMAND [--request FILE] [--response FILE]

Requests and responses are JSON files, because helper output and argv sizes are limited. On success
the response file is written and stdout is {"ok": true}; on a handled error stdout is
{"ok": false, "error": "...", "code": "..."} and the exit status is still 0. Without --response the
result is printed to stdout instead (useful for tests).
"""

import datetime
import json
import os
import shutil
import subprocess
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from umbriel_core import backups, paths, schema  # noqa: E402
from umbriel_core.launch import child_env  # noqa: E402

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
TOMLKIT_HINT = ("Python's tomlkit module is missing. Install it with your package manager "
                "(Arch: pacman -S python-tomlkit) or `pip install --user tomlkit`.")


class HelperError(Exception):
    def __init__(self, message, code="error"):
        super().__init__(message)
        self.code = code


def plugin_version():
    try:
        with open(os.path.join(PLUGIN_DIR, "plugin.toml"), encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("version"):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""


def need_tomlkit():
    try:
        import tomlkit  # noqa: F401
    except ImportError as error:
        raise HelperError(TOMLKIT_HINT, "missing_dependency") from error


def data_dir():
    return paths.default_gui_data_dir()


def saved_config_file():
    return os.path.join(data_dir(), "gui-config-path")


def config_path(request):
    """The config the request names, else the one the app or plugin last used, else the default."""
    requested = request.get("config")
    if isinstance(requested, str) and requested.strip():
        return paths.normalize_config_path(requested)
    return paths.load_saved_config_path(saved_config_file(), paths.DEFAULT_CONFIG_PATH)


def schema_state(coverage=False):
    """Return (options by path, info) from the installed Umbriel, or ({}, reason) when unavailable.

    With `coverage`, info also lists options without a setting (`missing`) and settings Umbriel lacks (`stale`).
    """
    try:
        document = schema.load_umbriel_schema()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        return {}, {"available": False, "reason": str(error)}
    info = {"available": True, "version": document.get("version"), "revision": document.get("revision")}
    if coverage:
        info["missing"], info["stale"] = schema.check_schema_coverage(document)
    return schema.schema_options_by_path(document), info


def session(request):
    need_tomlkit()
    from umbriel_core.session import ConfigSession
    options, _ = schema_state()
    return ConfigSession(config_path(request), data_dir(), options)


# ------------------------------------------------------------------ commands
def cmd_meta(request):
    """Write meta.json and search.json next to the response and return their paths."""
    from umbriel_core.meta import build_meta
    options, info = schema_state(coverage=True)
    meta = build_meta(options, info, plugin_version())
    search = []
    for fid, field in meta["fields"].items():
        search.append([fid, field.pop("search")])
    out_dir = request.get("out_dir")
    if not isinstance(out_dir, str) or not out_dir:
        return {"meta": meta, "search": search}
    os.makedirs(out_dir, exist_ok=True)
    result = {}
    for name, data in (("meta", meta), ("search", search)):
        path = os.path.join(out_dir, f"{name}.json")
        atomic_write_text(path, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        result[name] = path
    return result


def cmd_read(request):
    return session(request).read()


def cmd_preview(request):
    return session(request).preview(request.get("changes"), bool(request.get("validate", True)))


def cmd_save(request):
    current = session(request)
    report = current.save(request.get("changes"), bool(request.get("validate", True)))
    if report.get("saved") and request.get("remember_path"):
        paths.write_text_file(saved_config_file(), current.path)
    if report.get("saved"):
        report["state"] = current.read()
    return report


def cmd_set_config(request):
    """Check that a config can be read, remember it for the app and the plugin, and return it."""
    current = session(request)
    state = current.read()
    paths.write_text_file(saved_config_file(), current.path)
    return state


def backup_listing(path):
    config_dir = paths.config_gui_data_dir(path, data_dir())
    directory = backups.backup_dir(config_dir)
    items = []
    for snapshot in reversed(backups.list_backup_snapshots(directory, path)):
        try:
            stat = os.stat(snapshot)
        except OSError:
            continue
        items.append({
            "path": snapshot,
            "name": os.path.basename(snapshot),
            "time": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "size": stat.st_size,
        })
    return {"path": path, "directory": directory, "backups": items}


def cmd_backups(request):
    return backup_listing(config_path(request))


def cmd_backup_diff(request):
    """Diff the current config against one snapshot (snapshot shown as the new side)."""
    import difflib
    path = config_path(request)
    snapshot = checked_snapshot(path, request.get("snapshot"))
    with open(path, encoding="utf-8") as current, open(snapshot, encoding="utf-8") as old:
        diff = "".join(difflib.unified_diff(
            current.read().splitlines(keepends=True), old.read().splitlines(keepends=True),
            fromfile="current", tofile=os.path.basename(snapshot), n=2,
        ))
    return {"diff": diff}


def checked_snapshot(path, snapshot):
    listing = backup_listing(path)
    if snapshot not in {item["path"] for item in listing["backups"]}:
        raise HelperError("That backup no longer exists.")
    return snapshot


def cmd_restore(request):
    need_tomlkit()
    import tomlkit
    current = session(request)
    snapshot = checked_snapshot(current.path, request.get("snapshot"))
    if current.revision() != request.get("revision"):
        raise HelperError("The config changed since it was loaded. Reload before restoring.", "conflict")
    with open(snapshot, encoding="utf-8") as handle:
        text = handle.read()
    try:
        tomlkit.parse(text)
    except tomlkit.exceptions.TOMLKitError as error:
        raise HelperError(f"The backup is not valid TOML: {error}") from error
    if os.path.islink(current.path):
        raise HelperError("The config is a symlink; edit its target directly.")
    backups.create_backup_snapshot(current.path, current.config_dir, protect=snapshot)
    paths.write_text_file(current.path, text)
    return {"state": current.read(), "backups": backup_listing(current.path)}


def cmd_delete_backups(request):
    path = config_path(request)
    listing = backup_listing(path)
    marked = request.get("snapshots")
    if not isinstance(marked, list):
        raise HelperError("Choose backups to delete.")
    deleted, errors = backups.delete_backup_snapshots(listing["directory"], path, marked)
    return {"deleted": deleted, "errors": errors, "backups": backup_listing(path)}


def cmd_desktop(request):
    from umbriel_core import mimeapps, xdg_dirs
    dirs_text, dirs_revision = xdg_dirs.read_document(xdg_dirs.config_path())
    apps_text, apps_revision = mimeapps.read_document(mimeapps.config_path())
    return {
        "userdirs": xdg_dirs.snapshot(dirs_text, dirs_revision),
        "apps": mimeapps.snapshot(apps_text, apps_revision, mimeapps.installed_apps()),
        "roles": mimeapps.ROLES,
    }


def cmd_desktop_save(request):
    """Save user folders and default apps; each part checks its own revision."""
    from pathlib import Path

    from umbriel_core import mimeapps, xdg_dirs
    backup_dir = Path(data_dir()) / "backups"
    result = {}
    folders, apps = request.get("userdirs"), request.get("apps")
    if any(part is not None and not isinstance(part, dict) for part in (folders, apps)):
        raise HelperError("Desktop changes must be objects.")
    if folders:
        result["userdirs"] = xdg_dirs.save(
            xdg_dirs.config_path(), backup_dir, folders.get("revision"), folders.get("changes"))
    if apps:
        result["apps"] = mimeapps.save(
            mimeapps.config_path(), backup_dir, apps.get("revision"), apps.get("changes"))
    return result


def cmd_extension(request):
    from umbriel_core.mimeapps import extension_mime
    return {"mime": extension_mime(str(request.get("extension", "")))}


def cmd_outputs(request):
    executable = shutil.which("umbriel")
    if not executable:
        raise HelperError("The umbriel command was not found.", "missing_umbriel")
    try:
        result = subprocess.run([executable, "outputs", "--json"], capture_output=True, text=True,
                                timeout=5, check=False)
    except subprocess.TimeoutExpired as error:
        raise HelperError("`umbriel outputs --json` did not finish within 5 seconds. "
                          "Make sure Umbriel is running in this session.") from error
    if result.returncode:
        raise HelperError("`umbriel outputs --json` failed: "
                          + (result.stderr.strip() or result.stdout.strip() or f"exit status {result.returncode}"))
    try:
        outputs = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise HelperError(f"`umbriel outputs --json` returned invalid JSON: {error}") from error
    if not isinstance(outputs, list) or any(not isinstance(o, dict) or not isinstance(o.get("name"), str)
                                            for o in outputs):
        raise HelperError("`umbriel outputs --json` returned an unexpected output list.")
    return {"outputs": outputs}


def cmd_kde_colors(request):
    from umbriel_core import kde
    try:
        scheme = kde.qt6ct_scheme_path()
        colors, backgrounds, errors = kde.read_title_bar_rgb(scheme)
    except (OSError, UnicodeError, ValueError) as error:
        return {"available": False, "reason": str(error)}

    def hex_map(found):
        return {".".join(path): "#{:02X}{:02X}{:02X}FF".format(*rgb) for path, rgb in found.items()}

    return {
        "available": True, "scheme": scheme, "colors": hex_map(colors), "backgrounds": hex_map(backgrounds),
        "errors": {".".join(path): message for (_, path), message in errors.items()},
    }


def cmd_pick_folder(request):
    start = request.get("start") or os.path.expanduser("~")
    start = os.path.expanduser(str(start).replace("$HOME", os.path.expanduser("~"), 1))
    if shutil.which("zenity"):
        argv = ["zenity", "--file-selection", "--directory", f"--filename={start.rstrip('/')}/"]
    elif shutil.which("kdialog"):
        argv = ["kdialog", "--getexistingdirectory", start]
    else:
        raise HelperError("Install zenity or kdialog to browse for folders, or type the path.", "missing_chooser")
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=55, check=False, env=child_env())
    except subprocess.TimeoutExpired as error:
        raise HelperError("The folder chooser was open too long and was closed.") from error
    chosen = result.stdout.strip()
    if result.returncode != 0 or not chosen:
        return {"cancelled": True}
    home = os.path.expanduser("~")
    if chosen == home or chosen.startswith(home + "/"):
        chosen = "$HOME" + chosen[len(home):]
    return {"path": chosen}


def cmd_launch_app(request):
    """Start the standalone app through its per-user desktop entry, detached from this helper's output."""
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    entry = os.path.join(data_home, "applications", "umbriel-settings.desktop")
    if not os.path.isfile(entry):
        raise HelperError("Standalone desktop entry not found. Run Umbriel Settings once first.", "missing_app")
    gio = shutil.which("gio")
    if not gio:
        raise HelperError("Cannot launch the standalone app: gio is not installed.", "missing_gio")
    try:
        result = subprocess.run(
            [gio, "launch", entry], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True, timeout=10, check=False, env=child_env(),
        )
    except subprocess.TimeoutExpired as error:
        raise HelperError("Desktop launcher timed out; the app may still open.") from error
    if result.returncode:
        raise HelperError(f"Desktop launcher failed (exit code {result.returncode}).")
    return {}


def editor_file():
    return os.path.join(data_dir(), "editor-command")


def saved_editor():
    try:
        with open(editor_file(), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def editor_argv(command):
    """Split an editor command (the file is appended); None for the default app."""
    import shlex
    try:
        argv = shlex.split(command)
    except ValueError as error:
        raise HelperError(f"Editor command: {error}.") from error
    if not argv:
        return None
    if not shutil.which(argv[0]):
        raise HelperError(f"Editor not found: {argv[0]}", "missing_editor")
    return argv


def cmd_open_config(request):
    path = config_path(request)
    argv = editor_argv(saved_editor())
    if argv is None:
        if not shutil.which("xdg-open"):
            raise HelperError("xdg-open was not found. Set an editor command under About.", "missing_editor")
        argv = ["xdg-open"]
    subprocess.Popen(argv + [path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True, env=child_env())
    return {}


def cmd_set_editor(request):
    """Remember the command "Edit file" uses; empty means the default app (xdg-open)."""
    command = request.get("editor")
    command = command.strip() if isinstance(command, str) else ""
    if any(char in command for char in "\r\n\0"):
        raise HelperError("The editor command must be a single line.")
    editor_argv(command)
    if command:
        atomic_write_text(editor_file(), command + "\n")
    elif os.path.exists(editor_file()):
        os.unlink(editor_file())
    return {"editor": command}


def cmd_about(request):
    from umbriel_core import noctalia_theme
    return {"editor": saved_editor(), "palette": noctalia_theme.template_status()}


def cmd_palette_template(request):
    """Set up the Noctalia user template that writes the palette the standalone app follows."""
    need_tomlkit()
    from umbriel_core import noctalia_theme
    return {"palette": noctalia_theme.install_template(os.path.join(data_dir(), "noctalia-backups"))}


def cmd_titlebar(request):
    from umbriel_core import titlebar_theme
    return titlebar_theme.status(config_path(request))


def cmd_titlebar_follow(request):
    """Let a title-bar background follow Noctalia's palette (source kde/kde_header, opacity 0-1); source null stops."""
    need_tomlkit()
    from umbriel_core import titlebar_theme
    source, opacity = request.get("source"), request.get("opacity", 1)
    if source is not None and not isinstance(source, str):
        raise HelperError("The color source must be text.")
    if isinstance(opacity, bool) or not isinstance(opacity, (int, float)) or not 0 <= opacity <= 1:
        raise HelperError("Opacity must be between 0 and 1.")
    field = request.get("field")
    if not isinstance(field, str):
        raise HelperError("Choose a title bar field.")
    # Rounded half up like the panel's preview (round() would round 0.3 * 255 = 76.5 down to 76).
    return titlebar_theme.follow(config_path(request), field, source, int(opacity * 255 + 0.5),
                                 os.path.join(data_dir(), "noctalia-backups"))


COMMANDS = {
    "meta": cmd_meta, "read": cmd_read, "preview": cmd_preview, "save": cmd_save, "set-config": cmd_set_config,
    "backups": cmd_backups, "backup-diff": cmd_backup_diff, "restore": cmd_restore,
    "delete-backups": cmd_delete_backups, "desktop": cmd_desktop, "desktop-save": cmd_desktop_save,
    "extension": cmd_extension, "outputs": cmd_outputs, "kde-colors": cmd_kde_colors,
    "pick-folder": cmd_pick_folder, "launch-app": cmd_launch_app, "open-config": cmd_open_config,
    "set-editor": cmd_set_editor, "about": cmd_about, "palette-template": cmd_palette_template,
    "titlebar": cmd_titlebar, "titlebar-follow": cmd_titlebar_follow,
}

# Commands that write the config, its sidecars, backups or desktop files; they run one at a time across the
# plugin, the app and other windows, so a revision check and the write that follows can't interleave.
WRITE_COMMANDS = {"save", "set-config", "restore", "delete-backups", "desktop-save", "set-editor",
                  "palette-template", "titlebar-follow"}


def atomic_write_text(path, text):
    """Responses, caches and the editor command are private to the user."""
    paths.atomic_write(path, text, 0o600)


def parse_args(argv):
    if not argv or argv[0] not in COMMANDS:
        raise HelperError("Usage: umbriel_settings.py {" + ",".join(COMMANDS) + "} [--request F] [--response F]")
    options = {"--request": None, "--response": None}
    rest = argv[1:]
    while rest:
        flag = rest.pop(0)
        if flag not in options or not rest:
            raise HelperError(f"Unknown or incomplete option: {flag}")
        options[flag] = rest.pop(0)
    return argv[0], options["--request"], options["--response"]


def run(argv):
    """Run one command and return what the panel reads from stdout (the standalone app calls this in-process)."""
    try:
        command, request_file, response = parse_args(argv)
        request = {}
        if request_file:
            with open(request_file, encoding="utf-8") as handle:
                request = json.load(handle)
            if request == []:  # an empty Lua table encodes as a JSON array
                request = {}
            if not isinstance(request, dict):
                raise HelperError("The request must be a JSON object.")
        if command in WRITE_COMMANDS:
            with paths.write_lock(data_dir()):
                result = COMMANDS[command](request)
        else:
            result = COMMANDS[command](request)
        if response:
            atomic_write_text(response, json.dumps(result, ensure_ascii=False, separators=(",", ":")))
            return json.dumps({"ok": True})
        return json.dumps({"ok": True, "result": result}, ensure_ascii=False)
    except HelperError as error:
        return json.dumps({"ok": False, "error": str(error), "code": error.code})
    except TimeoutError as error:  # the write lock (subprocess timeouts are handled by each command)
        return json.dumps({"ok": False, "error": str(error), "code": "busy"})
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        return json.dumps({"ok": False, "error": str(error) or type(error).__name__, "code": "error"})
    except Exception as error:  # a bug: still answer, so the panel and the app never wait forever
        traceback.print_exc(file=sys.stderr)
        return json.dumps({"ok": False, "error": f"Internal error ({type(error).__name__}: {error}). "
                                                 "Please report it with the details printed to stderr.",
                           "code": "internal"})


def main(argv):
    print(run(argv))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
