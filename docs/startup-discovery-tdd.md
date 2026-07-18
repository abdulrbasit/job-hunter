# Startup discovery TDD evidence

Source plan: user-provided Startup Discovery implementation plan.

## Journeys

- A hunter can opt into bounded startup sources and package companies with one config choice.
- Startup/company metadata remains visible through discovery, persistence, and dashboard filters.
- Experience-ambiguous startup jobs fail open with an explicit `experience_unknown` signal.
- Cross-source duplicates collapse by canonical URL, then by title only within one normalized company.
- Maintainers can import validated startup lists into package shards without touching a user workspace.

## Evidence

| Guarantee | Test/evidence | Result |
|---|---|---|
| Missing startup contracts fail before production code | `uv run pytest tests/test_startup_discovery.py -q --tb=short` | RED: `ModuleNotFoundError: job_hunter.companies.classification` |
| Typed metadata, classification, adapters, toggle, persistence, UI, importer, and dedup | `tests/test_startup_discovery.py` | PASS |
| Existing source, company, location, and repository behavior remains compatible | Full `tests/` suite | 1,621 passed |
| Changed modules meet coverage target | Full suite with targeted `--cov` modules | 89.02% total; each changed module 82–100% |
| Formatting, lint, and types remain valid | Ruff format/check and `ty check` | PASS |

RED checkpoint: `9275f72 test: define startup discovery behavior (phase 1/4 red)`.

No live network calls run in tests. Adapter behavior uses offline RSS/HTML fixtures. Public endpoint and terms checks were performed separately during source research.
