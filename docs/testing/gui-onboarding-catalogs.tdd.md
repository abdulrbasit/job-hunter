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
| `career_stage` is accepted as an additive config field | `tests/test_gui_onboarding_catalogs_journeys.py::test_career_stage_not_yet_accepted_by_config_schema` | RED |
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

GREEN evidence: recorded per phase as each target lands (Phase 1: career_stage;
Phase 2: catalog; Phase 3: bootstrap; Phase 5: hunt service; Phase 6: terminal
removal; Phase 7/8: diagnostics self-test).

## Final validation (Phase 0 baseline)

- `.venv/Scripts/python.exe -m pytest tests/ -q --tb=short`: 1311 passed
  (pre-existing suite, unchanged) + 6 new journey tests failing as expected
  (1317 total, 6 failed — all six are this doc's planned RED tests).
- Ruff format/check and `ty check`: run as part of `/commit` preflight before
  the Phase 0 commit.
- No schema, version, or unrelated file changes in this phase.
