# Job Hunter

Job hunting is repetitive work. Job Hunter automates the parts that don't need you: scraping listings across major job boards, scoring each one against your profile, tailoring your resume per application, and drafting cover letters. You handle the conversations.

Works interactively inside Claude Code, Codex, Gemini CLI, or GitHub Copilot, or runs fully autonomous via LLM API for unattended pipelines and GitHub Actions.

## What It Does

- **Discovers jobs** across LinkedIn, Indeed, Glassdoor, Himalayas, Remotive, and more — filtered by your titles, regions, and exclusions
- **Scores each listing** against your career context so you know what to prioritize
- **Tailors your resume** per job and generates a cover letter, ready for PDF export
- **Tracks applications** with a dashboard and analytics so nothing slips through

## Install

```bash
pip install job-hunter-kit
# or
uv tool install job-hunter-kit
```

## Quick Start

```bash
job-hunter init my-workspace
cd my-workspace
cp .env.example .env
job-hunter config check
job-hunter doctor
```

Edit `config/job_hunter.yml` with your titles, regions, exclusions, profile paths, scoring thresholds, and provider/model choices. Put your positioning, writing style, and career context in `profile/career_context.md`. Secrets use fixed environment variable names in `.env` or GitHub Actions.

## Modes

| Mode | What runs | When to use |
|---|---|---|
| `agent` | Python prepares context; Claude Code, Codex, Gemini CLI, or Copilot skills handle scoring, tailoring, and writing | Interactive daily review |
| `llm-api` | Full autonomous pipeline; LLM APIs called inside Python | Unattended runs and GitHub Actions |

Set `mode:` in `config/job_hunter.yml`. Default is `agent`.

## Daily Workflow

```bash
job-hunter hunt --region primary
job-hunter brief
job-hunter dashboard --no-interactive
```

In `agent` mode, open the workspace in Claude Code, Codex, Gemini CLI, or GitHub Copilot and use:

```text
/job-hunter brief
/job-hunter batch
/job-hunter one <url>
/job-hunter finalize
```

In `llm-api` mode, `job-hunter hunt` runs scrape → score → tailor → cover letter → PDF → tracker in one pipeline.

## CLI Reference

- `job-hunter init <workspace>` — create a workspace
- `job-hunter config check` — validate `config/job_hunter.yml`
- `job-hunter doctor` — check setup health
- `job-hunter hunt` — discover and enrich jobs
- `job-hunter brief` — write the daily briefing
- `job-hunter tailor` — process job URLs or JD text
- `job-hunter dashboard`, `applications`, `analytics` — inspect application state
- `job-hunter update-skills` — refresh bundled `.claude/skills/`
- `job-hunter version`, `update-info` — version and upgrade guidance

Support commands (`agent-context`, `import-job`, `compile-pdf`, `update-readme`, `mark-processed`, `discard-job`, `cleanup-transient`, `finalize-run`) are used by skills and automation.

## Data Contract

Your data stays yours. Product updates must not overwrite `config/`, `profile/`, `outputs/`, or `.env`. Deterministic choices live in `config/job_hunter.yml`; career and writing guidance lives in `profile/career_context.md`; URL dedup state lives in `outputs/state/discovered_urls.yml`.

See `DATA_CONTRACT.md` for the full contract.

## Development

```bash
uv sync --extra dev
uv run pytest tests/ -q --tb=short
uv run ruff format --check job_hunter tests .github/scripts
uv run ruff check job_hunter tests .github/scripts
uv run ty check job_hunter tests
uv build
```

MIT licensed. See `CONTRIBUTING.md`.

## Lineage

Job Hunter is the evolution of a single experiment: **[job-hunter-core](https://github.com/JobHunterPath/job-hunter-core)** and **[job-hunter-template](https://github.com/JobHunterPath/job-hunter-template)** worked as one system to prove the pipeline, the workspace model, and the agent skill layer — everything this package ships today.
