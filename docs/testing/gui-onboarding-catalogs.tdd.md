# GUI onboarding + catalogs TDD evidence

## Acceptance metrics (spec exit criteria, checked at later-phase gates)

- At most 5 app actions from workspace creation to first hunt, excluding AI
  conversation, file chooser, and API-key entry.
- Returning user: launch app, one click for a normal hunt.
- Company Hunt: one separate click.
- No terminal required after desktop installation.
- Existing application streaks and milestones still work
  (`job_hunter/tracking/repository.py`, `job_hunter/ux/web/api.py`).

## Journeys

- Onboarding: a new user creates a workspace, completes one compact search
  setup + one AI-guided profile session, and reaches "Start First Hunt"
  without touching a terminal or YAML.
- Career-stage filtering: `career_stage` (student/early_career/experienced/
  leadership/custom) ranks and excludes jobs correctly, while existing
  configs missing the key keep behaving exactly as before via `custom`.
- Catalog company selection: a returning user's Company Hunt automatically
  uses a region-matched, package-owned catalog merged with their custom
  `career_pages.yml` entries.
- Daily hunt: a returning user opens Today and clicks Find Jobs once; a
  typed run service reports status without a terminal dashboard.
- Terminal removal: no terminal UI module, command, or user-facing daily
  command remains; hidden automation/agent/CI contracts still work.
- Packaged launch: a frozen desktop build launches, self-tests its bundled
  resources/catalog/workspace/config/DB, and needs no terminal step.

## Evidence

| Guarantee | Test | Result |
|---|---|---|
| `DashAPI.get_bootstrap` exists for the Get Started page | `tests/test_gui_onboarding_catalogs_journeys.py::test_onboarding_bootstrap_api_not_yet_built` | RED |
| `career_stage` is accepted as an additive config field | `tests/test_gui_onboarding_catalogs_journeys.py::test_career_stage_not_yet_accepted_by_config_schema` | PASS |
| All 249 ISO 3166-1 countries load with unique codes | `tests/test_reference_data.py::test_all_249_countries_load`, `::test_country_codes_are_unique_two_letter_codes` | PASS |
| Missing/`custom` `career_stage` preserves old `exclusions.title_terms` behavior exactly | `tests/test_reference_data.py::test_missing_career_stage_key_resolves_to_custom_and_preserves_user_terms`, `::test_custom_career_stage_disables_system_exclusions`, `::test_custom_career_stage_preserves_legacy_max_years_fallback` | PASS |
| Each career_stage hard-excludes its reviewed hard-filter title terms | `tests/test_reference_data.py::test_student_stage_excludes_senior_titles`, `::test_experienced_stage_excludes_internship_and_junior_titles`, `::test_leadership_stage_excludes_early_career_titles` | PASS |
| User excludes are additive with career_stage excludes, deduped | `tests/test_reference_data.py::test_user_title_terms_are_additive_with_stage_excludes`, `::test_stage_and_user_excludes_are_deduped` | PASS |
| Excludes are word-boundary matched, not substring false positives | `tests/test_reference_data.py::test_student_exclude_does_not_match_substring_false_positive`, `::test_experienced_exclude_does_not_match_partial_word` | PASS |
| Default experience caps per stage (student 1 / early_career 3 / experienced 8 / leadership uncapped), explicit override always wins | `tests/test_reference_data.py::test_student_default_max_years_is_one`, `::test_early_career_default_max_years_is_three`, `::test_experienced_default_max_years_is_eight`, `::test_leadership_has_no_years_cap`, `::test_explicit_max_years_override_wins_over_career_stage` | PASS |
| Preferred (soft-ranking) terms exist per stage without becoming mandatory | `tests/test_reference_data.py::test_student_preferred_terms_include_internship_signals`, `::test_leadership_preferred_terms_include_director_signals`, `::test_custom_stage_has_no_preferred_terms` | PASS |
| `job_hunter.catalog.load_companies` loads the bundled company catalog | `tests/test_gui_onboarding_catalogs_journeys.py::test_catalog_company_selection_package_not_yet_built` | RED |
| `DashAPI.start_hunt`/`get_hunt_status` typed run service exists | `tests/test_gui_onboarding_catalogs_journeys.py::test_daily_hunt_typed_service_not_yet_built` | RED |
| `job_hunter.ux.terminal` is removed | `tests/test_gui_onboarding_catalogs_journeys.py::test_terminal_ux_not_yet_removed` | RED |
| `job_hunter.diagnostics.self_test` exists for frozen-build smoke checks | `tests/test_gui_onboarding_catalogs_journeys.py::test_packaged_launch_self_test_not_yet_built` | RED |

