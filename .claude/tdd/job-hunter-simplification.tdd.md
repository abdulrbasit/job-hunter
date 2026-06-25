# Job Hunter simplification TDD evidence

## Source

Journeys and acceptance criteria came from the user-approved simplification plan.

## Journeys

- New user installs base package, initializes workspace, runs doctor, and starts agent-mode hunt.
- Autonomous user installs `llm` extra and runs same workflow in `llm-api` mode.
- Normal users see only stable public commands.
- Bundled skills retain deterministic support commands under hidden `internal` group.
- Worldwide source coverage remains represented by global and regional adapters.

## RED/GREEN

| Change | RED evidence | GREEN evidence |
|---|---|---|
| Public/internal CLI contract | Commit `4b25ce3`; focused run reported 14 intended failures | `tests/test_cli.py` and full suite pass |
| Optional LLM SDK guidance | Commit `ecb2a11`; 3 provider cases failed on old install messages | `tests/test_llm_client.py` passes |
| Mode-aware doctor/schema validation | Commit `7c83ba2`; 3 intended doctor failures | `tests/test_health.py` passes |
| Worldwide adapter contract | Added shared registry, geography, and signature checks | `tests/test_source_contracts.py` passes |

## Final guarantees

| Guarantee | Evidence |
|---|---|
| Nine public command groups; support commands hidden under `internal` | `python -m job_hunter.cli --help`; `internal --help` |
| Agent mode does not require Docker; `llm-api` checks Docker and provider SDK | `tests/test_health.py` |
| Config schema validation runs through doctor | `tests/test_health.py` |
| LLM SDKs are optional package dependencies | `tests/test_packaging.py` |
| Workspace template includes Python 3.12 setup, skills, workflows, and schema | `tests/test_workspace_init.py`; template sync check |
| Worldwide board registry remains intact | `tests/test_source_contracts.py` |
| Business-logic coverage gate is enforced | `642 passed`; `80.02%` coverage |

## Validation

- `python -m pytest tests/ -q --cov --cov-report=term` — 642 passed, 80.02%.
- `python -m ruff format --check job_hunter tests scripts` — pass.
- `python -m ruff check job_hunter tests scripts` — pass.
- `python -m ty check job_hunter tests` — pass.
- `python scripts/validate_config.py` — pass.
- `python scripts/sync_workspace_template.py --check` — pass.
- `python -m uv build` — wheel and sdist built.

## Coverage boundary

Coverage excludes subprocess-tested CLI registration and optional browser rendering glue. Their behavior is checked through CLI journey tests and mocked integration tests.
