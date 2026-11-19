"""What the running compositor reports (outputs, open windows, layer surfaces, keyboard layout), for pickers."""

import re

from .schema import run_umbriel_json


def _objects(data, command):
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise ValueError(f"`umbriel {command}` returned an unexpected list.")
    return data


def connected_outputs(timeout=5):
    """`umbriel outputs --json` as it is (names, descriptions, modes), checked to be a list of named outputs."""
    outputs = _objects(run_umbriel_json(["outputs", "--json"], timeout), "outputs --json")
    if any(not isinstance(output.get("name"), str) for output in outputs):
        raise ValueError("`umbriel outputs --json` returned an output without a name.")
    return outputs


def open_windows(timeout=5):
    """[{app_id, title, count, pattern, title_pattern}] for the open windows, one per app id (the first window's
    title), sorted; the patterns match the app id / title exactly."""
    found = {}
    for window in _objects(run_umbriel_json(["windows", "--json"], timeout), "windows --json"):
        app_id = window.get("app_id")
        if not isinstance(app_id, str) or not app_id:
            continue
        title = window.get("title") if isinstance(window.get("title"), str) else ""
        entry = found.setdefault(app_id, {"app_id": app_id, "title": title, "count": 0})
        entry["count"] += 1
    for entry in found.values():
        entry["pattern"], entry["title_pattern"] = regex_literal(entry["app_id"]), regex_literal(entry["title"])
    return sorted(found.values(), key=lambda item: item["app_id"].casefold())


def open_layers(timeout=5):
    """[{namespace, layer, outputs, pattern}] for the mapped layer surfaces, one per namespace, sorted."""
    found = {}
    for surface in _objects(run_umbriel_json(["layers", "--json"], timeout), "layers --json"):
        namespace = surface.get("namespace")
        if not isinstance(namespace, str) or not namespace:
            continue
        layer = surface.get("layer") if isinstance(surface.get("layer"), str) else ""
        entry = found.setdefault(namespace, {"namespace": namespace, "layer": layer, "outputs": []})
        output = surface.get("output")
        if isinstance(output, str) and output and output not in entry["outputs"]:
            entry["outputs"].append(output)
    for entry in found.values():
        entry["pattern"] = regex_literal(entry["namespace"])
    return sorted(found.values(), key=lambda item: item["namespace"].casefold())


def keyboard_layout(timeout=5):
    """The active keyboard layout's name, or None when Umbriel can't tell."""
    try:
        data = run_umbriel_json(["keyboard-layouts", "--json"], timeout)
        names, index = data["names"], data["current_index"]
        return names[index] if isinstance(names[index], str) else None
    except Exception:  # best effort: a hint only
        return None


def regex_literal(text):
    """A rule pattern that matches exactly `text` (escapes only the metacharacters every regex dialect
    shares, so `org.gajim.Gajim` → `^org\\.gajim\\.Gajim$` and a `-` stays as it is)."""
    return "^" + re.sub(r"([\\.^$|?*+()\[\]{}])", r"\\\1", text) + "$"
