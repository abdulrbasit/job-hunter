# Architecture Decision Record — Target Package Structure

Status: accepted, not yet implemented. Companion to [DATA_CONTRACT.md](DATA_CONTRACT.md) (user/system
file layer) and `AGENTS.md` (living operating context). This file is a point-in-time refactor plan — it
will go stale as migration phases land; update the migration table's status column in place rather than
rewriting history.

No code moved, renamed, or behavior-changed by this document. Phase 3+ execute the migration table below.

## 1. Module Ownership Map (current)

| Package | Owns | Crosses into other packages? |
|---|---|---|
| `cli/` | Typer command definitions, argument parsing, stdout formatting | Calls into every other package (by design — CLI is the composition root) |
| `config/` | YAML config loading, secrets, path/root resolution, defaults | Imported by everything (foundational) |
| `pipeline/` | Hunt/tailor orchestration, per-stage business logic (validate, score, tailor, cover letter, PDF) | Calls `sources/`, `llm/`, `tracking/`, `config/` |
| `sources/` | Job discovery adapters (board APIs, ATS APIs, career-page scraping, web search) | Calls `config/`, `core/` only — must not import `pipeline/` |
| `llm/` | LLM client, response caching | Called by `pipeline/`, `linkedin/` |
| `tracking/` + `db/` | Job/application state persistence, URL dedup | Called by `pipeline/`, `cli/`, `ux/` |
| `workspace/` | Init/update a user workspace, safety gating, template asset assembly | Called by `cli/` only |
| `ux/` | Terminal dashboard, web dashboard, analytics rendering, health checks | Reads `tracking/`, `db/`, `metrics/` |
| `linkedin/` | LinkedIn content generation (no browser automation, no auto-posting) | Calls `llm/`, `config/` |
| `agent_context/` | Builds context objects consumed by Claude Code skills (agent mode only) | Calls `pipeline/`, `sources/`, `tracking/` |
| `tools/` | One-off: profile compilation for the current run | Standalone |

**Rule going forward:** `sources/` must never import from `pipeline/`. This is the one boundary violation
worth actively guarding (discovery adapters have no business knowing about scoring/tailoring); everything
else in this repo is a pragmatic pipeline, not a strict layered architecture.

## 2. Public vs Internal APIs

- A module is **public** (no leading underscore) once anything outside its own package imports it, or once
  it defines a contract external code implements (e.g. `JobSourceAdapter`).
- A module is **private** (`_leading_underscore.py`) when only siblings in the same package import it.
  Tests reaching into private modules for characterization is fine and doesn't make a module public.
- The CLI's `internal` Typer sub-app (hidden from `--help`) is the one exception to "public = no
  underscore": those commands are public *contracts* (bundled skills call them by name) but intentionally
  absent from user-facing `--help`. Don't confuse "internal Typer group" with "private Python module."

## 3. CLI Command Ownership (current → owning module)

| Command | Module |
|---|---|
| `hunt`, `tailor` | `cli/__init__.py` (definition) + `cli/_dispatch.py` (mode routing) |
| `dash` | `cli/__init__.py` → `ux/webdash/` |
| `dashboard`, `internal analytics`, `doctor`, `internal verify` | `cli/_health_commands.py` |
| `applications list`, `applications update` | `cli/_application_commands.py` |
| `init`, `update`, `internal update-skills`, `internal update-workflows`, `version` | `cli/_workspace.py` |
| `internal linkedin ideas/draft/network/all` | `cli/_linkedin_commands.py` |
| `internal update-safety classify/report` | `cli/_update_safety_commands.py` |
| `internal agent-context ...` | `cli/_agent_context.py` |
| `internal import-job/compile-pdf/commit-job/update-readme/write-research/mark-processed/finalize-run/cleanup-transient/discard-job/compile-profile` | `cli/__init__.py` directly |

## 4. Pipeline Stage Ownership (current)

