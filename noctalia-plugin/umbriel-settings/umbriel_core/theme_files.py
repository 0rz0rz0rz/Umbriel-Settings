"""Theme folders in the user's search paths (cursor and icon themes): which copies are the user's own, and
deleting one so that a kill halfway never leaves a half theme a lookup would find."""

import os
import secrets
import shutil

REMOVING = ".umbriel-settings-removing-"  # hidden name of a theme folder while it is deleted


def home_roots(roots):
    """The search folders in `roots` that lie inside the home folder (what a user may delete without root)."""
    home = os.path.join(os.path.expanduser("~"), "")
    return [root for root in roots if os.path.join(root, "").startswith(home)]


def safe_name(name):
    """A theme name that stays one folder inside its root (no separators, no hidden or parent names)."""
    return isinstance(name, str) and name not in ("", ".", "..") and not name.startswith(".") \
        and "/" not in name and "\0" not in name


def discard(path, root, name):
    """Rename `path` to a hidden name in `root` (one rename: a theme lookup never finds it again), then delete it;
    what a kill leaves behind is swept by `sweep_leftovers`."""
    hidden = os.path.join(root, f"{REMOVING}{name}-{secrets.token_hex(4)}")
    os.rename(path, hidden)
    shutil.rmtree(hidden, ignore_errors=True)


def sweep_leftovers(roots):
    """Delete what a removal killed halfway left (hidden `REMOVING` folders in the home folders of `roots`)."""
    for root in home_roots(roots):
        try:
            entries = [entry for entry in os.scandir(root) if entry.name.startswith(REMOVING)]
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry.path, ignore_errors=True)
