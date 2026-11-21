---
name: community-plugin-pr
description: "Use when submitting the plugin to noctalia-dev/community-plugins or sending an update there: fork, copy the plugin folder from git, run the pinned validator, fill in the PR template, draft → ready."
---

# Submit or update the plugin in community-plugins

**Fork, push, open a PR or mark it ready only on the user's explicit request for that step.** Before a PR:
`update-screenshots` if the panel looks different since `thumbnail.webp` was made; the user has tried
the changed features in the live panel (Noctalia from the checkout, `noctalia-plugin/README.md`).

Upstream: one folder `umbriel-settings/` (= id suffix) at the repo root, one plugin per PR against `main`,
never commit `catalog.toml`, ≤ 200 files, `version` bumped on every change (here: only with a release, see
`build-appimage`), `thumbnail.webp` regenerated only after visible changes. Fork clone:
`~/Applications/community-plugins` (`gh repo fork noctalia-dev/community-plugins --clone=false`, then clone).

## Copy

Always from git (leaves out the ignored `__pycache__/`), never from the working tree; ship the folder
unchanged (`app.luau`, `lib/titlebar.luau`, `ui/sidebar.luau` are app-only; `umbriel_core/` is the synced copy):

```sh
cd ~/Applications/community-plugins && git switch main && git pull && git switch -c <branch>
rm -rf umbriel-settings && mkdir umbriel-settings
git -C ~/Applications/Umbriel-Settings archive HEAD noctalia-plugin/umbriel-settings \
  | tar -x --strip-components=2 -C umbriel-settings
git status --short   # only umbriel-settings/ changed
```

## Validate

The SHA is the one upstream's `.github/workflows/validate-plugins.yml` pins (also `VALIDATOR_REF` in our
`.github/workflows/check.yml`; keep both equal). Real `langdetect`, so the English check runs:

```sh
python -m venv <scratchpad>/v && <scratchpad>/v/bin/pip install langdetect
curl -o <scratchpad>/validate-plugins.py https://raw.githubusercontent.com/noctalia-dev/official-plugins/<sha>/.github/actions/validate-plugins/validate-plugins.py
<scratchpad>/v/bin/python -I <scratchpad>/validate-plugins.py --profile community --root ~/Applications/community-plugins
noctalia plugins lint ~/Applications/community-plugins/umbriel-settings
```

## PR

Commit `Add umbriel-settings` / `Update umbriel-settings to <version>`, push to the fork, then
`gh pr create -R noctalia-dev/community-plugins --draft --base main --head 0rz0rz0rz:<branch> --body-file <file>`.
Body = upstream's `.github/PULL_REQUEST_TEMPLATE.md`, fetched fresh: keep the marker line, every heading and every
checkbox text word for word (a bot checks them). Fill in: Id `0rz0rz0rz/umbriel-settings`; New plugin or Update;
what it does (README intro); dependencies `python3` (bundled helper), `python-tomlkit`, `umbriel`, optional `gio`,
`xdg-open`/editor, plus files written, processes and "Network: none" from the README Notes; Tested on another
compositor: Umbriel; Noctalia version actually tested; Plugin API level = `plugin_api`; screenshots by raw URL
of the pushed fork commit. Show the user the body first. Tick a box only when it is true; `gh pr ready` once the
live test passed and the `validate-plugins` check is green. Review changes: fix here, commit, copy again, push
to the same branch.
