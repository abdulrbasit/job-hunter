# Contributing

## Setup

```bash
git clone https://github.com/abdulrbasit/job-hunter
cd job-hunter
uv sync --extra dev
```

## Repo map

```text
job_hunter/           Python package (installed as job-hunter-kit)
  cli/                Typer command definitions (composition root)
  config/             YAML loading, schema, secrets, path resolution
  pipeline/            Hunt/tailor orchestration and per-stage logic
  sources/             Job discovery: boards/, career_pages/, search/
  llm/                LLM client, typed stage service, response caching
  tracking/            Job/application state (outputs/state/jobs.db)
  workspace/           init/update, safety gating, template asset assembly
  ux/                  Terminal + web dashboard, analytics, health checks
  linkedin/            LinkedIn content generation (no auto-posting)
  agent_context/       Context objects consumed by Claude Code/Codex skills
  templates/workspace/ Bundled workspace template — see below
.claude/skills/        Claude Code skills (mirrored to .agents/skills/ for Codex)
config/                Dev-repo's own job_hunter.yml + schemas/
tests/                 Test suite (see docs/testing.md)
docs/                  Deep-dive reference docs, linked from README.md
scripts/               Dev-only tooling (not shipped in the package)
```

Full module ownership and package boundaries: [docs/architecture.md](docs/architecture.md).

`job_hunter/templates/workspace/` is what `job-hunter init` copies into a
new user workspace. `CLAUDE.md`, `GEMINI.md`, `config/`, and every
user-facing skill under `.claude/skills/` there are synced from this
repo's root by `scripts/sync_workspace_template.py` — edit the root copy
(or root `.claude/skills/<name>/`), then run the script. Exception:
`config/job_hunter.yml` is never synced (the template ships a blank
example, the root copy is this maintainer's personal config). Everything
else under `templates/workspace/` (`SETUP.md`, `SETUP_AGENT.md`,
`SETUP_LLM_API.md`, `.env.example`, `profile/`, `.github/workflows/*.yml`,
`outputs/`) has no root counterpart and is edited directly in place.

## Checks

All must pass before a PR:

```bash
uv run pytest tests/ -q --tb=short
uv run ruff format --check job_hunter tests scripts
uv run ruff check job_hunter tests scripts
uv run ty check job_hunter tests
```

See [docs/testing.md](docs/testing.md) for what the test suite enforces
(no live network calls, coverage gate, package-boundary rules) and how to
use the shared fixtures in `tests/conftest.py`.

If you changed `CLAUDE.md`, `GEMINI.md`, root `config/`, or a user-facing skill:

```bash
python scripts/sync_workspace_template.py
```

Starter profile and resume templates are maintained directly in
`job_hunter/templates/workspace/profile/`. Keep `examples/profile/` aligned
with reusable layout changes, while preserving its fictional example content.

## Adding a job source adapter

See [docs/sources.md](docs/sources.md#adding-a-new-job-board-adapter) for
the full steps: implement `JobSourceAdapter` under `sources/boards/`,
register it in `sources/boards/registry.py::BOARD_REGISTRY`, add a
fixture-based test, and register any new secret in
`config/defaults.py::SECRET_ENV_VARS` plus `.env.example`.

## Adding Config Keys or Workspace Files

`_UPDATE_ASSETS` in `job_hunter/workspace/assets.py` controls what
`job-hunter update` refreshes. See [docs/workspace-updates.md](docs/workspace-updates.md)
for exactly how that update runs.

- **Non-YAML files** — always overwritten (e.g. `SETUP.md`, `README.md`).
- **YAML config files** (`config/job_hunter.yml`, `config/career_pages.yml`) — fully user-owned.
  Update only writes them if missing; an existing file is never read or rewritten.

To add a new config key: add it to `config/schemas/job_hunter.schema.json`
with a default in the template YAML — see [docs/config.md](docs/config.md#adding-a-new-config-key).
Existing users only pick it up automatically if it falls under a runtime-merged
default section (`llm`, `linkedin`, `tailoring`, `cover_letter`,
`scoring.prompt_context` — see `job_hunter/config/loader.py::get_job_hunter_config`).
Anything else requires the user to add the key by hand; `job-hunter doctor` flags
what's missing against the schema.

## Commits

One line, 72 chars max: `type(scope): description`

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

## Pull Requests

- One logical change per PR
- Rebase onto `main`, no merge commits
- Fill in the PR template

## Rules

- User-owned paths (`config/`, `profile/`, `outputs/`, `.env`) must not be touched by product updates. See `DATA_CONTRACT.md`.
- Mock external services in tests; no live network calls — enforced by an autouse fixture in `tests/conftest.py`.
- `config/schemas/` holds validation schemas — system-owned, not user-editable.

## Security

Report security issues privately. See `SECURITY.md`.