`hunt.py` (discovery entry) → `enrichment.py` → `screening.py` (config rules) → `validator.py` →
`pre_llm_gate.py` → `scorer.py` → `tailorer.py`/`tailor.py` → `cover_writer.py` → `pdf_compiler.py` →
`readme_writer.py`. `orchestrator.py` is the mode dispatcher (`hunt` / `tailor-links` / `tailor-raw`) and
owns the `_process_jobs` chain that calls the above in order. `_match_processor.py` and `_artifacts.py` are
private helpers `orchestrator.py` and `cli/__init__.py` both call into.

**Naming collision to resolve during migration:** `pipeline/orchestrator.py` (whole-pipeline dispatcher)
and `sources/orchestrator.py` (multi-source discovery orchestration) are unrelated modules with the same
name in different packages. Rename on move (see migration table).

## 5. Source Adapter Contract

`sources/_base.py::JobSourceAdapter` (ABC): `source_name` (abstract property), `tier` (`"free"|"api"|
"search"|"browser"`, controls `--depth` filtering), `is_enabled(api_cfg)`, `_fetch(params) -> list[
JobPosting]` (abstract, may raise), `fetch(params)` (public entry point, never raises — wraps `_fetch` in
try/except, returns `[]` on failure). `.name` is a backward-compat alias for `.source_name` (see §8).
Every adapter accepts the shared `SearchParams` contract — enforced today by
`tests/test_source_contracts.py::test_all_adapters_accept_shared_search_contract`. ATS adapters
(`sources/ats/*.py`) currently do **not** share a base class beyond two helpers in `sources/ats/_base.py` —
this is the weakest part of the contract and the first real refactor target (Phase 3 backlog).

## 6. Data Contract

See [DATA_CONTRACT.md](DATA_CONTRACT.md) — not duplicated here. Enforcement lives in
`data_contract.py` (classification) + `update_safety.py` (report/gate), both slated to move into
`workspace/` (see migration table) since nothing outside `workspace/`+`cli/` calls them.

## 7. Template Sync Contract

Two distinct mechanisms, easy to conflate — keep them distinct in the target structure too:

1. **Dev-time repo sync** (`scripts/sync_workspace_template.py`): keeps `job_hunter/templates/workspace/`
   byte-identical to the canonical root files (`.claude/skills/`, `config/`, `AGENTS.md`, etc.), minus
   dev-only skills. Runs via `--check` in CI before `uv build`. Not shipped in the package. **Not** part of
   `job_hunter/workspace/` — it's a contributor tool, stays in `scripts/`.
2. **Runtime asset assembly** (`workspace/_assets.py`): at install/update time, assembles a user's
   workspace from either the source checkout (editable install) or packaged resources (real wheel
   install), deep-merges YAML, preserves README-generated blocks. This is what `job-hunter init`/`update`
   actually run.

## 8. Skill Mirroring Contract

`.claude/skills/` is the source of truth. `_DEV_SKILL_DIRS` (`workspace/_assets.py`) excludes dev-only
skills (`code`, `commit`, `dev-skills`, `dev-tools`, `refactor`, `test`) from the user-facing template.
Every remaining skill dir needs a matching `pyproject.toml` package-data glob
(`workspace/.claude/skills/<name>/**/*`) or it silently drops from real wheel installs — this exact bug
(missing `caveman` entry) was found and fixed in the Phase 1 pass; `tests/test_packaging.py` now guards it
structurally instead of by name.

## 9. Target Package Structure

Adopting the proposed structure with the deviations below (each justified against what actually crosses
package boundaries today — see §12 for the reasoning behind every leading-underscore call).

