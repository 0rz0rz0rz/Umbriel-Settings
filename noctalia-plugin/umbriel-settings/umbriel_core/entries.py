"""Readable names for rule entries (array-of-tables) and map entries."""

import re

from .tomlops import MISSING, getp, py, totext


def readable_pattern(value):
    """Drop regex anchors and escaped dots so a match pattern reads like a name."""
    text = str(value)
    if text.startswith("^"):
        text = text[1:]
    if text.endswith("$") and not text.endswith("\\$"):
        text = text[:-1]
    return text.replace("\\.", ".")


def readable_match(key, value):
    """Describe one identifying key, e.g. app id "^org.mozilla.firefox$" as "firefox (app id)"."""
    plain = py(value)
    if key in ("app_id", "title", "namespace"):
        names = []
        for pattern in plain if isinstance(plain, list) else [plain]:
            text = readable_pattern(pattern)
            if key == "app_id" and re.fullmatch(r"[\w-]+(\.[\w-]+){2,}", text):
                text = text.rsplit(".", 1)[1]
            names.append(text)
        kind = {"app_id": "app id", "namespace": "layer"}.get(key, key)
        return f"{', '.join(names)} ({kind})"
    word = key.removeprefix("is_").replace("_", " ")
    if isinstance(plain, bool):
        return word if plain else f"not {word}"
    return f"{word}: {totext(value)}"


def entry_label_info(entry, index, custom_label=""):
    """Return (list text, raw TOML keys for a tooltip, whether the name is automatic) for one rule entry."""
    raw_lines = []
    for p in (("name",), ("index",)):
        v = getp(entry, p)
        if v is not MISSING:
            raw_lines.append(f"{'.'.join(p)} = {totext(v)}")
    m = getp(entry, ("match",))
    if m is not MISSING and hasattr(m, "items"):
        raw_lines.extend(f"match.{k} = {totext(v)}" for k, v in m.items())
    raw = "\n".join(raw_lines)
    number = index + 1
    if custom_label and custom_label.strip():
        return f"{number}. {custom_label.strip()}", raw, False
    name = getp(entry, ("name",))
    if name is not MISSING:
        return f"{number}. {py(name)}", raw, False
    for key in ("app_id", "title", "namespace"):
        v = getp(entry, ("match", key))
        if v is not MISSING:
            return f"{number}. {readable_match(key, v)}", raw, True
    workspace = getp(entry, ("index",))
    if workspace is not MISSING:
        return f"{number}. Workspace {py(workspace)}", raw, True
    if m is not MISSING and hasattr(m, "items") and len(m):
        k = next(iter(m))
        return f"{number}. {readable_match(k, m[k])}", raw, True
    return f"{number}. (matches everything)", raw, True
