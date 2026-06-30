# Job Hunter — LLM API Mode Setup

This guide gets you from zero to a running autonomous job search pipeline.

**LLM API mode**: Python handles everything — scraping, scoring, tailoring, cover letters, PDFs, and tracking — via GitHub Actions on a schedule. No interactive review session required.

Two setup paths:

- **With Claude Code or Codex** — run `/setup onboard` in VS Code for guided interactive setup.
- **Browser only (no Claude Code / Codex)** — follow the manual steps in this file using ChatGPT or Claude browser.

---

## Prerequisites

| Tool | Required | Notes |
|---|---|---|
| Python 3.12 or 3.13 | Yes | [python.org/downloads](https://www.python.org/downloads/) |
| Git | Yes | [git-scm.com/downloads](https://git-scm.com/downloads) |
| GitHub account | Yes | Private workspace + Actions runner |
| LLM API key | Yes | Anthropic, OpenAI, or Google |
| VS Code + Claude Code or Codex | Recommended | For guided setup — not required for running |
| Docker Desktop | Recommended | PDF resume compilation in CI |

---

## 1. Install Job Hunter

```bash
pip install job-hunter-kit
```

Or with uv:

```bash
pip install uv
uv tool install job-hunter-kit
```

Verify:

```bash
job-hunter --version
```

If you see `command not found`, open a new terminal window and try again.

---

## 2. Create Your Private Workspace

Create a **private** GitHub repository (do not make it public — it will contain your resume and personal data).

Clone it locally:

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_PRIVATE_REPO.git
cd YOUR_PRIVATE_REPO
```

Initialise the workspace:

```bash
job-hunter init
```

---

## 3. Setup — With Claude Code or Codex

Open the workspace in VS Code:

```bash
code .
```

In the Claude Code or Codex panel:

```
/setup onboard
```

Select **B — LLM API mode, with agent**. The skill walks you through config, profile files (career context, stories, resume), API keys, and GitHub Actions setup in one session (~60 minutes).

Skip to [Section 7 (GitHub Secrets)](#7-github-secrets) after onboarding is complete.

---

## 3. Setup — Browser Only (No Claude Code / Codex)

If you do not have Claude Code or Codex, configure everything manually using ChatGPT or Claude browser.

### 3a. Config file

Open `config/job_hunter.yml` in a text editor and set:

```yaml
mode: llm-api

job_titles:
  - Senior Product Manager    # replace with your actual titles
  - Head of Product

regions:
  primary:
    enabled: true
    primary: true
    location: "Berlin"        # your city
    country: "DE"             # ISO alpha-2 country code (see lookup below)
    search_lang: en           # en or local language code (e.g. de)
    description: "Primary region"

exclusions:
  title_terms:
    - intern
    - internship
    - trainee
    - working student
    - werkstudent
    - junior
    - principal
    - expert
    - chief product
  languages:
    - german                  # remove if you apply in German
  companies: []
  industries: []

scoring:
  min_fit_score: 70
  max_years_experience_required: 5
  batch_size: 15

llm:
  default_provider: anthropic   # or openai, google
  models:
    tailoring: claude-sonnet-4-6
    cover_letter: claude-sonnet-4-6
```

**Country code lookup (common cities):**

| City | Code | | City | Code |
|---|---|---|---|---|
| Munich / Berlin / Hamburg | DE | | London / Edinburgh | GB |
| Paris / Lyon | FR | | Amsterdam / Rotterdam | NL |
| Zurich / Geneva / Bern | CH | | Vienna / Graz | AT |
| Stockholm / Gothenburg | SE | | Oslo | NO |
| Copenhagen | DK | | Helsinki | FI |
| Warsaw / Krakow | PL | | Prague | CZ |
| Lisbon / Porto | PT | | Dublin | IE |
| Brussels | BE | | Madrid / Barcelona | ES |
| Milan / Rome | IT | | Toronto / Vancouver | CA |
| Sydney / Melbourne | AU | | New York / San Francisco | US |
| Dubai | AE | | Bangalore / Mumbai | IN |
| Singapore | SG | | Tokyo / Osaka | JP |
| Seoul | KR | | São Paulo / Rio | BR |

### 3b. Career context

Open [Claude.ai](https://claude.ai) or [ChatGPT](https://chatgpt.com) in your browser.

Open `.claude/skills/setup/modes/context.md` in a text editor, copy the full content, and paste it into the browser chat. Follow the instructions. When done, paste the result into `profile/career_context.md`.

### 3c. Story bank

Open a new browser session. Open `.claude/skills/setup/modes/stories.md`, copy it, and paste into the chat. Follow the instructions. Paste the result into `profile/story_bank.md`.

### 3d. Base resume

Open a new browser session. Open `.claude/skills/setup/modes/resume.md`, copy it, and paste into the chat along with your `career_context.md` and `story_bank.md` content. Follow the instructions. Paste the LaTeX output into `profile/resume_double_column.tex` (or `resume_single_column.tex`).

---

## 4. API Keys — Local

```bash
cp .env.example .env
```

Open `.env` and fill in at minimum your LLM provider key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Optional job board keys for more results:

```
ADZUNA_APP_ID=
ADZUNA_API_KEY=
JOOBLE_API_KEY=
REED_API_KEY=        # UK only
BRAVE_API_KEY=
TAVILY_API_KEY=
EXA_API_KEY=
```

Get keys from:
- Anthropic: [console.anthropic.com](https://console.anthropic.com/)
- OpenAI: [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- Adzuna: [developer.adzuna.com](https://developer.adzuna.com/)
- Brave Search: [api-dashboard.search.brave.com](https://api-dashboard.search.brave.com/app/keys)
- Jooble: [jooble.org/api/about](https://jooble.org/api/about)
- Reed: [reed.co.uk/developers](https://www.reed.co.uk/developers/jobseeker) (UK only)

---

## 7. GitHub Secrets

GitHub Actions cannot read your local `.env` file. Add each key as a GitHub Secret.

1. Open your repository on GitHub.
2. Go to **Settings → Secrets and variables → Actions → New repository secret**.
3. Add each key from `.env` using the exact same name.

Required:

| Secret | Provider |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic Claude |
| `OPENAI_API_KEY` | OpenAI (if using OpenAI) |
| `GOOGLE_API_KEY` | Google (if using Google) |

Optional (more job sources):

| Secret | Service |
|---|---|
| `BRAVE_API_KEY` | Brave Search |
| `TAVILY_API_KEY` | Tavily |
| `EXA_API_KEY` | Exa |
| `ADZUNA_APP_ID` + `ADZUNA_API_KEY` | Adzuna |
| `JOOBLE_API_KEY` | Jooble |
| `REED_API_KEY` | Reed (UK) |

---

## 8. Enable GitHub Actions Schedule

Open `.github/workflows/find-jobs.yml` in a text editor. Find these lines:

```yaml
  # schedule:
  #   - cron: "0 18 * * 0-4"   # 20:00 Berlin (CEST) / 19:00 CET - Mon-Fri
```

Remove the `#` from both lines:

```yaml
  schedule:
    - cron: "0 18 * * 0-4"   # 20:00 Berlin (CEST) / 19:00 CET - Mon-Fri
```

Adjust the cron time to suit your timezone. Then commit and push.

---

## 9. Run Your First Hunt

**Locally:**

```bash
job-hunter hunt --region primary
```

**Via GitHub Actions (manual trigger):**

Go to your repository → **Actions → Find Jobs → Run workflow**.

After the run, check `outputs/` for scored jobs, tailored resumes, and cover letters.

---

## Troubleshooting

```bash
job-hunter doctor
```

Shows the status of every configured component. Fix any red items before the first run.

For detailed setup help, see the full `SETUP.md` guide in this workspace.
