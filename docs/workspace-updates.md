# Workspace Updates

What `job-hunter update` actually does, for anyone debugging an update or
changing what it touches.

## The three steps (`cli/commands/update.py::update`)

1. **Workspace assets** — `workspace/assets.py::update_workspace_assets`.
   Iterates `_UPDATE_ASSETS` (currently `README.md`, `SETUP.md`,
   `SETUP_AGENT.md`, `SETUP_LLM_API.md`, `config/career_pages.yml`,
   `config/job_hunter.yml`):
   - Non-YAML files are overwritten outright, except `README.md`, whose
     `<!-- JOBS_STATS_START -->`/`<!-- JOBS_TABLE_START -->` blocks are
     copied forward from the existing file first (`_preserve_readme_blocks`).
   - YAML files are deep-merged (`_merge_yaml`): new template keys are
     added, your existing values win on every conflict, lists and scalars
     included.
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

`--skills-only` / `--workflows-only` run just step 2 or step 3.

## What never gets touched

`profile/`, `outputs/`, `.env`, and any `config/*.yml` key you've already
set (deep-merge preserves it). See [DATA_CONTRACT.md](../DATA_CONTRACT.md).

## Workspace manifest

`job-hunter init` writes `.job-hunter-manifest.json`
(`workspace/manifest.py`): `workspace_version` (currently `"1.0"`),
`package_version_created_with`, and `managed_files` (the skill
path → sha256 map used for stale-file cleanup above). It's a small bit of
system-owned state, not something to hand-edit.

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
