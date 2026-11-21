---
name: build-appimage
description: "Use when building, releasing, or republishing a new Umbriel Settings AppImage: bumping the MAJOR.MINOR.PATCH version, running appimage/build-appimage.sh, testing the result, and updating the GitHub release."
---

# Build and release an Umbriel Settings AppImage

**Only build when the user has explicitly allowed this build.** Otherwise stop and ask; prepare the version bump and script changes without running the build.

## Version scheme

`__version__` in `python/umbriel_settings/__init__.py` is the project's own `MAJOR.MINOR.PATCH` (`0.2.0`); `plugin.toml` `version`, the AppImage file name, `--version` and the tag `v<version>` use the same string. Bump from the latest tag (`git describe --tags --abbrev=0`):

- PATCH: only fixes since the last release.
- MINOR (PATCH → 0): new settings, pages or features, a new Umbriel target (`UMBRIEL_VERSION`) or a raised `plugin_api` (`NOCTALIA_VERSION`).
- MAJOR stays 0 until the user decides on 1.0.0. Releases up to `0.1.0-006` used the old `<Umbriel version>-<NNN>` names.
- If `__version__` is already above the latest tag (set when the scheme changed), build it as is.

Versions are raised only here, as part of building and releasing a new AppImage; commits and pushes in between keep the released version. Also update the Versions tables in `README.md` (incl. **Latest release**), `noctalia-plugin/README.md` and `noctalia-plugin/umbriel-settings/README.md`; `tests/test_core.py` (`test_versions_agree`) checks app, plugin, targets and READMEs agree.

The build copies `python/umbriel_settings/assets/icon.png` into the recipe as the desktop icon, and bundles `python/umbriel_settings`, `python/umbriel_core` (one `-x` with two paths) and the shared Luau UI from the plugin (`app.luau`, `lib/`, `ui/`, `pages/`, `umbriel_settings.py`) as `umbriel_settings/ui_shared/`. It installs `python/requirements.txt` (PySide6, tomlkit, lupa) and keeps QtWebEngine, QtWebChannel and their Qt libraries (`libexec/QtWebEngineProcess`, `resources/`, `translations/qtwebengine_locales`). If the built app fails at runtime, check that `umbriel_core/` sits next to `umbriel_settings/` and `ui_shared/app.luau` exists, and run it from a terminal (WebEngine fails when a pruned library is missing). The script prunes unused Qt libraries, plugins and Python stdlib/tooling, then fails if a remaining Qt library still needs a pruned `libQt6*` (uses `readelf`); extend the prune lists, not the guard.

## Pinned downloads

`appimage/fetch-pinned.sh` downloads everything first and checks each file's SHA-256: python-appimage and its dependencies (`appimage/build-tools.lock`), the Python base image and appimagetool (`appimage/pins.sh`, per architecture), and the app's wheels with every dependency (`appimage/requirements.lock`). python-appimage then gets the base image with `-b`, and its pip runs with `PIP_NO_INDEX=1` and `PIP_FIND_LINKS=<verified wheels>`, so nothing unverified enters the image. The Python version (3.12), python-appimage (1.4.7) and appimagetool (1.9.1, not "continuous") are set in `tools/update_appimage_pins.py`.

- After changing `python/requirements.txt` or a version in that tool: `python tools/update_appimage_pins.py` (`--check` compares). `tests/test_core.py` fails when the lock is missing a requirement.
- "Checksum mismatch" or a 404 for the base image: the python-appimage `python3.12` release replaces its files with each Python patch release. Rerun the tool, look at what changed, and rebuild.
- Testing the downloads without building: `appimage/fetch-pinned.sh <scratch dir>`.
- python-appimage reads the Python version from the base image's file name, so `fetch-pinned.sh` keeps the release name under `base/`; a renamed file fails with "Invalide base image".

## Steps

1. Bump `__version__` as described above.
2. After editing the build scripts or `recipe/entrypoint.sh`, run `python tools/check.py lint` (shellcheck). Build: `appimage/build-appimage.sh` (needs network, `python3` with `venv`, `curl`, `sha256sum`, `readelf`, FUSE or `APPIMAGE_EXTRACT_AND_RUN=1`). Output: `dist/Umbriel-Settings-<version>-<arch>.AppImage`.
3. Test: `dist/Umbriel-Settings-<version>-<arch>.AppImage --appimage-extract-and-run --version` must print the new version, and a normal start must open the window with the sidebar and pages (launching it here is required). Always start the AppImage file itself (with `--appimage-extract-and-run` if FUSE is missing), never an extracted `squashfs-root` (`AppRun` or its Python): a started app registers itself as the desktop entry the plugin opens, and an extracted copy is a temporary folder (the app now refuses to register one). The user's entry carries `X-Umbriel-Settings-Keep=true`, so a test start doesn't take it over; leave that line in place. The image must contain `usr/share/licenses/Umbriel-Settings/LICENSE` and `.../host/web/fonts/LICENSE-tabler-icons.txt`.
4. Commit the version bump, then `git push origin main`.
5. Tag and release (tag is `v<version>`):
   ```sh
   git tag v<version> -m "v<version>" && git push origin v<version>
   gh release create v<version> dist/Umbriel-Settings-<version>-<arch>.AppImage \
     --title "v<version>" --notes "<what changed>"
   ```
6. Remove superseded AppImages from `dist/`; `dist/` is git-ignored.

## Rules

- Do not force-push, delete tags, or replace an existing release's assets unless the user asks.
- Ask before pushing if the user has not requested it. Once a permitted build is pushed, always tag and release it (steps 5-6) without asking.
