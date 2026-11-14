"""Copy the rendered title-bar colors into the Umbriel config (standard library only).

Noctalia runs this as the `post_hook` of the `umbriel_titlebar` user template after every palette change:
    python3 titlebar_apply.py <rendered titlebar file> <umbriel config.toml>
Only `background` and `background_unfocused` inside [colors.title_bar] change; everything else stays as written.
The config wins over every include (Noctalia's theme include is always last), which is why it is edited directly.
The result must parse as TOML or nothing is written; the previous config is kept as one rolling backup next to this
script.
"""

import os
import re
import sys
import tempfile

try:
    import tomllib
except ImportError:  # Python < 3.11: write without the parse check
    tomllib = None

KEYS = ("background", "background_unfocused")
VALUE = re.compile(r'^(background(?:_unfocused)?) = "(#[0-9A-Fa-f]{8})"', re.M)
HEADER = re.compile(r"^\s*\[colors\.title_bar\]\s*(#.*)?$")
KEY_LINE = re.compile(r"^(\s*)(background(?:_unfocused)?)\s*=")


def rendered_values(text):
    return {key: color.upper() for key, color in VALUE.findall(text)}


def apply(text, values):
    """Return `text` with the title-bar keys in `values` set; other lines are kept byte for byte."""
    lines = text.splitlines(keepends=True)
    start = next((index for index, line in enumerate(lines) if HEADER.match(line.rstrip("\r\n"))), None)
    if start is None:
        if not values:
            return text
        block = "".join(f'{key} = "{values[key]}"\n' for key in KEYS if key in values)
        separator = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return text + separator + "[colors.title_bar]\n" + block
    end = next((index for index in range(start + 1, len(lines)) if lines[index].lstrip().startswith("[")), len(lines))
    done = set()
    for index in range(start + 1, end):
        match = KEY_LINE.match(lines[index])
        if match and match.group(2) in values:
            line = lines[index]
            newline = line[len(line.rstrip("\r\n")):]
            lines[index] = f'{match.group(1)}{match.group(2)} = "{values[match.group(2)]}"{newline}'
            done.add(match.group(2))
    eol = "\r\n" if lines[start].endswith("\r\n") else "\n"
    missing = "".join(f'{key} = "{values[key]}"{eol}' for key in KEYS if key in values and key not in done)
    if missing:
        lines.insert(start + 1, missing)
    return "".join(lines)


def backup_file(config):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), os.path.basename(config) + ".titlebar.bak")


def check(text):
    """Return None when `text` is valid TOML (or cannot be checked), else the parse error."""
    if tomllib is None:
        return None
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        return str(error)
    return None


def write(path, text):
    mode = os.stat(path).st_mode & 0o7777 if os.path.exists(path) else 0o644
    handle, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as out:
            out.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(argv):
    if len(argv) != 2:
        print("usage: titlebar_apply.py <rendered titlebar file> <umbriel config.toml>", file=sys.stderr)
        return 2
    rendered, config = argv
    if os.path.islink(config):
        print(f"{config} is a symlink; not changing it.", file=sys.stderr)
        return 1
    with open(rendered, encoding="utf-8") as handle:
        values = rendered_values(handle.read())
    with open(config, encoding="utf-8", newline="") as handle:
        text = handle.read()
    updated = apply(text, values)
    if updated == text:
        return 0
    error = check(updated)
    if error:
        print(f"{config}: not changed, the title bar colors would make it invalid ({error}). "
              "Write [colors.title_bar] as its own table.", file=sys.stderr)
        return 1
    write(backup_file(config), text)
    write(config, updated)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
