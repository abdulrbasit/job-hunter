# Job Hunter Setup

This page is written for non-technical users. It helps you pick a mode and
get Job Hunter installed. Detailed, step-by-step guides live in two other
files — this page tells you which one to open.

## 1. What Job Hunter does

Job Hunter searches job boards and company career pages, scores each listing
against your resume and background, tailors your resume per job, and drafts
a cover letter. You review everything before applying — it never submits
applications, posts on LinkedIn, or contacts anyone automatically.

## 2. Which mode should I use?

| Mode | Best for | Daily tool |
|---|---|---|
| **LLM API mode** | Fully automated runs — the dashboard and GitHub Actions do everything | Just the **Job Hunter dashboard** (`job-hunter dash`). No VS Code, no Claude Code. |
| **Agent mode** | Reviewing jobs interactively, one day at a time, no LLM API key/billing | The dashboard for setup, plus **Claude Code or Codex in VS Code** for daily review/tailoring. |

Not sure? If you don't want to touch VS Code at all, pick **LLM API
mode** — setup and daily use both happen in the dashboard. You can switch
later by changing `mode:` in `config/job_hunter.yml`.

## 3. Requirements

| Tool | Needed for | Get it |
|---|---|---|
| Python 3.12 or 3.13 | Both modes (there's no packaged installer yet — install still runs through a terminal once) | [python.org/downloads](https://www.python.org/downloads/) |
| [uv](https://docs.astral.sh/uv/) | Both modes (recommended installer) | Installed in step 4 below |
| An LLM API key (Anthropic, OpenAI, or Google) | LLM API mode only | See [SETUP_LLM_API.md](SETUP_LLM_API.md) |
| VS Code + Claude Code or Codex extension | Agent mode's daily review/tailoring only — not needed for setup, and not needed at all in LLM API mode | [code.visualstudio.com](https://code.visualstudio.com/) |

Python 3.14 and Python 3.11 or older are not supported.

## 4. Install Job Hunter

Open a terminal and run:

```bash
python -m pip install uv
python -m uv tool install job-hunter-kit
python -m uv tool update-shell
```

Close and reopen your terminal, then check it worked:

```bash
job-hunter version
```

**Expected result:** prints the installed version, e.g. `job-hunter 0.14`.

**Common mistake:** if `job-hunter` is "not recognized" or "command not
found", your terminal needs restarting after `update-shell`, or your
Python Scripts folder isn't on `PATH`. See the troubleshooting sections in
[SETUP_AGENT.md](SETUP_AGENT.md) or [SETUP_LLM_API.md](SETUP_LLM_API.md).

## 5. Create a workspace

```bash
job-hunter init FirstName.LastName-Resume
cd FirstName.LastName-Resume
```

This creates a folder with `config/`, `profile/`, `outputs/`, `.github/`,
and `.claude/` — your resume, settings, and results all live here, private
to you. **Expected result:** `[ok] Workspace created at: ...` with next
steps printed.

## 6. Open the dashboard and finish setup there

```bash
job-hunter dash
```

A new workspace opens straight into a guided setup wizard: mode, job
titles, region, languages/experience/exclusions — then a **Career
Profile** panel for the parts an LLM has to write (career context, story
bank, base resume). Each of those three offers two paths: a one-click
command if you have Claude Code or Codex, or a copy-paste prompt plus
paste-back Import if you only have a browser chatbot (ChatGPT, Claude.ai,
etc.) — either way nothing here needs VS Code. The wizard reappears
whenever something it needs is still missing; once everything's set, Get
Started shows a plain summary and a **Run first hunt** button instead.

For mode-specific detail (the `.env` file for LLM API mode, or the
`/setup`/`/job-hunter` agent skills for agent mode), see:

- **[SETUP_AGENT.md](SETUP_AGENT.md)** — agent mode, interactive review in VS Code
- **[SETUP_LLM_API.md](SETUP_LLM_API.md)** — LLM API mode, automated runs and GitHub Actions

## 7. Update an existing workspace

After upgrading the `job-hunter-kit` package:

```bash
job-hunter update
job-hunter doctor
```

`job-hunter update` refreshes system-owned files (skills, workflows,
config schemas) and merges in any new `config/job_hunter.yml` keys. It never
touches your existing values, `profile/`, `outputs/`, or `.env`. Run
`job-hunter update --skills-only` or `--workflows-only` for a narrower
refresh. The same refresh is also a button — **Settings → Diagnostics →
Update workspace** — if you'd rather not use a terminal at all.

## 8. Common troubleshooting

- **`job-hunter` command not found** — restart your terminal, or run
  `python -m uv tool update-shell` again.
- **`job-hunter doctor` reports failures** — each failure line includes a
  suggested fix; work through them top to bottom.
- **No jobs found** — confirm a region is `enabled: true` in
  `config/job_hunter.yml` and your job titles aren't too narrow.

More troubleshooting specific to each mode is in SETUP_AGENT.md and
SETUP_LLM_API.md.

## 9. Where files live

```text
config/       your settings (mode, titles, regions, exclusions, scoring)
profile/      your resume, career context, and story bank
outputs/      discovered jobs, tailored files, and application state
.github/      GitHub Actions workflows
.claude/      agent skills for Claude Code
.agents/      agent skills for Codex
```

## 10. What not to edit manually

- `config/schemas/` — validation schemas, replaced on every update
- `.claude/skills/` and `.agents/skills/` — replaced on every update
- `outputs/state/jobs.db` — managed by the CLI; edit application status with
  `job-hunter applications update`, not a text editor
- The `<!-- JOBS_TABLE_START -->` / `<!-- JOBS_STATS_START -->` blocks in
  `README.md` — regenerated automatically

Everything else under `config/`, `profile/`, and `.env` is yours to edit
freely — updates never overwrite it.

## 11. Company Career Hunt (optional)

The dashboard's **Company Hunt** tab (under Job Candidates) is an optional, on-demand
alternative to the regular `find-jobs` hunt. Instead of searching job boards, it scrapes
the career pages of your enabled companies (falling back to a real browser, Playwright,
only for pages that need JavaScript). Its results are written to `outputs/state/jobs.db`
— the same database `find-jobs` uses — so they're deduped, screened, scored, and
tailored through the exact same pipeline as any other discovered job; there's nothing
separate to review or copy.

To use it: open `job-hunter dash` → **Job Candidates** → **Company Hunt** →
**Manage Companies**, add your own companies (under "My Companies") and/or opt into
bundled ones (under "Shared Catalog"), then click "Run Company Hunt" whenever you want.
You'll see each company checked in real time, plus a plain-English summary if any
couldn't be checked. New candidates show up alongside jobs from the regular hunt.