RED evidence: all six focused tests fail today for the planned reason only —
`get_bootstrap`/`start_hunt`/`get_hunt_status` are missing from `DashAPI`
(`job_hunter/ux/web/api.py`), the config schema's `additionalProperties: false`
rejects `career_stage` (`job_hunter/templates/workspace/config/schemas/job_hunter.schema.json`),
`job_hunter.catalog` and `job_hunter.diagnostics` don't exist yet, and
`job_hunter/ux/terminal/` still exists (correct — it's removed at Phase 6,
not Phase 0). No import errors, typos, or unrelated failures.

GREEN evidence:

- Phase 1 (career_stage + countries/filters catalogs): landed. `countries.json`
  built from the canonical ISO 3166-1 alpha-2 list (lukes/ISO-3166-Countries-with-Regional-Codes)
  cross-referenced with mledoze/countries for language codes; `filters.json`
  migrates the existing `LANGUAGE_INDICATORS` dict (`job_hunter/config/defaults.py`)
  verbatim rather than re-authoring translations, and adds hand-authored
  `career_stages`/`employment_types`/`industries` sections. `career_stage`
  added to both schema copies (additive, `additionalProperties: false` still
  holds for every other key). `job_hunter/config/reference_data.py` loads and
  Pydantic-validates both files and resolves `exclusions.title_terms` and
  `scoring.max_years_experience_required` from the active stage, wired into
  `job_hunter/sources/policy.py` (`JobPolicy.excluded_title_terms`),
  `job_hunter/sources/orchestrator.py`, `job_hunter/pipeline/runner.py`, and
  `job_hunter/pipeline/stages/scoring.py` (all four previously read
  `exclusions.title_terms` / `max_years_experience_required` directly).
  Deferred: `preferred_title_terms()` is implemented and tested in isolation
  but not yet wired into a ranking/sort call site — there is no results list
  to rank against until the Phase 4 Candidates UI exists (see `ponytail:`
  comment in `reference_data.py`). Deferred: `LANGUAGE_INDICATORS` still lives
  in `job_hunter/config/defaults.py` as well as `filters.json` (spec allows
  removing the Python copy "after parity tests pass" — not done this phase to
  avoid an unreviewed behavior change to `job_hunter/sources/policy.py`'s
  existing language-exclusion runtime path).
- Phase 2 (catalog), Phase 3 (bootstrap), Phase 5 (hunt service), Phase 6
  (terminal removal), Phase 7/8 (diagnostics self-test): not started; their
  RED tests still fail in `tests/test_gui_onboarding_catalogs_journeys.py`.

## Final validation

- Phase 0: `pytest tests/ -q --tb=short` — 1311 passed (pre-existing,
  unchanged) + 6 new journey tests failing as planned (1317 total, 6 failed).
- Phase 1: `pytest tests/ -q --tb=short` — 1337 passed, 5 failed (the
  remaining Phase 2/3/5/6/7 RED journeys; `career_stage` journey now passes).
  `ruff format --check`, `ruff check`, `ty check`, `scripts/validate_config.py`,
  `scripts/sync_workspace_template.py --check`, and `uv build --wheel` all
  passed; wheel inspection confirmed `job_hunter/config/countries.json` and
  `job_hunter/config/filters.json` are packaged.
- No version bump.
