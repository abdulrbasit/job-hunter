# Job Hunter — Agent Mode Setup

This guide gets you from zero to reviewing tailored job candidates in Claude Code or Codex.

**Agent mode**: Python scrapes and filters jobs → you review, score, and tailor them interactively each day in VS Code with Claude Code or Codex. No LLM API keys required for the core workflow.

---

## Prerequisites

| Tool | Required | Notes |
|---|---|---|
| Python 3.12 or 3.13 | Yes | [python.org/downloads](https://www.python.org/downloads/) |
| VS Code | Yes | [code.visualstudio.com](https://code.visualstudio.com/) |
| Git | Yes | [git-scm.com/downloads](https://git-scm.com/downloads) |
| Claude Code **or** Codex extension | One required | See below |
| Docker Desktop | Recommended | PDF resume compilation |
| GitHub account | Recommended | Private workspace and backup |

**Install one AI extension in VS Code:**

- Claude Code: [marketplace.visualstudio.com](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code) — requires Claude subscription
- Codex: [marketplace.visualstudio.com](https://marketplace.visualstudio.com/items?itemName=openai.chatgpt) — requires ChatGPT Plus or API access

Enable auto-approve in your extension settings to allow tool use without per-step confirmation.

---

## 1. Install Job Hunter

Open a terminal and run:

```bash
pip install job-hunter-kit
```

Or with uv (faster):

```bash
pip install uv
uv tool install job-hunter-kit
```

Check the install worked:

```bash
job-hunter --version
```

If you see `command not found`, open a new terminal window and try again.

---

## 2. Create Your Private Workspace

Create a private GitHub repository (do not make it public — it will contain your resume and personal data).

Clone it locally:

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_PRIVATE_REPO.git
cd YOUR_PRIVATE_REPO
```

Initialise the workspace:

```bash
job-hunter init
```

This creates the folder structure: `config/`, `profile/`, `outputs/`, `.github/`, and skill files.

---

## 3. Open in VS Code

```bash
code .
```

Open the Claude Code or Codex panel in the left sidebar. Sign in if prompted.

---

## 4. Run Onboarding

In the Claude Code or Codex chat panel, type:

```
/setup onboard
```

Select **A — Agent mode** when asked. The onboarding skill walks you through:

1. Job titles to search for
2. Primary city and region
3. Exclusions (title terms, languages, companies, industries)
4. Resume layout and scoring settings
5. Career context (your background, targeting, writing style)
6. Story bank (STAR stories for tailoring)
7. Base resume (LaTeX, compiled to PDF via Docker)

This takes approximately 30–60 minutes in a single session.

---

## 5. API Keys (Optional)

Agent mode does not need LLM API keys. To enable more job sources:

```bash
cp .env.example .env
```

Open `.env` and add optional keys:

- `ADZUNA_APP_ID` + `ADZUNA_API_KEY` — [developer.adzuna.com](https://developer.adzuna.com/)
- `JOOBLE_API_KEY` — [jooble.org/api/about](https://jooble.org/api/about)
- `REED_API_KEY` (UK only) — [reed.co.uk/developers](https://www.reed.co.uk/developers/jobseeker)
- `BRAVE_API_KEY` — [api-dashboard.search.brave.com](https://api-dashboard.search.brave.com/app/keys)

---

## 6. Run Your First Hunt

```bash
job-hunter hunt --region primary
```

This scrapes job boards, filters by your config, and writes candidates to the database.

---

## 7. Review Candidates

In the Claude Code or Codex panel:

```
/job-hunter batch
```

This processes up to 15 candidates: scores each against your resume, tailors the resume for APPLY jobs, and writes a cover letter. Review the output in `outputs/jobs/`.

---

## Ongoing Workflow

1. Run `job-hunter hunt` daily (or set a GitHub Actions schedule for LLM API mode).
2. Run `/job-hunter batch` in VS Code to review new candidates.
3. Run `/job-hunter finalize` when ready to apply to move jobs to applied status.

---

## Troubleshooting

```bash
job-hunter doctor
```

Shows the status of every configured component. Fix any red items before the first hunt.

If you see `command not found` for `job-hunter`, check that the tool install location is in your PATH.

For detailed setup help, see the full `SETUP.md` guide in this workspace.
