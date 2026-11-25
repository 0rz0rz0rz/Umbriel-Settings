"""Noctalia's community shaders (github.com/noctalia-dev/community-umbriel-shaders): the catalogue, cached
previews and files, and the effects a config includes from `shaders/community/` next to it.

The network is used only on request: the catalogue, previews and an effect's files go into the private cache
(`<data>/community/`). Files land next to the config only while a reviewed save holds the write lock (`install`,
before the config is replaced), and only a later save that no longer includes them removes them again (`sweep`).
Every file this app puts there is listed in `.umbriel-settings.json` before it is written, so nothing else is
ever deleted; files changed since, everything of a git checkout, and everything while a Try can still go back
are left alone.
"""

import hashlib
import json
import os
import posixpath
import re
import time
import tomllib
import urllib.error
import urllib.request

from .included import include_lists
from .paths import atomic_write, private_dir

REPOSITORY = "noctalia-dev/community-umbriel-shaders"
CATALOGUE_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/catalogue/catalogue.json"
FILE_URL = "https://raw.githubusercontent.com/" + REPOSITORY + "/{revision}/{path}"
ROOT = "shaders/community"  # next to the config, as the repository's README installs it
MANIFEST = ".umbriel-settings.json"
KINDS = ("window", "border", "screen", "cursor", "animation")
CATALOGUE_LIMIT = 4 << 20
FILE_LIMIT = 1 << 20
TIMEOUT = 15
PREVIEW_TIMEOUT = 8
PREVIEW_BUDGET = 12  # seconds per request: stay inside the helper's 20 s read timeout
PREVIEW_BATCH = 24
USER_AGENT = "umbriel-settings"
ID_RE = re.compile(r"[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*")
PART_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*")
SHA_RE = re.compile(r"[0-9a-f]{64}")
REVISION_RE = re.compile(r"[0-9a-f]{40}")


class ShaderError(ValueError):
    """A readable failure (download, checksum, unsafe path, missing cache); the helper reports it as is."""


def urlopen(request, timeout):  # tests replace this
    return urllib.request.urlopen(request, timeout=timeout)


def cache_dir(data_dir):
    return os.path.join(data_dir, "community")


def _fetch(url, limit, timeout=TIMEOUT):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout) as response:
            data = response.read(limit + 1)
    except (urllib.error.URLError, OSError, ValueError) as error:  # incl. HTTPError and socket timeouts
        reason = getattr(error, "reason", None) or error
        raise ShaderError(f"Could not download {url}: {reason}") from None
    if len(data) > limit:
        raise ShaderError(f"{url} is larger than expected.")
    return data


def _sha_file(path):
    """SHA-256 of a regular file, None when it is missing; a symlink is refused (never followed)."""
    if os.path.islink(path):
        raise ShaderError(f"{path} is a symlink; Umbriel Settings doesn't write through symlinks.")
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except (FileNotFoundError, NotADirectoryError):
        return None


def _safe_path(path):
    if not isinstance(path, str) or not all(PART_RE.fullmatch(part) for part in path.split("/")):
        raise ShaderError(f"The shader catalogue lists an unsafe path: {path!r}.")
    return path


# ------------------------------------------------------------------ catalogue
def _checked(data):
    revision = data.get("source", {}).get("revision") if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("effects"), list) \
            or not isinstance(data.get("files"), dict) or not isinstance(revision, str) \
            or not REVISION_RE.fullmatch(revision):
        raise ShaderError("The shader catalogue has a format this version of Umbriel Settings doesn't know.")
    return data


def load_catalogue(data_dir):
    """(catalogue, fetched at) from the cache; (None, None) when there is none or it is unusable."""
    path = os.path.join(cache_dir(data_dir), "catalogue.json")
    try:
        with open(path, "rb") as handle:
            return _checked(json.loads(handle.read())), os.path.getmtime(path)
    except (OSError, ValueError):
        return None, None


def refresh_catalogue(data_dir):
    raw = _fetch(CATALOGUE_URL, CATALOGUE_LIMIT)
    try:
        data = _checked(json.loads(raw))
    except ValueError as error:
        raise ShaderError(f"The downloaded shader catalogue is unusable: {error}") from None
    atomic_write(os.path.join(private_dir(cache_dir(data_dir)), "catalogue.json"), raw, 0o600)
    return data


