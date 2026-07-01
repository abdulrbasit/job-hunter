# Agent telemetry TDD evidence

## Journeys

- A Claude Code or Codex user runs `/job-hunter` normally and can compare token use by mode, phase, and job.
- An LLM API user gets the same normalized role totals without changing provider execution.
- Workspace setup enables telemetry without replacing unrelated user OTel configuration.

## Evidence

| Guarantee | Test | Result |
|---|---|---|
| Claude and Codex OTLP payloads normalize to common token fields | `tests/test_telemetry.py` | PASS |
| Prompt text and unknown raw fields are not retained | `tests/test_telemetry.py` | PASS |
| Phase/job totals roll up once and unfinished phases are interrupted | `tests/test_telemetry.py` | PASS |
| Setup is idempotent and preserves existing OTel config | `tests/test_telemetry_setup.py` | PASS |
| Agent outcomes and direct LLM role totals are recorded | `tests/test_telemetry.py`, `tests/test_pipeline_metrics.py` | PASS |
| Dashboard API exposes normalized analytics | `tests/test_web_api.py` | PASS |

RED evidence: focused tests initially failed on missing telemetry modules, collector,
workspace setup, direct-LLM normalization, outcome storage, and dashboard integration.
GREEN evidence: each focused target passed after its minimal implementation.

## Final validation

- `uv run pytest tests/ -q --tb=short`: 784 passed.
- `uv run pytest tests/ --cov=job_hunter ...`: 82.04%, above 80% gate.
- Ruff format/check and `ty check`: passed.
- Workspace template sync check: passed.
- `uv build`: source and wheel builds passed; wheel inspection confirmed all telemetry modules.
