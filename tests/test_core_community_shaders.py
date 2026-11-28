"""Community shaders (`umbriel_core.community_shaders`): catalogue, cache, install with the save, sweep (no network)."""

import hashlib
import io
import json
import os
import stat
import tempfile
import time
import tomllib
import unittest
import urllib.error
from unittest.mock import patch

from umbriel_core import community_shaders as shaders
from umbriel_core.session import ConfigSession

REVISION = "a" * 40
FILES = {
    "LICENSES/A-MIT.txt": b"MIT license text\n",
    "window/crt/effect.toml": b'[effects.preset."window.crt"]\nkind = "window"\nshader = "shader.glsl"\n',
    "window/crt/shader.glsl": b"// crt\n",
    "window/crt/preview.png": b"\x89PNG crt",
    "border/rainbow/effect.toml": (b'[include]\nfiles = ["../../window/rainbow-overlay/effect.toml"]\n\n'
                                   b'[effects.preset."rainbow"]\nkind = "border"\nshader = "shader.glsl"\n'
                                   b'overlay = "rainbow-overlay"\n'),
    "border/rainbow/shader.glsl": b"// rainbow\n",
    "window/rainbow-overlay/effect.toml": (b'[effects.preset."rainbow-overlay"]\nkind = "window"\n'
                                           b'shader = "shader.glsl"\n'),
    "window/rainbow-overlay/shader.glsl": b"// overlay\n",
}


def record(effect, preset, role="effect", deps=(), settings=None):
    kind, name = effect.split("/")
    files = ["LICENSES/A-MIT.txt", f"{effect}/effect.toml", f"{effect}/shader.glsl"]
    return {"id": effect, "kind": kind, "name": name.title(), "description": f"The {name} effect.", "author": "A",
            "license": "MIT", "tags": ["test"], "role": role, "preset": preset, "dependencies": list(deps),
            "install_files": files, "preview": {"image": f"{effect}/preview.png", "animation": None},
            "activation": {"include": [f"{effect}/effect.toml"], "settings": settings or {}} if role == "effect"
            else None}


def catalogue(files=FILES):
    return {
        "schema_version": 1, "draft": False, "source": {"repository": "x", "revision": REVISION},
        "feature_definitions": {}, "families": [],
        "effects": [record("window/crt", "window.crt", settings={"effects.window": "window.crt"}),
                    record("border/rainbow", "rainbow", deps=["window/rainbow-overlay"],
                           settings={"effects.border": "rainbow"}),
                    record("window/rainbow-overlay", "rainbow-overlay", role="companion")],
        "files": {path: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                  for path, data in files.items()},
    }


class Server:
    """Stands in for raw.githubusercontent.com: url → bytes; counts requests."""

    def __init__(self, served):
        self.served, self.requests = served, []

    def __call__(self, request, timeout):
        url = request.full_url
        self.requests.append(url)
        if url not in self.served:
            raise urllib.error.URLError("not found")
        return io.BytesIO(self.served[url])


def serve(files=FILES, data=None):
    served = {shaders.FILE_URL.format(revision=REVISION, path=path): content for path, content in files.items()}
    served[shaders.CATALOGUE_URL] = json.dumps(data or catalogue()).encode()
    return Server(served)