def _records(catalogue):
    """{id: record} of the well-formed records (others are left out)."""
    found = {}
    for record in catalogue["effects"]:
        if isinstance(record, dict) and isinstance(record.get("id"), str) and ID_RE.fullmatch(record["id"]) \
                and record.get("kind") in KINDS and isinstance(record.get("install_files"), list):
            found[record["id"]] = record
    return found


def _closure(records, effect):
    """`effect` and the effects it depends on, each once."""
    order, pending = [], [effect]
    while pending:
        current = pending.pop()
        if current in order:
            continue
        if current not in records:
            raise ShaderError(f"The shader catalogue has no effect {current}.")
        order.append(current)
        pending += [dep for dep in records[current].get("dependencies") or [] if isinstance(dep, str)]
    return order


def _files(catalogue, records, effects):
    """{path: sha256} of the files the effects install."""
    listed, wanted = catalogue["files"], {}
    for effect in effects:
        for path in records[effect]["install_files"]:
            info = listed.get(_safe_path(path))
            sha = info.get("sha256") if isinstance(info, dict) else None
            if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
                raise ShaderError(f"The shader catalogue has no checksum for {path}.")
            wanted[path] = sha
    return wanted


def _text(value, limit=300):
    return value[:limit] if isinstance(value, str) else ""


def include_path(effect):
    """The include entry that loads an effect, relative to the config's folder."""
    return f"{ROOT}/{effect}/effect.toml"


def effect_of(include, config_dir):
    """The effect an include entry loads from `shaders/community/` next to the config, else None."""
    if not isinstance(include, str):
        return None
    path = os.path.expanduser(include)
    if os.path.isabs(path):
        path = os.path.relpath(path, config_dir)
    match = re.fullmatch(r"shaders/community/([a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*)/effect\.toml",
                         posixpath.normpath(path))
    return match.group(1) if match else None


def _effect_dir(config_dir, effect):
    return os.path.join(config_dir, ROOT, effect)


def is_git_checkout(config_dir):
    return os.path.lexists(os.path.join(config_dir, ROOT, ".git"))


def entries(catalogue, config_dir):
    """Rows for the UI: the selectable effects (companions come along as dependencies), by kind and name."""
    records, rows = _records(catalogue), []
    for effect, record in records.items():
        if record.get("role") != "effect":
            continue
        activation = record.get("activation") if isinstance(record.get("activation"), dict) else {}
        settings = activation.get("settings") if isinstance(activation.get("settings"), dict) else {}
        try:
            presets = [records[dep].get("preset") for dep in _closure(records, effect)]
        except ShaderError:  # a missing dependency: not installable
            continue
        rows.append({
            "id": effect, "kind": record["kind"], "name": _text(record.get("name"), 60) or effect,
            "description": _text(record.get("description")), "author": _text(record.get("author"), 60),
            "license": _text(record.get("license"), 40),
            "tags": [tag for tag in record.get("tags") or [] if isinstance(tag, str)][:4],
            "include": include_path(effect),
            "settings": {key: value for key, value in settings.items()
                         if isinstance(key, str) and isinstance(value, (str, int, float, bool))},
            "presets": [name for name in presets if isinstance(name, str)],
            "installed": os.path.isfile(os.path.join(_effect_dir(config_dir, effect), "effect.toml")),
        })
    rows.sort(key=lambda row: (KINDS.index(row["kind"]), row["name"].casefold()))
    return rows


