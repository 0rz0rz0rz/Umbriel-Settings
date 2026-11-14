"""Entry editors (rules, outputs, devices, effects) and key/value maps, with replayable edit operations.

Operations mirror the app's EntryEditor/KVTable/RawValueMapEditor behavior so a UI can record what the
user did and the helper can replay it on a fresh parse of the config, keeping comments intact.
"""

import copy

import tomlkit

from .fields import (
    EFFECT_POOL_GROUPS,
    EFFECT_PRESET_GROUPS,
    INPUT_DEVICE,
    LAYER_RULE,
    OUTPUT_GROUPS,
    SCRATCHPAD,
    SECURITY_RULE,
    WINDOW_RULE_GROUPS,
    WORKSPACE_RULE_GROUPS,
)
from .tomlops import ENV_NAME_RE, MISSING, RESERVED_ENV, ensure_table, getp, parse_toml_value, putp, py

# id: (page, title, TOML path, mode, groups, collapsible)
ENTRY_EDITORS = {
    "output": ("Outputs", "Outputs (connector or monitor)", "output", "map", OUTPUT_GROUPS, True),
    "window_rule": ("Window rules", "[[window_rule]]", "window_rule", "aot", WINDOW_RULE_GROUPS, True),
    "layer_rule": ("Layer rules", "[[layer_rule]]", "layer_rule", "aot", [("Layer rule", LAYER_RULE)], False),
    "workspace": ("Workspace rules", "[[workspace]]", "workspace", "aot", WORKSPACE_RULE_GROUPS, True),
    "security_context_rule": ("Security rules", "[[security_context_rule]]", "security_context_rule", "aot",
                              [("Security context rule", SECURITY_RULE)], False),
    "scratchpad": ("Scratchpads", "[[scratchpad]]", "scratchpad", "aot", [("Scratchpad", SCRATCHPAD)], False),
    "input_device": ("Input devices", "[[input.device]]", "input.device", "aot",
                     [("Device override", INPUT_DEVICE)], False),
    "effect_preset": ("Effects", "Effect presets", "effects.preset", "map", EFFECT_PRESET_GROUPS, True),
    "effect_pool": ("Effects", "Effect pools", "effects.pool", "map", EFFECT_POOL_GROUPS, True),
}

# id: (page, title, TOML path, value kind: "string" | "array" | "table")
MAP_EDITORS = {
    "environment": ("Environment", "Environment variables", "environment", "string"),
    "beziers": ("Animation curves", "Named Bézier curves", "animation.beziers", "array"),
    "springs": ("Animation curves", "Named spring curves", "animation.springs", "table"),
}


def editor_path(editor_id):
    spec = ENTRY_EDITORS.get(editor_id) or MAP_EDITORS.get(editor_id)
    if spec is None:
        raise ValueError(f"Unknown editor: {editor_id}")
    return tuple(spec[2].split("."))


def schema_prefix(editor_id):
    """Schema path prefix of an entry editor's fields, e.g. 'window_rule[]' or 'output.<name>'."""
    _, _, path, mode, _, _ = ENTRY_EDITORS[editor_id]
    return path + (".<name>" if mode == "map" else "[]")


def editor_fields(editor_id):
    """Return {dotted field path: Field} for an entry editor."""
    return {
        ".".join(field.path): field
        for _, fields in ENTRY_EDITORS[editor_id][4]
        for field in fields
    }


def container(doc, editor_id, create=False):
    """Return the array of tables or table of tables holding an editor's entries (None when absent)."""
    mode = ENTRY_EDITORS[editor_id][3]
    path = editor_path(editor_id)
    c = getp(doc, path)
    if c is MISSING and create:
        if mode == "aot":
            c = tomlkit.aot()
            putp(doc, path, c)
        else:
            c = ensure_table(doc, path)
    return None if c is MISSING else c


def entries(doc, editor_id):
    """List entries as tables ('aot') or (name, table) pairs ('map')."""
    c = container(doc, editor_id)
    if c is None:
        return []
    return list(c) if ENTRY_EDITORS[editor_id][3] == "aot" else list(c.items())


def entry_at(doc, editor_id, index):
    items = entries(doc, editor_id)
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(items):
        raise ValueError(f"{ENTRY_EDITORS[editor_id][0]}: entry {index} does not exist.")
    item = items[index]
    return item if ENTRY_EDITORS[editor_id][3] == "aot" else item[1]


def _entry_name(name, existing):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Enter a name for the entry.")
    name = name.strip()
    if name in existing:
        raise ValueError(f'"{name}" already exists.')
    return name


