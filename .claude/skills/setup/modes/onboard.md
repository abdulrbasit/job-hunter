# Onboard

Interactive first-time setup for a new Job Hunter workspace. Walk the user through every required setting one step at a time, detect template placeholder values, and write the final result to `config/job_hunter.yml`.

**Rules:**
- Ask one topic at a time. Wait for the user's answer before moving on.
- Never skip a step or assume prior knowledge.
- Detect and flag any template placeholder values — do not treat them as "already configured".
- At the end, show a full preview of the new config and ask the user to confirm before writing.

---

## Before You Start

Read `config/job_hunter.yml` and note:
- Is `location: "Your City"` still there? → region is NOT configured
- Are job titles still `["Product Manager", "Product Owner"]`? → likely template defaults
- Is `languages: [german]` in exclusions? → template default, must ask the user

---

## Step 1 — Mode

Ask:

> Welcome to Job Hunter onboarding. Let's get your workspace configured.
>
> First: which mode are you setting up?
> - **agent** — you review jobs interactively each day using Claude Code, Codex, Gemini CLI, or GitHub Copilot
> - **llm-api** — the full pipeline runs automatically (score, tailor, cover letter, PDF, tracker) — great for GitHub Actions or unattended runs
>
> Type `agent` or `llm-api`.

Set `mode:` accordingly.

---

## Step 2 — Job Titles

Show the current titles from config. If they match the template defaults (`Product Manager`, `Product Owner`), flag them.

Ask:

> What job titles should I search for? List all variations — the more specific, the better results.
>
> Examples: `Senior Product Manager`, `Head of Product`, `Director of Product`, `Group Product Manager`
>
> List them one per line (or comma-separated).

Replace `job_titles` with the user's list. Keep them as strings in YAML.

---

## Step 3 — Resume Layout

Ask:

> Which resume layout do you prefer?
> - **double column** (default) — compact, two-column AltaCV layout. Best for experienced candidates with a lot to show.
> - **single column** — clean, traditional single-column layout. Better for ATS systems and simpler profiles.

Update `profile.resume_tex`:
- Double column → `"profile/resume_double_column.tex"`
- Single column → `"profile/resume_single_column.tex"`

---

## Step 4 — Primary Search Region

Check if `regions.primary.location` equals `"Your City"` (the template placeholder). If so, tell the user it needs to be set.

Ask:

> What city or region are you job hunting in?
>
> Examples: `Berlin`, `London`, `Amsterdam`, `Munich`, `Remote`

Then ask:

> What's the two-letter country code for that region?
>
> Examples: `DE` (Germany), `GB` (UK), `NL` (Netherlands), `US` (United States), `SG` (Singapore)

Then ask:

> Should job board searches use English only, or also the local language? (Default: `en` — English only. Change to the local language code if you want local-language results too.)

Update `regions.primary` with the answers. Keep `enabled: true`, `primary: true`.

Then ask:

> Do you want to add any other search regions? (Optional — you can always add more later with `/setup region add`)

If yes, repeat the city / country / language questions for each additional region. Use the city name (lowercased, spaces to underscores) as the YAML key. If no, move on.

---

## Step 5 — Exclusions

### Title terms

Show the current exclusion list:
```
intern, internship, trainee, working student, werkstudent, junior, principal, expert, chief product
```

Ask:

> These job title terms are excluded from search results. Any to remove? Any to add? (Enter to keep as-is)

Update `exclusions.title_terms` if they changed anything.

### Language exclusions

**Important:** The template defaults to excluding German-language job postings. This is not right for everyone.

Ask:

> The template currently excludes jobs posted in German. Do you want to apply in German? If yes, I'll remove German from the exclusion list.
>
> Are there other languages you want to exclude? (Leave blank to exclude none — English-only postings are never excluded by this setting)

Update `exclusions.languages`. If they are fine applying in German, remove `german` from the list. If they list other languages to exclude, add them.

### Company exclusions

Ask:

> Any specific companies you always want to skip? (Optional — press Enter to leave empty. You can update this later.)

Update `exclusions.companies` if provided.

---

## Step 6 — Scoring Thresholds

Show current values: `min_fit_score: 70`, `max_years_experience_required: 5`.

Ask:

> Scoring defaults:
> - Minimum fit score: **70/100** (jobs below this are filtered out)
> - Max years of experience required: **5** (jobs that require more than this are skipped)
>
> Want to change either? (Enter to keep defaults)

Update `scoring.min_fit_score` and/or `scoring.max_years_experience_required` if changed.

---

## Step 7 — LLM Provider

Show current default: `anthropic`.

Ask:

> Which LLM provider do you want to use as your primary?
> - **anthropic** — Claude models (requires `ANTHROPIC_API_KEY`)
> - **openai** — GPT models (requires `OPENAI_API_KEY`)
> - **google** — Gemini models (requires `GOOGLE_API_KEY`)
>
> You can mix providers per task, but pick a primary default.

Update `llm.default_provider` and all entries in `llm.providers` to match.

Then ask:

> Which model should be used for resume tailoring and cover letters? This is the most impactful choice — it determines the quality of your tailored documents.
>
> Suggested defaults by provider:
> - Anthropic: `claude-sonnet-4-6`
> - OpenAI: `gpt-4o`
> - Google: `gemini-2.0-flash`
>
> (Enter to keep the current default)

Update `llm.models.tailoring` and `llm.models.cover_letter` if changed.

---

## Step 8 — LLM Web Search (optional)

Inform the user:

> **LLM web search** is disabled by default (`search.llm_search.enabled: false`). When enabled, the pipeline uses AI to search the web for job listings when regular job boards find fewer results than a threshold you set. Useful for niche roles, but uses more API credits.

Ask:

> Do you want to enable LLM web search? (Default: no)

If yes, ask:

> What trigger threshold? (Default: 15 — AI search kicks in when fewer than 15 candidates are found from regular sources)

If yes, ask:

> Max AI search results per run? (Default: 20)

Update `search.llm_search.enabled`, `trigger_threshold`, and `max_results_per_run` accordingly.

---

## Step 9 — LLM API Mode extras (only if mode = llm-api)

Tell the user:

> Since you chose **llm-api mode**, a few things to know:
>
> 1. **API keys** — Add all your keys as GitHub repository secrets (Settings → Secrets and variables → Actions), not just in `.env`. The scheduled workflow reads from secrets.
> 2. **Workflow schedule** — Open `.github/workflows/find-jobs.yml` and uncomment the `schedule:` and `- cron:` lines when you are ready for automatic runs.
> 3. **Outputs** — After each run, check `outputs/` for scored jobs, tailored resumes, and cover letters. The tracker at `outputs/applications.yml` is updated automatically.
>
> No config changes needed here — just confirming you know what to expect.

---

## Step 10 — Confirm and Write

Build the full updated `config/job_hunter.yml` from the user's answers (preserve all existing comments and structure, only change the values that were updated).

Show the user a preview:

> Here is the updated `config/job_hunter.yml` I will write:
>
> ```yaml
> [full file content]
> ```
>
> Ready to write? (yes/no)

After confirmation, write the file.

---

## Step 11 — Next Steps

Tell the user:

> Config saved. Here is what to do next, in order:
>
> 1. **Career context** — Run `/setup context`. This captures your positioning, resume style, cover letter voice, and evidence rules. The pipeline reads this for every tailored document it writes.
>
> 2. **Story bank** — Run `/setup stories`. Paste in your raw work notes or existing CV bullets. The skill structures them into rated STAR stories with stable IDs.
>
> 3. **Base resume** — Run `/setup resume`. Reads your career context and story bank to draft a fully populated LaTeX resume. Do steps 1 and 2 first.
>
> 4. **Style** (optional) — Run `/setup style` to adjust colours, font, font size, and layout.
>
> 5. **Health check** — Run `/setup doctor` to confirm everything is green before your first run.