def previews(catalogue, data_dir, effects, offline=False):
    """{paths: {id: cached PNG}, failed: [ids]}; downloads what isn't cached yet (not when `offline`), for as long
    as PREVIEW_BUDGET allows. Each image is checked against the catalogue's checksum."""
    records, listed = _records(catalogue), catalogue["files"]
    revision = catalogue["source"]["revision"]
    folder = os.path.join(cache_dir(data_dir), "previews")
    found, failed, started = {}, [], time.monotonic()
    for effect in [e for e in effects if isinstance(e, str)][:PREVIEW_BATCH]:
        record = records.get(effect)
        preview = record.get("preview") if record else None
        path = preview.get("image") if isinstance(preview, dict) else None
        info = listed.get(path) if isinstance(path, str) and path.endswith(".png") else None
        sha = info.get("sha256") if isinstance(info, dict) else None
        if not isinstance(sha, str):
            failed.append(effect)
            continue
        target = os.path.join(folder, effect.replace("/", "--") + ".png")
        if _sha_file(target) == sha:
            found[effect] = target
            continue
        if offline or time.monotonic() - started > PREVIEW_BUDGET:
            continue
        try:
            data = _fetch(FILE_URL.format(revision=revision, path=_safe_path(path)), FILE_LIMIT, PREVIEW_TIMEOUT)
        except ShaderError:
            failed.append(effect)
            continue
        if hashlib.sha256(data).hexdigest() != sha:
            failed.append(effect)
            continue
        private_dir(folder)
        atomic_write(target, data, 0o600)
        found[effect] = target
    return {"paths": found, "failed": failed}


def prepare(catalogue, data_dir, effect, offline=False):
    """Download an effect and its dependencies into the cache (nothing next to the config) and return what the
    draft needs: its include entry and the preset names it defines."""
    records = _records(catalogue)
    effects = _closure(records, effect)
    revision = catalogue["source"]["revision"]
    folder = os.path.join(cache_dir(data_dir), "files")
    for path, sha in _files(catalogue, records, effects).items():
        target = os.path.join(folder, path)
        if _sha_file(target) == sha:
            continue
        if offline:
            raise ShaderError("Noctalia is in offline mode, so the shader can't be downloaded.")
        data = _fetch(FILE_URL.format(revision=revision, path=path), FILE_LIMIT)
        if hashlib.sha256(data).hexdigest() != sha:
            raise ShaderError(f"{path} does not match the catalogue's checksum; try again later.")
        atomic_write(target, data, 0o600)  # the directories it creates are 0700
    return {"id": effect, "include": include_path(effect),
            "presets": [records[e].get("preset") for e in effects if isinstance(records[e].get("preset"), str)]}


# ------------------------------------------------------------------ next to the config
def validation_path(include, config_dir, data_dir):
    """The cached copy of a community effect that `include` names but that only the save will install, so the
    config can be validated before that; None otherwise."""
    effect = effect_of(include, config_dir)
    if effect is None or os.path.isfile(os.path.join(_effect_dir(config_dir, effect), "effect.toml")):
        return None
    cached = os.path.join(cache_dir(data_dir), "files", effect, "effect.toml")
    return cached if os.path.isfile(cached) else None


def config_effects(data, config_dir):
    """The community effects a parsed config includes directly."""
    found = []
    for include in include_lists(data):
        effect = effect_of(include, config_dir)
        if effect and effect not in found:
            found.append(effect)
    return found


def _manifest_path(config_dir):
    return os.path.join(config_dir, ROOT, MANIFEST)


def _read_manifest(config_dir):
    """{path: sha256} of the files this app installed; empty when unreadable (then nothing is ever deleted)."""
    try:
        with open(_manifest_path(config_dir), "rb") as handle:
            files = json.loads(handle.read()).get("files")
    except (OSError, ValueError, AttributeError):
        return {}
    return {path: sha for path, sha in files.items() if isinstance(sha, str)} if isinstance(files, dict) else {}


def _write_manifest(config_dir, files):
    atomic_write(_manifest_path(config_dir), json.dumps({"version": 1, "files": files}, indent=1, sort_keys=True),
                 0o644)


def _refuse_symlinks(config_dir, path):
    """No symlink between the config's folder and `path` (relative to ROOT): writes never leave the tree."""
    current = config_dir
    for part in [*ROOT.split("/"), *path.split("/")]:
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise ShaderError(f"{current} is a symlink; Umbriel Settings doesn't write through symlinks.")


