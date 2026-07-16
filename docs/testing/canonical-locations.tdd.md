# Canonical locations — TDD evidence

## Source and journeys

Requirements came from the Canonical Location Allowlist implementation plan and
its package-ownership correction. Guarantees cover package-owned reference data,
canonical config loading, fail-closed discovery/screening/company hunt, legacy
read compatibility, and country-scoped dashboard payloads.

## RED / GREEN evidence

- RED: focused location tests initially failed because canonical location
  models, package resources, resolution, gates, and dashboard APIs did not exist.
- GREEN: `python -m pytest tests/test_locations.py ...` passed the focused
  location and integration matrix.
- GREEN: `python -m pytest tests/ -q --tb=short` passed 1,461 tests.
- Coverage: full-suite instrumentation reported 86.35%, above the repository's
  80% threshold. One five-second thread join timed out only under coverage
  overhead; the timeout was widened for that test and its instrumented rerun
  passed.
- Phase 3 RED: a source adapter test failed because `SearchParams` did not yet
  expose canonical location context; the catalog contract test failed before
  typed company evidence existed.
- Phase 3 GREEN: source parameters now carry `Location`, browser-hunt jobs gain
  canonical evidence before screening, and catalog company matching consumes
  typed evidence through the shared matcher.

## Test specification

| Guarantee | Evidence |
|---|---|
| All 249 ISO countries and requested-country cities load from wheel resources | `tests/test_locations.py::test_dashboard_serves_all_countries_and_only_requested_country_cities`; wheel resource check |
| Munich/München share one ID; runtime matching never fuzzes | `test_config_resolution_canonicalizes_munich_aliases`; `test_runtime_resolution_is_exact_not_fuzzy` |
| Munich + Berlin excludes Stuttgart | `test_munich_and_berlin_scopes_do_not_match_stuttgart` |
| Legacy text canonicalizes in memory without rewriting user YAML | `test_legacy_region_is_canonicalized_in_memory_and_warns` |
| Discovery skips unsupported country sources and rejects disabled cities | `test_orchestrator_rejects_disabled_city_and_skips_unsupported_country_source` |
| Screening rejects unknown/out-of-scope evidence | `test_screening_fails_closed_for_disabled_city_and_unknown_location` |
| Company candidates and extracted jobs obey city scopes before insertion | `test_company_hunt_candidate_requires_enabled_city_metadata`; `tests/test_browser_hunt.py::test_browser_hunt_rejects_extracted_job_outside_enabled_city` |
| Dashboard auto-detects legacy active regions and fetches cities per country | `test_dashboard_detects_legacy_region_as_active_package_city`; requested-country payload test |
| Init creates no workspace location dataset | `tests/test_workspace_init.py::test_init_creates_complete_workspace_from_package_template` |

## Remaining work

Phase 4 will measure and optimize cold imports, per-country loads, lookup/gate
throughput, and dashboard payload sizes. Existing `career_pages.yml` retirement
belongs to its separate ownership migration; this phase does not add or migrate
company config.
