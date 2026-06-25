# Job Hunter Workspace

Personal workspace for the `job-hunter` Python package.

First time? See [SETUP.md](SETUP.md) for installation and onboarding steps.

## Start

```bash
cp .env.example .env
job-hunter config check
job-hunter doctor
```

Edit:

- `config/job_hunter.yml` for titles, regions, mode, exclusions, scoring, and LLM settings.
- `profile/career_context.md` for your career target and writing preferences.
- `profile/story_bank.md` for STAR stories.

## Run

```bash
job-hunter hunt --region primary
job-hunter brief
job-hunter dashboard --no-interactive
```

In `agent` mode, use `/job-hunter` from Claude Code, Gemini CLI, or Codex in this workspace.
In `llm-api` mode, the CLI runs the full pipeline.

## Optional browser hunt

Add company career pages to `config/career_pages.yml`, then run
**Company Career Hunt** from GitHub Actions. Results are committed to
`outputs/browser_hunt/jobs.json`.

Package docs/source: https://github.com/abdulrbasit/job-hunter

## Applications

<!-- JOBS_STATS_START -->
No jobs tracked yet.
<!-- JOBS_STATS_END -->

<!-- JOBS_TABLE_START -->
| Date | Job | Location | Score | Files |
|---|---|---|---|---|
<!-- JOBS_TABLE_END -->
