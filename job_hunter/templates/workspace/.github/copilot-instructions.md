# Job Hunter Workspace

Job Hunter automates job search: Python gathers candidates, agent skills handle
scoring, tailoring, and cover letters.

## Mode

Set `mode:` in `config/job_hunter.yml`. Use `agent` for interactive review with
Copilot; use `llm-api` for autonomous unattended runs.

## Key Commands

```bash
job-hunter hunt --region primary   # scrape new candidates
job-hunter brief                   # show today's queue
job-hunter dashboard --no-interactive
```

## Skill Commands

```
/job-hunter brief      — show candidate queue
/job-hunter batch      — process next frozen batch (score → research → tailor)
/job-hunter one <url>  — process one job URL end-to-end
/job-hunter score <job>
/job-hunter tailor <job>
/job-hunter research <company>
/job-hunter finalize   — commit reviewed outputs
/linkedin ideas
/setup doctor
```

## Key Paths

| What | Path |
|---|---|
| Config | `config/job_hunter.yml` |
| Career context | `profile/career_context.md` |
| Story bank | `profile/story_bank.md` |
| Job outputs | `outputs/jobs/<slug>/` |
| URL dedup | `outputs/state/discovered_urls.yml` |
| Skills | `.claude/skills/` or `.github/skills/` |

## Safety Rules

- Never fabricate resume facts, employers, dates, metrics, or skills.
- Never submit applications or send messages automatically.
- Never overwrite `profile/`, `outputs/`, `config/job_hunter.yml`, or `.env`.
- Leave generated changes uncommitted unless `finalize` is explicitly invoked.
