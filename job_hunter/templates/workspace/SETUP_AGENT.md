# Job Hunter — Agent Mode Setup

## 1. Who this mode is for

You want to review jobs yourself, a batch at a time, inside VS Code. You're
comfortable running a few terminal commands but don't need to write code.

## 2. What runs in this mode

- Python searches job boards and career pages, filters by your config, and
  stores candidates.
- Claude Code or Codex — through the bundled `/job-hunter` and `/setup`
  skills — handles reviewing, scoring, tailoring, and writing.

No LLM API key is required for the core review-and-tailor workflow.
Claude Code/Codex use your existing subscription or sign-in, not a
separate API bill. Full-mode batch also tries an optional company-research
step through your configured `llm` provider — if no key is set, that one
step is skipped and everything else continues.

## 3. Required tools

| Tool | Why |
|---|---|
| Python 3.12 or 3.13 | Runs Job Hunter |
| [uv](https://docs.astral.sh/uv/) | Recommended installer |
| VS Code | Runs the AI skills |
| Claude Code or Codex extension | Reviews and tailors jobs |

## 4. Install steps

**Do this:**

```bash
python -m pip install uv
python -m uv tool install job-hunter-kit
python -m uv tool update-shell
```

**Why this matters:** `uv tool install` puts the `job-hunter` command on
your PATH in an isolated environment, so it won't conflict with other
Python projects.

Close and reopen your terminal, then create your workspace:

```bash
job-hunter init FirstName.LastName-Resume
cd FirstName.LastName-Resume
```

**Expected result:** `[ok] Workspace created at: ...` followed by
next-step instructions.

**Common mistake:** running `job-hunter init` inside a folder you already
created and `cd`'d into — it creates a *new* subfolder for you, so give it
a name directly instead of pre-making an empty directory.

Open the workspace in VS Code:

```bash
code .
```

If `code` isn't recognized, open VS Code manually and use
**File → Open Folder**. Install the Claude Code or Codex extension and
sign in.

## 5. First-time workspace setup

**Do this**, in order, from the Claude Code or Codex chat panel:

```text
job-hunter doctor
```

Run this from a terminal first. It's normal to see failures before
onboarding — each one lists a fix. Then in the chat panel:

```text
/setup onboard
/setup context
/setup stories
/setup resume
```

- `/setup onboard` — asks for job titles, region, exclusions, and scoring
  settings, and writes `config/job_hunter.yml`.
- `/setup context` — builds `profile/career_context.md` from your
  background and target roles.
- `/setup stories` — turns your achievements into STAR-format stories in
  `profile/story_bank.md`.
- `/setup resume` — builds your base resume as a LaTeX file in `profile/`.

**Expected result:** `job-hunter doctor` shows no required failures.
**Common mistake:** rushing career context — thin or vague input here
produces weak scoring and generic tailored resumes later.

## 6. Daily workflow

```bash
job-hunter hunt --region primary
```

Then in VS Code:

```text
/job-hunter batch
```

Processes up to 15 candidates: screens, scores, tailors resumes, and
writes cover letters for jobs above your score threshold. It runs to
completion without stopping for confirmation on ordinary status lines —
this needs your editor's auto-approve setting turned on first:

- **Claude Code** — switch the mode selector at the bottom of the panel to
  **Auto**. It resets when you close the panel, so re-enable it each
  session.
- **Codex** — turn on **"Approve for me"** (or the equivalent auto-approve
  toggle) in the extension sidebar.

> **Auto mode scope:** with auto-approve on, the AI runs commands, writes
> files, and fetches web pages without asking at each step. Batch is
> limited to `outputs/` writes, `job-hunter internal` commands, and
> WebFetch — no application is ever submitted, no `git push` happens, and
> no message is sent anywhere. Run `/job-hunter finalize` yourself,
> separately, once you've reviewed the output.

```bash
job-hunter dash
```

Review what got tailored. Then, per job:

```text
/job-hunter one <url>
```

Process a single job URL end-to-end, outside the batch flow. When you're
done reviewing:

```text
/job-hunter finalize
```

Confirms outputs are consistent and asks before committing or pushing.

### Review token usage

Workspace setup enables privacy-safe token telemetry for both Claude Code and
Codex. Restart the editor after setup, run `/job-hunter batch` normally, then
open `job-hunter dash` and select Analytics. Metrics are
stored locally in `outputs/state/metrics.db`; prompts, responses, resume text,
and tool arguments are not stored. Telemetry failure never blocks a batch.

## 7. How to update after a new package release

```bash
uv tool upgrade job-hunter-kit
```

Then, inside your workspace:

```bash
job-hunter update
job-hunter doctor
```

`job-hunter update` refreshes skills, workflows, and config schemas. It
never overwrites your `config/`, `profile/`, `outputs/`, or `.env`.

## 8. Troubleshooting

**Command not found**
Restart your terminal, or run `python -m uv tool update-shell` again.

**Python version wrong**
Install Python 3.12 or 3.13, then reinstall: `uv tool install --force job-hunter-kit`.

**uv not found**
Run `python -m pip install uv` again, then restart your terminal.

**VS Code extension can't see skills**
Confirm you opened the workspace folder itself (containing `.claude/`),
not its parent folder.

**Workspace opened at the wrong folder**
Close the folder in VS Code and reopen the exact directory `job-hunter init`
created.

**Doctor reports missing profile/config**
Run `/setup context`, `/setup stories`, and `/setup resume` — template
placeholders count as incomplete until you replace them.

**No jobs found**
Confirm a region is `enabled: true` in `config/job_hunter.yml`, and that
your job titles and exclusions aren't too narrow.

**Skills not updated after upgrading**
Run `job-hunter update --skills-only`, then reopen the VS Code window.

## 9. Safety notes

- You decide what to apply for. Job Hunter never submits applications.
- Nothing is posted to LinkedIn or sent to anyone automatically.
- Keep your workspace repository private — it contains your resume and
  personal career details.
