# Architecture

Job Hunter combines a Python engine with agent skills. Both execution modes
share configuration, source discovery, domain rules, persistence, and output
formats.

## Execution modes

- `agent`: Python discovers and prepares candidates. Claude Code or Codex runs
  bundled skills for scoring, research, tailoring, and cover letters.
- `llm-api`: Python runs the complete pipeline using configured Anthropic,
  OpenAI, Google, or Ollama providers.

`job_hunter.cli` is the composition root. Typer command definitions live under
`cli/commands/`; `pipeline/runner.py` dispatches typed options to hunt,
tailor-links, or tailor-raw modes.

## Package ownership

| Package | Responsibility |
|---|---|
| `agent_context/` | Bounded context objects consumed by agent skills |
| `cli/` | Command parsing, output, and service composition |
| `companies/` | Package-owned per-country company seed, the runtime SQLite store, and region/industry gating |
| `config/` | YAML loading, choice validation, migrations, secrets, schemas, and workspace paths |
| `core/` | Cross-package utilities and package-owned built-in quality filters |
| `filters/` | Package-owned filter resource loading, type binding, normalization, and matching |
| `linkedin/` | LinkedIn ideas, drafts, and engagement planning |
| `locations/` | Package-owned country/city resources, canonical resolution, and scope matching |
| `llm/` | Provider routing, typed requests/responses, prompts, and token accounting |
| `metrics/` | Pipeline history and normalized agent/API telemetry |
| `pipeline/` | Hunt/tailor orchestration and processing stages |
| `sources/` | Job boards, ATS discovery, career pages, and web search |
| `tracking/` | SQLite job/application state and URL deduplication |
| `ux/` | Terminal and web dashboards, analytics, and health checks |
| `workspace/` | Safe init/update operations and packaged template assets |

## Dependency boundaries

- `cli/` may compose every package; other packages must not import it.
- `sources/` must not import `pipeline/`.
- `pipeline/`, `tracking/`, and `agent_context/` must not depend on `ux/`.
- `tracking/` must not depend on `agent_context/`.
- `filters/` must not depend on `config/`; config binds user choices to the
  lower-level package registry.
- Shared helpers move inward to `core/`, `config/`, or `tracking/`; presentation
  and agent-specific helpers do not leak into lower layers.

Ruff banned-import rules and `tests/test_dependency_boundaries.py` enforce
these boundaries.

## Pipeline

`pipeline/runner.py` creates `PipelineRunContext`, resets run-local token
accounting, dispatches a mode, processes jobs, and persists metrics.

Hunt flow:

1. Resolve each enabled region to a typed `Location`, pass it to adapters as
   `SearchParams.canonical_location`, and discover postings through
   `sources/orchestrator.py`.
2. Deduplicate, enrich descriptions, and reject closed listings.
3. Screen objective filters and apply the quality gate (rank/cap before LLM scoring).
4. Validate, score, research, tailor, write cover letters, and compile PDFs.
5. Persist job/application state, generated artifacts, README summaries, and
   telemetry.

Agent mode exits after discovery/state preparation. Bundled `job-hunter`
skills continue the same lifecycle through hidden CLI contracts under
`job-hunter internal ...`.

## Data and state

- `config/job_hunter.yml`: sole user-owned config; choices reference package-owned catalogs.
- `job_hunter/locations/data/`: read-only canonical city resources shipped in the wheel.
- `job_hunter/companies/data/*.jsonl`: read-only per-country company seed shipped in the wheel
  (built by `scripts/build_company_seed.py`), imported into `outputs/state/companies.db` on
  first use.
