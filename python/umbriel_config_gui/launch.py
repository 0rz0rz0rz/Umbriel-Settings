"""Start external programs (editors, terminals) without leaking the AppImage's Python environment."""

import os
import shutil

# The AppImage entrypoint overrides these to isolate its bundled Python and records the host's
# values (UMBRIEL_GUI_HOST_<NAME>) so launched programs see the user's original environment.
APPIMAGE_ENV_MARKER = "UMBRIEL_GUI_APPIMAGE_ENV"
HOST_PYTHON_VARS = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONNOUSERSITE")

# Terminals tried in order, and how each expects the command to run.
TERMINALS = ("x-terminal-emulator", "kitty", "foot", "konsole", "gnome-terminal", "alacritty")
_DIRECT_ARGV = {"kitty", "foot"}
_DOUBLE_DASH = {"gnome-terminal", "kgx", "ptyxis"}


def child_env(environ=None):
    """Return the environment for launched programs, restoring host Python variables inside the AppImage."""
    env = dict(os.environ if environ is None else environ)
    if not env.pop(APPIMAGE_ENV_MARKER, None):
        return env
    for name in HOST_PYTHON_VARS:
        saved = env.pop(f"UMBRIEL_GUI_HOST_{name}", None)
        if saved is None:
            env.pop(name, None)
        else:
            env[name] = saved
    return env


def find_terminal():
    """Return the first available terminal emulator, or None."""
    for name in TERMINALS:
        path = shutil.which(name)
        if path:
            return path
    return None


def terminal_command(terminal, argv):
    """Build the argv that runs `argv` inside `terminal`, using that terminal's command syntax."""
    name = os.path.basename(terminal)
    if name in _DIRECT_ARGV:
        return [terminal, *argv]
    if name in _DOUBLE_DASH:
        return [terminal, "--", *argv]
    return [terminal, "-e", *argv]
