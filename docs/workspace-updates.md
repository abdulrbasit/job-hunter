# Workspace Updates

What `job-hunter update` actually does, for anyone debugging an update or
changing what it touches.

## The steps (`cli/commands/update.py::update`)

1. **Workspace assets** — `workspace/assets.py::update_workspace_assets`.
   Iterates `_UPDATE_ASSETS` (currently `README.md`, `SETUP.md`,
   `SETUP_AGENT.md`, `SETUP_LLM_API.md`):
   - Non-YAML files are overwritten outright, except `README.md`, whose
     `<!-- JOBS_STATS_START -->`/`<!-- JOBS_TABLE_START -->` blocks are
     copied forward from the existing file first (`_preserve_readme_blocks`).
   - `config/job_hunter.yml` is user-owned YAML. If the file already exists,
     update leaves it alone — no reading, no rewriting, no merging of any
     kind. `job-hunter doctor` schema-validates it and tells you what to add
     by hand if a future release ever needs a new required key. Doctor also
     migrates a leftover `config/career_pages.yml` (the retired company-config
     file) into `companies.targets` once, then removes it.
   - `_OBSOLETE_CLI_DIRS` (currently just `.gemini/`) is removed outright
     first, if present — an old mirrored agent-CLI skill tree with no user
     data in it.
2. **Skills** — `workspace/operations.py::update_skills`. Overwrites every
   file under `.claude/skills/` (and its `.agents/skills/` mirror) with the
   current template. Compares against `manifest.managed_files` (a
   path → sha256 map, from `job-hunter init` and each prior update) to
   detect and remove skill files that were removed upstream — but only if
   your copy is unmodified; a locally-edited stale file is preserved with a
   warning instead of deleted.
3. **Workflows** — `workspace/operations.py::update_workflows`. Overwrites
   `.github/` files, but `_preserve_user_schedule` carries forward any
   active (uncommented) `cron:` line from your existing `find-jobs.yml` so
   enabling a schedule survives updates.
4. **Telemetry** — `workspace/operations.py::install_telemetry`. Merges
   OTel hook config into `.claude/settings.json` and `.codex/hooks.json`
   (workspace-local), and into `~/.codex/config.toml` (global, once per
   machine — left alone if it already has non-Job-Hunter `[otel]` config).

`--skills-only` / `--workflows-only` run just step 2 or step 3.

## What never gets touched

`profile/`, `outputs/`, `.env`, and any existing `config/*.yml` file —
byte for byte, not just its values. See [DATA_CONTRACT.md](../DATA_CONTRACT.md).

## Workspace manifest

`job-hunter init` writes `.job-hunter/manifest.json`
(`workspace/manifest.py`): `workspace_version` (currently `"1.0"`),
`package_version_created_with`, `managed_files`, and `applied_migrations`.

`managed_files` tracks **skill files only** (the path → sha256 map used for
stale-skill cleanup in step 2 above) — it is not a record of every file the
steps above write. Workspace assets and workflows are overwritten (or, for
existing user-owned YAML, left alone) directly and aren't tracked in the
manifest.

`applied_migrations` is a list of migration IDs, reserved for any future
one-off workspace migration; nothing currently writes to it.

It's a small bit of system-owned state, not something to hand-edit.

## Dev-time vs. runtime sync — two different things

Easy to conflate, so keep them distinct:

- **`scripts/sync_workspace_template.py`** — a contributor tool. Copies
  canonical root files (`CLAUDE.md`, `GEMINI.md`, `SETUP.md`, `config/`,
  user-facing skill dirs) into `job_hunter/templates/workspace/` so
  contributors don't hand-maintain two copies. Run it (or its `--check`
  mode, which CI runs before `uv build`) after editing one of the synced
  root files. It is **not** shipped in the package and has nothing to do
  with `job-hunter update`.
- **`workspace/assets.py`** — the runtime code above. This is what
  `job-hunter init`/`update` actually execute against an installed
  package's bundled resources.

Note: `SETUP_AGENT.md` and `SETUP_LLM_API.md` are **not** synced by
`scripts/sync_workspace_template.py` — they exist only under
`job_hunter/templates/workspace/` and are edited there directly.
