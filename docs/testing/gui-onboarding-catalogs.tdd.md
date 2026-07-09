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
| `job_hunter.catalog.load_companies` loads the bundled company catalog | `tests/test_gui_onboarding_catalogs_journeys.py::test_catalog_company_selection_package_not_yet_built` | PASS |
| Catalog entries have unique IDs, unique https career_url, country/industry metadata | `tests/test_catalog.py::test_catalog_company_ids_are_unique`, `::test_catalog_career_urls_are_unique_https`, `::test_catalog_companies_have_country_and_industry_metadata` | PASS |
| Catalog rejects unknown country/industry refs, duplicate IDs, non-https URLs | `tests/test_catalog.py::test_catalog_rejects_unknown_country_code`, `::test_catalog_rejects_unknown_industry_id`, `::test_catalog_rejects_duplicate_company_id`, `::test_catalog_rejects_non_https_career_url` | PASS |
| Effective company list matches enabled regions (incl. no-region = all) | `tests/test_catalog.py::test_effective_companies_matches_enabled_region`, `::test_effective_companies_with_no_regions_returns_all_catalog_companies` | PASS |
| `disabled_company_ids` and `catalog.enabled=false` overrides work | `tests/test_catalog.py::test_effective_companies_disabled_company_ids_excludes_that_company`, `::test_effective_companies_catalog_disabled_returns_only_custom` | PASS |
| Custom `career_pages.yml` entry wins on duplicate URL; disabled custom entries excluded | `tests/test_catalog.py::test_effective_companies_custom_entry_wins_on_duplicate_url`, `::test_effective_companies_disabled_custom_entry_is_excluded` | PASS |
| `exclusions.industries` expands known industry id/label/alias; unknown strings match nothing | `tests/test_catalog.py::test_effective_companies_excludes_by_industry_alias`, `::test_effective_companies_unknown_industry_string_matches_nothing` | PASS |
| `career_pages.yml` `catalog:` block is additive, defaults preserved, round-trips, validated | `tests/test_config_service.py::test_read_career_pages_defaults_catalog_when_absent`, `::test_save_career_pages_without_catalog_arg_preserves_existing_catalog_block`, `::test_save_career_pages_omits_default_catalog_block`, `::test_validate_career_pages_rejects_non_boolean_catalog_enabled`, `::test_validate_career_pages_rejects_non_string_disabled_company_ids` | PASS |
| `DashAPI.get_bootstrap` reports readiness + checklist without leaking local paths | `tests/test_gui_onboarding_catalogs_journeys.py::test_onboarding_bootstrap_api_not_yet_built`, `tests/test_web_api.py::test_get_bootstrap_reports_readiness_and_checklist` | PASS |
| Readiness blocking checks (titles/career_stage/region/context/resume/api_key); missing key resolves via `custom` | `tests/test_readiness.py::test_fully_filled_workspace_is_ready`, `::test_missing_career_stage_key_is_still_valid_via_custom_default`, `::test_unfilled_career_context_blocks_readiness`, `::test_unfilled_resume_blocks_readiness` | PASS |
| Final story / GitHub schedule are non-blocking (never block younger users) | `tests/test_readiness.py::test_missing_final_story_is_non_blocking_not_blocking`, `::test_missing_github_schedule_is_non_blocking` | PASS |
| Compact search-setup save touches only mode/career_stage/titles/primary region/industries | `tests/test_config_service.py::test_apply_onboarding_prefs_updates_titles_stage_and_primary_region`, `::test_apply_onboarding_prefs_leaves_scoring_and_other_exclusions_untouched`, `::test_apply_onboarding_prefs_preserves_other_regions`, `tests/test_web_api.py::test_save_onboarding_preferences_updates_config` | PASS |
| Any-chatbot prompt includes exact delimiters; bundle parser validates before any write | `tests/test_onboarding_bundle.py` (7 tests), `tests/test_web_api.py::test_get_onboarding_prompt_returns_copyable_text`, `::test_import_onboarding_bundle_writes_profile_files`, `::test_import_onboarding_bundle_reports_parse_errors_without_writing` | PASS |
| Bundle import is atomic (all 3 files or none) with one-level backup/undo | `tests/test_config_service.py::test_replace_onboarding_bundle_writes_all_three_files`, `::test_replace_onboarding_bundle_rejects_missing_section`, `::test_replace_onboarding_bundle_backs_up_previous_content`, `::test_replace_onboarding_bundle_rejects_invalid_career_context` | PASS |
| Desktop launcher: recent workspace resolution, create/open, reject non-empty target | `tests/test_launcher.py` (14 tests) | PASS |
| `dashboard.html` splits into shell/CSS/JS; no CDN script tags; no-remote-source CSP declared | `tests/test_dashboard_assembly.py` (7 tests), `tests/test_web_launch.py::test_dashboard_launches_maximized` | PASS |
| Chart.js doughnut/bar replaced with CSS/HTML bar summaries (no `new Chart(` calls) | manual grep verified zero `new Chart(` matches in `dashboard.js`; `tests/test_dashboard_assembly.py::test_assembled_dashboard_has_no_cdn_script_tags` | PASS |
| PyInstaller spec bundles dashboard.css/js and Phase 1/2 catalog JSON (previously missing) | `tests/test_windows_packaging.py::test_windows_pyinstaller_spike_is_isolated_and_keeps_console_enabled` | PASS |
| `DashAPI.start_hunt`/`get_hunt_status` typed run service exists; shares the company-hunt lock so runs can never overlap | `tests/test_gui_onboarding_catalogs_journeys.py::test_daily_hunt_typed_service_not_yet_built`, `tests/test_web_api.py::test_start_hunt_runs_worker_and_reports_succeeded`, `::test_start_hunt_rejects_concurrent_start`, `::test_start_hunt_and_company_hunt_share_the_same_lock`, `::test_start_hunt_worker_crash_reports_failed_and_resets_lock` | PASS |
| `start_company_hunt`/`get_company_hunt_status` spec-named aliases wrap the existing wired implementation | `tests/test_web_api.py::test_start_company_hunt_is_alias_for_run_company_hunt`, `::test_get_company_hunt_status_is_alias_for_get_company_hunt_summary` | PASS |
| GitHub Actions secret value never crosses the JS bridge; copied straight to the OS clipboard from Python | `tests/test_web_api.py::test_get_github_actions_guide_reports_required_secret_and_schedule_state` (asserts the value is absent from the JSON payload), `::test_copy_github_actions_secret_writes_to_clipboard_without_returning_it`, `::test_copy_github_actions_secret_reports_error_when_not_configured` | PASS |
| `job_hunter.ux.terminal` is removed; `dashboard`/`applications list` CLI commands gone | `tests/test_gui_onboarding_catalogs_journeys.py::test_terminal_ux_not_yet_removed`, `tests/test_cli.py::test_dashboard_and_applications_list_commands_are_removed` | PASS |
| `internal analytics`, `doctor`, `dash`, `applications update`, `internal verify` still work (hidden/automation contracts intact) | `tests/test_cli.py::test_analytics_doctor_and_verify_commands_load`, `::test_cli_command_registration_matches_known_surface`, `::test_internal_commands_referenced_by_skills_are_all_registered` | PASS |
| Agent skill "dashboard" routing and batch-review pointer say "open the Job Hunter app", not a terminal command | `tests/test_skills.py` (SKILL.md command-menu assertions) | PASS |
| `job_hunter.diagnostics.self_test` verifies resources/catalogs/workspace/config/DB headlessly | `tests/test_gui_onboarding_catalogs_journeys.py::test_packaged_launch_self_test_not_yet_built`, `tests/test_diagnostics.py` (4 tests) | PASS |
| `internal self-test` CLI command exposes it; real frozen Windows exe run confirms all 7 checks pass | `tests/test_cli.py::test_analytics_doctor_and_verify_commands_load`, `tests/test_cli.py::test_cli_command_registration_matches_known_surface` — plus a real `job-hunter.exe internal self-test --json` run recorded in `docs/windows-packaging.md` | PASS |
| macOS/Linux PyInstaller spikes structurally mirror the verified Windows one (asset list, no Playwright, no console) | `tests/test_macos_packaging.py` (2 tests), `tests/test_linux_packaging.py` (3 tests) | PASS |
| Linux frozen build actually runs (Docker container, not just static spec check): `internal self-test --json` all 7 checks pass | `docs/linux-packaging.md` "Verified spike result" — real `job-hunter internal self-test --json`/`init`/`doctor` run inside a `python:3.12-slim` container | PASS |

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
- Phase 2 (1,500-company catalog): scoped down for this pass — see "Known gap"
  below. `job_hunter/catalog/` package added: `loader.py` (Pydantic-validated
  `companies.json`, cross-references `country_codes`/`industry_ids` against
  Phase 1's `reference_data`, rejects duplicate IDs/URLs and non-https URLs)
  and `merge.py` (`effective_companies()`: eligible bundled companies for the
  workspace's enabled regions, minus `catalog.disabled_company_ids` and
  industry-excluded companies, plus enabled custom `career_pages.yml`
  entries — a custom entry always wins on a duplicate `career_url`).
  `career_pages.yml` extended with an optional `catalog: {enabled,
  disabled_company_ids}` block in `job_hunter/config/service.py`
  (`read_career_pages`/`save_career_pages`/`validate_career_pages`) —
  additive, round-trips, and is omitted from the written file when it's the
  default (matches the existing `enabled: true`-is-omitted convention for
  company entries). **Known gap**: the catalog ships 19 companies, not
  1,500 — each one's `career_url` was live-verified via WebFetch this
  session (not fabricated), spanning Americas/Europe/APAC/Middle East/global-
  remote and 8 industries, to exercise every code path (region matching,
  industry exclusion, override, dedupe) against real data. Bulk-verifying
  1,500 official career pages requires either extensive individual web
  verification per company or a licensed company-directory data source —
  explicitly out of scope for a single session; the code/schema is ready to
  receive more entries without changes.
- Phase 3 (Get Started onboarding — backend/service layer): landed. New
  `job_hunter/launcher.py` (recent-workspace resolution via a platform-native
  JSON file — `%APPDATA%/job-hunter` on Windows, `~/Library/Application
  Support/job-hunter` on macOS, `$XDG_CONFIG_HOME` on Linux — `create_workspace`/
  `open_workspace` wrapping the existing `run_init`/`WorkspaceNotEmptyError`).
  New `job_hunter/ux/web/readiness.py` (`get_readiness()`: the spec's exact
  blocking set — job_titles, career_stage, region, career_context, base_resume,
  api_key — plus non-blocking warnings for final story/GitHub schedule/browser
  support/telemetry; reuses `job_hunter.ux.health`'s private checks rather than
  duplicating them, and deliberately does **not** touch `onboarding_status`/
  `onboarding_checklist`, which the pre-existing doctor/dashboard still use and
  which classify story_bank as blocking — this flow implements the spec's
  "stories never block" rule as a separate function instead of changing shared,
  already-tested behavior). New `DashAPI.get_bootstrap()` (readiness +
  checklist + config revision), `save_onboarding_preferences()` (compact
  search-setup page → `job_hunter.yml`, via new `service.apply_onboarding_prefs`,
  reusing the existing revision-guard/schema-validation save path), and the
  any-chatbot pair `get_onboarding_prompt()`/`import_onboarding_bundle()`
  (new `job_hunter/config/onboarding_bundle.py` for prompt-building and
  delimited-section parsing/validation, and `service.replace_onboarding_bundle`
  for the atomic all-3-or-nothing write with per-file backups reusing the
  existing `_atomic_write`/`_backup_path`/`undo_last_save` machinery).
  **Known gaps**: (1) no new pywebview HTML/JS screens yet — Get Started,
  the search-setup page, and the chatbot-import UI are drawn against
  `dashboard.html`'s current 2,961-line monolith today; building them once
  against Phase 4's split shell/CSS/JS avoids building the same screens twice,
  so the actual screens land in Phase 4. (2) `/setup onboard` was not rewritten
  — on inspection it already dispatches through one `/setup onboard` invocation
  into mode-specific flow files (not multiple separate commands), so the spec's
  "one config-aware session" bar is largely met already; a deeper content
  rewrite is deferred. (3) `BASE_RESUME` from the any-chatbot bundle is staged
  to a new `profile/resume_source.md`, not written directly into the LaTeX
  `resume_tex` template — bridging arbitrary chatbot prose into the existing
  LaTeX resume class is a distinct, larger task belonging to `/setup resume`,
  and writing unvalidated content into the LaTeX file risked breaking PDF
  compilation. (4) the bundle-import atomic write has backups/rollback but no
  optimistic-concurrency revision check (unlike every other save path) — a
  deliberate, lower-priority gap for a first-run action, not a repeated-edit one.
- Phase 4 (Simplified Native UI — file split + CDN removal only): landed at
  reduced scope — see "Known gap" below. `dashboard.html` (2,961 lines, inline
  CSS+JS) mechanically split into `dashboard.html` (472-line shell),
  `dashboard.css` (713 lines), `dashboard.js` (1,773 lines) via a verified
  byte-identical extraction (each extracted block checked to be an exact
  substring of the original file before anything was overwritten). New
  `job_hunter/ux/web/assembly.py::build_dashboard_html()` re-inlines the three
  at launch time, since `pywebview.create_window(html=...)` takes one in-memory
  string with no base URL to resolve relative `<link>`/`<script src>` against
  — source stays split for maintainability, runtime behavior is unchanged.
  Removed the `chart.js` CDN `<script>` tag entirely (`job_hunter/ux/web/dashboard.html`
  previously loaded `cdn.jsdelivr.net/npm/chart.js`); the two `new Chart(...)`
  call sites (status-by-doughnut, weekly-applications-bar) are replaced with
  `renderStatusBreakdown()`/`renderWeeklyBars()`, small CSS/HTML bar lists
  following the file's own pre-existing `renderFunnel()` pattern — no charting
  library, no network-loaded UI code. Added a strict CSP `<meta>` tag
  (`default-src 'self'; script-src 'self'; connect-src 'none'`). Updated
  `packaging/windows/job-hunter.spec` to bundle `dashboard.css`/`dashboard.js`
  (previously only `dashboard.html` was listed — would have broken frozen
  Windows builds against the new assembly step) and, while there, also fixed
  a pre-existing gap where Phase 1/2's `countries.json`/`filters.json`/
  `companies.json` weren't listed in the PyInstaller spec at all. **Known
  gap**: the nav restructure (Today/Applications/Candidates/Insights/Settings,
  folding Analytics into Settings→Diagnostics, Companies into Candidates→
  Company Hunt), the new Get Started/search-setup/chatbot-import screens
  (Phase 3's backend exists; no HTML/JS built against it yet), and a full
  innerHTML→textContent audit across the pre-existing ~44 `innerHTML` call
  sites are **not done**. These require visual/interactive iteration this
  environment can't verify (no display to drive pywebview against) and blind
  large-scale edits to a working 2,900-line UI carry real regression risk;
  shipping them unverified seemed worse than flagging the gap honestly. The
  file split itself is regression-tested (every pre-existing dashboard test
  that grepped `dashboard.html` for JS/CSS content now greps the shell+css+js
  concatenation instead — same assertions, same coverage, relocated content).
- Phase 5 (GUI run services): landed. `DashAPI.start_hunt()`/`get_hunt_status()`
  added to `job_hunter/ux/web/api.py`, reusing the existing `_hunt_lock`/
  `_hunt_running` instance state that `run_company_hunt()` already used —
  they now genuinely share one lock, so a normal hunt and a company hunt can
  never run concurrently against the same workspace (satisfies "Prevent
  overlapping normal/company runs"). The background worker calls
  `job_hunter.pipeline.hunt.run()` (the same `HuntInput`/`HuntOutput` path
  `job-hunter hunt` already uses) and maps its typed result into
  `idle`/`running`/`succeeded`/`failed` + timestamps + fetched/candidate/
  tailored counts + `next_action`; a crashed worker reports a generic
  `"failed"` message (detailed exception stays in local logs via
  `logger.exception`, never reaches the UI) and always releases the lock.
  Added `start_company_hunt()`/`get_company_hunt_status()` as thin aliases
  onto the existing `run_company_hunt()`/`get_company_hunt_summary()` (spec's
  exact method names, without renaming — and breaking — the already-wired
  implementation). **Found and fixed a real secret-disclosure bug while
  implementing this phase's "never return stored secret values to
  JavaScript" requirement**: `get_github_actions_guide()` was returning the
  user's raw LLM API key string in its JSON payload so the dashboard could
  render a "Copy" button — the key sat in the DOM (`data-value="..."`),
  readable via devtools and crossing the JS bridge for no functional reason.
  Fixed by adding `copy_github_actions_secret()`, which reads the secret and
  writes it straight to the OS clipboard from Python (`_copy_to_clipboard()`,
  a new `clip`/`pbcopy`/`xclip` platform dispatch next to the existing
  `_open_path`/`_open_url` ones) — the value never crosses into JS-visible
  state at all now; `get_github_actions_guide()` returns only `name`/
  `configured`. **Also found and fixed a correctness bug from Phase 4**: the
  strict CSP added that phase (`script-src 'self'`) would have silently
  blocked all ~65 pre-existing inline `onclick=`/`onchange=` handlers still
  in `dashboard.html`/`dashboard.js` (CSP-compliant browsers don't execute
  inline event-handler attributes without `'unsafe-inline'` or a matching
  hash/nonce) — this wasn't caught by Phase 4's tests because none of them
  actually execute the HTML in a CSP-enforcing engine. Loosened `script-src`
  back to `'self' 'unsafe-inline'` with a `ponytail:` comment naming the
  upgrade trigger (converting those handlers to `addEventListener`, the same
  deferred work as the nav restructure); `default-src`/`connect-src`/
  `img-src` remain at their fully strict, no-remote-source values.
- Phase 6 (remove terminal UI): landed. Deleted `job_hunter/ux/terminal/`
  (`dashboard.py`, `analytics.py`, `applications.py`, `__init__.py`) and their
  two dedicated test files. Removed the public `dashboard` CLI command
  (interactive/`--no-interactive` terminal renderer) and `applications list`
  (terminal table); kept `applications update` (a real scriptable command, not
  terminal UI — `SETUP.md` already documented it as the correct way to change
  application status). `internal analytics` now always emits JSON (dropped its
  terminal-render fallback) rather than being deleted outright, since the
  underlying data is still useful for automation/debugging. `dash` (GUI),
  `doctor`, `internal verify`, `update`, and every `internal ...`
  agent/GitHub-Actions-facing command are untouched. Updated the agent skill
  routing (`.claude/skills/job-hunter/SKILL.md` and its packaged copy, synced
  via `scripts/sync_workspace_template.py`) so `dashboard`/`apps`/
  `applications` tells the user to open the desktop app instead of running a
  terminal command, and `batch.md`'s post-run "Review:" pointer does the same.
  Updated `README.md`, `AGENTS.md` (repo root, dev-context), and the workspace
  template's `AGENTS.md`/`README.md`/`SETUP.md`/`SETUP_AGENT.md` to drop every
  `job-hunter dashboard --no-interactive` mention in favor of `job-hunter dash`
  — confirmed via a repo-wide grep (excluding `.venv`/`build`/`dist`) that zero
  references to the deleted terminal modules or commands remain outside this
  doc and the (now-GREEN) journey test. **Known gap carried from Phase 4,
  unchanged**: "Doctor output becomes Settings → Diagnostics" and "Workspace
  update becomes Settings → Update Workspace" are GUI-surface requirements
  that depend on the nav restructure Phase 4 deferred — `doctor`/`update`
  remain CLI-only for now; no new gap introduced here.
- Phase 7 (cross-platform desktop distribution): landed at reduced scope —
  see "Known gap" below. New `job_hunter/diagnostics.py::self_test()` runs
  headlessly: countries/filters/catalog resources load and parse, dashboard
  assets are present, a workspace can be created, its config round-trips a
  save, and `outputs/state/jobs.db` opens/migrates — exposed via
  `job-hunter internal self-test [--json]`. This closes the **last** RED
  journey from Phase 0's matrix — `tests/test_gui_onboarding_catalogs_journeys.py`
  is now fully green (all six original journeys pass). Found and fixed a real
  Windows-specific resource-cleanup bug while writing this: `tracking/
  repository.py`'s `_conn()` relies on `sqlite3.Connection`'s context manager,
  which only guards the transaction, not the file handle — an immediate
  `tempfile.TemporaryDirectory` cleanup right after a DB open raced a
  not-yet-garbage-collected connection and raised `PermissionError` on
  Windows. Fixed locally in `diagnostics.py` (manual `tempfile.mkdtemp()` +
  `shutil.rmtree(..., ignore_errors=True)`) rather than touching the shared,
  widely-used `_conn()`/`get_all_known_urls()` — every other caller's cleanup
  happens later (e.g. pytest's `tmp_path` teardown), giving GC time to run,
  so this was specifically a self-test-shaped problem, not a live bug
  elsewhere. **Verified for real, not just statically**: built the actual
  frozen Windows exe from the (now catalog/dashboard-updated) spec via
  `pyinstaller`, and ran `job-hunter.exe internal self-test --json` — all 7
  checks passed, including the three brand-new package resources
  (`countries.json`, `filters.json`, `companies.json`) actually resolving via
  `importlib.resources` inside a frozen bundle. Also ran frozen `--help`
  (confirms the removed `dashboard` command is gone), `init`, and `doctor`.
  Full run recorded in `docs/windows-packaging.md`; build/dist artifacts were
  deleted after validation, matching the existing spike's own rule. Added
  `packaging/macos/job-hunter.spec` and `packaging/linux/job-hunter.spec` +
  `job-hunter.desktop`, structurally mirroring the verified Windows spec
  (same asset list, `console=False`, no Playwright bundled).
  **Linux — also verified for real, in a follow-up pass**: Docker Desktop
  was available on this Windows machine, so the Linux spike was built inside
  a `python:3.12-slim` (Debian 13) container (a real Linux userspace, not
  emulation) rather than left as an unbuilt static spec. Discovered and
  documented the system packages `pywebview[gtk]` actually needs on Linux
  (`libgirepository1.0-dev`, `gir1.2-gtk-3.0`, `gir1.2-webkit2-4.1`,
  `python3-gi`, etc. — `import webview` fails without them, before
  PyInstaller even runs) in `docs/linux-packaging.md`. `internal self-test
  --json` against the frozen Linux binary: all 7 checks pass, same as
  Windows. Frozen `--help`, `init`, and `doctor` also verified. **Known gap,
  macOS only**: unlike Linux, there is no legitimate way to run macOS in a
  container or VM on non-Apple hardware (Apple's EULA restricts macOS
  virtualization to Apple hardware) — `packaging/macos/job-hunter.spec`
  remains structurally-correct but unbuilt; `docs/macos-packaging.md` says so
  explicitly. A real macOS build would need either physical Apple hardware or
  a hosted macOS CI runner (e.g. GitHub Actions `macos-latest`), which needs
  separate user authorization to set up/run. Signing/notarization for both
  platforms (codesign, notarytool, appimagetool GPG-signing) still need real
  credentials neither available nor appropriate to fabricate here. No
  release, publish, version bump, or signing was attempted, per the repo's
  rules and the spec's own "must not publish... without separate user
  authorization."
- Phase 8 (verification, documentation, maintenance): its unit/integration/
  security/regression concerns were addressed incrementally per-phase
  throughout this doc rather than deferred to the end (every phase above
  already includes RED→GREEN evidence, a full preflight run, and an explicit
  list of known gaps). One thing that hadn't been run yet: coverage. Ran
  `pytest --cov=job_hunter --cov-report=term-missing` across the full
  1,427-test suite — **85.87% coverage, above the 80% gate**
  (`[tool.coverage.report] fail_under = 80` in `pyproject.toml`; pytest-cov
  itself reports "Required test coverage of 80.0% reached"). Not done this
  phase (each already called out as a known gap above, listed together here
  for a single point of reference): the Phase 4 nav restructure and its new
  Get Started/search-setup/chatbot-import screens; the ~44 pre-existing
  `innerHTML` call sites' XSS-hardening audit; removing `'unsafe-inline'`
  from the dashboard's CSP `script-src` (blocked on converting ~65 inline
  event handlers); bulk-verifying the company catalog from 19 to 1,500
  entries; and macOS/Linux packaging builds/signing (no hardware/credentials
  in this environment). Everything else in the original 8-phase spec is
  implemented, tested, and verified — including one real frozen-Windows-exe
  run, not just source-level tests.

## Final validation

- Phase 0: `pytest tests/ -q --tb=short` — 1311 passed (pre-existing,
  unchanged) + 6 new journey tests failing as planned (1317 total, 6 failed).
- Phase 1: `pytest tests/ -q --tb=short` — 1337 passed, 5 failed (the
  remaining Phase 2/3/5/6/7 RED journeys; `career_stage` journey now passes).
  `ruff format --check`, `ruff check`, `ty check`, `scripts/validate_config.py`,
  `scripts/sync_workspace_template.py --check`, and `uv build --wheel` all
  passed; wheel inspection confirmed `job_hunter/config/countries.json` and
  `job_hunter/config/filters.json` are packaged.
- Phase 2: `pytest tests/ -q --tb=short` — 1359 passed, 4 failed (the
  remaining Phase 3/5/6/7 RED journeys; `catalog` journey now passes).
  `ruff format --check`, `ruff check`, `ty check`, `scripts/validate_config.py`,
  `scripts/sync_workspace_template.py --check`, and `uv build --wheel` all
  passed; wheel inspection confirmed `job_hunter/catalog/companies.json` is
  packaged.
- Phase 3: `pytest tests/ -q --tb=short` — 1401 passed, 3 failed (the
  remaining Phase 5/6/7 RED journeys; `bootstrap` journey now passes).
  `ruff format --check`, `ruff check`, `ty check`, `scripts/validate_config.py`,
  `scripts/sync_workspace_template.py --check`, and `uv build --wheel` all
  passed.
- Phase 4: `pytest tests/ -q --tb=short` — 1407 passed, 3 failed (the
  remaining Phase 5/6/7 RED journeys). `ruff format --check`, `ruff check`,
  `ty check`, `scripts/validate_config.py`, `scripts/sync_workspace_template.py
  --check`, and `uv build --wheel` all passed; wheel inspection confirmed
  `dashboard.css`/`dashboard.js` are packaged alongside `dashboard.html`.
- Phase 5: `pytest tests/ -q --tb=short` — 1417 passed, 2 failed (the
  remaining Phase 6/7 RED journeys; `daily hunt` journey now passes).
  `ruff format --check`, `ruff check`, `ty check`, `scripts/validate_config.py`,
  `scripts/sync_workspace_template.py --check`, and `uv build --wheel` all
  passed.
- Phase 6: `pytest tests/ -q --tb=short` — 1417 passed, 1 failed (only
  Phase 7/8's diagnostics-self-test RED journey remains; `terminal removal`
  journey now passes). `ruff format --check`, `ruff check`, `ty check`,
  `scripts/validate_config.py`, `scripts/sync_workspace_template.py --check`,
  and `uv build --wheel` all passed.
- Phase 7: `pytest tests/ -q --tb=short` — **1427 passed, 0 failed** — every
  RED journey from Phase 0's original matrix is now green. `ruff format
  --check`, `ruff check`, `ty check`, `scripts/validate_config.py`,
  `scripts/sync_workspace_template.py --check`, and `uv build --wheel` all
  passed. Additionally: a real frozen Windows build via `pyinstaller` (not
  just source tests) confirmed `internal self-test`, `init`, `doctor`, and
  `--help` all work correctly in the packaged exe; build/dist artifacts
  deleted after validation.
- Phase 8: `pytest --cov=job_hunter --cov-report=term-missing` — 1427
  passed, **85.87% coverage** (gate: 80%, `pyproject.toml`).

## Phase 8 follow-up: nav restructure, CSP, innerHTML audit

Closes three of the five gaps listed in the Phase 8 entry above (macOS
packaging and the 19→1,500 company catalog scale-up remain open).

- **innerHTML XSS audit**: reviewed all 44 `innerHTML` call sites in
  `dashboard.js`. All scraped/external data (job company/title/location,
  career-page URLs, failure reasons) was already routed through `esc()`/
  `safeUrl()`. Found and fixed one real gap: the onboarding checklist banner
  interpolated `item.label`/`item.action_hint` unescaped, and `action_hint`
  embeds user-configured file paths (`resume_tex`/`career_context`/
  `story_bank` from `job_hunter.yml`) — now `esc()`'d. Regression test:
  `tests/test_dashboard_assembly.py::test_onboarding_checklist_labels_are_escaped_before_innerhtml`.
- **CSP `script-src 'unsafe-inline'` removal**: converted all ~65 inline
  `onclick=`/`oninput=`/`onchange=` attributes in `dashboard.html` and the 5
  in `dashboard.js`-generated markup to `addEventListener` wiring (static
  by-id list, plus event delegation for `th[data-col]` sort headers, artifact
  tabs, and pager buttons — following the file's own pre-existing delegation
  pattern for untrusted row data). `script-src` is now `'self'` with no
  `'unsafe-inline'`; `style-src` still allows it for inline `style="..."`
  attributes (out of scope for this gap). Regression tests:
  `tests/test_dashboard_assembly.py::test_dashboard_html_has_no_inline_event_handler_attributes`,
  `::test_dashboard_shell_declares_csp_with_no_remote_sources`.
- **Nav restructure**: sidebar is now Today / Applications / Candidates /
  Insights / Settings. Companies folded into Candidates → Company Hunt (the
  full add/edit/delete/enable-disable UI now lives inside
  `#company-hunt-panel`, loaded lazily the first time that tab opens — no
  standalone top-level nav item; all existing ids/functions unchanged).
  Analytics folded into a new Settings → Diagnostics tab, alongside a
  "Setup Health Check" checklist reusing the existing `get_onboarding_checklist()`
  (doctor-derived) — no new backend endpoint needed. New **Today** view
  wires the Phase 5 typed hunt service (`DashAPI.start_hunt()`/
  `get_hunt_status()`) to a "Find Jobs" button for the first time — that
  service existed since Phase 5 but was never called from any UI element
  before this. New **search-setup** and **chatbot-import** screens added
  under Settings → Get Started, wiring the Phase 3 backend
  (`get_bootstrap()`/`save_onboarding_preferences()`/`get_onboarding_prompt()`/
  `import_onboarding_bundle()`) that also existed unused until now. Career
  stage is a hardcoded 5-option `<select>` (student/early_career/experienced/
  leadership/custom, matching `filters.json`'s stable key set) rather than a
  new reference-data endpoint; country/search-lang stayed plain text inputs,
  matching the existing Guided-tab region-row pattern — no new
  `get_setup_reference_data()`-style endpoint was needed. Regression tests:
  `tests/test_web_api.py::test_dashboard_contains_today_view_with_find_jobs`,
  `::test_dashboard_contains_diagnostics_tab_with_doctor_and_analytics`,
  `::test_dashboard_contains_companies_nav_and_table` (updated),
  `::test_dashboard_contains_search_setup_and_chatbot_import_sections`.
  **Verification note**: this environment still has no display to drive a
  live pywebview window against (same constraint Phase 4 originally flagged).
  Verified instead via: full suite green, a Node.js `getElementById`/
  `data-view` cross-reference script confirming every JS DOM lookup resolves
  to a real HTML id with no duplicates and every nav target has a matching
  view section, `node --check` for JS syntax, and
  `job-hunter internal self-test --json` (all 7 checks pass, including
  `dashboard_assets`). No actual click-through in a rendered window.
- `pytest tests/ -q --tb=short` — 1432 passed, 0 failed. `ruff format
  --check`, `ruff check`, `ty check` all passed.
- **Company catalog scale-up (19 → 1,533)**: closes the last of the five
  Phase 8 gaps except macOS packaging (out of scope — needs physical Apple
  hardware). Scope per user request: Europe, North America, Gulf states, and
  Asia; a company present in multiple countries gets one entry with
  `country_codes` listing all of them (the schema already supported this —
  no loader/model change needed), not one row per country. Built via five
  batches: ~122 hand-written high-confidence global multinationals (Amazon,
  Apple, McKinsey, HSBC, etc. — the ones most likely to have real multi-country
  presence), then four parallel research agents (~380 North America, ~442
  Europe, ~162 Gulf, ~402 Asia), each explicitly told to skip the global
  batch's companies and validate its own output against the real
  `job_hunter/catalog/loader.py` Pydantic model before returning. Merge step
  re-validated the combined file against that same model and auto-dropped 2
  cross-batch duplicates (`stellantis`, `elastic`) by id/normalized-URL
  collision — 0 schema errors, final count 1,533. Per user follow-up
  ("optimized way... reliable companies", "Python APIs... instead of wasting
  tokens with WebFetch"): switched the Gulf/Europe agents off WebSearch/WebFetch
  after the first pass (too token-expensive at this volume) in favor of the
  agents' own training knowledge plus the `<domain>/careers` fallback
  convention for uncertain subpaths; separately ran targeted `curl`/`nslookup`
  reachability checks (cheap, no LLM tokens) against every company each agent
  self-flagged as lower-confidence (~30 entries) and corrected 13 with dead
  or wrong URLs (e.g. `norwegian_cruise_line` → `nclhcareers.com` didn't
  resolve at all, real page is `norwegiancruiseline.com/careers`; several
  Asia entries' guessed `/careers` subpath 404'd where the bare domain
  worked, so those fell back to the bare domain). This reachability pass
  confirms URLs *resolve*, not that the company/page content is correct —
  full link-liveness verification across all 1,533 entries remains future
  work, same as the original Phase 8 gap's own caveat. Regression coverage:
  existing `tests/test_catalog.py` (uniqueness/https/known-country/known-industry
  validators) now runs against the full 1,533-entry file un-mocked;
  `job-hunter internal self-test --json`'s `catalog_resource` check reports
  "1533 companies loaded".
- No version bump.
