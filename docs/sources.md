# Job Sources

Every discovery mechanism Job Hunter uses, and what each needs to run.

## Job boards (`job_hunter/sources/boards/`)

The single membership list is `sources/boards/registry.py::BOARD_REGISTRY`.
Each adapter has a `tier`: `"free"` (no key needed) or `"api"` (needs a key).

| Source | Tier | Notes |
|---|---|---|
| `arbeitnow`, `arbeitsagentur` | free | Arbeitsagentur is Germany-only |
| `careerjet`, `gulftalent`, `hh`, `himalayas`, `jobbank`, `jobicy`, `jobspy`, `jobstreet`, `mycareersfuture`, `remoteok`, `remotive`, `the_muse`, `weworkremotely`, `workingnomads` | free | No API key required |
| `adzuna` | api | Needs `ADZUNA_APP_ID` + `ADZUNA_API_KEY` |
| `jooble` | api | Needs `JOOBLE_API_KEY` |
| `reed` | api | UK only, needs `REED_API_KEY` |
| `jsearch` | api | RapidAPI, needs `RAPIDAPI_KEY` |

Every adapter implements `sources/base.py::JobSourceAdapter`: a
`source_name`, `tier`, `is_enabled(api_config)`, and `_fetch(params)`.
`fetch()` wraps `_fetch()` and never raises — one source failing does not
stop the run.

Most adapters are one class per `sources/boards/<name>.py` file. Two are
not: `arbeitnow` and `jsearch` still live as `ArbeitnowSource`/`JSearchSource`
classes inside `sources/job_boards.py`, a legacy module that predates the
per-file layout — `registry.py` imports them from there rather than from
`sources/boards/`. Behavior is unaffected; this is a known backlog item, not
a bug. Future cleanup may split them into `sources/boards/arbeitnow.py` and
`sources/boards/jsearch.py` to match every other adapter, but that split is
out of scope for now.

## Company career pages (`job_hunter/sources/career_pages/`)

For `config/career_pages.yml` targets, tries in order: ATS public endpoint,
JSON-LD structured data, sitemap crawl, static HTML parsing — falling back
to a real browser (the **Company Career Hunt** GitHub Actions workflow,
`.github/workflows/career-hunt.yml`) only when the page needs JavaScript.
Results are written to `outputs/browser_hunt/jobs.json`.

## ATS discovery (`job_hunter/sources/search/ats_discovery.py`)

Search-based discovery of company job pages hosted on common ATS
platforms (Greenhouse, Lever, etc.), driven by the search providers below
rather than a hardcoded per-platform adapter list.

## Search providers (`job_hunter/sources/search/providers.py`)

Plain web-search APIs, not LLM calls — used for company/career-URL
discovery (`sources/search/discovery.py`) and ATS discovery (below) when
regular job-board sources come up thin. Each needs its own API key:

| Provider | Env var |
|---|---|
| Brave Search | `BRAVE_API_KEY` |
| Tavily | `TAVILY_API_KEY` |
| Exa | `EXA_API_KEY` |
| Firecrawl (also used as a career-page rendering fallback) | `FIRECRAWL_API_KEY` |

None of these are required — Job Hunter runs on the free job boards alone.
Add keys incrementally as you find gaps in coverage.

## Adding a new job board adapter

1. Create `job_hunter/sources/boards/<name>.py` implementing
   `JobSourceAdapter` (see any existing adapter, e.g. `remotive.py`, for
   the free-tier shape, or `adzuna.py` for the api-tier shape).
2. Register it in `sources/boards/registry.py::BOARD_REGISTRY` — this is
   the only place source membership is declared.
3. Add a fixture-based test (`tests/test_<name>_source.py`) that mocks the
   HTTP call — no live network calls in tests (see [testing.md](testing.md)).
4. If it needs a secret, add the env var to
   `job_hunter/config/defaults.py::SECRET_ENV_VARS` and to
   `.env.example` in the workspace template.

`sources/` must never import from `pipeline/` — discovery adapters have no
business knowing about scoring or tailoring. This is enforced by a ruff
banned-api rule in `pyproject.toml`.
