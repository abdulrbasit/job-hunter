# Onboard — LLM API Mode (with Agent)

Full interactive setup for LLM API mode. Runs config → career context → story bank → base resume in one session.

**Rules:**
- One topic at a time. Wait for the user's answer before moving on.
- Flag any template placeholder values — never treat them as configured.
- Derive country code from city; confirm before using it.

---

## Before You Start

Read `config/job_hunter.yml`. Note any fields still at template defaults (`Your City`, empty `job_titles`, etc.).

---

## Step 1 — Job Titles

Show current titles. Flag if they are still template defaults.

Ask:

> What job titles should I search for? List all variations — the more specific, the better.
>
> Examples: `Senior Product Manager`, `Head of Product`, `Director of Product`
>
> List them one per line or comma-separated.

Replace `job_titles` with the user's list.

---

## Step 2 — Primary Region

Check if `regions.primary.location` is still `"Your City"`. If so, tell the user it must be set.

Ask:

> What city or region are you job hunting in?
> Examples: `Berlin`, `London`, `Amsterdam`, `Munich`, `Remote`

Derive the ISO alpha-2 country code from the city name (Munich→DE, London→GB, Amsterdam→NL, Paris→FR, Zurich→CH, Vienna→AT, Stockholm→SE, Oslo→NO, Copenhagen→DK, Warsaw→PL, Prague→CZ, Dublin→IE, Brussels→BE, Madrid→ES, Milan→IT, Toronto→CA, Sydney→AU, New York→US, San Francisco→US, Dubai→AE, Bangalore→IN, Singapore→SG, Tokyo→JP, Seoul→KR, São Paulo→BR). For cities not in this list, ask for the country code explicitly.

Show the derived code: `I'll use country code XX — correct? (Enter to confirm or type the right code)`

Then ask:

> Should searches use English only, or also the local language?
> Default `en` (English only). Type a language code to add local-language results (e.g., `de` for German).

Update `regions.primary` (keep `enabled: true`, `primary: true`, set `mode: llm-api`).

Then ask:

> Any other search regions? (Optional — add more later with `/setup region add`)

If yes, repeat city → code → language for each. Use the city name (lowercased, underscores) as the YAML key.

---

## Step 3 — Exclusions

Show current values in one block:

```
Current exclusions — edit anything or press Enter to keep as-is:

Title terms to skip:  intern, internship, trainee, working student, werkstudent, junior, principal, expert, chief product
Languages to exclude: german
Companies to skip:    (none)
Industries to skip:   (none)
```

Ask:

> Any changes? Examples: "remove junior", "add consulting to industries", "remove german from languages".
> Press Enter to keep all defaults.

Apply any changes to the four `exclusions.*` fields.

---

## Step 4 — Quick Settings

Show all at once:

```
Quick settings — press Enter to keep defaults or type changes:

Resume layout:               double column  (alt: single column)
Profile photo:               none           (provide filename if you have one in profile/)
Min fit score:               70 / 100
Max years experience req'd:  5
Batch size:                  15
LLM provider:                anthropic      (alt: openai, google)
Tailoring model:             claude-sonnet-4-6
```

Ask: `Any changes?`

Update:
- `profile.resume_tex`: `profile/resume_double_column.tex` or `profile/resume_single_column.tex`
- `profile.profile_image`: path or `""`
- `scoring.min_fit_score`, `scoring.max_years_experience_required`, `scoring.batch_size`
- `llm.default_provider` and all `llm.providers.*`
- `llm.models.tailoring` and `llm.models.cover_letter`

---

## Step 5 — API Keys and GitHub Actions

Tell the user:

> **LLM API mode requires API keys.** Set them up in two places:
>
> **Local (for testing):**
> 1. `cp .env.example .env`
> 2. Open `.env` and fill in at minimum `ANTHROPIC_API_KEY` (or your chosen provider's key).
> 3. Add optional job board keys (Adzuna, Reed, Jooble, Brave, etc.) for more results.
>
> **GitHub Actions (for scheduled runs):**
> Go to your repository → Settings → Secrets and variables → Actions → New repository secret.
> Add the same keys as secrets (exact names from `.env.example`):
> - `ANTHROPIC_API_KEY` (required for scoring and tailoring)
> - `BRAVE_API_KEY`, `TAVILY_API_KEY`, `EXA_API_KEY` (optional search)
> - `ADZUNA_APP_ID`, `ADZUNA_API_KEY`, `JOOBLE_API_KEY`, `REED_API_KEY` (optional job boards)
>
> **Enable the schedule:**
> Open `.github/workflows/find-jobs.yml` and uncomment the `schedule:` and `- cron:` lines.
> The default runs Mon–Fri at 20:00 Berlin time. Adjust the cron expression if needed.
>
> Full setup guide: see the README in the job-hunter repository.

No config changes here. Continue when ready.

---

## Step 6 — Config Preview and Write

Set `mode: llm-api` in the config.

Show the full updated `config/job_hunter.yml` preview:

```
Here is the config I will write:

[full file content]

Ready to write? (yes/no)
```

After confirmation, write the file.

---

## Step 7 — Health Check

Run:

```bash
job-hunter doctor --json
```

Parse and display results in a compact table (✓ pass / ✗ fail with fix hint). If anything is red that blocks the first run, help the user fix it before continuing.

---

## Step 8 — Career Context

Tell the user:

> Config saved. Now let's build your career profile — this is what the pipeline uses to score, tailor, and write cover letters accurately.
>
> Starting with career context…

Execute `.claude/skills/setup/modes/context.md` inline.

---

## Step 9 — Story Bank

Tell the user:

> Career context saved. Now let's capture your STAR stories — reusable proof points the tailoring step references.

Execute `.claude/skills/setup/modes/stories.md` inline.

---

## Step 10 — Base Resume

Tell the user:

> Stories saved. Now building your base LaTeX resume from your context and stories.

Execute `.claude/skills/setup/modes/resume.md` inline.

---

## Step 11 — Done

Tell the user:

> Setup complete. Trigger your first run:
>
> ```bash
> # Locally:
> job-hunter hunt --region primary
>
> # Via GitHub Actions:
> gh workflow run find-jobs.yml
> ```
>
> Scored candidates, tailored resumes, and cover letters will appear in `outputs/` after the run.