```
job_hunter/
  cli/
    app.py                  # typer app + sub-app wiring (was cli/__init__.py's app/internal_app/... defs)
    commands/
      hunt.py                tailor.py               dashboard.py
      applications.py         update.py                linkedin.py
      internal.py            (import-job, compile-pdf, commit-job, update-readme, write-research,
                               mark-processed, finalize-run, cleanup-transient, discard-job, compile-profile)
    _dispatch.py             # stays private — only cli/commands/*.py import it
    options.py
    output.py

  config/
    loader.py                defaults.py              schema.py   (was core/config_schema.py)
    secrets.py                paths.py

  domain/
    models.py                 # renamed from top-level models.py — NOT pre-split into 7 files (see §12.1)

  pipeline/
    runner.py                 # was pipeline/orchestrator.py's run() dispatch
    context.py                # shared args/config threading, extracted from runner.py
    stages/
      discovery.py    (hunt.py)         enrichment.py
      screening.py                       validation.py   (validator.py)
      scoring.py       (scorer.py, pre_llm_gate.py)
      tailoring.py     (tailor.py, tailorer.py)
      cover_letter.py  (cover_writer.py)
      pdf.py           (pdf_compiler.py)
      readme.py        (readme_writer.py)   # NOT "tracking.py" — collides with tracking/ package (see §12.2)
    artifacts.py               # was pipeline/_artifacts.py + tracker.py::import_job_artifact
    timing.py                  # was core/metrics.py — collides in name with metrics/store.py otherwise

  sources/
    base.py            (was sources/_base.py — public: JobSourceAdapter is an external contract)
    policy.py           (was sources/_policy.py — public: pipeline/screening.py imports it across packages)
    _http.py             # STAYS private — only sources/*_source.py import it (see §12.3)
    boards/
      registry.py        (was sources/boards/__init__.py::BOARD_REGISTRY)
      adzuna.py  careerjet.py  gulftalent.py  hh.py  himalayas.py  jd_fetcher.py  job_boards.py
      jobbank.py  jobicy.py  jobspy.py  jobstreet.py  jooble.py  mycareersfuture.py  reed.py
      remoteok.py  remotive.py  the_muse.py  weworkremotely.py  workingnomads.py  arbeitsagentur.py
      # pattern: sources/<name>_source.py -> sources/boards/<name>.py, drop the redundant "_source" suffix
    ats/                 (unchanged layout; ats/_base.py becomes a real ATSAdapter base class — Phase 3+)
    career_pages/        (unchanged)
    search/               (was search_providers/)

  llm/
    client.py             budgets.py    (was core/api_budget.py)
    token_usage.py         (was core/llm_utils.py + pipeline/llm_stage.py's get_token_totals)
    # providers.py / prompts.py: NOT created yet — client.py (254 lines) isn't large enough to
    # justify the split until provider-dispatch logic actually grows (see §12.4)

  tracking/
    repository.py          (was db/jobs.py — jobs.db)
    metrics_store.py        (was metrics/store.py — same SQLite-repository shape, same package)
    applications.py         (data half of ux/applications.py: load/filter/update — no rendering)
    processed_urls.py       (was tracking/tracker.py::load_processed/mark_processed)
    discovery_cache.py      (legacy YAML dedup — unchanged location, see §13 for removal plan)

  workspace/
    init.py    update.py    (both were workspace/_ops.py, split by responsibility)
    manifest.py              (unchanged — already correctly named)
    assets.py                (was workspace/_assets.py — public: cli/_workspace.py imports it)
    safety.py                (was data_contract.py + update_safety.py, merged — always used together)
    # NOT "template_sync.py" — that name collides with scripts/sync_workspace_template.py, a
    # different dev-time-only tool. assets.py already owns the runtime side (see §7).

  ux/
    terminal/
      dashboard.py           applications.py  (rendering half only — render_dashboard, render_applications_table)
    web/                      (was ux/webdash/)
    health.py                 # STAYS flat — doctor/verify serve both terminal and --json/programmatic
                               # consumers, not terminal-only presentation (deviation from ux/analytics/ split)
    analytics.py               # STAYS flat — 2 functions today, a package would be an empty-drawer

  linkedin/
    config.py  (was linkedin/_config.py — nothing outside linkedin/ imports it either way; renamed only
                 for consistency since its sibling engagement_support.py is genuinely private)
    ideas.py    drafts.py    engagement.py    _engagement_support.py  (stays private)

  tools/
    compile_profile.py       (unchanged)

  agent_context/              (unchanged — already well-factored: _types.py, _utils.py stay private,
                                batch.py/candidates.py/lifecycle.py/score_context.py/stories.py/
                                tailor_context.py/briefing.py are the public per-mode surface)
```

## 10. Migration Table

Patterned moves (one row covers the whole group) are marked with *.

