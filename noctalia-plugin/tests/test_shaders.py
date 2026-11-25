"""Helper commands for community shaders and their kill points (a real SIGTERM, a full disk) in `save`. No network:
the catalogue and the files are put in the cache first, as after Browse and Install."""

import hashlib
import json
import subprocess
import sys
import textwrap
import unittest

from support import HELPER, ConfigTestCase

REVISION = "b" * 40
CRT = "shaders/community/window/crt/effect.toml"
FILES = {
    "LICENSES/A-MIT.txt": b"MIT\n",
    "window/crt/effect.toml": b'[effects.preset."window.crt"]\nkind = "window"\nshader = "shader.glsl"\n',
    "window/crt/shader.glsl": b"// crt\n",
}


def catalogue():
    return {
        "schema_version": 1, "source": {"revision": REVISION},
        "effects": [{"id": "window/crt", "kind": "window", "name": "CRT", "description": "Scanlines.", "author": "A",
                     "license": "MIT", "tags": ["retro"], "role": "effect", "preset": "window.crt",
                     "dependencies": [], "install_files": sorted(FILES),
                     "preview": {"image": "window/crt/preview.png"},
                     "activation": {"settings": {"effects.window": "window.crt"}}}],
        "files": {path: {"sha256": hashlib.sha256(data).hexdigest()} for path, data in FILES.items()},
    }


class ShaderHelperTests(ConfigTestCase):
    def setUp(self):
        super().setUp()
        self.cache = self.root / "data" / "umbriel-settings" / "community"
        (self.cache / "files").mkdir(parents=True)
        (self.cache / "catalogue.json").write_text(json.dumps(catalogue()))
        for path, data in FILES.items():
            (self.cache / "files" / path).parent.mkdir(parents=True, exist_ok=True)
            (self.cache / "files" / path).write_bytes(data)
        self.shaders = self.config.parent / "shaders" / "community"

    def request(self, includes, **extra):
        state = self.ok("read", {"config": str(self.config)})
        return {"config": str(self.config), "changes": {"revision": state["revision"], "fields": {
            "include.files": {"value": includes}, **extra}}}

    def save(self, includes, **extra):
        return self.ok("save", self.request(includes, **extra))

    def interrupted_save(self, request, how):
        """`save` killed by SIGTERM right after the manifest (`manifest`) or the config (`config`) was written, or
        with a full disk at the first shader file (`full`)."""
        wrapper = textwrap.dedent("""\
            import importlib.util, os, signal, sys
            helper, how, config = sys.argv[1:4]
            spec = importlib.util.spec_from_file_location("umbriel_settings_under_test", helper)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            from umbriel_core import community_shaders, session
            real_write, real_config = community_shaders.atomic_write, session.write_text_file
            def write(path, data, mode=None):
                if how == "full" and not path.endswith(community_shaders.MANIFEST):
                    raise OSError(28, "No space left on device")
                real_write(path, data, mode)
                if how == "manifest":
                    os.kill(os.getpid(), signal.SIGTERM)
            def write_config(path, text, *rest):
                real_config(path, text, *rest)
                if how == "config" and os.path.abspath(path) == config:
                    os.kill(os.getpid(), signal.SIGTERM)
            community_shaders.atomic_write, session.write_text_file = write, write_config
            sys.exit(module.main(sys.argv[4:]))
        """)
        request_file = self.root / "request.json"
        request_file.write_text(json.dumps(request), encoding="utf-8")
        return subprocess.run([sys.executable, "-I", "-c", wrapper, str(HELPER), how, str(self.config), "save",
                               "--request", str(request_file)], env=self.env, capture_output=True, text=True,
                              check=False)

    def manifest(self):
        return json.loads((self.shaders / ".umbriel-settings.json").read_text())["files"]

    def test_listing_reads_the_cache_and_never_downloads_offline(self):
        listing = self.ok("shaders", {"config": str(self.config), "refresh": True, "offline": True})
        self.assertTrue(listing["loaded"])
        self.assertIsNone(listing["error"])
        [row] = listing["rows"]
        self.assertEqual((row["id"], row["include"], row["installed"]), ("window/crt", CRT, False))
        (self.cache / "catalogue.json").unlink()
        self.assertEqual(self.ok("shaders", {"config": str(self.config), "offline": True}), {"loaded": False})
        self.assertIn("isn't downloaded", self.fails("shader-prepare", {"id": "window/crt"})["error"])

    def test_prepare_offline_uses_the_cache_and_writes_nothing_next_to_the_config(self):
        result = self.ok("shader-prepare", {"id": "window/crt", "offline": True})
        self.assertEqual((result["include"], result["presets"]), (CRT, ["window.crt"]))
        self.assertFalse(self.shaders.exists())

    def test_save_installs_review_lists_and_a_later_save_removes(self):
        preview = self.ok("preview", self.request([CRT]))
        self.assertIn({"page": "Effects", "label": "Install shader files: window/crt"}, preview["summary"])
        report = self.save([CRT], **{"effects.window": {"value": "window.crt"}})
        self.assertTrue(report["saved"])
        self.assertEqual((self.shaders / "window/crt/shader.glsl").read_bytes(), FILES["window/crt/shader.glsl"])
        self.assertIn("window.crt", report["state"]["included"]["effect_preset"])
        self.assertTrue(self.save([])["saved"])
        self.assertFalse((self.shaders / "window").exists())
        self.assertEqual(self.manifest(), {})

    def test_sigterm_after_the_manifest_leaves_known_files_for_the_next_save(self):
        result = self.interrupted_save(self.request([CRT]), "manifest")
        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertNotIn("shaders", self.config.read_text(), "the config wasn't written")
        self.assertEqual(sorted(self.manifest()), sorted(FILES), "every file it may write is known")
        self.assertTrue(self.save([], **{"general.mod_key": {"value": "Alt"}})["saved"])
        self.assertFalse((self.shaders / "window").exists(), "the orphans are swept")

    def test_sigterm_after_the_config_write_keeps_what_it_includes(self):
        result = self.interrupted_save(self.request([CRT]), "config")
        self.assertEqual(result.returncode, 143, result.stderr)
        self.assertIn(CRT, self.config.read_text())
        self.assertTrue(self.save([CRT], **{"general.mod_key": {"value": "Alt"}})["saved"])
        self.assertTrue((self.shaders / "window/crt/effect.toml").is_file(), "still included: kept")

    def test_a_full_disk_fails_the_save_and_leaves_no_half_files(self):
        result = self.interrupted_save(self.request([CRT]), "full")
        self.assertIn("No space left on device", json.loads(result.stdout)["error"])
        self.assertNotIn("shaders", self.config.read_text())
        self.assertFalse((self.shaders / "window/crt/effect.toml").exists())
        self.assertEqual(list(self.shaders.glob("**/*.tmp")), [], "atomic writes leave no temp files")
        self.assertTrue(self.save([CRT])["saved"], "the next attempt works")

    def test_restoring_a_backup_puts_its_shader_files_back_from_the_cache(self):
        self.save([CRT])
        report = self.save([])
        self.assertFalse((self.shaders / "window").exists())
        restored = self.ok("restore", {"config": str(self.config), "snapshot": report["backup"],
                                       "revision": report["state"]["revision"], "validate": False})
        self.assertNotIn("warnings", restored)
        self.assertTrue((self.shaders / "window/crt/shader.glsl").is_file())
        self.assertIn(CRT, self.config.read_text())


if __name__ == "__main__":
    unittest.main()
