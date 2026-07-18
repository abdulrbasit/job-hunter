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

## Performance evidence

`uv run python scripts/benchmark_startup_discovery.py` on 2026-07-18 measured:

- Startup calls for DE/US/FR: 7 before run-once dispatch, 3 after (57.1% fewer).
- 30,000-row company-type feed: 6.631 ms without the composite index, 4.505 ms with it (32.1% faster).
- 4,000-post fuzzy dedup: 77.885 ms global scan versus 44.050 ms company-bucketed (43.4% faster).
- 50,000 URL normalizations: 294.307 ms, producing 10,000 canonical identities.
- SQLite inspection confirms a unique index whose sole column is `canonical_url`.
  The redundant non-unique index on the same column was removed.

Figures are synthetic medians except the one-run 4,000-post global scan. They guard relative hot-path behavior, not production latency promises.
