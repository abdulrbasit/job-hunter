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

`job-hunter update` runs four steps:

0. **Bridge migration** (temporary, `job_hunter/workspace/bridge_migration.py`) —
   removes files obsoleted by the Phase 8-13 refactor if they're unmodified,
   preserves them with a warning if you edited them, and carries forward the
   `config/companies_browser.yml` → `config/career_pages.yml` rename. Run
   `job-hunter update --dry-run` to preview this step only. This step is
   removed once all known workspaces have upgraded past it.
1. **Workspace assets** — controlled by `_UPDATE_ASSETS` in `job_hunter/workspace/assets.py`:
   - Non-YAML files (for example `README.md` and `SETUP.md`): always replaced.
   - YAML config files: deep-merged — new template keys are added, your values are kept. Lists: your version wins.
2. **Skills** — replaces `.claude/skills/` and the mirrored agent CLI trees.
3. **Workflows** — replaces `.github/`. Your cron schedule in `find-jobs.yml` is preserved.

See [docs/workspace-updates.md](docs/workspace-updates.md) for exactly
which files each step touches.

## Example: config deep-merge

A new package release adds a `scoring.strategic_overrides` key with a
template default of `[]`. Your existing `config/job_hunter.yml`:

```yaml
scoring:
  min_fit_score: 75
  batch_size: 10
```

After `job-hunter update`:

```yaml
scoring:
  min_fit_score: 75      # your value, kept
  batch_size: 10          # your value, kept
  strategic_overrides: [] # new key, added
```

If you had already set `strategic_overrides` yourself, your list would
have been kept as-is instead of overwritten.
