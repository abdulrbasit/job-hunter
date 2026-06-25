# Command Reference

How to invoke job-hunter skills — what to type, and when.

---

## First-time setup

Run these once, in this order.

| Step | Command |
|---|---|
| 1. Configure workspace | `/setup onboard` |
| 2. Set career positioning | `/setup context` |
| 3. Add work stories | `/setup stories` |
| 4. Build your resume | `/setup resume` |
| 5. Style resume | `/setup style` |
| 6. Health check | `/setup doctor` |

---

## Daily review loop (agent mode)

Run these after pulling the latest pipeline results.

| Step | Command |
|---|---|
| 1. See what was found | `/job-hunter brief` |
| 2. Work through candidates | `/job-hunter batch` |
| 3. Save your work | `/job-hunter finalize` |

---

## Per-job actions

Replace `<job>` with the job slug — the folder name under `outputs/jobs/`.
For example: `outputs/jobs/stripe-senior-pm-2025-06/` → slug is `stripe-senior-pm-2025-06`.

| What you want to do | Command |
|---|---|
| Tailor resume + cover letter | `/job-hunter tailor <job>` |
| Score a job fit | `/job-hunter score <job>` |
| Research a company | `/job-hunter research <company>` |
| Generate interview questions | `/job-hunter interview <job>` |
| Draft LinkedIn outreach | `/job-hunter outreach <job>` |
| Process one job URL directly | `/job-hunter one <url>` |

---

## LinkedIn

| What you want to do | Command |
|---|---|
| Get weekly post ideas | `/linkedin ideas` |
| Write a post draft | `/linkedin draft` |
| Draft comments | `/linkedin engage` |
| Build connection queue | `/linkedin network` |

All output is draft only — nothing is posted automatically.

---

## Utility commands

| What you want to do | Command |
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
