# LLM API Mode

`mode: llm-api` in `config/job_hunter.yml`. Beginner setup:
[SETUP_LLM_API.md](../job_hunter/templates/workspace/SETUP_LLM_API.md).

## Pipeline

`job-hunter hunt` runs the whole pipeline inside Python, no agent session
involved: discovery (`sources/`) → enrichment → screening → validation →
quality gate → scoring → tailoring → cover letter → PDF compile → README
update → tracker. `pipeline/runner.py` is the mode dispatcher; it calls
each stage module in order (see [architecture.md](architecture.md#pipeline) for
ownership).

## LLM client

`job_hunter/llm/client.py` is the low-level provider transport
(Anthropic/OpenAI/Google/Ollama). `job_hunter/llm/stage.py::LLMStage` is
the typed request/response service every pipeline stage calls through —
stages never talk to a provider SDK directly.

Token compression via headroom runs automatically through
`llm/client.py` — `max_tokens` in config still controls the model's output
budget, headroom controls how much conversation/context gets sent.

## Roles and models

Every LLM call is tagged with a role: `validation`, `scoring`, `tailoring`,
`cover_letter`, `research`, `linkedin`, `jd_extraction`. `config/job_hunter.yml`'s
`llm.models`/`llm.max_tokens`/`llm.rate_limits` are keyed by these role
names, so you can assign a cheap/fast model to high-volume roles (scoring,
validation) and a stronger model to tailoring/cover letters — see
[config.md](config.md#llm).

## Concurrency and rate limits

`llm.max_workers` controls how many jobs are scored/tailored concurrently
in one run. `llm.rate_limits.<role>.requests_per_minute` throttles a
specific role independently of worker count. There is no code-side spend
cap — set spend limits in your provider's own console (Anthropic Console,
OpenAI usage limits, etc.); a code-side budget module would just duplicate
what the provider already offers.

## GitHub Actions

The shipped **Find Jobs** workflow
(`job_hunter/templates/workspace/.github/workflows/find-jobs.yml`) runs
`job-hunter hunt` on a schedule (commented out by default — you enable it)
or on manual dispatch. It reads provider keys from GitHub Secrets, not
`.env` (Actions can't see your local filesystem), and commits the run's
output back to the repository. See
[SETUP_LLM_API.md](../job_hunter/templates/workspace/SETUP_LLM_API.md#9-run-unattended-with-github-actions).

Two other bundled workflows: **Tailor Job** (`tailor-job.yml`, manual
dispatch — tailor up to 5 pasted job URLs without a full hunt) and
**Company Career Hunt** (`career-hunt.yml`, manual dispatch — the
browser-backed career-page scrape described in [sources.md](sources.md)).

## What agent mode skips

Agent mode's Python side does discovery only and stops. Everything from
scoring onward in this document is `llm-api`-only, or — for the narrow
company-research step — an optional call agent-mode batch makes through
the same `llm.` config (see [agent-mode.md](agent-mode.md)).
