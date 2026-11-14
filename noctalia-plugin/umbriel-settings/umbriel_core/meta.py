"""Describe pages, groups, fields, editors and actions as plain JSON for a declarative UI."""

from . import CORE_VERSION, entry_ops
from .actions import ACTION_CATEGORIES, ACTION_INFO, ARG_HELP, REQUIRED_ARG_ACTIONS
from .cursor_themes import installed_cursor_themes
from .fields import ACTION_TEMPLATES, NAV_SECTIONS, TABS
from .help import CATEGORY_HELP, GROUP_HELP, setting_help_text
from .keybinds import BIND_BOOL_OPTIONS
from .schema import field_schema_option
from .values import to_ui

PAGE_KINDS = {
    "User folders": "userdirs",
    "Default apps": "apps",
    "Keybinds": "keybinds",
    "Environment": "map",
    "Animation curves": "map",
}
PAGE_GLYPHS = {
    "User folders": "folder", "Default apps": "apps", "General": "settings", "Appearance": "palette",
    "Colors": "color-swatch", "Animation": "movie", "Animation curves": "vector-bezier",
    "Effects": "sparkles", "Input": "keyboard", "Layout": "layout-grid", "Workspaces": "layout-board",
    "Keybinds": "command", "Window rules": "app-window", "Layer rules": "stack-2",
    "Workspace rules": "layout-columns", "Outputs": "device-desktop", "Scratchpads": "notes",
    "Input devices": "mouse", "Security rules": "shield-lock", "Environment": "variable",
}


def describe_field(field, category, group, schema_options, schema_path, cursor_themes, entry=False):
    """Describe one field. `default` is what Umbriel uses when the key is absent (None when unknown);
    `initial` is the value a control starts from when the user sets the key."""
    option = field_schema_option(schema_options, schema_path)
    if option is not None and "default" in option:
        default = option["default"]
    elif not entry and not schema_options:
        default = field.default  # no installed schema: the app's fallback is the best guess for page fields
    else:
        default = None  # rule fields have no default: an absent key means "any" or "unchanged"
    kind = field.kind
    info = {
        "label": field.label,
        "kind": kind,
        "path": ".".join(field.path),
        "opt": bool(field.opt),
        "default": to_ui(field, default) if default is not None else None,
        "initial": to_ui(field, field.default) if field.default not in (None, "") else None,
        "restart": "(restart)" in field.label or "(restart)" in group,
    }
    choices = None
    if kind in ("choice", "combo"):
        choices = list(field.extra or [])
        if option is not None and option.get("values"):
            choices = list(option["values"])
        if field.path == ("input", "cursor", "theme"):
            choices = cursor_themes
        info["choices"] = [str(c) for c in choices]
    if kind in ("int", "float"):
        low, high = None, None
        if isinstance(field.extra, (list, tuple)) and len(field.extra) == 2:
            low, high = field.extra
        if option is not None and "min" in option and "max" in option:
            low, high = option["min"], option["max"]
        info["min"], info["max"] = low, high
    if kind == "table":
        info["keys"] = list(field.extra or ())
    if option is not None and option.get("format") == "effect":
        info["placeholder"] = "Effect preset name"
    info["help"] = setting_help_text(field, group)
    info["search"] = " ".join([field.label, info["path"], group, category, info["help"]]).casefold()
    return info


def build_meta(schema_options, schema_info=None, plugin_version=""):
    """Return the metadata document; `schema_options` maps schema paths to options (may be empty)."""
    themes = installed_cursor_themes()
    fields, pages = {}, {}
    for page, groups in TABS.items():
        page_groups = []
        for title, group_fields in groups:
            ids = []
            for field in group_fields:
                fid = ".".join(field.path)
                fields[fid] = describe_field(field, page, title, schema_options, fid, themes)
                ids.append(fid)
            page_groups.append({"title": title, "help": GROUP_HELP.get(title, ""), "fields": ids})
        pages[page] = {"kind": "form", "groups": page_groups}
    editors = {}
    for eid, (page, title, path, mode, groups, _) in entry_ops.ENTRY_EDITORS.items():
        prefix = entry_ops.schema_prefix(eid)
        editor_groups = []
        for group_title, group_fields in groups:
            ids = []
            for field in group_fields:
                fpath = ".".join(field.path)
                fields[f"{eid}:{fpath}"] = describe_field(
                    field, page, group_title, schema_options, f"{prefix}.{fpath}", themes, entry=True)
                ids.append(f"{eid}:{fpath}")
            editor_groups.append({"title": group_title, "help": GROUP_HELP.get(group_title, ""), "fields": ids})
        editors[eid] = {"page": page, "title": title, "path": path, "mode": mode, "groups": editor_groups}
        pages.setdefault(page, {"kind": "entries", "editors": []})["editors"].append(eid)
    maps = {
        eid: {"page": page, "title": title, "path": path, "value": kind}
        for eid, (page, title, path, kind) in entry_ops.MAP_EDITORS.items()
    }
    for eid, spec in maps.items():
        pages.setdefault(spec["page"], {"kind": "map", "maps": []})["maps"].append(eid)
    for page, kind in PAGE_KINDS.items():
        pages.setdefault(page, {"kind": kind})
    for page, info in pages.items():
        info["help"] = CATEGORY_HELP.get(page, "")
        info["glyph"] = PAGE_GLYPHS.get(page, "settings")
    return {
        "version": plugin_version, "core_version": CORE_VERSION,
        "schema": schema_info or {"available": False},
        "nav": [
            {"title": title, "pages": names, "help": CATEGORY_HELP.get(title, "")}
            for title, names in NAV_SECTIONS
        ],
        "pages": pages,
        "fields": fields,
        "editors": editors,
        "maps": maps,
        "actions": {
            "categories": [[name, [[a, d] for a, d in items]] for name, items in ACTION_CATEGORIES],
            "templates": ACTION_TEMPLATES,
            "required": sorted(REQUIRED_ARG_ACTIONS),
            "examples": {head: info[0] for head, info in ACTION_INFO.items()},
            "args": ARG_HELP,
            "options": [[name, label] for name, label in BIND_BOOL_OPTIONS],
        },
    }
