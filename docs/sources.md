# Job Sources

Every discovery mechanism Job Hunter uses, and what each needs to run.

## Job boards (`job_hunter/sources/boards/`)

The single membership list is `sources/boards/registry.py::BOARD_REGISTRY`.
Each adapter has a `tier`: `"free"` (no key needed) or `"api"` (needs a key).

| Source | Tier | Notes |
|---|---|---|
| `arbeitnow`, `arbeitsagentur` | free | Arbeitsagentur is Germany-only |
| `jobteaser` | free | Bounded public EU student and graduate listings |
| `startup_jobs`, `yc_jobs` | free | Bounded public startup listings; enabled by `companies.include_startups` |
| `start_munich` | free | Public Munich startup listings; Germany only and startup-toggle gated |
| `bayt`, `careerjet`, `gulftalent`, `hh`, `himalayas`, `jobbank`, `jobicy`, `jobspy`, `jobstreet`, `mycareersfuture`, `remoteok`, `remotive`, `the_muse`, `weworkremotely`, `workingnomads` | free | No API key required |
| `adzuna` | api | Needs `ADZUNA_APP_ID` + `ADZUNA_API_KEY` (free key) |
| `reed` | api | UK only, needs `REED_API_KEY` (free key) |

Every adapter implements `sources/base.py::JobSourceAdapter`: a
`source_name`, `tier`, `is_enabled(api_config)`, and `_fetch(params)`.
`fetch()` wraps `_fetch()` and never raises — one source failing does not
stop the run.

Student mode adds bounded internship, new-graduate, thesis, working-student, and
trainee queries to JobSpy. Arbeitsagentur uses its dedicated student offer category.
Handshake and Stellenwerk remain inactive standard-interface adapters. StudentJob and
Jobmensa were evaluated and deferred behind these higher-value public sources.

Startup discovery uses Startup.jobs RSS with canonical attribution, public Y Combinator
job pages, and Start Munich's public Getro board. Wellfound and JOIN were rejected because
their terms prohibit automated extraction; Startbase, EU-Startups, and Built in Europe
were deferred because current access or structure is not stable enough for an adapter.

Each adapter lives in `sources/boards/<name>.py`, e.g.
`sources/boards/arbeitnow.py`.

`gulftalent` and `bayt` are the Middle East/Gulf sources (AE, SA, QA, KW, BH,
OM). Other Middle East boards investigated but not implemented: NaukriGulf
(unreachable — connection blocked from this environment), Tanqeeb (returns an
empty JS-challenge response), Wuzzuf (reachable, but relies on hashed CSS-in-JS
class names with no stable card selector — a future adapter should key off its
`/jobs/p/` URL pattern instead of class names).

No adapter uses Playwright or any browser rendering — rendering is reserved
for the company career-page hunt (`career_pages/`, triggered from the dashboard's
"Run Company Browser Hunt" button) only. A browser render in a job-board adapter
is slow enough to time out the scheduled GitHub Actions hunt run, so job boards
are static-HTTP/API/RSS only,
even when that means a source occasionally returns fewer results than a
rendered fetch would.

### Classification

| Source | Access | Scope | Format |
|---|---|---|---|
| `remotive`, `remoteok`, `himalayas`, `workingnomads`, `weworkremotely`, `jobicy`, `the_muse` | no-key | global remote | structured API/RSS/JSON |
| `arbeitnow` | no-key | region-specific (Germany-leaning) | structured API |
| `arbeitsagentur` | no-key | region-specific (Germany) | structured API |
| `jobbank` | no-key | region-specific (Canada) | structured API |
| `mycareersfuture`, `jobstreet` | no-key | region-specific (Singapore / SEA) | structured API |
| `hh` | no-key | region-specific (Russia/CIS) | structured API |
| `jobspy` | no-key | global (Google Jobs + Indeed via python-jobspy) | scraped, per-site format |
| `gulftalent`, `bayt` | no-key | region-specific (Gulf/Middle East) | fragile HTML (anti-bot-protected; multi-strategy parsing, no rendering fallback) |
| `careerjet` | optional free key (affiliate id) | global (90+ locales; skips countries without a Careerjet locale instead of falling back to en_GB) | structured API |
| `adzuna` | optional free key | region-specific (per-country allowlist) | structured API |
| `reed` | optional free key | region-specific (UK) | structured API |

`jobspy`'s Google Jobs site needs `google_search_term` phrased as a natural-
language query (`"<title> jobs near <location>"`) — python-jobspy's own docs
note that passing just the bare title (which works fine for `search_term` on
the other sites) returns few or no Google results.

## Company career pages (`job_hunter/sources/career_pages/`)

For companies enabled in `job_hunter.companies` (package-catalog opt-ins plus
`config/job_hunter.yml`'s `companies.targets`), tries in order: ATS public endpoint,
JSON-LD structured data, sitemap crawl, static HTML parsing — falling back
to Playwright (the sole browser tool used here) only when the page needs
JavaScript. Run from the dashboard's "Run Company Browser Hunt" button
(`job_hunter/ux/web/`). Results are written to `outputs/state/jobs.db`, the
same store the regular `find-jobs` hunt uses.

Company Hunt persists pending tasks before work starts and each terminal
result as it finishes. Modes are:

- **New / changed**: default; skips recent successful checks during cooldown.
- **Failed only**: retries failed or never-run companies.
- **Force all**: checks every enabled company.
- **Resume**: continues pending or interrupted work from the latest run.

Cheap extraction stages use bounded concurrency. Playwright starts only when
the fallback queue is non-empty and reuses one browser per browser worker.
Disabled companies are never submitted.

## ATS discovery (`job_hunter/sources/search/ats_discovery.py`)

Search-based discovery of company job pages hosted on common ATS
platforms (Greenhouse, Lever, etc.), driven by the search providers below
rather than a hardcoded per-platform adapter list.

Direct public API extraction (`job_hunter/sources/_jd_ats.py`, used by both
`jd_fetcher.py` and ATS-discovery location verification) exists for:
Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Personio (public XML
feed — its JSON endpoint sits behind a bot checkpoint on many tenants),
Breezy, Recruitee, Teamtailor (JSON Feed with embedded schema.org
JobPosting), and Workday (per-tenant `wday/cxs` REST endpoint). BambooHR has
no verified stable public endpoint — companies using it are typically
discovered via their own ATS (many BambooHR customers actually post through
Greenhouse or similar), so no direct BambooHR fetcher was added.

Query variants for ATS discovery are code-owned and title-derived (never
config): `title+city`, `title+country`, `title+"Remote {country}"`,
`title+region-group` (Europe/EMEA add for EU-configured regions, EMEA/MENA
add for Middle East regions), and Gulf-specific terms (Bahrain, UAE, Qatar,
Saudi, Oman, Kuwait, Dubai, Riyadh, Doha, Manama) for AE/SA/QA/KW/BH/OM
regions. A conservative title-variant table adds e.g. Product Owner /
Technical Product Manager for "Product Manager" titles, and Backend
Engineer / Python Engineer for "Software Engineer" — only when the
configured title literally contains the base phrase.

## Search providers (`job_hunter/sources/search/providers.py`)

Plain web search, not LLM calls — used for company/career-URL discovery
(`sources/search/discovery.py`) and ATS discovery (above) when regular
job-board sources come up thin. The only provider is self-hosted SearXNG
(keyless): set `SEARXNG_BASE_URL` to your instance. It is optional — Job
Hunter runs on the free job boards and the ATS slug cache alone.

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
