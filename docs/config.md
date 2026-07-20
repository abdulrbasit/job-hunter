# Config Reference

`config/job_hunter.yml` is the canonical search config. It holds user choices
as references into package-owned catalogs; bundled countries,
cities, aliases, filters, and matching logic live under `job_hunter/` and ship
in the wheel.
It is validated against `config/schemas/job_hunter.schema.json`
(`additionalProperties: false` — unknown keys are rejected) and, before
that, checked for pre-cutoff removed keys by
`job_hunter/config/removed_keys.py::reject_removed_user_config`. Run
`job-hunter doctor` after any edit.

## Top-level keys

All seven are required: `mode`, `profile`, `job_titles`, `regions`,
`filters`, `scoring`, `llm`.

### `mode`

`"agent"` or `"llm-api"`. See [agent-mode.md](agent-mode.md) and
[llm-api-mode.md](llm-api-mode.md).

### `profile`

| Key | Required | Purpose |
|---|---|---|
| `resume_tex` | yes | Path to your base resume `.tex` file |
| `story_bank` | yes | Path to `story_bank.md` |
| `career_context` | yes | Path to `career_context.md` |
| `latex_class` | no | Custom LaTeX document class |
| `profile_image` | no | Path to a profile photo for the resume |

### `job_titles`

A non-empty array of strings. Matched against listing titles during
screening.

### `regions`

A map of region name → region config. At least one region is required.

| Key | Required | Purpose |
|---|---|---|
| `enabled` | yes | Whether this region is searched |
| `country` | yes | Two-letter country code (e.g. `DE`, `US`) |
| `scope` | yes | `city`, `country`, `remote_country`, or `remote_global` |
| `city_id` | for `city` | Package-owned canonical city ID |
| `primary` | no | Marks the default region for `--region primary` |
| `search_lang` | no | Language code for search-provider queries |
| `description` | no | Free text, shown in `doctor`/dashboard output |

Example city reference:

```yaml
regions:
  berlin:
    enabled: true
    primary: true
    country: DE
    scope: city
    city_id: "geonames:2950159"
    search_lang: en
```

The package owns all names and aliases for that ID. Legacy `location: Berlin`
values resolve in memory and emit a doctor warning, but loading and
`job-hunter update` never rewrite the user's file. Country-specific sources
(for example Arbeitsagentur for `DE`) run only for enabled matching scopes.
Remote/global sources are skipped unless an enabled scope can accept them.
Unknown runtime location evidence fails closed.

Dashboard region cards expose only Type, Country, and City by default. City is
one searchable package-backed field; config key, search language, and
description remain available under Advanced. Legacy country names and remote
phrases are inferred before rendering, so they do not appear as empty cities.

### `filters`

Filter choices are plain scalar lists. Available filter types, descriptions,
matching modes, normalization, and taxonomy expansion are package-owned in
`job_hunter.filters`; user config cannot define new types or matching logic.

```yaml
filters:
  hunt_languages: [en, de]
  experience_levels: [associate, mid, senior]
  posting_types: [internship, working_student]
  excluded_companies: ["Recruiter Corp"]
  excluded_industries: [aerospace_defense]
```

`experience_levels` is the only seniority/student-track filter — postings whose
detected required-experience group isn't selected are excluded automatically. There
is no separate `excluded_titles` field for seniority terms like "intern" or "chief";
`experience_levels` already covers that ground with fail-open detection, so a hand-typed
term list can't do anything it doesn't already do.

`hunt_languages` is an allowlist of ISO language codes (at least one required); there is
no `excluded_languages` list. Screening detects each posting's actual language —
offline, statistical (`job_hunter/core/language.py`) — and excludes it
(`language_not_hunted`) if the detection is confident and the code isn't in
`hunt_languages`; low-confidence detections fail open and are flagged
`language_uncertain` rather than excluded. There's no manual per-language keyword list
to maintain.

