# Job Hunter

Job Hunter is an installable Python package for running a personal job-search workspace. It has one CLI and two modes:

- `agent`: Python handles deterministic work; Claude/Codex skills handle screening, scoring, tailoring, and writing.
- `llm-api`: Python runs the autonomous LLM-backed pipeline for unattended jobs.

The default mode is `agent`.

## Install

```bash
pip install job-hunter
# or
uv tool install job-hunter
```

## Create a Workspace

```bash
job-hunter init my-job-hunter-workspace
cd my-job-hunter-workspace
cp .env.example .env
job-hunter config check
job-hunter doctor
```

Edit `config/job_hunter.yml` with deterministic machine choices: titles, regions, exclusions, profile paths, mode, scoring thresholds, LLM search gate, and provider/model choices. Put personal positioning and writing preferences in `profile/career_context.md`. Secrets use fixed environment variable names in `.env` or GitHub Actions.

## Daily Use

```bash
job-hunter hunt --region primary
job-hunter brief
job-hunter dashboard --no-interactive
```

In `agent` mode, open the workspace in Claude Code or Codex and use:

```text
/job-hunter brief
/job-hunter batch
/job-hunter one <url>
/job-hunter finalize
```

In `llm-api` mode, `job-hunter hunt` runs scrape, score, tailor, cover letter, PDF, tracker, and README updates in one pipeline.

## Public CLI

- `job-hunter init <workspace>` creates a workspace.
- `job-hunter config check` validates `config/job_hunter.yml`.
- `job-hunter doctor` checks setup health.
- `job-hunter hunt` discovers and enriches jobs.
- `job-hunter brief` writes the daily briefing.
- `job-hunter tailor` processes provided job URLs or JD text.
- `job-hunter dashboard`, `job-hunter applications`, and `job-hunter analytics` inspect application state.
- `job-hunter update-skills` refreshes bundled `.claude/skills/` only.
- `job-hunter version` and `job-hunter update-info` show version and upgrade guidance.

Support commands such as `agent-context`, `import-job`, `compile-pdf`, `update-readme`, `mark-processed`, `discard-job`, `cleanup-transient`, and `finalize-run` exist for skills and automation.

## Data Contract

Deterministic user choices live in `config/job_hunter.yml`; human career and writing guidance lives in `profile/career_context.md`. Persistent URL dedup lives in `outputs/state/discovered_urls.yml`. Product updates must not overwrite `config/`, `profile/`, `outputs/`, or `.env`.

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
