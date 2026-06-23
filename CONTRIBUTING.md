# Contributing

Thanks for helping make Job Hunter easier to install, run, and maintain.

## Development Setup

```bash
uv sync --extra dev
uv run pytest tests/ -q --tb=short
uv run ruff format --check job_hunter tests .github/scripts
uv run ruff check job_hunter tests .github/scripts
uv run ty check job_hunter tests
```

## Project Rules

- Keep `config/job_hunter.yml` as the only durable user config file.
- Keep persistent URL dedup in `outputs/state/discovered_urls.yml`.
- Do not add runtime dependencies on deleted legacy files such as `search_config.yml`, `api_config.yml`, or `processed_jobs.yml`.
- Treat root `.claude/`, `docs/`, `config/`, and `profile/template-files/` as canonical workspace asset sources.
- Mock external services in tests; do not require live network calls for the default suite.

## Pull Requests

Small, focused changes are easiest to review. Include tests for user-visible behavior, config/state contract changes, and source adapters touched by the change.
