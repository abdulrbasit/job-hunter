# Data Contract

Two layers. Product updates may replace system-owned files; they must never overwrite user job-search data.

## User Layer

Automated product updates must not modify these paths:

| Path | Purpose |
|---|---|
| `config/*.yml` | Deterministic machine choices: profile paths, search regions, exclusions, scoring thresholds, LLM search gate, provider/model choices, mode |
| `profile/` | Resume sources, story bank, career and writing context, LaTeX assets, optional profile photo |
| `outputs/` | Candidates, jobs, applications tracker, briefings, state |
| `.env` | Local secrets and provider keys |

Config schemas under `config/schemas/` are system-owned; live config values are user-owned.

## System Layer

Product updates may replace these paths:

| Path | Purpose |
|---|---|
| `job_hunter/` | Python package and deterministic automation |
| `tests/` | Product test suite |
| `.claude/skills/` | Agent workflow instructions |
| `.github/workflows/`, `.github/scripts/`, `.github/ISSUE_TEMPLATE/` | Product automation |
| `config/schemas/` | Validation schemas for user config |
| `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE` | Product documentation |
| `pyproject.toml` | Package metadata and dependencies |
| `DATA_CONTRACT.md` | This contract |

## Rule

If a file is user-owned, update tooling may read it for migration checks but must
not overwrite or delete it as part of a product update.

Installed workspaces currently expose only one package-to-workspace update path:
`job-hunter update-skills`, which writes `.claude/skills/` and nothing else.
Config migration is intentionally deferred until it is designed as a separate,
explicit feature.