`experience_levels` is an allowlist of package-owned level IDs (at least one required;
see `job_hunter/catalog/experience_levels.json` for the full taxonomy — 16 levels from
`student_intern` through `c_level`, each with a min/max years range and EN+DE title
keywords); there's no separate `excluded_experience_levels` list. Screening extracts
each posting's required-experience range — offline, deterministic, regex + title
keywords (`job_hunter/core/experience.py`) — and excludes it
(`experience_out_of_range`) if the detected range has no overlap with your selected
levels' combined range; low-confidence/no-signal postings fail open and are flagged
`experience_unknown` for scoring to judge instead. This replaces the retired
`career_stage` key; `job-hunter doctor` migrates an existing `career_stage` value into
an equivalent `experience_levels` selection once.

The seven public career groups are `student`, `entry`, `mid`, `senior`, `expert`,
`management`, and `executive`; existing detailed IDs remain valid aliases. `expert`
is the advanced individual-contributor track (Lead, Staff, Principal, Distinguished,
Fellow), parallel to Management.

`posting_types` is optional and accepts `internship`, `working_student`, `thesis`,
`graduate_program`, and `trainee`; missing or empty means unrestricted. First enabling
Student mode selects all five and changes the standard score threshold from 70 to 60,
while preserving custom thresholds.

`excluded_industries` contains IDs from the bundled industry taxonomy.
Dashboard controls read all three taxonomies from package resources. New package
options become selectable without changing existing user config. Legacy `{description,
entries}` groups load in memory for compatibility, but explicit saves write scalar
lists.

User preferences belong in these filter groups. Product-owned listing-quality
rulesâ€”such as stale-page phrases and non-listing URL patternsâ€”remain code-owned
in `job_hunter/core/builtin_filters.py`, their single canonical location shared
by discovery and screening without crossing package boundaries.

### `companies`

Optional. Your own company-hunt targets — the bundled catalog (thousands of
companies, package-owned, opt-in) is managed entirely through the dashboard's
Company Hunt → Manage Companies → Shared Catalog view, not through this key.

```yaml
companies:
  targets:
    - name: Acme
      url: https://acme.example/careers
      country: DE
      city: Berlin          # optional; must match a known city name for the country
      industry: software_it # optional; defaults to "other" (unclassified)
      enabled: true          # optional; defaults to true
```

`name`, `url` (https), and `country` (ISO alpha-2) are required per entry.
Bounded startup-board adapters and up to 100 verified package startup/scaleup
companies per enabled country are always included — there's no toggle for this.
`industry` values come from the same package-owned taxonomy as
`filters.excluded_industries`. Targets are mirrored into a runtime SQLite
store (`outputs/state/companies.db`) alongside the opted-in catalog rows —
that store is what the company hunt and the dashboard's Companies table
actually query; it's regenerable and gitignored, not itself a source of
truth. This key replaces the retired `config/career_pages.yml`; a leftover
copy is migrated into `companies.targets` once by `job-hunter doctor` and
then removed. See [architecture.md](architecture.md) for the store schema
and gating rules.

### `scoring`

| Key | Required | Purpose |
|---|---|---|
| `min_fit_score` | yes | 0-100 cutoff to tailor a job |
| `batch_size` | yes | Agent mode: candidates frozen per `/job-hunter batch`. LLM API mode: top-scored matches tailored per run |
| `max_years_experience_required` | no | Skip listings requiring more years than this |
| `strategic_overrides` | no | Per-company score/experience overrides (see below) |

