# Data Contract

Product updates may replace system-owned files. They must never overwrite user data.

## User Layer — never modified by updates

| Path | What it holds |
|---|---|
| `config/*.yml` | Your settings: profile paths, regions, titles, scoring, LLM choices |
| `profile/` | Resume files, story bank, career context, LaTeX assets |
| `outputs/` | Job candidates, applications, briefings, state |
| `.env` | API keys and secrets |

`config/schemas/` is system-owned. The values inside `config/*.yml` are yours.

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

1. **Workspace assets** — controlled by `_UPDATE_ASSETS` in `job_hunter/workspace/_assets.py`:
   - Non-YAML files (for example `README.md` and `SETUP.md`): always replaced.
   - YAML config files: deep-merged — new template keys are added, your values are kept. Lists: your version wins.
2. **Skills** — replaces `.claude/skills/` and the mirrored agent CLI trees.
3. **Workflows** — replaces `.github/`. Your cron schedule in `find-jobs.yml` is preserved.
