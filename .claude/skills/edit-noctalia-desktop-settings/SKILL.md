---
name: edit-noctalia-desktop-settings
description: "Use when changing user-folder paths, default applications, MIME associations, the icon theme page or the GTK/Qt theme settings it writes (shared desktop pages in the plugin and the app), or their helper protocol."
---

# Edit desktop settings (user folders, default apps, icon theme)

- The icon theme is the third desktop part (`icons`): `python/umbriel_core/icon_themes.py` (themes, preview icons, deleting home copies), `toolkit_settings.py` (gsettings + GTK/Qt/KDE files, only the theme lines, per-file backups and warnings; also the cursor theme a config save syncs) and `theme_files.py` (shared with cursor themes); helper `icon-themes`, `desktop` → `icons`, `desktop-save` → `save_icons`; UI `pages/icons.luau`. Tests never touch the real files: temp `HOME` and `GSETTINGS_BACKEND=memory` (or a fake `gsettings` on `PATH`).
- Logic lives in `python/umbriel_core/xdg_dirs.py` (folder parsing, validation, `update_text`, `save`) and `python/umbriel_core/mimeapps.py` (roles, `installed_apps` with localized `Name[...]` and `OnlyShowIn`/`NotShowIn`, `update_text`, `save`, `extension_mime`, `mime_extensions` → `extensions` in the snapshot so the file-type filter matches `.docx`); both read with `paths.read_document` and save through `backups.replace_checked` (symlink refusal, revision check, `snapshot_file` backup, `paths.atomic_write`). All are stdlib-only (`tests/test_core.py` checks it). Run `tools/sync_plugin_core.py` after editing them.
- Unsaved desktop edits go into the draft (`lib/drafts.luau` `drafts.save`) and come back in `store.loadDesktop` when the file's revision is unchanged. `desktop-save` returns only each written part's new `revision`; the page reloads the files afterwards.
- The helper exposes them as `desktop`, `desktop-save` (`{userdirs: {revision, changes}, apps: {revision, changes}}`) and `extension` in `noctalia-plugin/umbriel-settings/umbriel_settings.py`; the panel side is `pages/desktop.luau` and `store.desktopChanges`/`loadDesktop`. `noctalia.appIconPath` can take several ms per miss: icon lookups are capped per render by count and by `noctalia.nowMs` time (`ICON_BUDGET_MS`).
- Preserve unrelated entries and comments, MIME fallback IDs, unchanged values, revision conflict detection, timestamped backups in `$XDG_DATA_HOME/umbriel-settings/backups/` (`backups.snapshot_file`, newest 10), atomic replacement and symlink refusal. Surface invalid input and IO errors.
- The new app uses the same `pages/desktop.luau` and helper commands (in-process); app icons come from `icon_file` in `app_window.py`.
- Add isolated temporary-XDG tests in `noctalia-plugin/tests/test_user_dirs.py` or `test_default_apps.py`; use `add-test` and run `python tools/check.py core plugin host`.
