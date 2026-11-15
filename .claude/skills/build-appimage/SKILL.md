---
name: build-appimage
description: "Use when building, releasing, or republishing a new Umbriel Settings AppImage: bumping the <Umbriel version>-<revision> version, running appimage/build-appimage.sh, testing the result, and updating the GitHub release."
---

# Build and release an Umbriel Settings AppImage

**Only build when the user has explicitly allowed this build.** Otherwise stop and ask; prepare the version bump and script changes without running the build.

## Version scheme

`__version__` in `python/umbriel_settings/__init__.py` is `<Umbriel version>-<NNN>`, for example `0.1.0-001`.

- New GUI build for the same Umbriel version: increment `NNN` (`001` -> `002`).
- New Umbriel version (check `umbriel --version`): use it and reset `NNN` to `001`.

This single value is used by `--version`, the AppImage file name; `plugin.toml` follows it as `<major>.<minor>.<NNN>` (`0.1.0-004` → `0.1.4`; `tests/test_core.py` checks it). Never raise the `0.1.0` part on your own.

The build bundles `python/umbriel_settings`, `python/umbriel_core` (one `-x` with two paths) and the shared Luau UI from the plugin (`app.luau`, `lib/`, `ui/`, `pages/`, `umbriel_settings.py`) as `umbriel_settings/ui_shared/`. It installs `python/requirements.txt` (PySide6, tomlkit, lupa) and keeps QtWebEngine, QtWebChannel and their Qt libraries (`libexec/QtWebEngineProcess`, `resources/`, `translations/qtwebengine_locales`). The first build after the web-view switch is unverified: check that `umbriel_core/` sits next to `umbriel_settings/`, that `ui_shared/app.luau` exists, and that the app window opens and shows pages (WebEngine can fail at runtime when a pruned library is missing; run it from a terminal and read the errors). The script prunes unused Qt libraries, plugins and Python stdlib/tooling, then fails if a remaining Qt library still needs a pruned `libQt6*` (uses `readelf`); extend the prune lists, not the guard.

## Pinned downloads

`appimage/fetch-pinned.sh` downloads everything first and checks each file's SHA-256: python-appimage and its dependencies (`appimage/build-tools.lock`), the Python base image and appimagetool (`appimage/pins.sh`, per architecture), and the app's wheels with every dependency (`appimage/requirements.lock`). python-appimage then gets the base image with `-b`, and its pip runs with `PIP_NO_INDEX=1` and `PIP_FIND_LINKS=<verified wheels>`, so nothing unverified enters the image. The Python version (3.12), python-appimage (1.4.7) and appimagetool (1.9.1, not "continuous") are set in `tools/update_appimage_pins.py`.

- After changing `python/requirements.txt` or a version in that tool: `python tools/update_appimage_pins.py` (`--check` compares). `tests/test_core.py` fails when the lock is missing a requirement.
- "Checksum mismatch" or a 404 for the base image: the python-appimage `python3.12` release replaces its files with each Python patch release. Rerun the tool, look at what changed, and rebuild.
- Testing the downloads without building: `appimage/fetch-pinned.sh <scratch dir>`.
- python-appimage reads the Python version from the base image's file name, so `fetch-pinned.sh` keeps the release name under `base/`; a renamed file fails with "Invalide base image". First pinned build: 0.1.0-006.

## Steps

1. Bump `__version__` as described above.
2. After editing the build scripts or `recipe/entrypoint.sh`, run `python tools/check.py lint` (shellcheck). Build: `appimage/build-appimage.sh` (needs network, `python3` with `venv`, `curl`, `sha256sum`, `readelf`, FUSE or `APPIMAGE_EXTRACT_AND_RUN=1`). Output: `dist/Umbriel-Settings-<version>-<arch>.AppImage`.
3. Test: `dist/Umbriel-Settings-<version>-<arch>.AppImage --appimage-extract-and-run --version` must print the new version, and a normal start must open the window with the sidebar and pages (this is the one place where launching the app is required). The image must contain `usr/share/licenses/Umbriel-Settings/LICENSE` and `.../host/web/fonts/LICENSE-tabler-icons.txt`.
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
- Ask before pushing, tagging, or publishing if the user has not requested a release.
