# Setup Guide

---

## Prerequisites

Install these before anything else.

| Tool | Why you need it | Download |
|---|---|---|
| **Python 3.11+** | Runs the job-hunter pipeline | [python.org/downloads](https://www.python.org/downloads/) |
| **VS Code** | Open the workspace and run AI skills | [code.visualstudio.com](https://code.visualstudio.com/) |
| **Docker Desktop** | Compiles your resume PDF without installing LaTeX | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) |
| **Git** | Saves and syncs your workspace to GitHub | [git-scm.com/downloads](https://git-scm.com/downloads) |
| **GitHub Desktop** (optional) | Easier git for non-technical users | [desktop.github.com](https://desktop.github.com/) |

**VS Code extensions to install** (open VS Code → Extensions sidebar → search each name):
- **Claude Code** — runs the `/setup`, `/job-hunter`, and `/linkedin` skills
- **LaTeX Workshop** — compiles your resume PDF inside VS Code via Docker

Once Docker Desktop is running and LaTeX Workshop is installed, your workspace already has a `.vscode/settings.json` that configures it to use Docker automatically — no LaTeX installation needed.

---

## 1. Install job-hunter-kit

**Recommended — uv (handles PATH automatically):**

```bash
pip install uv
uv tool install job-hunter-kit
uv tool update-shell
```

If `pip` itself is not on PATH:
```bash
python -m pip install uv
python -m uv tool install job-hunter-kit
python -m uv tool update-shell
```

Restart your terminal after `update-shell`, then verify:

```bash
job-hunter version
```

---

**Alternative — pip:**

```bash
pip install job-hunter-kit
# or:
python -m pip install job-hunter-kit
```

If `job-hunter` is not found after install, your Python Scripts folder is not on PATH.

**Windows:** Open Start → search "Environment Variables" → Edit the system environment variables → click Environment Variables → under User variables select Path → Edit → New → paste the path from the pip warning (e.g. `C:\Users\<you>\AppData\Local\...\Scripts`) → click OK → restart your terminal.

**macOS:** Add `export PATH="$HOME/Library/Python/3.12/bin:$PATH"` to `~/.zshrc`, then run `source ~/.zshrc`.

**Linux:** Add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc`, then run `source ~/.bashrc`.

---

## 2. Create a workspace

```bash
job-hunter init FirstName.LastName-Resume
cd FirstName.LastName-Resume
```

Replace `FirstName.LastName-Resume` with your own name, e.g. `Abdul.Basit-Resume`.

---

## 3. Put your workspace on GitHub

The daily job-hunting pipeline runs on GitHub Actions — a free automated service that runs on GitHub's servers instead of your computer. Your workspace needs to be a GitHub repository for this to work.

**If you are not familiar with git, use GitHub Desktop.** It handles everything without the command line.

### Option A — GitHub Desktop (recommended if you're new to git)

1. Download and install [GitHub Desktop](https://desktop.github.com/)
2. Sign in with your GitHub account (or create one at [github.com](https://github.com) — it's free)
3. In GitHub Desktop: **File → Add Local Repository** → select your workspace folder
4. GitHub Desktop will say "This directory does not appear to be a Git repository" — click **Create a Repository**
5. Fill in the name, then click **Publish repository**
6. Choose **Private** (your resume and job applications should stay private) → click **Publish**

Done. Your workspace is now a private GitHub repository.

### Option B — Command line

```bash
git init
git add .
git commit -m "Initial workspace"
gh repo create FirstName.LastName-Resume --private --source=. --push
```

If you don't have the `gh` CLI: [cli.github.com](https://cli.github.com)

---

## 4. Add your API keys

You need two things: API keys in GitHub Secrets (for the automated pipeline) and in a local `.env` file (for running anything locally).

### GitHub Secrets (required for the pipeline)

GitHub Secrets store your keys securely on GitHub. The pipeline reads them automatically when it runs.

1. Go to your repository on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
3. Add each key you have:

| Secret name | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) |
| `GOOGLE_API_KEY` | [aistudio.google.com](https://aistudio.google.com) |
| `BRAVE_API_KEY` | [brave.com/search/api](https://brave.com/search/api) |
| `TAVILY_API_KEY` | [tavily.com](https://tavily.com) |
| `EXA_API_KEY` | [exa.ai](https://exa.ai) |
| `FIRECRAWL_API_KEY` | [firecrawl.dev](https://firecrawl.dev) |
| `RAPIDAPI_KEY` | [rapidapi.com](https://rapidapi.com) |
| `ADZUNA_APP_ID` + `ADZUNA_API_KEY` | [developer.adzuna.com](https://developer.adzuna.com) |
| `JOOBLE_API_KEY` | [jooble.org/api](https://jooble.org/api) |
| `REED_API_KEY` | [reed.co.uk/developers](https://reed.co.uk/developers) |

You only need keys for providers you actually plan to use — leave the rest out.

### Local `.env` file (for optional local runs)

```bash
cp .env.example .env
```

Open `.env` and fill in the same keys. This file is already in `.gitignore` — it will never be committed.

---

## 5a. Agent mode setup

Agent mode is the interactive approach: the Python pipeline fetches and enriches job candidates, and you review and process them with Claude Code (or Codex, Gemini CLI, or GitHub Copilot).

Open the workspace in **Claude Code** (or your preferred AI coding tool), then run these skills in order.

---

### Step 1 — Onboard: configure your workspace

```
/setup onboard
```

This walks you through everything needed in `config/job_hunter.yml`: your mode, job titles, resume layout (single or double column), search regions, exclusion rules, scoring thresholds, and LLM provider/model choices.

See `examples/config/job_hunter.yml` for a filled reference.

---

### Step 2 — Career context: your positioning and writing rules

```
/setup context
```

This creates `profile/career_context.md` — a structured document that tells the AI how to write for you: what you're targeting, how you write, your cover letter voice, your LinkedIn tone, interview prep notes, and which metrics you're allowed to use.

This file is the single most important input for tailoring quality. Spend time on it.

See `examples/profile/career_context.md` for a fully filled reference.

---

### Step 3 — Add your stories

```
/setup stories
```

Paste your raw work notes, existing CV bullets, or STAR-format stories into the conversation. The skill structures them with stable IDs. These stories are the raw material the resume builder and tailoring pipeline draw from — do this before building your resume.

---

### Step 4 — Build your base resume

```
/setup resume
```

This reads your career context and story bank, then guides you through building your base resume as a `.tex` file. Works for both single-column and double-column layouts.

See `examples/profile/resume_double_column.tex` and `examples/profile/resume_single_column.tex` for references.

---

### Step 4b — Compile to PDF

Once the `.tex` file is written, compile it to check the layout.

**In VS Code with LaTeX Workshop + Docker (recommended):**
1. Open your resume `.tex` file in VS Code (`profile/resume_double_column.tex` or `resume_single_column.tex`)
2. Make sure **Docker Desktop is running**
3. Press `Ctrl+Alt+B` (Windows/Linux) or `Cmd+Alt+B` (macOS) — LaTeX Workshop compiles it automatically using the Docker image
4. The PDF opens in the side panel. If it looks wrong, run `/setup style` to adjust

**If you don't have LaTeX Workshop/Docker set up yet:**
The `/setup resume` skill has a built-in compile step at the end — it will attempt `pdflatex` locally if available, and tell you what to install if not. You can also skip this and compile later once Docker Desktop is running.

---

### Step 5 — Style your resume (optional)

```
/setup style
```

Adjust colours, font, font size, column ratio (double-column only), and paper format. Fully interactive with before/after preview.

---

### Step 6 — Health check

```
/setup doctor
```

Checks that your config, resume, and career context are all filled — not just present, but actually containing real content. Fix anything flagged before continuing.

---

## 5b. LLM API mode setup

LLM API mode runs the full pipeline autonomously: score, tailor, cover letter, PDF, tracker. No agent session needed. This is the mode that runs inside GitHub Actions.

**Run `/setup onboard` first** (same as agent mode) and choose `llm-api` as your mode. Then:

1. Fill in `profile/career_context.md` — run `/setup context` in Claude Code once, or edit the file directly following the format in `examples/profile/career_context.md`
2. Build your story bank — run `/setup stories` in Claude Code once to populate `profile/story_bank.md`
3. Build your resume — run `/setup resume` in Claude Code once (reads career context + stories, so do steps 1 and 2 first)
4. Run a health check:

```bash
job-hunter config check
job-hunter doctor
```

Both must pass before the pipeline will run cleanly.

---

## 6. Commit and push your workspace

Once setup is done, save everything to GitHub. This is what triggers the automated pipeline and keeps your work backed up.

If you have never used git before, think of it this way: **commit** = save a snapshot locally, **push** = send that snapshot to GitHub.

### Using GitHub Desktop (recommended)

1. Open **GitHub Desktop**
2. You will see a list of changed files on the left — these are everything you just set up (config, career context, resume, stories, skills)
3. At the bottom left, there is a box that says **"Summary (required)"** — type a short note like:
   `Initial setup — config, career context, resume, stories`
4. Click **Commit to main**
5. Click **Push origin** (top right button)

That's it. Your workspace is now on GitHub.

### Using the command line

```bash
git add config/ profile/ .claude/ .agents/ .gemini/ .github/ .gitignore .env.example README.md AGENTS.md CLAUDE.md GEMINI.md
git commit -m "Initial setup — config, career context, resume, stories"
git push
```

> **Note:** Never add your `.env` file — it contains your API keys and is already excluded by `.gitignore`.

---

## 7. Test your GitHub Actions pipeline

Before relying on the automated pipeline, run it once manually to confirm everything is wired up.

1. Go to your repository on **GitHub.com**
2. Click the **Actions** tab at the top
3. In the left sidebar, click **Find Jobs**
4. Click **Run workflow** (top right of the workflow table) → **Run workflow**
5. Wait for it to finish (usually 2–5 minutes) — a green checkmark means it worked

If it fails, click the failed run → click the failing step to read the error log. Common causes: a missing API key secret, a config validation error, or a region with no results.

---

## 8. Daily workflow

The daily job-hunting loop is: push your workspace to GitHub, let the pipeline run overnight, pull the results in the morning, then review and process them in Claude Code.

### Push (triggers the pipeline)

**GitHub Desktop:**
1. Open GitHub Desktop
2. Write a short note in the "Summary" box (e.g. "Add new story, update exclusions")
3. Click **Commit to main**
4. Click **Push origin**

**Command line:**
```bash
git add -p          # review what changed
git commit -m "Update config: add Munich region"
git push
```

The `find-jobs.yml` workflow runs automatically on a schedule (check `.github/workflows/find-jobs.yml` for the cron time). You can also trigger it manually at any time from the Actions tab (see Section 7 above).

### Pull (after the pipeline runs)

**GitHub Desktop:** Click **Fetch origin** → **Pull origin**

**Command line:**
```bash
git pull
```

### Review and process (in Claude Code)

```
/job-hunter brief     # read today's job briefing
/job-hunter batch     # score and tailor the candidate queue
/job-hunter finalize  # commit and clean up outputs
```

That's the full loop. Most days this takes 15–30 minutes.

---

## 8. Upgrading

When a new version of job-hunter-kit is released, upgrade the package first, then update your workspace skills.

**Upgrade the package:**

```bash
uv tool upgrade job-hunter-kit
# or with pip:
pip install --upgrade job-hunter-kit
```

**Then update your workspace** (run inside your workspace directory):

```bash
job-hunter update
```

This updates both agent skills (`.claude/skills/`) and GitHub Actions workflows (`.github/workflows/`) in one step. Your cron schedule, config, resume, story bank, and career context are never touched.

You can also run each part individually if needed:
```bash
job-hunter update-skills     # skills only
job-hunter update-workflows  # workflows only
```

---

## 9. Local testing (optional)

You don't need to run the pipeline locally — that's what GitHub Actions is for. But if you want to test locally before pushing:

```bash
job-hunter hunt --region primary
job-hunter brief
```

You need your `.env` file populated with API keys for local runs.

**Run the test suite** (requires dev dependencies):

```bash
uv sync --extra dev
uv run pytest tests/ -q --tb=short
```

All tests must pass before pushing if you've made config or code changes.
