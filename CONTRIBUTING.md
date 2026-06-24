# Contributing

Contributions to Job Hunter are welcome. This guide covers the development workflow.

## Types of Contributions

- Bug fixes and reliability improvements
- New job source adapters (`job_hunter/sources/`)
- LLM provider integrations (`job_hunter/llm/`)
- Documentation improvements
- Test coverage for existing behavior

## Development Setup

```bash
git clone https://github.com/abdulrbasit/job-hunter
cd job-hunter
uv sync --extra dev
```

## Running Checks

All four checks must pass before a PR. The PR template checklist reminds you, but run them locally first:

```bash
uv run pytest tests/ -q --tb=short
uv run ruff format --check job_hunter tests scripts
uv run ruff check job_hunter tests scripts
uv run ty check job_hunter tests
```

If you changed `SETUP.md`, also run:

```bash
python scripts/sync_workspace_template.py
```

This keeps the bundled workspace template copy in sync. The CI build will fail if it drifts.

## Commit Style

One line, 72 characters or fewer. Format: `type(scope): description`

Common types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

No body, no bullet points, no `Co-authored-by` trailers.

## Pull Requests

- One logical change per PR — easier to review and revert if needed
- Rebase onto `main` before opening; no merge commits
- Fill in the PR template — motivation matters more than a list of files changed
- Small PRs land faster than large ones

## Project Rules

- `config/job_hunter.yml` stores the main deterministic user settings.
- `config/companies_browser.yml` stores optional browser-hunt company targets.
- `outputs/state/discovered_urls.yml` is the persistent URL dedup store.
- Treat `.claude/`, `config/`, and `profile/template-files/` as canonical workspace asset sources.
- Mock external services in tests; no live network calls in the default suite.
- Product updates must not touch user-owned paths. See `DATA_CONTRACT.md`.

## Code Ownership

Key paths have required reviewers defined in `.github/CODEOWNERS`. PRs touching the workspace template, data contract, CI workflows, or `pyproject.toml` will automatically request a maintainer review.

## Security

Report security issues privately — do not open a public issue. See `SECURITY.md`.
