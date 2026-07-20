# Job Hunter — LLM API Mode Setup

## 1. Who this mode is for

You want Job Hunter to run unattended — on a schedule, with no one reviewing
each step — typically via GitHub Actions. This is also the mode to pick if
you don't want to install or use VS Code at all: setup and daily use both
happen in the `job-hunter dash` window.

## 2. What runs in this mode

The full pipeline runs inside Python: search → validate → score → tailor →
cover letter → PDF → tracker. The LLM API you configure is called directly
by Python for scoring, tailoring, cover letters, and company research —
there's no agent chat session involved.

## 3. Required tools

| Tool | Why |
|---|---|
| Python 3.12 or 3.13 | Runs Job Hunter |
| [uv](https://docs.astral.sh/uv/) | Recommended installer |
| An API key from Anthropic, OpenAI, or Google | Powers scoring/tailoring |
| GitHub Actions (optional) | Runs on a schedule without your computer on |

## 4. Install steps

```bash
python -m pip install uv
python -m uv tool install job-hunter-kit
python -m uv tool update-shell
```

Close and reopen your terminal, then check it worked:

```bash
job-hunter version
```

**Expected result:** prints the installed version.

## 5. Create workspace

```bash
job-hunter init FirstName.LastName-Resume
cd FirstName.LastName-Resume
```

**Expected result:** `[ok] Workspace created at: ...`.

## 6. Add your API key

Open `job-hunter dash` — a new workspace opens straight into the setup
wizard, which asks for your API key on the Basics step (once you've picked
`llm-api` mode). Paste it there; it's stored in your OS keyring, never
written to a file.

Get a key from whichever provider you set as `llm.default_provider`:

- Anthropic: [console.anthropic.com](https://console.anthropic.com/)
- OpenAI: [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- Google: [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)

**Common mistake:** pasting a real key into `config/job_hunter.yml` or any
file tracked by Git. Local keys belong in the OS keyring (via the
dashboard) and GitHub Actions keys belong in repository Secrets — never in
a committed file. The workspace's `.env.example` file is a template for
GitHub Actions Secrets only (see step 9) — Job Hunter does not read a local
`.env` file for anything running on your own computer.

## 7. Configure job titles, region, and filters

The setup wizard in `job-hunter dash` writes `job_titles`, `regions`, and
`filters` for you — no manual YAML editing needed. It produces a file
shaped like this:

```yaml
mode: llm-api

job_titles:
  - Senior Product Manager

regions:
  primary:
    enabled: true
    primary: true
    country: "DE"        # two-letter country code
    location: "Berlin"
    description: "Primary region"

filters:
  hunt_languages: [en]
  experience_levels: [associate, mid, senior]
  excluded_companies: []
  excluded_industries: []

scoring:
  min_fit_score: 70
  batch_size: 15
  # max_years_experience_required: 5   # optional — defaults to the max of your experience_levels

llm:
  default_provider: anthropic   # or openai, google, ollama
  max_workers: 4
  models:
    tailoring: claude-sonnet-4-6
    cover_letter: claude-sonnet-4-6
```

- `mode` — must be `llm-api` for this mode; set on the wizard's Basics step.
- `default_provider` — which LLM API GitHub Secrets must supply a key for.
- `max_workers` — how many jobs the pipeline scores/tailors at once. Higher
  is faster but hits provider rate limits sooner. Not wizard-covered — set
  it via Settings → Guided → Advanced YAML if you need a non-default value.
- `job_titles`, `regions`, `filters` — same shape as agent mode.
- `scoring.min_fit_score` — the cutoff for tailoring a job (0-100).

`job-hunter dash`'s Setup Health Check (Settings → Diagnostics) validates
the file continuously and links straight to the fix for anything missing.

## 8. Run locally

```bash
job-hunter doctor
job-hunter hunt --region primary
job-hunter dash
```

**Expected result:** `hunt` prints a summary of jobs found, scored, and
tailored. `dash` opens a native window with Applications, Candidates,
Insights, and Settings tabs (Analytics lives under Settings → Diagnostics;
a manual/local hunt trigger lives there too, for testing — day-to-day
hunting normally runs on GitHub Actions' schedule, see the next section).

## 9. Run unattended with GitHub Actions

The workspace ships with a **Find Jobs** workflow
(`.github/workflows/find-jobs.yml`).

**GitHub Secrets** — Actions can't read your local `.env`, so add the same
keys as repository secrets:

1. Open your repository on GitHub → **Settings → Secrets and variables → Actions**.
2. Click **New repository secret** for each key you use (e.g. `ANTHROPIC_API_KEY`).

**Manual run** — Actions tab → **Find Jobs** → **Run workflow**.
**Expected result:** a green check mark and new files committed under `outputs/`.

**Schedule** — open `find-jobs.yml`, uncomment the `schedule:` block, and
adjust the `cron:` time. Commit and push to enable it.

**How outputs get committed** — a successful run commits discovered jobs,
tailored resumes, and cover letters back to your repository automatically.
To review them locally, open `job-hunter dash` and click **Sync** in the
topbar — it merges the workflow's `outputs/state/jobs.db` with your local
one and pulls everything else down. No `git pull` needed, and it also runs
automatically each time you open the dashboard.

## 10. Cost and token safety

- Every API call to Anthropic, OpenAI, or Google costs money, billed by
  your provider account — Job Hunter has no separate billing of its own.
- `scoring.batch_size` caps how many jobs get tailored (the expensive step)
  per run. Keep it small (10-20) while you're testing.
- `llm.models` lets you assign a cheaper/faster model to high-volume roles
  (scoring, validation) and a stronger model only to tailoring and cover
  letters, which run less often.
- To keep a test run cheap: set `scoring.batch_size: 3` and `min_fit_score`
  high, run `job-hunter hunt --region primary` once, and check `outputs/`
  before widening either setting.
- Spend limits and usage alerts are configured in your provider's own
  console (e.g. the Anthropic Console), not in Job Hunter.

## 11. Updating after a new release

```bash
uv tool upgrade job-hunter-kit
job-hunter update
job-hunter doctor
```

`job-hunter update` never overwrites `config/`, `profile/`, `outputs/`, or `.env`.

## 12. Troubleshooting

**Missing API key**
`job-hunter doctor` reports which provider key is missing. Add it via
`job-hunter dash`'s setup wizard (local) or GitHub Secrets (Actions).

**Wrong provider/model**
Confirm `llm.default_provider` in `config/job_hunter.yml` matches the key
you actually set, and that any model name under `llm.models` is one your
provider account has access to.

**Rate limit**
Lower `llm.max_workers`, or set a `llm.rate_limits.<role>.requests_per_minute`
value in config.

**No jobs found**
Confirm a region is `enabled: true`, and job titles/filters aren't too narrow.

**PDF compile fails**
The workflow's PDF step needs LaTeX in the runner image. Check the failed
step's log; a missing `.tex` file (tailoring failed first) is the most
common cause.

**GitHub Action failed**
Open the failed run → the failed step → read the last error lines. Missing
secrets and invalid config are the most common causes.

**Workflow did not run on schedule**
Confirm the `schedule:` block is uncommented and pushed to the default
branch — GitHub Actions ignores schedules defined only on other branches.

**Outputs not committed**
Check the workflow's final step succeeded; a failed pipeline step earlier
in the run stops the commit step from executing.

## 13. Privacy and safety notes

- Keep your workspace repository private.
- Never commit `.env` — it's excluded by `.gitignore` already.
- Review every tailored resume and cover letter before applying — LLMs can
  make mistakes.
- Job Hunter never submits applications or posts anywhere automatically,
  even in this mode.