- `profile/`: user-owned resume, career context, and story evidence.
- `outputs/state/jobs.db`: canonical job and application state; git-synced across machines.
- `outputs/state/companies.db`: runtime company store (package seed + a mirror of
  `config/job_hunter.yml`'s `companies.targets`) — regenerable, gitignored, not synced.
- `outputs/state/metrics.db`: pipeline and token telemetry.
- `outputs/jobs/<slug>/`: durable per-application artifacts.

Typed models (`job_hunter/models.py`) are the canonical contract for job,
profile, and config data — for new code, and at the boundaries that already
use them (public job/search/LLM/pipeline command contracts). Raw
`dict[str, Any]` still remain at legacy pipeline boundaries (job records
flowing through scrape/score/gate stages, e.g. `PipelineRunContext`,
`StageResult`, `ModeOutcome` in `job_hunter/pipeline/context.py`) and at
external JSON, YAML, SQLite, and generated-artifact serialization
boundaries. Narrowing those remaining dict boundaries to typed models is
future cleanup, not something this pass claims to have finished.

Location ownership follows the same boundaries. `config/locations.py` is the
explicit compatibility surface for config loading and migration; runtime
sources, pipeline screening, catalog matching, and dashboard reference-data
endpoints use `job_hunter.locations` directly. Source adapters receive a typed
canonical search location. Orchestrator results and browser-hunt extraction
attach canonical location evidence before the defense-in-depth screening gate.
Fuzzy aliases are therefore confined to config-time resolution; runtime gates
compare canonical IDs and scopes.

### Companies

`job_hunter/companies/` replaces the retired `config/career_pages.yml`:

- `seed.py` reads the bundled per-country JSONL shards (`data/<CC>.jsonl` +
  `data/manifest.json`) via `importlib.resources`.
- `store.py` owns `outputs/state/companies.db` — one `companies` table
  (`id, catalog_id, name, normalized_name, url, normalized_url, country, city,
  industry, source, batch, enabled, created_at, updated_at`, unique on
  `(normalized_url, country, source)`, indexed on `country`, `(country, city)`,
  and `industry`). `ensure_seeded()` (re-)imports the seed on a version bump,
  preserving each catalog row's `enabled` flag by `(normalized_url, country)`;
  `sync_user_targets()` mirrors `config/job_hunter.yml`'s `companies.targets`
  as `source='user'` rows on every hunt/dashboard read.
- `gating.py` derives eligible countries from enabled regions (`None` for a
  remote_global region = every country; `[]` for no enabled regions = nothing)
  and expands `filters.excluded_industries` to taxonomy IDs, the same taxonomy
  `filters/catalog.py` uses.
- `pipeline/browser_hunt.py` and `sources/ats_slugs.py` both consume
  `job_hunter.companies.hunt_candidates()` / `store.candidate_companies()` —
  an index-backed `WHERE enabled = 1 AND country IN (...) AND industry NOT IN
  (...)` query, not a full-catalog scan. When a user target and a catalog row
  share a `(normalized_url, country)`, the user row wins (mirrors the old
  career_pages.yml custom-entry-wins rule).

`companies.db` is regenerable (seed + config mirror) and gitignored — unlike
`jobs.db`, it is never synced across machines. `config/job_hunter.yml`'s
`companies.targets` is the durable, git-synced record of a user's own targets.

## Shared writing policy

`job_hunter/writing/` is code-owned and mode-agnostic: `rules.py` exposes
`universal_resume_rules()`, `universal_cover_letter_rules()`,
`universal_outreach_rules()`, `universal_evidence_rules()`, and
`universal_ats_rules()`. `llm-api` mode bakes these into system prompts
(`llm/prompts/tailoring.py`, `pipeline/cover_writer.py`); `agent` mode
delivers them via `agent_context/tailor_context.py`, `outreach_context.py`,
and `evidence_context.py`'s `writing_rules` field, consumed through
`job-hunter internal agent-context tailor-context`/`outreach-context`/`evidence-context`.
The `job-hunter` and `linkedin` skill modes (`tailor.md`, `outreach.md`,
`draft.md`, `ideas.md`, `engage.md`, `network.md`) all read `writing_rules`
this way instead of hand-mirroring rule text. `career_context.md` preferences
never override them.

## Workspace templates and skills

`.claude/skills/` is canonical. `scripts/sync_workspace_template.py` mirrors
user-facing skills into `job_hunter/templates/workspace/.claude/skills/`.
Runtime asset assembly also exposes them under `.agents/skills/` for Codex.

`workspace/assets.py` reads canonical files in editable installs and packaged
resources in wheels. `workspace/operations.py` performs init/update writes.
User data under `config/`, `profile/`, `outputs/`, and `.env` is protected by
the contract in [DATA_CONTRACT.md](../DATA_CONTRACT.md).

## Safety and observability

Tests block non-loopback network connections. Source failures are isolated per
adapter. Workspace updates preserve user-owned data.

Claude Code, Codex, and direct LLM API usage normalize into the same telemetry
schema without storing prompts, model responses, resume content, or tool
arguments.