def install(config_dir, data_dir, effects):
    """Copy the files of `effects` (and their dependencies) that are not next to the config yet from the cache;
    called under the write lock before the config that includes them is written. Each file is listed in the
    manifest before it is written; a file changed by hand is never replaced. Returns the effects copied."""
    effects = [e for e in effects if not os.path.isfile(os.path.join(_effect_dir(config_dir, e), "effect.toml"))]
    if not effects:
        return []
    root = os.path.join(config_dir, ROOT)
    if is_git_checkout(config_dir):
        raise ShaderError(f"{root} is a git checkout without {', '.join(effects)}; update it with git.")
    catalogue, _ = load_catalogue(data_dir)
    if catalogue is None:
        raise ShaderError("The shader catalogue isn't downloaded; open Effects → Community shaders first.")
    records, closure = _records(catalogue), []
    for effect in effects:
        closure += [e for e in _closure(records, effect) if e not in closure]
    manifest, copies = _read_manifest(config_dir), {}
    for path, sha in _files(catalogue, records, closure).items():
        _refuse_symlinks(config_dir, path)
        current = _sha_file(os.path.join(root, path))
        if current == sha:
            continue
        if current is not None and manifest.get(path) != current:
            raise ShaderError(f"{os.path.join(root, path)} was changed by hand; move it away to install "
                              f"{', '.join(effects)}.")
        source = os.path.join(cache_dir(data_dir), "files", path)
        if _sha_file(source) != sha:
            raise ShaderError(f"{path} isn't downloaded; click Install on the Effects page again.")
        copies[path] = (source, sha)
    if copies:
        manifest.update({path: sha for path, (_, sha) in copies.items()})
        _write_manifest(config_dir, manifest)  # first: a kill after it leaves only files the manifest knows
        for path, (source, sha) in copies.items():
            with open(source, "rb") as handle:
                data = handle.read()
            if hashlib.sha256(data).hexdigest() != sha:
                raise ShaderError(f"The cached {path} changed; click Install on the Effects page again.")
            atomic_write(os.path.join(root, path), data, 0o644)
    return closure


def _used_dirs(config_dir, effects):
    """Effect folders (relative to ROOT) the effects use, following the include entries of their effect.toml."""
    root, used, pending = os.path.join(config_dir, ROOT), set(), list(effects)
    while pending:
        effect = pending.pop()
        if effect in used:
            continue
        used.add(effect)
        folder = _effect_dir(config_dir, effect)
        try:
            with open(os.path.join(folder, "effect.toml"), "rb") as handle:
                data = tomllib.load(handle)
        except (OSError, ValueError):
            continue
        for include in include_lists(data):
            path = os.path.relpath(os.path.normpath(os.path.join(folder, os.path.expanduser(include))), root)
            match = re.fullmatch(r"([a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*)/effect\.toml", path.replace(os.sep, "/"))
            if match:
                pending.append(match.group(1))
    return used


def sweep(config_dir, data_dir, effects, trial_pending=False):
    """Remove what this app installed that the written config (which includes `effects`) no longer uses; called
    under the write lock after the config was written, and when the plugin is disabled. Decides from the files on
    disk only: a file changed since is kept (and forgotten), and nothing goes while a Try may still go back to a
    config that uses it. Returns the removed paths (relative to ROOT)."""
    manifest = _read_manifest(config_dir)
    if trial_pending or not manifest:
        return []
    root, used = os.path.join(config_dir, ROOT), _used_dirs(config_dir, effects)
    catalogue, _ = load_catalogue(data_dir)
    records = _records(catalogue) if catalogue else {}
    known = all(effect in records for effect in used)
    licenses = {path for effect in used if effect in records for path in records[effect]["install_files"]}
    removed = []
    for path, sha in sorted(manifest.items()):
        if any(path.startswith(effect + "/") for effect in used):
            continue
        if path.startswith("LICENSES/") and (path in licenses or used and not known):
            continue
        target = os.path.join(root, path)
        try:
            _refuse_symlinks(config_dir, path)
            if _sha_file(target) == sha:
                os.unlink(target)
                removed.append(path)
        except ShaderError:
            pass  # a symlink there now: not ours any more
        del manifest[path]
    for path in removed:  # empty effect folders go too, never ROOT itself
        folder = os.path.dirname(os.path.join(root, path))
        while folder != root and folder.startswith(root + os.sep):
            try:
                os.rmdir(folder)
            except OSError:
                break
            folder = os.path.dirname(folder)
    _write_manifest(config_dir, manifest)  # last: killed before it, the next sweep forgets the missing files
    return removed