def apply_entry_op(doc, editor_id, labels, op):
    """Apply one operation; `labels` (GUI-only names of 'aot' entries) is updated in place.

    Operations: add [name], remove index, move index to, duplicate index [name], label index text.
    Field edits go through values.apply_value on entry_at(...).
    """
    mode = ENTRY_EDITORS[editor_id][3]
    kind = op.get("op")
    if mode == "aot":
        count = len(entries(doc, editor_id))
        labels[:] = (labels + [""] * count)[:count]
    if kind == "add":
        if mode == "aot":
            container(doc, editor_id, True).append(tomlkit.table())
            labels.append("")
        else:
            c = container(doc, editor_id, True)
            c[_entry_name(op.get("name"), set(c.keys()))] = tomlkit.table()
    elif kind == "remove":
        index = op.get("index")
        entry_at(doc, editor_id, index)
        c = container(doc, editor_id)
        if mode == "aot":
            del c[index]
            labels.pop(index)
        else:
            del c[entries(doc, editor_id)[index][0]]
    elif kind == "move":
        if mode != "aot":
            raise ValueError("Only rules can be reordered.")
        index, target = op.get("index"), op.get("to")
        entry_at(doc, editor_id, index)
        entry_at(doc, editor_id, target)
        c = container(doc, editor_id)
        c.insert(target, c.pop(index))
        labels.insert(target, labels.pop(index))
    elif kind == "duplicate":
        index = op.get("index")
        clone = copy.deepcopy(entry_at(doc, editor_id, index))
        c = container(doc, editor_id)
        if mode == "aot":
            c.insert(index + 1, clone)
            labels.insert(index + 1, "")
        else:
            c[_entry_name(op.get("name"), set(c.keys()))] = clone
    elif kind == "label":
        if mode != "aot":
            raise ValueError("Only rules have display names.")
        index, text = op.get("index"), op.get("text")
        entry_at(doc, editor_id, index)
        if not isinstance(text, str):
            raise ValueError("Display names must be text.")
        labels[index] = " ".join(text.split())
    else:
        raise ValueError(f"Unknown entry operation: {kind}")


def map_rows(doc, editor_id):
    """Return [(name, value)] of a map editor, values as TOML items."""
    table = getp(doc, editor_path(editor_id))
    if table is MISSING or not hasattr(table, "items"):
        return []
    return list(table.items())


def map_value_from_ui(editor_id, name, text):
    """Parse and check one map value: plain text for environment, TOML for curves."""
    kind = MAP_EDITORS[editor_id][3]
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{MAP_EDITORS[editor_id][1]}: enter a name.")
    name = name.strip()
    if not isinstance(text, str):
        raise ValueError(f"{name}: expected text.")
    if kind == "string":
        if not ENV_NAME_RE.fullmatch(name):
            raise ValueError(f'Environment: "{name}" is not a valid variable name')
        if name in RESERVED_ENV:
            raise ValueError(f"Environment: {name} is owned by Umbriel and cannot be set here")
        return name, text
    try:
        value = parse_toml_value(text.strip())
    except ValueError as error:
        raise ValueError(f"{name}: invalid TOML value ({error})") from error
    if kind == "array":
        if not isinstance(value, tomlkit.items.Array):
            raise ValueError(f"{name}: expected a TOML array")
        points = py(value)
        if (len(points) != 4 or not all(isinstance(p, (int, float)) and not isinstance(p, bool) for p in points)):
            raise ValueError(f"{name}: Bézier curves need exactly four numbers: [x1, y1, x2, y2]")
        if not (0 <= points[0] <= 1 and 0 <= points[2] <= 1):
            raise ValueError(f"{name}: Bézier curves need x1 and x2 between 0 and 1")
    elif not isinstance(value, (tomlkit.items.InlineTable, tomlkit.items.Table)):
        raise ValueError(f"{name}: expected a TOML table")
    return name, value


def apply_map_op(doc, editor_id, op):
    """Apply set (name, value[, from]) or remove (name) to a map editor."""
    path = editor_path(editor_id)
    kind = op.get("op")
    if kind == "remove":
        table = getp(doc, path)
        if table is not MISSING and op.get("name") in table:
            del table[op["name"]]
        return
    if kind != "set":
        raise ValueError(f"Unknown map operation: {kind}")
    name, value = map_value_from_ui(editor_id, op.get("name"), op.get("value"))
    table = ensure_table(doc, path)
    old = op.get("from")
    if old not in (None, name):
        if name in table:
            raise ValueError(f"{name}: duplicate name")
        if old not in table:
            raise ValueError(f"{old}: no longer exists")
        del table[old]  # like the app's table editors: a renamed row is re-added at the end
        table[name] = value
        return
    if name in table and py(table[name]) == py(value):
        return
    table[name] = value