class ShaderTestCase(unittest.TestCase):
    def setUp(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        self.root = tempdir.name
        self.data = os.path.join(self.root, "data")
        self.config_dir = os.path.join(self.root, "umbriel")
        os.makedirs(self.config_dir)
        self.server = serve()
        patcher = patch.object(shaders, "urlopen", self.server)
        patcher.start()
        self.addCleanup(patcher.stop)

    def installed(self, path):
        return os.path.join(self.config_dir, shaders.ROOT, path)

    def manifest(self):
        with open(self.installed(shaders.MANIFEST), encoding="utf-8") as handle:
            return json.load(handle)["files"]

    def ready(self, *effects):
        """Catalogue and the effects' files in the cache, as after Browse + Install."""
        data = shaders.refresh_catalogue(self.data)
        for effect in effects:
            shaders.prepare(data, self.data, effect)
        return data


class CatalogueTests(ShaderTestCase):
    def test_refresh_caches_privately_and_rows_hide_companions(self):
        self.assertEqual(shaders.load_catalogue(self.data), (None, None))
        data = shaders.refresh_catalogue(self.data)
        path = os.path.join(self.data, "community", "catalogue.json")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(shaders.load_catalogue(self.data)[0], data)
        rows = shaders.entries(data, self.config_dir)
        self.assertEqual([row["id"] for row in rows], ["window/crt", "border/rainbow"])  # by kind, then name
        rainbow = rows[1]
        self.assertEqual(rainbow["presets"], ["rainbow", "rainbow-overlay"])
        self.assertEqual(rainbow["include"], "shaders/community/border/rainbow/effect.toml")
        self.assertEqual(rainbow["settings"], {"effects.border": "rainbow"})
        self.assertFalse(rainbow["installed"])

    def test_an_unknown_format_or_a_failed_download_is_refused(self):
        bad = catalogue()
        bad["schema_version"] = 2
        self.server.served[shaders.CATALOGUE_URL] = json.dumps(bad).encode()
        with self.assertRaisesRegex(shaders.ShaderError, "format"):
            shaders.refresh_catalogue(self.data)
        del self.server.served[shaders.CATALOGUE_URL]
        with self.assertRaisesRegex(shaders.ShaderError, "Could not download"):
            shaders.refresh_catalogue(self.data)
        self.assertFalse(os.path.exists(os.path.join(self.data, "community", "catalogue.json")))

    def test_previews_are_checked_cached_and_skipped_offline(self):
        data = shaders.refresh_catalogue(self.data)
        self.assertEqual(shaders.previews(data, self.data, ["window/crt"], offline=True),
                         {"paths": {}, "failed": []})
        found = shaders.previews(data, self.data, ["window/crt", "border/rainbow", "nope/x"])
        self.assertEqual(sorted(found["failed"]), ["border/rainbow", "nope/x"])  # rainbow: no preview served
        with open(found["paths"]["window/crt"], "rb") as handle:
            self.assertEqual(handle.read(), FILES["window/crt/preview.png"])
        count = len(self.server.requests)
        shaders.previews(data, self.data, ["window/crt"])
        self.assertEqual(len(self.server.requests), count, "cached")
        tampered = dict(FILES, **{"window/crt/preview.png": b"other"})
        self.server.served.update(serve(tampered).served)
        os.unlink(found["paths"]["window/crt"])
        self.assertEqual(shaders.previews(data, self.data, ["window/crt"])["failed"], ["window/crt"])

    def test_a_malformed_catalogue_is_a_readable_error_not_a_crash(self):
        for broken in ({"source": "x"}, {"source": None}):
            bad = dict(catalogue(), **broken)
            self.server.served[shaders.CATALOGUE_URL] = json.dumps(bad).encode()
            with self.assertRaisesRegex(shaders.ShaderError, "format"):
                shaders.refresh_catalogue(self.data)
        odd = catalogue()
        odd["effects"][0]["tags"] = 3
        odd["effects"][1]["dependencies"] = True
        self.server.served[shaders.CATALOGUE_URL] = json.dumps(odd).encode()
        rows = {row["id"]: row for row in shaders.entries(shaders.refresh_catalogue(self.data), self.config_dir)}
        self.assertEqual(rows["window/crt"]["tags"], [])
        self.assertIn("border/rainbow", rows)

    def test_a_download_stops_at_its_deadline_even_while_data_trickles_in(self):
        class Trickle(io.BytesIO):
            def read(self, size=-1):
                clock[0] += 10  # every chunk takes 10 s
                return super().read(1)
        clock = [0.0]
        with patch.object(shaders, "urlopen", lambda request, timeout: Trickle(b"x" * 100)), \
                patch.object(shaders.time, "monotonic", lambda: clock[0]):
            with self.assertRaisesRegex(shaders.ShaderError, "too long"):
                shaders._fetch("https://example.invalid/x", 1000, timeout=15)


class PrepareTests(ShaderTestCase):
    def test_prepare_caches_the_effect_and_its_dependencies_only(self):
        data = shaders.refresh_catalogue(self.data)
        result = shaders.prepare(data, self.data, "border/rainbow")
        self.assertEqual(result["presets"], ["rainbow", "rainbow-overlay"])
        cached = os.path.join(self.data, "community", "files")
        for path in ("border/rainbow/effect.toml", "window/rainbow-overlay/shader.glsl", "LICENSES/A-MIT.txt"):
            self.assertTrue(os.path.isfile(os.path.join(cached, path)), path)
        self.assertFalse(os.path.exists(os.path.join(self.config_dir, "shaders")), "nothing next to the config")
        count = len(self.server.requests)
        shaders.prepare(data, self.data, "border/rainbow", offline=True)  # cached: no download needed
        self.assertEqual(len(self.server.requests), count)

    def test_a_wrong_checksum_or_an_unsafe_path_writes_nothing(self):
        data = shaders.refresh_catalogue(self.data)
        self.server.served[shaders.FILE_URL.format(revision=REVISION, path="window/crt/shader.glsl")] = b"evil"
        with self.assertRaisesRegex(shaders.ShaderError, "checksum"):
            shaders.prepare(data, self.data, "window/crt")
        self.assertFalse(os.path.exists(os.path.join(self.data, "community", "files", "window/crt/shader.glsl")))
        data["effects"][0]["install_files"].append("../../outside.txt")
        with self.assertRaisesRegex(shaders.ShaderError, "unsafe"):
            shaders.prepare(data, self.data, "window/crt")
        with self.assertRaisesRegex(shaders.ShaderError, "offline"):
            shaders.prepare(shaders.load_catalogue(self.data)[0], self.data, "window/crt", offline=True)


class InstallAndSweepTests(ShaderTestCase):
    def test_install_records_files_before_writing_them(self):
        self.ready("border/rainbow")
        order = []
        real = shaders.atomic_write

        def write(path, data, mode=None):
            order.append(os.path.relpath(path, os.path.join(self.config_dir, shaders.ROOT)))
            if order[-1] != shaders.MANIFEST:  # killed right after the manifest: only known files may follow
                raise KeyboardInterrupt
            return real(path, data, mode)
        with patch.object(shaders, "atomic_write", write), self.assertRaises(KeyboardInterrupt):
            shaders.install(self.config_dir, self.data, ["border/rainbow"])
        self.assertEqual(order[0], shaders.MANIFEST)
        self.assertIn("border/rainbow/shader.glsl", self.manifest())
        self.assertEqual(shaders.install(self.config_dir, self.data, ["border/rainbow"]),
                         ["border/rainbow", "window/rainbow-overlay"])
        self.assertEqual(stat.S_IMODE(os.stat(self.installed("border/rainbow/shader.glsl")).st_mode), 0o644)
        self.assertEqual(shaders.install(self.config_dir, self.data, ["border/rainbow"]), [], "already there")

    def test_install_refuses_symlinks_hand_edits_git_checkouts_and_a_missing_cache(self):
        with self.assertRaisesRegex(shaders.ShaderError, "isn't downloaded"):
            shaders.install(self.config_dir, self.data, ["window/crt"])
        self.ready()
        with self.assertRaisesRegex(shaders.ShaderError, "isn't downloaded"):
            shaders.install(self.config_dir, self.data, ["window/crt"])  # catalogue only, no files cached
        self.ready("window/crt")
        elsewhere = os.path.join(self.root, "elsewhere")
        os.makedirs(elsewhere)
        os.makedirs(os.path.join(self.config_dir, "shaders"))
        os.symlink(elsewhere, os.path.join(self.config_dir, "shaders", "community"))
        with self.assertRaisesRegex(shaders.ShaderError, "symlink"):
            shaders.install(self.config_dir, self.data, ["window/crt"])
        self.assertEqual(os.listdir(elsewhere), [])
        os.unlink(os.path.join(self.config_dir, "shaders", "community"))
        os.makedirs(self.installed("window/crt"))
        with open(self.installed("window/crt/shader.glsl"), "w", encoding="utf-8") as handle:
            handle.write("// mine\n")
        with self.assertRaisesRegex(shaders.ShaderError, "changed by hand"):
            shaders.install(self.config_dir, self.data, ["window/crt"])
        os.makedirs(self.installed(".git"))
        with self.assertRaisesRegex(shaders.ShaderError, "git checkout"):
            shaders.install(self.config_dir, self.data, ["window/crt"])

    def test_sweep_removes_only_unused_unchanged_files_of_its_own(self):
        self.ready("window/crt", "border/rainbow")
        shaders.install(self.config_dir, self.data, ["window/crt", "border/rainbow"])
        mine = self.installed("window/crt/notes.txt")
        with open(mine, "w", encoding="utf-8") as handle:
            handle.write("not installed by the app\n")
        self.assertEqual(shaders.sweep(self.config_dir, self.data, ["window/crt"], trial_pending=True), [])
        removed = shaders.sweep(self.config_dir, self.data, ["window/crt"])
        self.assertEqual(sorted(removed), ["border/rainbow/effect.toml", "border/rainbow/shader.glsl",
                                           "window/rainbow-overlay/effect.toml", "window/rainbow-overlay/shader.glsl"])
        self.assertFalse(os.path.exists(self.installed("border")), "empty folders go too")
        self.assertTrue(os.path.isfile(self.installed("LICENSES/A-MIT.txt")), "crt still lists it")
        self.assertTrue(os.path.isfile(mine))
        with open(self.installed("window/crt/shader.glsl"), "w", encoding="utf-8") as handle:
            handle.write("// edited\n")
        self.assertEqual(sorted(shaders.sweep(self.config_dir, self.data, [])),
                         ["LICENSES/A-MIT.txt", "window/crt/effect.toml"])
        self.assertTrue(os.path.isfile(self.installed("window/crt/shader.glsl")), "an edited file is kept")
        self.assertEqual(self.manifest(), {}, "and forgotten")

    def test_a_sweep_killed_before_its_manifest_is_finished_by_the_next(self):
        self.ready("window/crt")
        shaders.install(self.config_dir, self.data, ["window/crt"])
        os.unlink(self.installed("window/crt/shader.glsl"))  # deleted, then killed: the manifest still lists it
        self.assertEqual(sorted(shaders.sweep(self.config_dir, self.data, [])),
                         ["LICENSES/A-MIT.txt", "window/crt/effect.toml"])
        self.assertEqual(self.manifest(), {})

    def test_a_dependency_stays_while_an_included_effect_uses_it(self):
        self.ready("border/rainbow")
        shaders.install(self.config_dir, self.data, ["border/rainbow"])
        self.assertEqual(shaders.sweep(self.config_dir, self.data, ["border/rainbow"]), [])
        self.assertTrue(os.path.isfile(self.installed("window/rainbow-overlay/effect.toml")))

    def test_effect_of_reads_relative_and_absolute_entries(self):
        absolute = os.path.join(self.config_dir, "shaders/community/window/crt/effect.toml")
        for entry in ("shaders/community/window/crt/effect.toml", "./shaders/community/window/crt/effect.toml",
                      absolute):
            self.assertEqual(shaders.effect_of(entry, self.config_dir), "window/crt", entry)
        for entry in ("colors.toml", "shaders/community/../x/y/effect.toml", "shaders/community/a/b/c/effect.toml"):
            self.assertIsNone(shaders.effect_of(entry, self.config_dir), entry)


class SessionTests(ShaderTestCase):
    def session(self, text="[general]\n"):
        path = os.path.join(self.config_dir, "config.toml")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        return ConfigSession(path, self.data)

    def save(self, includes, before_write=None):
        session = self.session()
        return session.save({"revision": session.read()["revision"],
                             "fields": {"include.files": {"value": includes}}},
                            validate=False, backup=lambda path, config_dir: None, before_write=before_write)

    def test_the_save_installs_what_the_new_config_includes_and_a_later_save_removes_it(self):
        self.ready("border/rainbow")
        include = shaders.include_path("border/rainbow")
        preview = self.session().preview({"revision": self.session().read()["revision"],
                                          "fields": {"include.files": {"value": [include]}}}, validate=False)
        self.assertIn({"page": "Effects", "label": "Install shader files: border/rainbow"}, preview["summary"])
        self.assertFalse(os.path.exists(self.installed("border")), "a preview writes nothing")
        seen = []
        report = self.save([include], before_write=lambda *_: seen.append(
            os.path.isfile(self.installed("window/rainbow-overlay/effect.toml"))))
        self.assertTrue(report["saved"])
        self.assertEqual(seen, [True], "the files are there before the config that needs them")
        self.assertEqual(self.session().read()["included"]["effect_preset"], ["rainbow", "rainbow-overlay"])
        report = self.save([])
        self.assertTrue(report["saved"])
        self.assertFalse(os.path.exists(self.installed("border")))

    def test_a_save_failing_before_the_write_leaves_files_a_later_save_sweeps(self):
        self.ready("window/crt")
        include = shaders.include_path("window/crt")

        def fail(*_):
            raise OSError(28, "No space left on device")
        with self.assertRaises(OSError):
            self.save([include], before_write=fail)
        with open(self.session().path, encoding="utf-8") as handle:
            self.assertNotIn("shaders", handle.read())
        self.assertTrue(os.path.isfile(self.installed("window/crt/effect.toml")), "left for the sweep, not undone")
        session = self.session()
        report = session.save({"revision": session.read()["revision"], "fields": {
            "general.mod_key": {"value": "Alt"}}}, validate=False, backup=lambda path, config_dir: None)
        self.assertTrue(report["saved"])
        self.assertFalse(os.path.exists(self.installed("window")), "the next save removes the orphan")

    def test_no_sweep_while_a_try_can_go_back_unless_its_watcher_died_long_ago(self):
        self.ready("window/crt")
        include = shaders.include_path("window/crt")
        self.save([include])
        session = self.session()
        os.makedirs(session.config_dir, exist_ok=True)
        token = os.path.join(session.config_dir, "trial.json")
        for deadline, kept in ((time.time() + 30, True), (time.time() - 3600, False)):
            with open(token, "w", encoding="utf-8") as handle:
                json.dump({"id": "t", "backup": "/x.bak", "deadline": deadline}, handle)
            self.save([])
            self.assertEqual(os.path.isfile(self.installed("window/crt/effect.toml")), kept, deadline)
            if kept:
                self.save([include])

    def test_validation_reads_effects_only_the_save_installs_from_the_cache(self):
        self.ready("window/crt")
        include = shaders.include_path("window/crt")
        text = self.session()._validation_text(f'[include]\nfiles = ["{include}", "colors.toml"]\n')
        files = tomllib.loads(text)["include"]["files"]
        self.assertEqual(files, [os.path.join(self.data, "community", "files", "window/crt/effect.toml"),
                                 "colors.toml"])
        self.save([include])
        self.assertEqual(self.session()._validation_text(f'[include]\nfiles = ["{include}"]\n'),
                         f'[include]\nfiles = ["{include}"]\n', "installed: validated in place")


if __name__ == "__main__":
    unittest.main()
