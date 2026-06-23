# Setup Guide

## 1. Install job-hunter-kit

**Recommended — uv (handles PATH automatically):**

```bash
pip install uv
uv tool install job-hunter-kit
uv tool update-shell
```

Restart your terminal after `update-shell`, then verify:

```bash
job-hunter version
```

---

**Alternative — pip:**

```bash
pip install job-hunter-kit
```

If `job-hunter` is not found after install, your Python Scripts folder is not on PATH. Fix it for your OS:

**Windows:**
1. Open **Start** → search **"Environment Variables"** → **Edit the system environment variables**
2. Click **Environment Variables** → under **User variables**, select **Path** → **Edit** → **New**
3. Paste the path from the pip warning (e.g. `C:\Users\<you>\AppData\Local\...\Scripts`)
4. Click OK and restart your terminal

**macOS:**
Add this to `~/.zshrc` (or `~/.bash_profile` if using bash):
```bash
export PATH="$HOME/Library/Python/3.12/bin:$PATH"
```
Then run `source ~/.zshrc` or open a new terminal.

**Linux:**
Add this to `~/.bashrc`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```
Then run `source ~/.bashrc` or open a new terminal.

---

## 2. Create a workspace

```bash
job-hunter init my-workspace
cd my-workspace
```

## 3. Add your API keys

```bash
cp .env.example .env
```

Open `.env` and fill in your keys. You only need keys for providers you plan to use — leave the rest blank.

| Key | Provider | Used for |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic | Claude models |
| `OPENAI_API_KEY` | OpenAI | GPT models |
| `GOOGLE_API_KEY` | Google | Gemini models |
| `BRAVE_API_KEY` | Brave Search | Job discovery via web search |
| `TAVILY_API_KEY` | Tavily | Job discovery via web search |
| `EXA_API_KEY` | Exa | Job discovery via web search |
| `RAPIDAPI_KEY` | RapidAPI | JSearch job board |
| `ADZUNA_APP_ID` / `ADZUNA_API_KEY` | Adzuna | Adzuna job board |

For GitHub Actions runs, add these as repository secrets instead of in `.env`.

---

## 4. Choose your mode

Edit `config/job_hunter.yml` and set `mode:` to one of:

| Mode | What it does | Best for |
|---|---|---|
| `agent` | Python fetches candidates; you review and process them interactively with Claude Code | Daily hands-on job hunting |
| `llm-api` | Python runs the full pipeline autonomously — score, tailor, cover letter, PDF, tracker | Unattended runs and GitHub Actions |

---

## 5a. Agent mode setup

Open the workspace in **Claude Code** (or Codex), then follow these steps in order.

**Run health check:**
```
/setup doctor
```
Fix anything flagged before continuing.

**Run onboarding — configures `config/job_hunter.yml`:**
```
/setup onboard
```
You will be guided through: job titles, search regions, exclusion rules, scoring thresholds, and LLM provider/model choices.

**Add each search region:**
```
/setup region add <city-or-region-name>
```
Example: `/setup region add Berlin`, `/setup region add Remote`

**Fill in your career context:**

Open `profile/career_context.md` and write:
- Who you are and what you are targeting
- Resume style preferences
- Cover letter tone
- LinkedIn voice and outreach tone
- Any calibration notes (seniority, salary, work style)

**Build your story bank:**
```
/setup stories
```
Paste your raw work notes or existing STAR stories into the conversation. The skill structures them with stable IDs for use in tailoring and cover letters.

**Set resume style:**
```
/setup style
```

**Final health check:**
```bash
job-hunter config check
job-hunter doctor
```
Both must pass before running a hunt.

**Daily workflow:**
```bash
job-hunter hunt --region primary   # discover and enrich new jobs
job-hunter brief                   # write today's briefing
```
Then in Claude Code:
```
/job-hunter brief    # review the briefing
/job-hunter batch    # score and tailor the candidate queue
/job-hunter finalize # commit outputs
```

---

## 5b. LLM API mode setup

No agent session is required. The full pipeline runs from the CLI or GitHub Actions.

**Run health check:**
```bash
job-hunter doctor
```

**Configure `config/job_hunter.yml`:**

Open it and set:
- `mode: llm-api`
- At least one region under `regions:`
- Your job titles under `search.titles`
- LLM provider and model under `llm:`

**Fill in your career context:**

Open `profile/career_context.md` — same as agent mode above.

**Fill your story bank:**

Open `profile/story_bank.md` and add your STAR stories, or run `/setup stories` in Claude Code once to populate it, then switch to `llm-api` mode.

**Final health check:**
```bash
job-hunter config check
job-hunter doctor
```

**Daily workflow:**
```bash
job-hunter hunt --region primary
job-hunter brief
job-hunter dashboard --no-interactive
```
The pipeline scores, tailors, compiles PDFs, and updates the tracker automatically.

**GitHub Actions (optional):**

Add your API keys as repository secrets, then enable the workflows under `.github/workflows/`. The `find-jobs.yml` workflow runs `job-hunter hunt` on a schedule and commits results back to the repo.
