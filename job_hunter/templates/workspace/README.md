# Job Hunter Workspace

Personal workspace for the `job-hunter` Python package. First time here?
Start at [SETUP.md](SETUP.md) — it points you to [SETUP_AGENT.md](SETUP_AGENT.md)
(interactive review in VS Code) or [SETUP_LLM_API.md](SETUP_LLM_API.md)
(automated runs and GitHub Actions).

Package docs: https://github.com/abdulrbasit/job-hunter

## Common commands

```bash
job-hunter doctor                      # check setup health
job-hunter hunt --region primary       # find and enrich jobs
job-hunter dash                        # open the desktop app
job-hunter update                      # refresh skills/workflows after an upgrade
```

`job-hunter dash` includes Settings and Companies editors with validation,
revision-safe saves, and one-level Undo. Company Hunt supports new/changed,
failed-only, force-all, and resume modes. In `llm-api` mode, process its
pending DB candidates without scraping again:

```bash
job-hunter hunt --from-db-candidates
```

In agent mode, from the Claude Code or Codex chat panel:

```text
/job-hunter batch
/job-hunter one <url>
/job-hunter finalize
```

## Tips

- Everything under `config/`, `profile/`, and `outputs/` is yours — Job
  Hunter never overwrites your values on update.
- Never commit `.env`; it's excluded by `.gitignore` already.
- Review every tailored resume and cover letter before applying — Job
  Hunter does not apply or post on your behalf.

## Applications

<!-- JOBS_STATS_START -->
No jobs tracked yet.
<!-- JOBS_STATS_END -->

<!-- JOBS_TABLE_START -->
| Date | Job | Location | Score | Files |
|---|---|---|---|---|
<!-- JOBS_TABLE_END -->
