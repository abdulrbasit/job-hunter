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

All four checks must pass before a PR:

```bash
uv run pytest tests/ -q --tb=short
uv run ruff format --check job_hunter tests .github/scripts
uv run ruff check job_hunter tests .github/scripts
uv run ty check job_hunter tests
```

## Project Rules

- `config/job_hunter.yml` is the only durable user config file. Do not add new config files.
- `outputs/state/discovered_urls.yml` is the persistent URL dedup store.
- Treat `.claude/`, `config/`, and `profile/template-files/` as canonical workspace asset sources.
- Mock external services in tests; no live network calls in the default suite.
- Product updates must not touch user-owned paths. See `DATA_CONTRACT.md`.

## Pull Requests

Small, focused changes are easiest to review. Include tests for user-visible behavior, config/state contract changes, and any source adapter touched. Describe the motivation in the PR description.

## Security

Report security issues privately. See `SECURITY.md`.
