# Testing

## Running tests

```bash
uv sync --extra dev
uv run pytest tests/ -q --tb=short
```

Coverage gate: `fail_under = 80` (`pyproject.toml`'s `[tool.coverage.report]`),
scoped to `job_hunter/` minus `job_hunter/cli/*` and
`job_hunter/sources/career_pages/_rendering.py`.

## No live network calls — enforced, not just a convention

`tests/conftest.py::_block_live_network` is an autouse fixture that
monkeypatches `socket.socket.connect` for every test. Any attempt to
connect to a non-loopback address raises immediately:

```text
blocked live network connect() to (...) during tests — mock the HTTP/network call instead
```

Mock the HTTP layer (`requests`/`httpx`/`playwright` calls) with
`unittest.mock`, not by hitting the real service.

## Test fixtures already set up for you

`conftest.py` also, at import time (before any test module loads):

- Sets placeholder `ANTHROPIC_API_KEY`/`BRAVE_API_KEY`/`RAPIDAPI_KEY` env
  vars — `job_hunter/config/secrets.py` reads these lazily at module level,
  so tests never need a real key.
- Builds an isolated temp workspace (`runtime_root`) with a minimal valid
  `config/job_hunter.yml` and empty profile files, and points
  `JOB_HUNTER_ROOT` at it — so `repo_path()` resolves to a throwaway
  directory, never your real dev checkout.
- `mock_llm_client(text)` fixture — factory returning a `MagicMock` whose
  `.complete()` returns `text`. Use this instead of hitting a real
  provider SDK.
- `_clear_llm_cache` (autouse) — resets `llm/client.py`'s response cache
  between tests so one test's mocked response can't leak into the next.
- `mk_params(job_titles, regions, ...)` — builds a `SearchParams` object
  from the legacy `(job_titles, regions)` shape adapter tests still use.

## Linting and types

```bash
uv run ruff format --check job_hunter tests scripts
uv run ruff check job_hunter tests scripts
uv run ty check job_hunter tests
```

Package-boundary rules are enforced by ruff's `flake8-tidy-imports`
banned-api list in `pyproject.toml` (`sources/` can't import `pipeline/`,
nothing can import `cli/` or `ux/` except their own package — see
`ARCHITECTURE.md` §1) and by `tests/test_dependency_boundaries.py`.

`ty` is strict (`error`, not `ignore`) only for `job_hunter/models.py` and
`job_hunter/config/**` (`[[tool.ty.overrides]]` in `pyproject.toml`);
everywhere else its rules are relaxed project-wide defaults — this is a
deliberate, incremental strictness rollout, not a blanket exemption.

## Packaging checks

```bash
uv build
```

`tests/test_packaging.py` guards two recurring failure modes: a
package-data glob that matches nothing (stale/typo'd entry) and a
user-facing file (skill directory or top-level workspace doc) that exists
in the template but is missing from package-data — invisible in an
editable install, silently dropped from a real wheel install. If you add a
new top-level file under `job_hunter/templates/workspace/` that
`job-hunter init`/`update` should ship, add it to package-data in the same
change.

## Adding a source adapter test

New job-board adapters need a fixture-based test
(`tests/test_<name>_source.py`) that mocks the HTTP response and asserts
on the parsed `JobPosting` list — see any existing `test_*_source.py` for
the pattern, and `test_source_contracts.py` for the shared-contract check
every adapter must pass.
