# Package-owned filters — TDD evidence

## Journeys

- A workspace owner edits filter choices only in `config/job_hunter.yml`.
- Discovery and screening bind those choices to package-owned matching rules.
- Dashboard users select package industries and hunt languages without editing
  taxonomies or matching logic.
- Existing nested filter groups continue working in memory without an automatic
  rewrite.

## RED / GREEN evidence

- RED: `tests/test_filter_registry.py` failed collection with
  `ModuleNotFoundError: No module named 'job_hunter.filters'`.
- GREEN: package registry unit tests pass after adding typed definitions,
  scalar binding, taxonomy expansion, and legacy in-memory canonicalization.

## Test specification

| Guarantee | Evidence |
|---|---|
| Four known types and their modes are package-owned | `test_package_registry_defines_known_filter_types_and_modes` |
| Scalar choices drive company/title/industry/language behavior | `test_scalar_choices_bind_to_package_matching_logic` |
| Legacy nested groups canonicalize without mutating input | `test_legacy_nested_groups_canonicalize_in_memory_without_mutating_input` |
| Unknown types and taxonomy values fail config validation | `tests/test_config_service.py` |
| Init writes no filter schema or filter files | `tests/test_workspace_init.py` |
| Dashboard options come from package taxonomies | `tests/test_web_api.py::test_get_filter_options_uses_package_taxonomies` |

## Phase 1 validation

- Full suite: 1,468 passed.
- Coverage: 86.55% (required: 80%).
- Ruff format, Ruff lint, and `ty check`: passed.
- Dependency boundaries, diagnostics, workspace init, and migration: 51 passed.
- Source and wheel builds: passed.
- Workspace template synchronization: clean.
- Root `config/job_hunter.yml`: unchanged.

## Phase 2 validation

- Simplification: removed the duplicate `FilterSet.choices` representation;
  bound filters retain user choices and expand package taxonomy terms internally.
- Full suite: 1,468 passed; coverage: 86.55%.
- Focused filter/policy/agent checks: 65 passed.
- Ruff format, Ruff lint, and `ty check`: passed.
