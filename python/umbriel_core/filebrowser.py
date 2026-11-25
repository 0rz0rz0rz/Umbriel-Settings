"""The UI's own file browser (the plugin panel would hide a chooser window): folder listings and the value a
chosen file or folder becomes in the config."""

import fnmatch
import os
import shlex


class BrowseError(ValueError):
    """A readable failure with the helper's error `code`."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def expand_home(path):
    return os.path.expanduser(str(path).replace("$HOME", os.path.expanduser("~"), 1))


def config_folder(request):
    config = str(request.get("config") or "")
    return os.path.dirname(os.path.abspath(os.path.expanduser(config))) if config else ""


def start_folder(request):
    """Where the file browser opens: `start` when it is a folder, else the config's folder, else home."""
    start = expand_home(request.get("start") or "")
    if os.path.isdir(start):
        return start
    folder = config_folder(request)
    return folder if os.path.isdir(folder) else os.path.expanduser("~")


def cmd_pick_folder(request):
    """The value for a folder chosen in the UI's file browser (`chosen`): home becomes `$HOME`."""
    chosen = str(request.get("chosen") or "")
    if not chosen:
        return {"cancelled": True}
    home = os.path.expanduser("~")
    if chosen == home or chosen.startswith(home + "/"):
        chosen = "$HOME" + chosen[len(home):]
    return {"path": chosen}


def file_patterns(request):
    pattern = request.get("filter")
    return pattern if isinstance(pattern, list) and len(pattern) == 2 else None


def cmd_pick_file(request):
    """The value for a file chosen in the UI's file browser (`chosen`): an absolute path, or relative to the
    config's folder (`relative`) when inside it; with `command`, an app's Exec command or the quoted program path."""
    chosen = str(request.get("chosen") or "")
    if not chosen:
        return {"cancelled": True}
    if request.get("command"):  # an autostart command: an app's Exec line, or the program itself
        if not chosen.endswith(".desktop"):
            return {"path": shlex.quote(chosen)}
        from . import mimeapps
        command = mimeapps.exec_command(chosen)
        if not command:
            raise BrowseError("That app has no command to run.", "no_command")
        return {"path": command}
    folder = config_folder(request)
    if request.get("relative") and folder:
        # compare real paths: the config folder is often a symlink into a dotfiles checkout
        real_folder, real_chosen = os.path.realpath(folder), os.path.realpath(chosen)
        if real_chosen.startswith(real_folder + os.sep):
            chosen = os.path.relpath(real_chosen, real_folder)
    return {"path": chosen}


LIST_DIR_LIMIT = 2000


def cmd_list_dir(request):
    """One folder for the UI's file browser (the plugin panel would hide a chooser window): `path`, else where
    it opens. Folders and files (matching `filter`; none with `folders`), hidden ones left out."""
    path = request.get("path")
    path = os.path.abspath(expand_home(path)) if path else start_folder(request)
    if not os.path.isdir(path):
        raise BrowseError(f"{path} is not a folder.", "not_folder")
    pattern = file_patterns(request)
    patterns = pattern[1].lower().split() if pattern else None
    folders, files = [], []
    try:
        with os.scandir(path) as listing:
            for entry in listing:
                if entry.name.startswith("."):
                    continue
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    continue
                if is_dir:
                    folders.append(entry.name)
                elif not request.get("folders") and (
                        not patterns or any(fnmatch.fnmatchcase(entry.name.lower(), p) for p in patterns)):
                    files.append(entry.name)
    except OSError as error:
        raise BrowseError(f"Can't open {path}: {error.strerror or error}", "unreadable") from error
    folders.sort(key=str.casefold)
    files.sort(key=str.casefold)
    truncated = len(folders) + len(files) > LIST_DIR_LIMIT
    files = files[:max(0, LIST_DIR_LIMIT - len(folders))]
    parent = os.path.dirname(path)
    return {"path": path, "parent": parent if parent != path else None, "folders": folders[:LIST_DIR_LIMIT],
            "files": files, "truncated": truncated, "home": os.path.expanduser("~")}
