# Data Contract

Product updates may replace system-owned files. They must never overwrite user data.

## User Layer — never modified by updates

| Path | What it holds |
|---|---|
| `config/job_hunter.yml` | Your choices: profile paths, location references, titles, filters, scoring, LLM choices, and your own `companies.targets` |
| `profile/` | Resume files, story bank, career context, LaTeX assets |
| `outputs/` | Job candidates, applications, briefings, state |
| `.env` | API keys and secrets |

`config/schemas/` is system-owned. Updates never replace user choices.
Deterministic location catalogs and matching logic are package resources under
`job_hunter/`; they are not copied into a workspace config directory.
Filter definitions, matching logic, industries, and languages are package
resources too. `config/job_hunter.yml` stores only selected scalar values; no
per-filter files or per-filter schemas are created in a workspace.

`config/career_pages.yml` is retired: the bundled company catalog is now a package
resource (`job_hunter/companies/data/*.jsonl`) imported into `outputs/state/companies.db`,
a regenerable runtime cache — not user data, not git-synced (unlike `outputs/state/jobs.db`).
Your own company targets live in `config/job_hunter.yml`'s `companies.targets` and are
mirrored into that store. `job-hunter doctor` migrates an existing `career_pages.yml`
into `companies.targets` once, then removes it (backup: `outputs/state/config_backups/career_pages.yml.bak`).

## System Layer — replaced by updates

| Path | What it holds |
|---|---|
| `job_hunter/` | Python package |
| `tests/` | Test suite |
| `.claude/skills/` | Agent skills |
| `.github/` | Workflows and automation |
| `config/schemas/` | Config validation schemas |
| `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE` | Docs |
| `pyproject.toml` | Package metadata |
| `DATA_CONTRACT.md` | This file |

## How updates work

`job-hunter update` runs three steps:

1. **Workspace assets** — controlled by `_UPDATE_ASSETS` in `job_hunter/workspace/assets.py`:
   - Non-YAML files (for example `README.md` and `SETUP.md`): always replaced.
   - `config/job_hunter.yml` remains fully user-owned. Legacy location values are
     adapted only in memory; neither update nor doctor rewrites them. Doctor
     schema-validates `config/job_hunter.yml` and migrates a leftover
     `config/career_pages.yml` into it (once), removing the retired file.
2. **Skills** — replaces `.claude/skills/` and the mirrored agent CLI trees.
3. **Workflows** — replaces `.github/`. Your cron schedule in `find-jobs.yml` is preserved.

See [docs/workspace-updates.md](docs/workspace-updates.md) for exactly
which files each step touches.
