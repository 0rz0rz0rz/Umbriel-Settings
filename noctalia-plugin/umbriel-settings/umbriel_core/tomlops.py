"""Comment-preserving TOML value helpers built on tomlkit."""

import re

import tomlkit

MISSING = object()
PINNED_OPTIONAL_INCLUDES = ("noctalia.toml", "titlebar.toml")
ENV_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
RESERVED_ENV = {
    "WAYLAND_DISPLAY", "WAYLAND_SOCKET", "DISPLAY", "UMBRIEL_SOCKET", "LIBEI_SOCKET",
    "XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "XDG_SESSION_TYPE",
}


# ----------------------------------------------------------------- toml helpers
def py(v):
    """Turn a tomlkit value (Integer, String, Array, ...) into a plain Python value so it can be compared."""
    return v.unwrap() if hasattr(v, "unwrap") else v


def totext(v):
    """Render a value as TOML text, e.g. 'x' -> '"x"' and a dict -> '{ a = 1 }'. Used for the raw-text fields."""
    if isinstance(v, dict) and not hasattr(v, "as_string"):
        it = tomlkit.inline_table()
        it.update(v)
        v = it
    item = v if hasattr(v, "as_string") else tomlkit.item(v)
    return item.as_string()


def getp(c, path):
    """Walk `path` (a tuple of keys) down through nested tables; return MISSING if any step does not exist."""
    cur = c
    for k in path:
        try:
            cur = cur[k]
        except (KeyError, TypeError, IndexError):
            return MISSING
    return cur


def normalize_optional_includes(files):
    """Keep Noctalia before titlebar while leaving other include slots unchanged."""
    files = list(files)
    pinned_indexes = [
        index for index, name in enumerate(files)
        if name in PINNED_OPTIONAL_INCLUDES
    ]
    pinned_files = sorted(
        (files[index] for index in pinned_indexes),
        key=PINNED_OPTIONAL_INCLUDES.index,
    )
    for index, name in zip(pinned_indexes, pinned_files):
        files[index] = name
    return files


def ensure_table(c, path):
    """Make sure every table along `path` exists (creating empty ones) and return the innermost table."""
    cur = c
    for k in path:
        if k not in cur:
            cur[k] = tomlkit.table()
        cur = cur[k]
    return cur


def putp(c, path, value):
    """Set the value at `path`, creating any missing parent tables on the way."""
    ensure_table(c, path[:-1])[path[-1]] = value


def delp(c, path):
    """Delete the key at `path` if present. Parent tables are left in place."""
    parent = getp(c, path[:-1]) if len(path) > 1 else c
    if parent is not MISSING and path[-1] in parent:
        del parent[path[-1]]


def parse_toml_value(text):
    """Parse one inline TOML value; reject input that adds further keys or tables, which would be silently dropped."""
    # The trailing newline matters: without it the parsed value carries no line break and is
    # written glued to the next "[[...]]" header when it is the last key of a rule.
    try:
        doc = tomlkit.parse("value = " + text + "\n")
    except tomlkit.exceptions.TOMLKitError as error:
        raise ValueError(str(error)) from error
    if list(doc) != ["value"]:
        raise ValueError("enter a single TOML value; extra keys or tables are not allowed")
    return doc["value"]
