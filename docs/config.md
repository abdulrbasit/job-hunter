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
  excluded_titles: [intern, trainee]
  excluded_companies: ["Recruiter Corp"]
  excluded_industries: [aerospace_defense]
```

`hunt_languages` is an allowlist of ISO language codes; there is no
`excluded_languages` list. `excluded_industries` contains IDs from the bundled
industry taxonomy. Dashboard controls read both taxonomies from package
resources. New package options become selectable without changing existing
user config. Legacy `{description, entries}` groups load in memory for
compatibility, but explicit saves write scalar lists.

User preferences belong in these filter groups. Product-owned listing-quality
rulesâ€”such as stale-page phrases and non-listing URL patternsâ€”remain code-owned
in `job_hunter/core/builtin_filters.py`, their single canonical location shared
by discovery and screening without crossing package boundaries.

### `scoring`

| Key | Required | Purpose |
|---|---|---|
| `min_fit_score` | yes | 0-100 cutoff to tailor a job |
| `batch_size` | yes | Agent mode: candidates frozen per `/job-hunter batch`. LLM API mode: top-scored matches tailored per run |
| `max_years_experience_required` | no | Skip listings requiring more years than this |
| `strategic_overrides` | no | Per-company score/experience overrides (see below) |

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

`job-hunter dash` opens the native web dashboard. Settings provides a guided
form with a generic Filters editor, Advanced YAML, and the career-context
editor. Saves validate the raw
user file, use a revision token to reject stale edits, and never write merged
runtime defaults back into YAML. Undo restores the exact previous bytes for
the most recent save. Validation errors do not replace the current file.

Location dropdowns read package resources through the dashboard API. Bootstrap
returns countries and current active selections; cities are fetched only for
the selected country. Existing legacy company configuration remains readable
during its planned retirement into the single config/store ownership model.
