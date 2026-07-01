# Config Reference

`config/job_hunter.yml` holds every deterministic, user-editable setting.
It is validated against `config/schemas/job_hunter.schema.json`
(`additionalProperties: false` — unknown keys are rejected) and, before
that, checked for pre-cutoff removed keys by
`job_hunter/config/removed_keys.py::reject_removed_user_config`. Run
`job-hunter doctor` after any edit.

## Top-level keys

All seven are required: `mode`, `profile`, `job_titles`, `regions`,
`exclusions`, `scoring`, `llm`.

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
| `location` | yes | City or area name passed to sources |
| `primary` | no | Marks the default region for `--region primary` |
| `search_lang` | no | Language code for search-provider queries |
| `description` | no | Free text, shown in `doctor`/dashboard output |

Country-specific sources (e.g. Arbeitsagentur for `DE`) only run for
matching regions. Global/remote sources run regardless of country.

### `exclusions`

All four are optional arrays of strings: `companies`, `title_terms`,
`languages`, `industries`. Applied during screening
(`job_hunter/pipeline/screening.py`), before scoring.

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

- Top-level: `about_me`, `sources`, `secrets`, `tailoring`, `cover_letter`
- `exclusions.*`: `senior_flags`, `stale_indicators`, `url_patterns`, `language_indicators`
- `scoring.prompt_context`
- `linkedin.*` (any key other than `linkedin.enabled`)

## Adding a new config key

1. Add the key to `config/schemas/job_hunter.schema.json`, with a sensible
   default in the bundled template's `config/job_hunter.yml`.
2. Read it via `job_hunter.config.loader` — don't reach into raw YAML dicts
   elsewhere.
3. Existing users get it automatically on their next `job-hunter update`
   (YAML configs are deep-merged: new template keys are added, existing
   user values are kept).

## What's not in config

Product defaults, the job-board/ATS source list, stale-listing filters,
prompt internals, and fixed secret env-var names live in code, not config
— see [sources.md](sources.md) and `AGENTS.md`'s "Config And State" section.