`max_years_experience_required` defaults to the max of your selected
`filters.experience_levels`' ranges when unset — it's now an explicit *override* of
that derived cap (previously it overrode the retired `career_stage`'s cap), not a
primary setting. Prefer adjusting `experience_levels` first; set this only to
override the derived default for a specific need.

`strategic_overrides` is an array of objects, each requiring `company` and
allowing `min_score_override`, `bypass_max_years_experience`, and `reason`
— useful for a target company you want tailored even below your usual
threshold.

### `llm`

| Key | Required | Purpose |
|---|---|---|
| `default_provider` | yes | `anthropic`, `openai`, `google`, or `ollama` |
| `providers` | no | Provider-specific overrides |
| `models` | no | Map of role name → model id (e.g. `tailoring: claude-sonnet-4-6`) |
| `max_tokens` | no | Map of role name → token cap |
| `max_workers` | no | Concurrent requests during a run |
| `rate_limits` | no | Map of role name → `requests_per_minute` |
| `ollama` | no | `base_url` for a local Ollama server |

Roles used across `models`/`max_tokens`/`rate_limits`: `validation`,
`scoring`, `tailoring`, `cover_letter`, `research`, `linkedin`,
`jd_extraction`. `llm-api` mode calls these for every stage. Agent mode's
full-batch flow uses only the `research` role, for an optional company-research
step (`job-hunter internal write-research`) — if no provider key is
configured, that one step is skipped and the rest of the batch continues.
`default_provider` is still required by the schema even in agent mode.

## Removed keys

Loading a workspace that still has one of these raises immediately with
migration guidance, instead of silently ignoring it:

- Top-level: `about_me`, `sources`, `secrets`, `tailoring`, `cover_letter`, `exclusions`
- `scoring.prompt_context`
- `linkedin.*` (any key other than `linkedin.enabled`)

## Adding a new config key

1. Add the key to `config/schemas/job_hunter.schema.json`, with a sensible
   default in the bundled template's `config/job_hunter.yml`.
2. Read it via `job_hunter.config.loader` — don't reach into raw YAML dicts
   elsewhere.
3. `config/job_hunter.yml` is fully user-owned; updates never rewrite it.
   Existing users only pick up a new key automatically if it falls under a
   runtime-merged default section (`llm`,
   `linkedin`, `tailoring`, `cover_letter`, `scoring.prompt_context` — see
   `get_job_hunter_config()`). Anything else needs the user to add it by
   hand; `job-hunter doctor` flags what's missing against the schema.

## What's not in config

Product defaults, the job-board/ATS source list, stale-listing filters,
prompt internals, and fixed secret env-var names live in code, not config
— see [sources.md](sources.md) and `AGENTS.md`'s "Config And State" section.

## Dashboard editing and Undo

`job-hunter dash` opens the native web dashboard. Sidebar order: Today (default
landing — fresh candidates from the last 3 days ranked by fit score, with
one-click shortlist/dismiss/tailor and `j`/`k`/`s`/`x`/`o` keyboard shortcuts),
Job Feed (card list over all candidates, filterable by country/posting
type/company type, with New/Shortlisted/Dismissed scope tabs), Applications
(kanban board by default — Saved/Tailored/Applied/Responded/Interview/Offer/
Rejected columns, drag-and-drop between them, with a Table toggle for the
original sortable list), Company Hunt, Insights, Settings, and Get Started.

Settings provides a guided form with a generic Filters editor, Advanced YAML,
and the career-context editor. Saves validate the raw
user file, use a revision token to reject stale edits, and never write merged
runtime defaults back into YAML. Undo restores the exact previous bytes for
the most recent save. Validation errors do not replace the current file.

Location dropdowns read package resources through the dashboard API. Bootstrap
returns countries and current active selections; cities are fetched only for
the selected country. The Company Hunt tab's Manage Companies view edits
`companies.targets` (My Companies, revision-guarded like the rest of
`job_hunter.yml`) and the runtime store's catalog opt-ins (Shared Catalog,
server-paginated, filterable by country/city/industry/enabled/source).

### Statuses, shortlisting, and dismiss reasons

The pipeline status vocabulary is `candidate → shortlisted | discarded →
tailored → applied → responded → interview → offer | rejected`. `shortlisted`
("Saved" in the UI) is a candidate that's been kept for later — it has no
tailored artifacts yet, is not counted as an active application, and does not
affect the applications streak. `applications update <job> saved` (CLI) and
the Today/Feed "⭐ Save" action both set it; `applications update <job>
shortlist` is an accepted alias.

Dismissing a candidate from Today or the Job Feed records a reason code
(`not_interested`, `wrong_role`, `wrong_location`, `experience_mismatch`, or
`excluded_company`) in a queryable `rejection_reason` column — Insights'
"Why Jobs Were Dismissed" chart aggregates these. Picking "Never show this
company" additionally appends the company name to `filters.excluded_companies`
through the same revision-guarded config save Settings uses; a stale revision
or invalid YAML fails the exclusion (the dismiss itself still succeeds) and
surfaces a warning toast instead of silently dropping the edit.
