# Command Reference

How to invoke job-hunter skills — what to type, and when.

---

## How skills work

**Claude Code, Gemini CLI, Codex** — type slash commands directly in the AI panel:
```
/setup onboard
/job-hunter brief
```

**GitHub Copilot app** — no slash commands, describe the task in plain language:
```
"onboard me and set up my workspace"
"show me today's job briefing"
```

---

## First-time setup

Run these once, in this order.

| Step | Slash command | Copilot: say this |
|---|---|---|
| 1. Configure workspace | `/setup onboard` | "onboard me and set up my workspace" |
| 2. Set career positioning | `/setup context` | "help me fill in my career context" |
| 3. Add work stories | `/setup stories` | "help me add my work stories and CV bullets" |
| 4. Build your resume | `/setup resume` | "build my base resume" |
| 5. Style resume | `/setup style` | "change my resume colours and font" |
| 6. Health check | `/setup doctor` | "run a health check on my workspace" |

---

## Daily review loop (agent mode)

Run these after pulling the latest pipeline results.

| Step | Slash command | Copilot: say this |
|---|---|---|
| 1. See what was found | `/job-hunter brief` | "show me today's job briefing" |
| 2. Work through candidates | `/job-hunter batch` | "let's go through today's candidates" |
| 3. Save your work | `/job-hunter finalize` | "finalize and commit my reviewed jobs" |

---

## Per-job actions

For slash commands, replace `<job>` with the job slug — the folder name under `outputs/jobs/`.
For example: `outputs/jobs/stripe-senior-pm-2025-06/` → slug is `stripe-senior-pm-2025-06`.

| What you want to do | Slash command | Copilot: say this |
|---|---|---|
| Tailor resume + cover letter | `/job-hunter tailor <job>` | "tailor my resume for the [company] job" |
| Score a job fit | `/job-hunter score <job>` | "score the [company] job for me" |
| Research a company | `/job-hunter research <company>` | "research [company] for me" |
| Generate interview questions | `/job-hunter interview <job>` | "help me prep for the [company] interview" |
| Draft LinkedIn outreach | `/job-hunter outreach <job>` | "draft LinkedIn outreach for the [company] job" |
| Process one job URL directly | `/job-hunter one <url>` | "process this job posting: [paste URL]" |

---

## LinkedIn

| What you want to do | Slash command | Copilot: say this |
|---|---|---|
| Get weekly post ideas | `/linkedin ideas` | "give me LinkedIn post ideas for this week" |
| Write a post draft | `/linkedin draft` | "write a LinkedIn post about [topic]" |
| Draft comments | `/linkedin engage` | "help me write comments for LinkedIn posts" |
| Build connection queue | `/linkedin network` | "build my LinkedIn connection list from my job targets" |

All output is draft only — nothing is posted automatically.

---

## Utility commands

| What you want to do | Slash command |
|---|---|
| Search for more jobs | `/job-hunter search` |
| Pre-screen batch against exclusions | `/job-hunter screen` |
| View the application tracker | `/job-hunter dashboard` |
| Refine existing work stories | `/job-hunter stories` |
| Add a new search region | `/setup region add <name>` |
| Remove a search region | `/setup region remove <name>` |

---

## Modes at a glance

**Agent mode** (`mode: agent` in `config/job_hunter.yml`)
Pipeline scrapes and builds a briefing. You review and process candidates interactively with the daily loop above. No LLM API keys required for the pipeline.

**LLM API mode** (`mode: llm-api` in `config/job_hunter.yml`)
Pipeline runs fully automatically — scrape, score, tailor, cover letter, PDF, and tracker update happen inside GitHub Actions without you. LLM API keys must be added as GitHub Secrets. You still run the one-time setup steps above, then just pull and review the committed outputs.
