# Job Hunter

Job hunting is repetitive work. Job Hunter automates the parts that don't need you: scraping listings across major job boards, scoring each one against your profile, tailoring your resume per application, and drafting cover letters. You handle the conversations.

Works interactively inside Claude Code or Codex (VS Code extensions), or runs fully autonomous via LLM API for unattended pipelines and GitHub Actions.

## What It Does

- **Discovers jobs** across supported job boards, aggregators, and company career pages — filtered by your titles, regions, and exclusions
- **Scores each listing** against your career context so you know what to prioritize
- **Tailors your resume** per job and generates a cover letter, ready for PDF export
- **Tracks applications** with a dashboard and analytics so nothing slips through

## Install

Requires [Python 3.12 or 3.13](https://www.python.org/downloads/). See the
complete beginner-friendly [SETUP.md](job_hunter/templates/workspace/SETUP.md)
for installation, PATH troubleshooting, API-key links, and agent permissions.

```bash
uv tool install job-hunter-kit
```

Standard install supports both agent and `llm-api` modes.

## Quick Start

```bash
job-hunter init my-workspace
cd my-workspace
job-hunter doctor
```

Open the workspace in VS Code with Claude Code or Codex, then run `/setup onboard`, `/setup context`, `/setup stories`, and `/setup resume`. `job-hunter doctor` validates config and reports exact fixes.

## Modes

| Mode | What runs | When to use |
|---|---|---|
| `agent` | Python prepares context; Claude Code or Codex (VS Code) skills handle scoring, tailoring, and writing | Interactive daily review |
| `llm-api` | Full autonomous pipeline; LLM APIs called inside Python | Unattended runs and GitHub Actions |

Set `mode:` in `config/job_hunter.yml`. Default is `agent`.

## Daily Workflow

```bash
job-hunter hunt --region primary
job-hunter dash                      # desktop app
```

In `agent` mode, open the workspace in VS Code with Claude Code or Codex and use:

```text
/job-hunter batch
/job-hunter one <url>
/job-hunter finalize
```

In `llm-api` mode, `job-hunter hunt` runs scrape → score → tailor → cover letter → PDF → tracker in one pipeline.

## For Students

1. Run `job-hunter dash`, open onboarding, and enable **Student mode**.
2. Choose target roles and locations; internships, working-student roles, thesis
   positions, graduate programs, and trainee roles are selected automatically.
3. Run `job-hunter hunt`, then review the posting-type-filtered Candidates feed.

Student scoring emphasizes verified education, coursework, projects, internships, and
transferable skills. Posting types and the automatic score threshold remain editable.

## Company Hunt

For company career pages that need a real browser, add your own companies or
opt in to the shared catalog in the **Company Hunt** tab's **Manage Companies**
view in `job-hunter dash`, then click **Run Company Hunt**. Results land in
`outputs/state/jobs.db`, the same store the normal hunt uses.

The native web dashboard includes Settings, Companies, paginated Applications
and Candidates, Company Hunt (its own top-level tab), Insights, and Analytics.
Settings and Companies use revision-guarded saves with one-level Undo. Company
Hunt is one button — it continues an interrupted run automatically, otherwise
checks whatever's new or changed; recent successful pages are skipped by
default and every company result is persisted immediately. Bundled catalog
companies (Manage Companies → Shared Catalog) are opt-in per company or per
sector; companies you add yourself stay enabled by default.

## CLI Reference

- `job-hunter init <workspace>` — create a workspace
- `job-hunter doctor` — check setup health
- `job-hunter hunt` — discover and enrich jobs
- `job-hunter tailor` — tailor resume for one or more job postings
- `job-hunter finalize` — validate and commit durable outputs (README, config, profile, job/LinkedIn outputs, jobs.db); `--push` to also push. Same action as the dashboard's Finalize button
- `job-hunter dash` — open the desktop app in a native window (Applications, Insights, Analytics)
- `job-hunter applications update <job> <status>` — update an application's lifecycle status from a script
- `job-hunter hunt --from-db-candidates` — process pending company-hunt candidates in `llm-api` mode
- `job-hunter update` — update workspace assets, skills, and workflows after a package upgrade
- `job-hunter update --skills-only` or `--workflows-only` — targeted refresh
- `job-hunter version` — version and upgrade guidance

Bundled skills use hidden `job-hunter internal ...` commands. They are not part of normal user workflow.

## Data Contract

Your data stays yours. Product updates must not overwrite `config/`, `profile/`, `outputs/`, or `.env`. Deterministic choices live in `config/job_hunter.yml`; career and writing guidance lives in `profile/career_context.md`; all job and application state lives in `outputs/state/jobs.db`.

See [DATA_CONTRACT.md](DATA_CONTRACT.md) for the full contract.

## Safety Boundaries

Job Hunter never submits applications, posts on LinkedIn, or contacts anyone automatically. It writes files under `outputs/` for you to review. `job-hunter finalize` and `job-hunter update` only touch system-owned paths — see the data contract above.

## Development

```bash
uv sync --extra dev
uv run pytest tests/ -q --tb=short
uv run ruff format --check job_hunter tests scripts
uv run ruff check job_hunter tests scripts
uv run ty check job_hunter tests
uv build
```

MIT licensed. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Documentation

- [docs/architecture.md](docs/architecture.md) — package structure and module boundaries
- [DATA_CONTRACT.md](DATA_CONTRACT.md) — user vs. system-owned files
- [docs/config.md](docs/config.md) — every `config/job_hunter.yml` key
- [docs/sources.md](docs/sources.md) — job boards, career pages, search providers
- [docs/agent-mode.md](docs/agent-mode.md) — how agent mode works
- [docs/llm-api-mode.md](docs/llm-api-mode.md) — how LLM API mode works
- [docs/workspace-updates.md](docs/workspace-updates.md) — what `job-hunter update` does
- [docs/testing.md](docs/testing.md) — running and writing tests
- [CONTRIBUTING.md](CONTRIBUTING.md) — contributor guide

## Lineage

Job Hunter is the evolution of a single experiment: **[job-hunter-core](https://github.com/JobHunterPath/job-hunter-core)** and **[job-hunter-template](https://github.com/JobHunterPath/job-hunter-template)** worked as one system to prove the pipeline, the workspace model, and the agent skill layer — everything this package ships today.