| Old path | New path | Reason | Public/Private | Tests to update | Risk |
|---|---|---|---|---|---|
| `cli/__init__.py` (app/internal_app defs) | `cli/app.py` | separate app wiring from command bodies | public | `test_cli.py` (import paths only) | low |
| `cli/__init__.py` (10 internal command bodies) | `cli/commands/internal.py` | group by CLI surface, not by "everything in `__init__`" | public (Typer contract) | `test_cli.py` | low |
| `cli/__init__.py` (`hunt`) + `_dispatch.py::dispatch_hunt` | `cli/commands/hunt.py` | one command, one file | public | `test_cli.py`, `test_hunt_pipeline.py` | low |
| `cli/__init__.py` (`tailor`) + `_dispatch.py::dispatch_tailor` | `cli/commands/tailor.py` | one command, one file | public | `test_tailor_pipeline.py` | low |
| `cli/_health_commands.py` | `cli/commands/dashboard.py` | matches command name, not a grab-bag | public | `test_cli.py`, `test_health.py` | low |
| `cli/_application_commands.py` | `cli/commands/applications.py` | rename for consistency | public | `test_applications.py` | low |
| `cli/_workspace.py` | `cli/commands/update.py` (+ `init` folded in) | matches target grouping | public | `test_workspace_init.py`, `test_cli.py` | low |
| `cli/_linkedin_commands.py` | `cli/commands/linkedin.py` | rename for consistency | public (internal Typer group) | `test_linkedin.py` | low |
| `cli/_update_safety_commands.py` | folds into `cli/commands/internal.py` | 2 subcommands, not worth its own file | public (internal Typer group) | `test_cli.py` | low |
| `models.py` | `domain/models.py` | package boundary, not a rewrite | public | every test importing `job_hunter.models` (~40 files) — mechanical import-path change only | **medium** (import fan-out; do as its own PR, grep-and-replace, no logic change) |
| `pipeline/orchestrator.py::run/_process_jobs` | `pipeline/runner.py` | resolves name collision with `sources/orchestrator.py`; matches Phase 0 backlog (decompose orchestrator) | public | `test_orchestrator.py` (rename import, logic unchanged) | **high** (core execution path — do last, small commits) |
| `pipeline/hunt.py` | `pipeline/stages/discovery.py` | stage-per-file | public | `test_hunt_pipeline.py` | medium |
| `pipeline/validator.py` | `pipeline/stages/validation.py` | naming convention: noun matches stage | public | `test_validator.py` | low |
| `pipeline/scorer.py` + `pipeline/pre_llm_gate.py` | `pipeline/stages/scoring.py` | gate is pre-scoring filtering, same stage concern | public | `test_scorer.py`, `test_pre_llm_gate.py` | medium (verify gate ordering preserved) |
| `pipeline/tailor.py` + `pipeline/tailorer.py` | `pipeline/stages/tailoring.py` | two files, one stage — verify no name clash between `run_tailor` and `tailor()` before merging | public | `test_tailor_pipeline.py`, `test_tailorer.py`, `test_tailorer_story_filter.py` | medium |
| `pipeline/cover_writer.py` | `pipeline/stages/cover_letter.py` | naming convention | public | `test_cover_writer.py` | low |
| `pipeline/pdf_compiler.py` | `pipeline/stages/pdf.py` | naming convention | public | `test_pdf_compiler.py` | low |
| `pipeline/readme_writer.py` | `pipeline/stages/readme.py` | **not** `tracking.py` — avoids collision with `tracking/` package | public | `test_orchestrator.py` (readme tests live there today) | low |
| `core/metrics.py` | `pipeline/timing.py` | it's a pipeline-stage timing helper, not a generic core util; avoids name collision with `metrics/store.py` | private→private, path only | none (no direct tests found) | low |
| `sources/_base.py` | `sources/base.py` | public: `JobSourceAdapter` is an external contract, imported by every adapter + tests | public | `test_source_contracts.py`, `test_sources.py`, all adapter tests | **medium** (import fan-out across ~20 files) |
| `sources/_policy.py` | `sources/policy.py` | public: `pipeline/screening.py` and `sources/orchestrator.py` already import it across the package boundary | public | `test_job_policy.py`, `test_orchestrator.py` | medium |
| `sources/_http.py` | unchanged | **not moved** — only `himalayas_source.py`/`remotive_source.py` import it; stays private | private | `test_http_helpers.py` (no path change) | none |
| `sources/*_source.py` (18 files)* | `sources/boards/<name>.py` | one adapter, one file, under the package that owns the registry; drop redundant `_source` suffix | public | every `test_*_source.py` file + `test_sources.py`, `test_new_sources.py`, `test_job_boards.py` | **high** (18 files, do 3-4 per commit, diff fixture output per adapter — matches Phase 0 backlog Phase 2) |
| `sources/boards/__init__.py::BOARD_REGISTRY` | `sources/boards/registry.py` | separates registry from package `__init__` | public | `test_source_contracts.py` | low |
| `sources/search_providers/` | `sources/search/` | naming convention (shorter, matches target tree) | public | `test_search_providers.py` (rename import) | low |
| `core/config_schema.py` | `config/schema.py` | belongs with the config it validates | public | `test_config.py` | low |
| `core/api_budget.py` | `llm/budgets.py` | it's LLM rate/cost budgeting specifically, not a generic core concern | public | `test_api_budget.py` | low |
| `core/llm_utils.py` + `pipeline/llm_stage.py::get_token_totals/reset_token_totals` | `llm/token_usage.py` | token accounting belongs next to the client that produces it | public | `test_llm_utils.py`, `test_llm_stage.py` | medium (called from `orchestrator.py`'s `_persist_metrics`/`_log_token_summary`) |
| `db/jobs.py` | `tracking/repository.py` | same package as the other state stores | public | `test_tracker.py` and anything importing `job_hunter.db.jobs` | **medium** (539 lines, widely imported — do as its own commit) |
| `metrics/store.py` | `tracking/metrics_store.py` | same SQLite-repository shape as `db/jobs.py`, belongs in the same package | public | `test_metrics_store.py` | low |
| `tracking/tracker.py::load_processed/mark_processed` | `tracking/processed_urls.py` | matches target tree name exactly | public | `test_cli.py`, `test_tracker.py` | low |
| `tracker.py` (top-level `repo_path`) | `config/paths.py` | it's a path-resolution helper, not a tracking concern — resolves the confusing `tracker.py` vs `tracking/tracker.py` naming collision that exists **today** | public | almost every test file (`repo_path` is imported everywhere) | **high** (highest fan-out in the whole migration — do last, mechanical import-path change only, no logic change) |
| `tracker.py::import_job_artifact` | `pipeline/artifacts.py` | it writes pipeline job-folder artifacts, not tracking state | public | `test_cli.py`, `test_tracker.py` | medium |
| `data_contract.py` + `update_safety.py` | `workspace/safety.py` (merged) | always used together (classify → report → gate); nothing outside `workspace/`+`cli/` imports either separately | public | `test_data_contract.py` (rename import, logic unchanged) | low |
| `workspace/_ops.py::run_init` | `workspace/init.py` | matches target tree | public | `test_workspace_init.py` | low |
| `workspace/_ops.py::update_skills/update_workflows/_preserve_user_schedule` | `workspace/update.py` | matches target tree | public | `test_workspace_init.py` | low |
| `workspace/_assets.py` | `workspace/assets.py` | public: `cli/_workspace.py` already imports it across the package boundary | public | `test_workspace_init.py`, `test_skill_contracts.py` (Phase 1 parity test), `test_packaging.py` | medium |
| `ux/webdash/` | `ux/web/` | matches target tree | public | none found (no direct tests) | low |
| `ux/dashboard.py` | `ux/terminal/dashboard.py` | groups with the other terminal-only renderer | public | `test_dashboard_analytics.py` | low |
| `ux/applications.py` (rendering fns: `render_dashboard`, `render_applications_table`) | `ux/terminal/applications.py` | presentation half of the module | public | `test_applications.py` | medium (split, not move — verify no shared private state between the two halves) |
| `ux/applications.py` (data fns: `load_applications`, `filtered_applications`, `update_application_status`, `upsert_application_from_job`) | `tracking/applications.py` | data-access half belongs with the other repositories | public | `test_applications.py`, `test_orchestrator.py` (readme test uses `upsert_application_from_job`) | medium |
| `ux/health.py` | unchanged | **not** split into `ux/terminal/` — serves `--json` output too, not terminal-only | public | `test_health.py` | none |
| `ux/analytics.py` | unchanged | **not** a package — 2 functions today | public | `test_dashboard_analytics.py` | none |
| `linkedin/_config.py` | `linkedin/config.py` | rename only, for consistency with target tree; still nothing outside `linkedin/` imports it | private→public in name only | `test_linkedin.py` | low |
| `scripts/sync_workspace_template.py` | unchanged | **not** folded into `workspace/` — dev-time-only tool, not shipped, different concern than runtime `workspace/assets.py` (see §7) | n/a (script) | `test_config.py`, `test_packaging.py` (glob checks, unaffected) | none |

## 11. Naming Conventions

- Modules: noun or clear action noun. `_utils.py` only where genuinely cross-cutting and nothing more
  specific fits (`core/utils.py` qualifies; a hypothetical `sources/board_utils.py` would not).
- No leading underscore once any file outside the module's own package imports it. Leading underscore
  inside a package boundary is not just allowed but *expected* — don't strip it just to "look public."
- Domain models use domain nouns (`JobPosting`, `SearchParams`, `HuntInput`/`HuntOutput`), not their
  serialization shape (`JobDict`, `ResultPayload`).
- Pipeline stage functions are verbs: `discover_jobs`, `enrich_jobs`, `validate_jobs`, `score_jobs`,
  `tailor_job`. Current code mostly already does this (`validate()`, `score_and_filter_jobs()`) — keep the
  pattern, don't force a rename onto something already verb-shaped and clear.
- Config functions: `load_*` reads and parses from disk, `get_*` returns a cached/derived value, `resolve_*`
  turns a partial/relative input into a concrete one (`resolve_root`, `profile_path`). Current code already
  mostly follows this; `get_job_hunter_config`/`get_api_config`/`get_config` are fine as-is.
- Source adapters: `sources/boards/<name>.py`, one adapter per file, matching `source_name`. Don't
  reintroduce a `<source>_adapter.py` suffix — the directory (`boards/`, `ats/`) already disambiguates.
- Rename on move, not blindly: `dict[str, Any]` payload variables get typed names only when the surrounding
  function actually gets typed too (Phase 0 backlog Phase 5, tracked separately — renaming a variable
  without typing the function it lives in is churn, not clarity).
- Abbreviation replacements (`jd` → `job_description`, `cfg` → `config`, `url_checker` →
  `liveness_checker`, `args` → `command_options`) apply **only** to new/moved code and public signatures.
  Do not do a repo-wide rename pass — that's a diff with zero behavior change and maximum review cost for
  no safety benefit. Apply the new name the next time a function is genuinely touched for another reason.

## 12. Deviations From the Proposed Tree, and Why

1. **`domain/` is one file (`models.py`), not seven.** The proposed `job.py`/`company.py`/
   `application.py`/`scoring.py`/`llm.py`/`telemetry.py` split assumes each domain concept already has
   enough independent model code to justify its own file. Today `models.py` is 237 lines total. Splitting
   it now creates six mostly-empty files — the opposite of ponytail's "fewest files possible." Revisit the
   split if/when a specific concept's models exceed roughly 100 lines on their own.
2. **`pipeline/stages/readme.py`, not `tracking.py`.** The proposed tree names the README-writing stage
   `tracking.py`, which collides with the top-level `tracking/` package that already exists for job/URL
   state. Two different things named "tracking" in one repo is exactly the kind of ambiguity this ADR
   exists to prevent.
3. **`sources/_http.py` and would-be `sources/policy.py` don't get the same treatment.** The proposed tree
   makes both public (`http.py`, `policy.py`). Verified by grep: `_policy.py` is imported from
   `pipeline/screening.py` and `sources/orchestrator.py` (crosses the package boundary → public, matches
   proposal). `_http.py` is imported only by two sibling adapters inside `sources/` (`himalayas_source.py`,
   `remotive_source.py`) → stays private, contradicting the proposed tree's flat `http.py`. Apply the
   naming rule (§11) mechanically, not the sketch literally.
4. **No `llm/providers.py` or `llm/prompts.py` yet.** `llm/client.py` is 254 lines today. Worth splitting
   once provider-dispatch logic (anthropic/openai/gemini/ollama branching) is large enough to earn its own
   file — not speculatively ahead of that.
5. **No `workspace/template_sync.py`.** The name overloads two genuinely different things: the dev-time
   `scripts/sync_workspace_template.py` (contributor tooling, not shipped) and the runtime
   `workspace/assets.py` (what `job-hunter init`/`update` actually run). Keeping one name for both would be
   the same class of mistake as the `pipeline/orchestrator.py` vs `sources/orchestrator.py` collision this
   ADR is trying to resolve elsewhere.

## 13. Compatibility Removal Plan

| Item | Current location | Disposition |
|---|---|---|
| `JobSourceAdapter.name` (alias for `source_name`) | `sources/_base.py` | **keep temporarily** — Phase 1 added a characterization test for it; remove after every internal call site is confirmed to use `.source_name` directly (none currently use `.name` outside tests) |
| `HuntOutput.snapshot_path` | `models.py` | **keep** — actively load-bearing for `--from-snapshot`, not dead compat despite the "legacy" comment; removing it means removing the feature, out of scope |
| `pipeline/orchestrator.py::_build_parser` + `argparse` `__main__` entry point | `pipeline/orchestrator.py` | **remove after tests** — grep confirms no script, doc, or workflow invokes `python -m job_hunter.pipeline.orchestrator` directly; the Typer CLI never calls `_build_parser`. Phase 1 added characterization tests for it specifically so removal is a deliberate, tested deletion, not a silent one |
| `outputs/state/discovered_urls.yml` legacy YAML dedup | `tracking/discovery_cache.py` | **remove after tests** — confirm zero real workspace still reads it (jobs.db unique constraints already supersede it); check via telemetry-free means (survey users or wait N releases) before deleting |
| Old config keys (`about_me`, `sources`, `secrets`, top-level `tailoring`/`cover_letter`, `exclusions.{senior_flags,stale_indicators,url_patterns,language_indicators}`, `scoring.prompt_context`, rich `linkedin.*` keys) | rejected by `config/loader.py::_reject_removed_user_config` | **keep the rejection guard** — the keys themselves are already gone from the schema; the guard is the intentional break-loudly mechanism for anyone upgrading from a pre-cutoff config, not itself removable |
| Old public CLI commands demoted to `internal` (`agent-context`, `analytics`, `cleanup-transient`, `compile-pdf`, `discard-job`, `finalize-run`, `import-job`, `linkedin`, `mark-processed`, `update-readme`, `update-safety`, `verify`) | `cli/__init__.py` + submodules | **done** — already migrated, already locked by `test_removed_commands_not_in_help` (Phase 1). Nothing further to do |
| `.gemini/` obsolete agent-CLI mirror dir | `workspace/_assets.py::_OBSOLETE_CLI_DIRS` | **keep temporarily** — cleanup-on-update code for any workspace still carrying the old dir; no telemetry to know when it's safe to drop, keep indefinitely (near-zero cost) |
| `workspace/COMMANDS.md` stale package-data glob | `pyproject.toml` | **done** — removed in Phase 1 |
| `caveman` skill missing from package-data | `pyproject.toml` | **done** — fixed in Phase 1, now structurally guarded by `test_packaging.py` |

## 14. Verification (for every migration phase, not just this doc)

`uv run pytest tests/ -q --tb=short`, `uv run ruff format --check job_hunter tests`,
`uv run ruff check job_hunter tests`, `uv run ty check job_hunter tests`, `uv build` — same gate as Phase 1.
For any row marked medium/high risk in §10: run the move as its own commit, and where the row touches
adapter/scoring behavior, diff a fixture-based before/after run (established pattern from Phase 0's
backlog) rather than trusting the test suite alone.
