# Contributing

## Setup

```bash
git clone https://github.com/abdulrbasit/job-hunter
cd job-hunter
uv sync --extra dev
```

## Checks

All must pass before a PR:

```bash
uv run pytest tests/ -q --tb=short
uv run ruff format --check job_hunter tests scripts
uv run ruff check job_hunter tests scripts
uv run ty check job_hunter tests
```

If you changed `SETUP.md`:

```bash
python scripts/sync_workspace_template.py
```

Starter profile and resume templates are maintained directly in
`job_hunter/templates/workspace/profile/`. Keep `examples/profile/` aligned
with reusable layout changes, while preserving its fictional example content.

## Commits

One line, 72 chars max: `type(scope): description`

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

## Pull Requests

- One logical change per PR
- Rebase onto `main`, no merge commits
- Fill in the PR template

## Rules

- User-owned paths (`config/`, `profile/`, `outputs/`, `.env`) must not be touched by product updates. See `DATA_CONTRACT.md`.
- Mock external services in tests; no live network calls.
- `config/schemas/` holds validation schemas — system-owned, not user-editable.

## Adding Config Keys or Workspace Files

`_UPDATE_ASSETS` in `job_hunter/workspace/_assets.py` controls what `job-hunter update` refreshes.

- **Non-YAML files** — always overwritten (e.g. `SETUP.md`, `README.md`).
- **YAML config files** — deep-merged: new keys from the template are added, existing user values are kept. Lists and scalars: user wins.

To add a new config key: add it with a default to the template YAML. Users get it on next `job-hunter update`.

## Security

Report security issues privately. See `SECURITY.md`.
