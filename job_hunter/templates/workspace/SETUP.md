# Job Hunter Setup Guide

This guide is written for non-technical users. Follow it from top to bottom the first time.

Job Hunter supports two complete ways of working:

- **Agent mode**: recommended. You review jobs interactively in VS Code with Claude Code or Codex.
- **LLM API mode**: fully automated. GitHub Actions scores jobs, tailors resumes, writes cover letters, and creates application files.

The normal `job-hunter-kit` installation supports both modes. Guided
onboarding asks which mode and provider you want, then creates
`config/job_hunter.yml` from your answers.

Fastest path:

1. Install [Python 3.12+](https://www.python.org/downloads/).
2. Install Job Hunter.
3. Create and open your workspace.
4. Run `/setup onboard` in Claude Code or Codex.

---

## Before you begin

You will create a private workspace containing:

- your resume;
- your career context;
- your work stories;
- job-search settings;
- discovered jobs;
- tailored application files;
- application tracking data.

Keep this workspace private because it contains personal information.

Job Hunter never submits applications, posts on LinkedIn, or contacts people automatically.

---

## Prerequisites

Install these tools before continuing.

| Tool | Required? | Why |
|---|---:|---|
| Python 3.12+ | Yes | Runs Job Hunter |
| VS Code | Yes for agent mode | Opens workspace and runs AI skills |
| Git | Yes | Saves workspace history |
| GitHub account | Recommended | Runs scheduled searches and stores private workspace |
| GitHub Desktop | Recommended for beginners | Easier Git interface |
| Docker Desktop | Recommended | Compiles PDF resumes and runs browser/search services |
| Claude Code or Codex | One required for agent setup | Guides onboarding and interactive review |

Download links:

- Python 3.12+: <https://www.python.org/downloads/>
- VS Code: <https://code.visualstudio.com/>
- Git: <https://git-scm.com/downloads>
- GitHub Desktop: <https://desktop.github.com/>
- Docker Desktop: <https://www.docker.com/products/docker-desktop/>
- Claude Code extension: <https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code>
- Codex extension: <https://marketplace.visualstudio.com/items?itemName=openai.chatgpt>
- LaTeX Workshop extension: <https://marketplace.visualstudio.com/items?itemName=James-Yu.latex-workshop>

### Check Python version

Open a terminal and run:

```bash
python --version
```

Expected result:

```text
Python 3.12.x
```

Python 3.13 also works. Python 3.14 is not yet supported — use 3.12 or 3.13. Python 3.11 and older are not supported.

### Windows terminal

Use PowerShell, Windows Terminal, or the terminal inside VS Code.

If `python` opens Microsoft Store instead of showing a version:

1. Install Python from python.org.
2. During installation, enable **Add Python to PATH**.
3. Close and reopen the terminal.
4. Run `python --version` again.

### macOS terminal

Use Terminal or the terminal inside VS Code.

If `python` is unavailable but `python3` works, use `python3` in installation commands.

### Linux terminal

Use your normal terminal. Install Python 3.12 through your distribution package manager if needed.

---

## 1. Install Job Hunter

### Recommended installation with uv

First install uv:

```bash
python -m pip install uv
```

Then install Job Hunter:

```bash
python -m uv tool install job-hunter-kit
python -m uv tool update-shell
```

Close and reopen the terminal after `update-shell`.

Verify installation:

```bash
job-hunter version
```

You should see the installed Job Hunter version and update instructions.

### Alternative installation with pip

```bash
python -m pip install job-hunter-kit
```

If `job-hunter` is not recognized, Python's Scripts directory is not on your PATH.

On Windows, the pip warning normally shows the missing Scripts directory. Add that directory to the user `Path` environment variable, then restart the terminal.

On macOS or Linux, use uv if possible because it handles the command path more reliably.

### `job-hunter` command not found

For a uv installation, run:

```bash
python -m uv tool update-shell
```

Close every terminal and VS Code window, reopen them, then run:

```bash
job-hunter version
```

If still missing, print uv's executable directory:

```bash
python -m uv tool dir --bin
```

Add that directory to your user `PATH`, then restart the terminal. Reinstall
only if `python -m uv tool list` does not show `job-hunter-kit`:

```bash
python -m uv tool install --force job-hunter-kit
```

### What gets installed

The standard package includes:

- agent mode support;
- LLM API mode support;
- Anthropic, OpenAI, and Google LLM provider SDKs;
- job-board and ATS adapters;
- configuration validation;
- workspace templates;
- bundled Claude Code and Codex skills.

Optional extras:

```bash
python -m uv tool install "job-hunter-kit[browser]"
```

This adds Playwright for browser-backed career pages.

```bash
python -m uv tool install "job-hunter-kit[secrets]"
```

This adds operating-system keyring support.

```bash
python -m uv tool install "job-hunter-kit[all]"
```

This installs all optional features.

---

## 2. Create your workspace

Choose a private folder name, normally based on your name:

```bash
job-hunter init FirstName.LastName-Resume
cd FirstName.LastName-Resume
```

Example:

```bash
job-hunter init Abdul.Basit-Resume
cd Abdul.Basit-Resume
```

The workspace contains:

```text
config/       machine-readable search settings
profile/      resume, career context, and story bank
outputs/      discovered jobs and application files
.github/      GitHub Actions workflows
.claude/      interactive agent skills
.agents/      Codex-compatible skills
```

Run the first health check:

```bash
job-hunter doctor
```

Several failures are normal before onboarding. Each failure should include a suggested fix.

---

## 3. Open workspace in VS Code

From inside the workspace:

```bash
code .
```

If `code` is not recognized:

1. Open VS Code manually.
2. Select **File → Open Folder**.
3. Choose your Job Hunter workspace.

Install one AI extension:

- [Claude Code](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code)
- [Codex](https://marketplace.visualstudio.com/items?itemName=openai.chatgpt)

Sign in using the extension's instructions.

Agent mode can use the extension subscription/account flow. It does not require LLM API keys for normal interactive processing.

**Recommended model tier:** For Claude Code, choose **claude-sonnet-4-6** or the equivalent Standard/Sonnet tier in the model selector. For Codex, choose **gpt-4o-mini** or the Standard tier. Both balance quality and cost well for daily job-search use.

---

## 4. Put workspace on GitHub

Use a **private** GitHub repository.

GitHub is recommended because:

- it backs up your workspace;
- GitHub Actions can search on a schedule;
- generated job results can be committed automatically;
- you can review changes before accepting them.

### GitHub Desktop method

This is recommended for non-technical users.

1. Install and open GitHub Desktop.
2. Sign in to your GitHub account.
3. Select **File → Add Local Repository**.
4. Choose your Job Hunter workspace.
5. If prompted, choose **Create a Repository**.
6. Enter a repository name.
7. Click **Publish repository**.
8. Keep **Private repository** enabled.

### Command-line method

```bash
git init
git add .
git commit -m "Initial Job Hunter workspace"
```

If GitHub CLI is installed:

```bash
gh repo create FirstName.LastName-Resume --private --source=. --push
```

Never make a workspace repository public unless you have removed all personal data.

---

## 5. Choose your mode

Run `/setup onboard`; it asks for
`agent` or `llm-api`, asks which provider you want, then writes only relevant
values to `config/job_hunter.yml`.

### Agent mode

Best for most users.

Python finds jobs and prepares candidate data. You use `/job-hunter` skills to score, review, tailor, and finalize jobs with human oversight.

Benefits:

- easier to understand;
- interactive review;
- no LLM API billing required for normal agent actions;
- you can correct context before files are generated;
- safer for first-time users.

### LLM API mode

Best for unattended automation.

Python calls configured LLM APIs directly and runs the whole pipeline:

```text
search → validate → score → tailor → cover letter → PDF → tracker
```

Requirements:

- one supported LLM API key;
- provider and model settings in config;
- Docker recommended for PDF creation;
- GitHub Secrets for GitHub Actions.

---

## 6. Agent mode setup

Open the workspace in VS Code with Claude Code or Codex.

Complete these steps in order.

### Step 1: Guided onboarding

Run:

```text
/setup onboard
```

This configures:

- agent or LLM API mode;
- target job titles;
- primary search region;
- additional regions;
- excluded companies;
- excluded title terms;
- excluded industries;
- language exclusions;
- scoring threshold;
- maximum experience requirement;
- batch size;
- preferred resume layout;
- optional profile photo;
- LLM provider and models used by API mode.

When asked for a country, use a two-letter country code such as:

- `DE` Germany;
- `US` United States;
- `CA` Canada;
- `GB` United Kingdom;
- `SG` Singapore;
- `AE` United Arab Emirates.

### Step 2: Career context

Run:

```text
/setup context
```

This creates or improves:

```text
profile/career_context.md
```

Include:

- current role;
- years of experience;
- target roles;
- strongest achievements;
- industries;
- product or technical strengths;
- preferred writing tone;
- facts that must never be invented;
- relocation and remote-work preferences;
- cover-letter style;
- interview positioning;
- LinkedIn positioning.

Spend time here. Better context produces better scores and application materials.

### Step 3: Story bank

Run:

```text
/setup stories
```

Provide:

- existing resume bullets;
- project notes;
- performance-review notes;
- achievements;
- metrics;
- difficult situations;
- leadership examples;
- launches;
- failures and lessons;
- customer or stakeholder stories.

The skill converts notes into reusable evidence with stable story IDs.

Only verified facts should enter final stories.

### Step 4: Build base resume

Run:

```text
/setup resume
```

The skill reads career context and story bank, then helps build:

```text
profile/resume_double_column.tex
```

or:

```text
profile/resume_single_column.tex
```

Use single-column layout when ATS compatibility matters most.

Use double-column layout when compact visual presentation matters more.

### Step 5: Resume styling

Optional:

```text
/setup style
```

You can adjust:

- colors;
- font;
- font size;
- spacing;
- paper size;
- column proportions;
- profile photo.

### Step 6: Compile PDF

Recommended method:

1. Start Docker Desktop.
2. Install the LaTeX Workshop VS Code extension.
3. Open the resume `.tex` file.
4. Run **Terminal → Run Build Task** or press `Ctrl+Shift+B`.

The workspace build task runs `pdflatex` inside
`texlive/texlive:latest-full`; no local LaTeX installation is needed.

### Step 7: Final setup check

Run:

```text
/setup doctor
```

Also run:

```bash
job-hunter doctor
```

Fix required failures before the first search. Workflow schedule warnings can remain until you are ready for automatic runs.

### Enable autonomous batch mode

`/job-hunter batch` runs up to 15 candidates end-to-end without stopping. Each AI tool needs its own auto-approve setting, otherwise it pauses after every command and waits for confirmation.

> **Warning — Auto mode scope**: auto mode lets the AI run commands, write files, and fetch web pages without asking at each step. Batch scope is limited to `outputs/` writes, `job-hunter internal` commands, and WebFetch. No applications are submitted, no git push occurs, and no messages are sent. Run `/job-hunter finalize` separately after reviewing outputs.

#### Claude Code (VS Code extension)

Enable **Auto** mode in the Claude Code panel before running batch. The mode selector is at the bottom of the extension panel. Auto mode resets when you close the panel.

> **Disclaimer**: In Auto mode, Claude Code executes bash commands, reads and writes files, and fetches URLs without per-step confirmation. Job Hunter batch does not commit or push.

#### Codex (VS Code extension)

Use the built-in approval setting in the Codex extension panel. Look for **"Approve for me"** or the equivalent auto-approve toggle in the extension sidebar — no config file changes are needed.

> **Disclaimer**: Auto-approve lets Codex run commands and write files without per-step confirmation. Keep the workspace private and review generated changes. Job Hunter batch does not commit, push, or send messages.

---

## 7. LLM API mode setup

LLM API mode uses the same profile, stories, resume, titles, regions, and exclusions as agent mode.

Complete `/setup onboard`, `/setup context`, `/setup stories`, and `/setup resume` first.

Then set:

```yaml
mode: llm-api
```

### Choose provider

Supported providers:

- Anthropic;
- OpenAI;
- Google (LLM API mode only — requires `GOOGLE_API_KEY`);
- Ollama.

Example:

```yaml
llm:
  default_provider: anthropic
```

Role-specific providers and models can remain at their defaults during initial setup.

### Local API keys

Copy the example environment file:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS/Linux:

```bash
cp .env.example .env
```

Open `.env` and add only keys you use.

Examples:

```text
ANTHROPIC_API_KEY=your-key
OPENAI_API_KEY=your-key
GOOGLE_API_KEY=your-key
```

Do not commit `.env`. It is ignored by Git.

### Test API mode

```bash
job-hunter doctor
job-hunter hunt --region primary
```

Doctor checks whether selected provider SDK is available. Hunt confirms the complete configured pipeline.

### Onboarding without Claude Code or Codex (LLM API mode)

If you chose LLM API mode and don't have Claude Code or Codex installed, you cannot run `/setup` skills. Build your profile files manually using a browser AI instead.

Open [Claude](https://claude.ai) or [ChatGPT](https://chatgpt.com) in your browser. Create each file in order.

**1. career_context.md**

Paste this prompt:

> I need to fill in a career context file for a job search tool. This file tells the AI how to write my resume bullets, cover letters, and LinkedIn posts. Ask me questions about my background, target roles, writing style, and career goals — one topic at a time. Then format the result as a markdown file with these sections: About Me, Target Roles, Key Achievements (verified facts only — no invented metrics), Resume Style, Cover Letter Style, LinkedIn Voice, Writing Rules.

Work through the conversation. Paste the final result into `profile/career_context.md`.

**2. story_bank.md**

Paste this prompt:

> I need to create a story bank for a job search tool. Each story should follow STAR format (Situation, Task, Action, Result) with a unique ID like `story-001`. Ask me to share my work achievements and experiences one at a time. Only include verified facts — no invented metrics or approximations. Format each as a STAR story with the ID, a short title, and a rating from 1–10.

Work through your stories. Paste the result into `profile/story_bank.md`.

**3. Resume**

The workspace includes starter LaTeX templates at `profile/resume_double_column.tex` and `profile/resume_single_column.tex`. Open one in a text editor and replace the placeholder sections with your name, contact info, and content from your career context and story bank.

For help with specific resume sections, paste the section into your browser AI with:

> Rewrite this resume section using only verified facts from my career context below. No invented metrics.

Then paste your career_context.md content.

**After building profile files**

Edit `config/job_hunter.yml` to set `mode: llm-api`, your provider, and your API key path. Then continue from [Section 8 (GitHub Secrets)](#8-github-secrets).

---

## 8. GitHub Secrets

GitHub Actions cannot read your local `.env` file. Add required keys as GitHub Secrets.

1. Open your private repository on GitHub.
2. Select **Settings**.
3. Select **Secrets and variables → Actions**.
4. Click **New repository secret**.
5. Enter exact secret name and value.

LLM provider secrets:

| Secret | Provider | Create key |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic | [Anthropic Console](https://console.anthropic.com/) |
| `OPENAI_API_KEY` | OpenAI | [OpenAI API keys](https://platform.openai.com/api-keys) |
| `GOOGLE_API_KEY` | Google | [Google AI Studio](https://aistudio.google.com/app/apikey) |

Optional search-source secrets:

| Secret | Service | Create key |
|---|---|---|
| `BRAVE_API_KEY` | Brave Search | [Brave Search API](https://api-dashboard.search.brave.com/app/keys) |
| `TAVILY_API_KEY` | Tavily | [Tavily](https://app.tavily.com/) |
| `EXA_API_KEY` | Exa | [Exa](https://dashboard.exa.ai/api-keys) |
| `FIRECRAWL_API_KEY` | Firecrawl | [Firecrawl](https://www.firecrawl.dev/app/api-keys) |
| `RAPIDAPI_KEY` | JSearch/RapidAPI | [JSearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) |
| `ADZUNA_APP_ID` | Adzuna | [Adzuna Developer](https://developer.adzuna.com/) |
| `ADZUNA_API_KEY` | Adzuna | [Adzuna Developer](https://developer.adzuna.com/) |
| `JOOBLE_API_KEY` | Jooble | [Jooble REST API](https://jooble.org/api/about) |
| `REED_API_KEY` | Reed | [Reed API](https://www.reed.co.uk/developers) |

You do not need every source key. Job Hunter also uses free feeds, public career pages, ATS discovery, and available providers.

For agent mode, LLM API secrets are only needed if GitHub Actions performs LLM API work. Normal interactive agent review can use your signed-in VS Code extension.

---

## 9. Test GitHub Actions

Before enabling a schedule:

1. Push setup changes to GitHub.
2. Open repository **Actions** tab.
3. Choose **Find Jobs**.
4. Click **Run workflow**.
5. Select a region if desired.
6. Start the workflow.
7. Wait for green success.

If workflow fails:

1. Open failed run.
2. Open failed step.
3. Read final error lines.
4. Common causes:
   - missing secret;
   - invalid config;
   - unfilled profile file;
   - provider quota;
   - temporary job-board failure;
   - Docker or browser startup failure.

Run `job-hunter doctor` locally after config changes.

---

## 10. First job search

The easiest and recommended first hunt is through GitHub Actions. This confirms your private repository, secrets, workflow, and Job Hunter configuration all work together.

### Commit and push your completed setup

Do this only after onboarding, career context, stories, resume, and `job-hunter doctor` are complete.

GitHub Desktop:

1. Open GitHub Desktop.
2. Review changed files.
3. Enter summary: `Complete Job Hunter setup`.
4. Click **Commit to main**.
5. Click **Push origin**.

Command line:

```bash
git add .
git commit -m "Complete Job Hunter setup"
git push
```

Never commit `.env`. It is ignored automatically.

### Run the first hunt with GitHub Actions

On GitHub.com:

1. Open your private workspace repository.
2. Select **Actions**.
3. Select **Find Jobs**.
4. Click **Run workflow**.
5. Leave region blank to run all enabled regions, or enter `primary`.
6. Click the green **Run workflow** button.
7. Wait for the run to finish.

Short path: **Actions → Find Jobs → Run workflow**.

When the run succeeds, GitHub Actions commits discovered candidates back to your repository.

### Pull first results

GitHub Desktop:

1. Click **Fetch origin**.
2. Click **Pull origin**.

Command line:

```bash
git pull
```

Now open VS Code and review:

```text
/job-hunter brief
/job-hunter batch
```

### Optional local hunt

Local hunt is useful for troubleshooting or development, but is not required for first setup.

```bash
job-hunter hunt --region primary
job-hunter brief
```

To process one URL:

```text
/job-hunter one <job-url>
```

To finish and save processed work:

```text
/job-hunter finalize
```

---

## 11. Daily agent workflow

### Before review

Pull latest GitHub changes.

GitHub Desktop:

1. Click **Fetch origin**.
2. Click **Pull origin** if available.

Command line:

```bash
git pull
```

### Review

```text
/job-hunter brief
/job-hunter batch
```

Batch mode:

- loads unprocessed candidates;
- applies deterministic exclusions;
- retrieves full descriptions where possible;
- scores fit;
- selects verified stories;
- creates tailored files for accepted jobs;
- leaves rejected jobs recorded for deduplication.

### Inspect application tracker

Open the web dashboard in a native window:

```bash
job-hunter dash
```

Or use the terminal dashboard:

```bash
job-hunter dashboard --no-interactive
job-hunter applications list
```

### Save work

```text
/job-hunter finalize
```

The skill asks before committing or pushing when appropriate.

---

## 12. Daily LLM API workflow

In LLM API mode, `job-hunter hunt` performs the autonomous pipeline.

You can:

- run it locally;
- trigger GitHub Actions manually;
- enable scheduled GitHub Actions.

Review generated files under:

```text
outputs/jobs/
outputs/applications.yml
README.md
```

Check generated resumes and cover letters before applying.

LLMs can make mistakes. Never send generated application materials without review.

---

## 13. Command reference

Public terminal commands:

| Command | Purpose |
|---|---|
| `job-hunter init <folder>` | Create workspace |
| `job-hunter doctor` | Validate setup and config |
| `job-hunter hunt` | Search and process jobs according to mode |
| `job-hunter brief` | Create daily candidate briefing |
| `job-hunter tailor` | Tailor from URLs or job-description file |
| `job-hunter dash` | Open web dashboard (Applications · Insights · Analytics) |
| `job-hunter dashboard` | Terminal application dashboard |
| `job-hunter applications list` | List applications |
| `job-hunter applications update` | Change application status |
| `job-hunter update` | Refresh managed workspace files |
| `job-hunter version` | Show versions and update instructions |

Common agent skills:

| Skill | Purpose |
|---|---|
| `/setup onboard` | Guided configuration |
| `/setup context` | Build career context |
| `/setup stories` | Build story bank |
| `/setup resume` | Build base resume |
| `/setup style` | Adjust resume appearance |
| `/setup doctor` | Guided health check |
| `/job-hunter brief` | Review daily summary |
| `/job-hunter batch` | Process candidate batch |
| `/job-hunter one <url>` | Process one job |
| `/job-hunter tailor <job>` | Tailor application |
| `/job-hunter score <job>` | Score fit |
| `/job-hunter research <job>` | Research company |
| `/job-hunter interview <job>` | Prepare interview |
| `/job-hunter outreach <job>` | Draft outreach |
| `/job-hunter finalize` | Validate and save work |
| `/linkedin ideas` | Draft content ideas |
| `/linkedin draft` | Draft LinkedIn post |
| `/linkedin engage` | Draft comments |
| `/linkedin network` | Build networking queue |

---

## 14. Application statuses

Use application tracker to record progress.

Typical statuses include:

- discovered;
- scored;
- tailored;
- applied;
- screening;
- interviewing;
- offer;
- rejected;
- withdrawn.

Update from terminal:

```bash
job-hunter applications update <job-folder> applied
```

Add a note:

```bash
job-hunter applications update <job-folder> interviewing --note "First interview scheduled"
```

---

## 15. Search regions

Regions live in:

```text
config/job_hunter.yml
```

Example:

```yaml
regions:
  primary:
    enabled: true
    primary: true
    country: "DE"
    search_lang: "en"
    location: "Berlin"
    description: "Primary search region"
```

Add another region through:

```text
/setup region add munich
```

Country-specific sources run only for matching countries. Global remote sources run independently.

---

## 16. Search quality tips

- Use several realistic job titles, not dozens.
- Add title exclusions for roles you never want.
- Add language exclusions only when necessary.
- Keep regions specific enough for useful results.
- Start with default score threshold.
- Review false positives before making filters stricter.
- Keep career context factual and current.
- Add strong final stories before judging tailoring quality.
- Do not enable every optional API before testing basic workflow.

---

## 17. Privacy and safety

- Keep repository private.
- Never commit `.env`.
- Never paste API keys into chat.
- Review generated resumes.
- Review generated cover letters.
- Review company research.
- Review outreach drafts.
- Job Hunter does not apply automatically.
- Job Hunter does not post automatically.
- Product updates preserve `config/`, `profile/`, `outputs/`, and `.env`.

---

## 18. Updating Job Hunter

With uv:

```bash
uv tool upgrade job-hunter-kit
```

With pip:

```bash
python -m pip install --upgrade job-hunter-kit
```

Then, inside workspace:

```bash
job-hunter update
job-hunter doctor
```

Targeted updates:

```bash
job-hunter update --skills-only
job-hunter update --workflows-only
```

Update preserves user-owned config, profile, outputs, and secrets.

---

## 19. Troubleshooting

### `job-hunter` command not found

- Restart terminal after installation.
- Run `python -m uv tool update-shell`.
- Reinstall with uv.
- Check Python Scripts directory is on PATH.

### Wrong Python version

Install Python 3.12+, then reinstall Job Hunter using that Python.

### Doctor says config is invalid

Open `config/job_hunter.yml`.

Common YAML mistakes:

- tabs instead of spaces;
- missing colon;
- broken indentation;
- duplicate keys;
- country code longer than two letters;
- empty job title list.

Run:

```bash
job-hunter doctor
```

after each fix.

### Doctor says resume or context is unfilled

Run:

```text
/setup context
/setup stories
/setup resume
```

Template placeholders are intentionally treated as incomplete.

### Docker is unavailable

Agent mode can still search and review jobs. PDF compilation may be skipped.

LLM API mode should have Docker running for autonomous PDF generation.

### No jobs found

- Confirm region is enabled.
- Confirm location and country.
- Try broader title.
- Remove overly strict exclusions.
- Run without scheduled workflow first.
- Check workflow logs for failed sources.
- Add optional search API keys.

### One job source fails

Temporary source failures are expected. Job Hunter continues with other sources.

Do not assume whole run failed unless final command exits with error.

### LLM API error

- Confirm selected provider.
- Confirm exact secret name.
- Confirm API key has credit/quota.
- Confirm configured model exists.
- Run `job-hunter doctor`.
- Retry after provider outage.

### PDF compilation fails

- Start Docker Desktop.
- Check Docker works: `docker version`.
- Ensure resume `.tex` file exists.
- Review LaTeX error log.
- Use LaTeX Workshop from VS Code.

### GitHub Actions cannot push

- Confirm repository is private and accessible.
- Open workflow permissions.
- Allow Actions read/write access where required.
- Pull latest changes before local edits.

### Need help understanding an error

Copy only the relevant error message, not API keys or `.env` content, into Claude Code or Codex and ask for explanation.

---

## 20. Setup completion checklist

- [ ] Python 3.12+ installed.
- [ ] Job Hunter installed.
- [ ] `job-hunter version` works.
- [ ] Workspace created.
- [ ] Workspace opened in VS Code.
- [ ] Claude Code or Codex installed.
- [ ] Private GitHub repository created.
- [ ] Mode selected.
- [ ] `/setup onboard` completed.
- [ ] Career context completed.
- [ ] Story bank contains final stories.
- [ ] Base resume created.
- [ ] Resume PDF reviewed.
- [ ] `job-hunter doctor` required checks pass.
- [ ] Required GitHub Secrets added.
- [ ] Manual GitHub Actions run tested.
- [ ] First `job-hunter hunt --region primary` completed.
- [ ] First briefing reviewed.

Once these are complete, normal daily work is:

```text
pull → brief → batch → review → finalize
```
