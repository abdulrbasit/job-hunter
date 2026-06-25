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

**VS Code extension to install** (open VS Code → Extensions sidebar → search):
- **LaTeX Workshop** — compiles your resume PDF inside VS Code via Docker

Once Docker Desktop is running and LaTeX Workshop is installed, your workspace already has a `.vscode/settings.json` that configures it to use Docker automatically — no LaTeX installation needed.

### AI coding assistant (agent mode only — pick one)

You need one AI coding tool to run the interactive review workflow. **You only need one.**

| Tool | Cost | Slash skills | How it works |
|---|---|---|---|
| **Gemini CLI** | **Free** (Google account, generous daily quota) | ✓ Full | VS Code panel + slash commands |
| **Claude Code** | Paid (Claude Pro ~$20/mo or API credits) | ✓ Full | VS Code extension + slash commands |
| **Codex CLI** | Paid (OpenAI API, pay-per-use) | ✓ Full | CLI + slash commands |
| **GitHub Copilot app** | Free tier / Paid ($10/mo) | ✗ No custom skills | Standalone desktop app, agent mode |

**Recommendation:** Start with Gemini CLI — it's free, supports the full skill workflow, and you can switch later.

**Gemini CLI:** Install [Node.js 20+](https://nodejs.org/en/download/) (includes npm), restart your terminal, then `npm install -g @google/gemini-cli`. Run `gemini` to sign in with your Google account.

**Claude Code:** VS Code → Extensions sidebar → search **Claude Code** → Install. Sign in with your Anthropic account.

**Codex CLI:** `npm install -g @openai/codex` — requires an OpenAI API key set as `OPENAI_API_KEY`.

See [COMMANDS.md](COMMANDS.md) for the full skill reference.

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

**Windows:** Open Start → search "Environment Variables" → Edit system environment variables → Environment Variables → under User variables select **Path** → Edit → New → paste the path from the pip warning (e.g. `C:\Users\<you>\AppData\Local\...\Scripts`) → OK → restart your terminal.

**macOS:** Add `export PATH="$HOME/Library/Python/3.12/bin:$PATH"` to `~/.zshrc`, then `source ~/.zshrc`.

**Linux:** Add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc`, then `source ~/.bashrc`.

---

## 2. Create a workspace

```bash
job-hunter init FirstName.LastName-Resume
cd FirstName.LastName-Resume
```

Replace `FirstName.LastName-Resume` with your own name, e.g. `Abdul.Basit-Resume`.

---

## 3. Put your workspace on GitHub

The daily pipeline runs on GitHub Actions — a free service that runs on GitHub's servers instead of your computer. Your workspace needs to be a GitHub repository.

**If you are not familiar with git, use GitHub Desktop.** It handles everything without the command line.

### Option A — GitHub Desktop (recommended if you're new to git)

1. Download and install [GitHub Desktop](https://desktop.github.com/)
2. Sign in with your GitHub account (or create one at [github.com](https://github.com) — it's free)
3. In GitHub Desktop: **File → Add Local Repository** → select your workspace folder
4. GitHub Desktop will say "This directory does not appear to be a Git repository" — click **Create a Repository**
5. Fill in the name, then click **Publish repository**
6. Choose **Private** (your resume and job applications should stay private) → click **Publish**

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

You need API keys in GitHub Secrets (for the automated pipeline) and in a local `.env` file (for running anything locally).

### GitHub Secrets (required for the pipeline)

GitHub Secrets store your keys securely on GitHub. The pipeline reads them automatically when it runs.

1. Go to your repository on GitHub
2. Click **Settings → Secrets and variables → Actions → New repository secret**
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

Agent mode is the interactive approach: the pipeline fetches job candidates, and you review and process them with your AI tool.

Open the workspace in your AI tool (Claude Code, Gemini CLI, or Codex), then run these skills in order.

---

### Step 1 — Onboard: configure your workspace

```
/setup onboard
```

Walks you through everything needed in `config/job_hunter.yml`: your mode, job titles, resume layout, search regions, exclusion rules, scoring thresholds, and LLM provider/model choices.

See `examples/config/job_hunter.yml` for a filled reference.

---

### Step 2 — Career context: your positioning and writing rules

```
/setup context
```

Creates `profile/career_context.md` — a structured document that tells the AI how to write for you: what you're targeting, how you write, your cover letter voice, your LinkedIn tone, interview prep notes, and which metrics you're allowed to use.

**This is the single most important input for tailoring quality. Spend time on it.**

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

Reads your career context and story bank, then guides you through building your base resume as a `.tex` file. Works for both single-column and double-column layouts.

See `examples/profile/resume_double_column.tex` and `examples/profile/resume_single_column.tex` for references.

---

### Step 4b — Compile to PDF

**In VS Code with LaTeX Workshop + Docker (recommended):**
1. Open your resume `.tex` file in VS Code (`profile/resume_double_column.tex` or `resume_single_column.tex`)
2. Make sure **Docker Desktop is running**
3. Press `Ctrl+Alt+B` (Windows/Linux) or `Cmd+Alt+B` (macOS) — LaTeX Workshop compiles it automatically using Docker
4. The PDF opens in the side panel. If it looks wrong, run `/setup style`

**If you don't have LaTeX Workshop/Docker set up yet:** The `/setup resume` skill has a built-in compile step — it will attempt `pdflatex` locally if available. You can also skip this and compile later once Docker Desktop is running.

---

### Step 5 — Style your resume (optional)

```
/setup style
```

Adjust colours, font, font size, column ratio (double-column only), and paper format. Interactive with before/after preview.

---

### Step 6 — Health check

```
/setup doctor
```

Checks that your config, resume, and career context are all filled with real content. Fix anything flagged before continuing.

---

## 5a-ii. Reviewing results with your AI tool

After the pipeline runs on GitHub Actions and you pull the latest changes, open your workspace in your AI tool.

See [COMMANDS.md](COMMANDS.md) for the full skill reference. Quick loop:

```
/job-hunter brief     # read today's briefing — what was found and why
/job-hunter batch     # score and tailor the candidate queue one by one
/job-hunter finalize  # commit outputs and clean up the queue
```

---

## 5b. LLM API mode setup

LLM API mode runs the full pipeline autonomously: score, tailor, cover letter, PDF, tracker. No agent session needed. This is the mode that runs inside GitHub Actions.

**Run `/setup onboard` first** (same as agent mode) and choose `llm-api` as your mode. Then:

1. Fill in `profile/career_context.md` — run `/setup context` in your AI tool once, or edit the file directly following `examples/profile/career_context.md`
2. Build your story bank — run `/setup stories` once to populate `profile/story_bank.md`
3. Build your resume — run `/setup resume` once (reads career context + stories, so do steps 1 and 2 first)
4. Run a health check:

```bash
job-hunter config check
job-hunter doctor
```

Both must pass before the pipeline will run cleanly.

---

## 6. Commit and push your workspace

Once setup is done, save everything to GitHub. This is what triggers the automated pipeline.

If you have never used git before: **commit** = save a snapshot locally, **push** = send that snapshot to GitHub.

### Using GitHub Desktop (recommended)

1. Open **GitHub Desktop**
2. You will see a list of changed files on the left
3. In the **Summary** box at the bottom, type: `Initial setup — config, career context, resume, stories`
4. Click **Commit to main**
5. Click **Push origin** (top right)

### Using the command line

```bash
git add config/ profile/ .claude/ .agents/ .gemini/ .github/ .gitignore .env.example README.md AGENTS.md CLAUDE.md GEMINI.md
git commit -m "Initial setup — config, career context, resume, stories"
git push
```

> **Never add your `.env` file** — it contains your API keys and is already excluded by `.gitignore`.

---

## 7. Test your GitHub Actions pipeline

Before relying on the automated pipeline, run it once manually to confirm everything is wired up.

1. Go to your repository on **GitHub.com**
2. Click the **Actions** tab
3. In the left sidebar, click **Find Jobs**
4. Click **Run workflow** → **Run workflow**
5. Wait for it to finish (usually 2–5 minutes) — a green checkmark means it worked

If it fails, click the failed run → click the failing step to read the error log. Common causes: a missing API key secret, a config validation error, or a region with no results.

---

## 8. Daily workflow

Push your workspace to GitHub, let the pipeline run overnight, pull the results in the morning, then review and process them with your AI tool.

### Push (triggers the pipeline)

**GitHub Desktop:**
1. Open GitHub Desktop
2. Write a short note in the Summary box (e.g. "Add new story, update exclusions")
3. Click **Commit to main**
4. Click **Push origin**

**Command line:**
```bash
git add -p
git commit -m "Update config: add Munich region"
git push
```

The `find-jobs.yml` workflow runs on a schedule — check `.github/workflows/find-jobs.yml` for the cron time. You can also trigger it manually from the Actions tab.

### Pull (after the pipeline runs)

**GitHub Desktop:** Click **Fetch origin** → **Pull origin**

**Command line:** `git pull`

### Review and process

Open your workspace in your AI tool and run the daily loop — see [COMMANDS.md](COMMANDS.md) for the full skill reference. Most days 15–30 minutes.

---

## 9. Upgrading

When a new version of job-hunter-kit is released:

```bash
uv tool upgrade job-hunter-kit
# or with pip:
pip install --upgrade job-hunter-kit
```

Then update your workspace (run inside your workspace directory):

```bash
job-hunter update
```

This updates both agent skills (`.claude/skills/`) and GitHub Actions workflows (`.github/workflows/`) in one step. Your cron schedule, config, resume, story bank, and career context are never touched.

```bash
job-hunter update-skills     # skills only
job-hunter update-workflows  # workflows only
```

---

## 10. Local testing (optional)

You don't need to run the pipeline locally — that's what GitHub Actions is for. But if you want to test locally:

```bash
job-hunter hunt --region primary
job-hunter brief
```

You need your `.env` file populated with API keys for local runs.
