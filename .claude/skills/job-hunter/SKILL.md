---
name: job-hunter
description: "Primary job search command center. Routes to individual skills for all job search work."
when_to_use: "Use for all job search work: running hunts, processing candidates, tailoring, researching, and managing the pipeline."
argument-hint: "[batch|one <url>|search|finalize|tailor <job>|outreach <job>|interview <job>|score <job>|research <co>|stories|linkedin <cmd>|add-region|style|setup|doctor|dashboard|help]"
disable-model-invocation: true
allowed-tools: Bash Read Edit Write WebSearch WebFetch
author: "Abdul Basit (@abdulrbasit)"
category: workflow
---

Execute `.claude/skills/caveman/SKILL.md` inline before processing any command.
Execute `.claude/skills/job-hunter/_rules.md` inline before processing any command.

# Job Hunter Command Center

One entry point for all job search work. Keep output compact — no raw candidate snapshots, full logs, PDFs, or Draft/raw story-bank sections.

Arguments: `$ARGUMENTS`

## Key Paths

| What | Path |
|---|---|
| Story bank | `profile/story_bank.md` |
| Candidate queue | `outputs/state/agent_candidate_queue.json` |
| Job outputs | `outputs/jobs/<slug>/` |
| Job DB | `outputs/state/jobs.db` |
| Config | `config/job_hunter.yml` |

## Safety Rules

- Never fabricate resume facts, employers, dates, metrics, skills, or job history.
- Never submit applications, send messages, connect, follow, like, comment, or post automatically.
- Never overwrite profile/config inputs unless that mode requires it and the user requested it.
- Leave generated changes uncommitted unless `finalize` is explicitly invoked.

## Initialization

Before any mode that reads profile files (batch, one, tailor, score), run:

```bash
job-hunter internal compile-profile
```

This compiles profile files into minified versions for the session. Silent on failure.

## Routing

Normalize the first argument to lowercase. Empty argument → `help`.

**Daily workflow**
- `dashboard`, `apps`, `applications`: run `job-hunter dashboard --no-interactive`, pass remaining arguments through.
- `batch`, `batch lite`, `process`, `queue`: execute `.claude/skills/job-hunter/modes/batch.md` inline.
- `one <url>`, `url <url>`, or any pasted `http(s)://` URL: execute `.claude/skills/job-hunter/modes/one.md` inline with the URL and remaining arguments.
- `search`: execute `.claude/skills/job-hunter/modes/search.md` inline.
- `finalize`: execute `.claude/skills/job-hunter/modes/finalize.md` inline.
- `screen`: execute `.claude/skills/job-hunter/modes/screen.md` inline.

**Per-job actions** — second token is the job slug
- `tailor <job>`: execute `.claude/skills/job-hunter/modes/tailor.md` inline.
- `outreach <job>`: execute `.claude/skills/job-hunter/modes/outreach.md` inline.
- `interview <job>`: execute `.claude/skills/job-hunter/modes/interview.md` inline.
- `score <job>`: execute `.claude/skills/job-hunter/modes/score.md` inline.
- `research <job>`: execute `.claude/skills/job-hunter/modes/research.md` inline.
- `stories`: execute `.claude/skills/job-hunter/modes/stories.md` inline.

**LinkedIn sub-router** — `linkedin` (alone or with sub-argument): execute `.claude/skills/linkedin/SKILL.md` inline with remaining arguments.

**Setup sub-router** — `setup`, `init`, `onboard`, `doctor`, `health`, `check`, `add-region`, `region`, `style`: execute `.claude/skills/setup/SKILL.md` inline with remaining arguments.

Unknown mode → print the command menu and ask the user to choose a listed mode.

## Command Menu

```text
Job Hunter Command Center

── Daily Workflow ──────────────────────────────────────────────────────
/job-hunter dashboard          Show the application tracker dashboard
/job-hunter batch              Process the next frozen candidate batch
/job-hunter batch lite         Lite batch: skip semantic screen, research, and cover letters
/job-hunter one <url>          Process one job URL end-to-end
/job-hunter search             Search for more jobs when candidates are thin
/job-hunter finalize           Commit durable reviewed outputs
/job-hunter screen             Pre-screen a frozen batch against config exclusion rules

── Per-Job Actions ─────────────────────────────────────────────────────
/job-hunter tailor <job>       Tailor resume + cover letter for a job
/job-hunter outreach <job>     Draft LinkedIn connection + follow-up
/job-hunter interview <job>    Generate predicted interview questions
/job-hunter score <job>        Score one job 0-100 vs. resume and story bank
/job-hunter research <job>     Web-search a company for an imported job
/job-hunter stories            Refine raw work notes into rated STAR stories

── LinkedIn ────────────────────────────────────────────────────────────
/job-hunter linkedin ideas     Generate weekly LinkedIn post ideas
/job-hunter linkedin draft     Write one ready-to-post LinkedIn draft
/job-hunter linkedin engage    Draft comments for posts in your feed
/job-hunter linkedin network   Build a weekly connection queue

── Tools ───────────────────────────────────────────────────────────────
/job-hunter add-region [add|remove] <name>   Add or remove a search region
/job-hunter style              Change resume color scheme or font
/job-hunter setup              One-time onboarding for a fresh workspace
/job-hunter doctor             Run the health checker and show setup status
```

## Output Rules

- Execute child skills inline from their `SKILL.md`; do not print a slash command as a handoff.
- Print only paths, counts, short decisions, and next actions.
- Leave generated changes uncommitted unless `finalize` is explicitly invoked.
