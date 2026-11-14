---
name: edit-noctalia-desktop-settings
description: "Use when changing user-folder paths, default applications, MIME associations (shared desktop page in the plugin and the app) or their helper protocol."
---

# Edit desktop settings (user folders, default apps)

- Logic lives in `python/umbriel_core/xdg_dirs.py` (folder parsing, validation, `read_document`, `save`) and `python/umbriel_core/mimeapps.py` (roles, `installed_apps` with localized `Name[...]` and `OnlyShowIn`/`NotShowIn`, `update_text`, `save`, `extension_mime`); writes go through `paths.atomic_write`, backups through `backups.snapshot_file`. All are stdlib-only (`tests/test_core.py` checks it). Run `tools/sync_plugin_core.py` after editing them.
- Unsaved desktop edits go into the draft (`store.saveDraft`) and come back in `store.loadDesktop` when the file's revision is unchanged.
- The helper exposes them as `desktop`, `desktop-save` (`{userdirs: {revision, changes}, apps: {revision, changes}}`) and `extension` in `noctalia-plugin/umbriel-settings/umbriel_settings.py`; the panel side is `pages/desktop.luau` and `store.desktopChanges`/`loadDesktop`.
- Preserve unrelated entries and comments, MIME fallback IDs, unchanged values, revision conflict detection, timestamped backups in `$XDG_DATA_HOME/umbriel-settings/backups/` (`backups.snapshot_file`, newest 10), atomic replacement and symlink refusal. Surface invalid input and IO errors.
- The new app uses the same `pages/desktop.luau` and helper commands (in-process); app icons come from `icon_file` in `app_window.py`.
- Add isolated temporary-XDG tests in `noctalia-plugin/tests/test_user_dirs.py` or `test_default_apps.py`; use `test-noctalia-plugin` and run `python tools/check.py core plugin host`.
