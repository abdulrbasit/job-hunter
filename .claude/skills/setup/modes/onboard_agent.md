# Onboard — Agent Mode

Full interactive setup for agent mode. Runs config → career context → story bank → base resume in one session.

**Rules:**
- One topic at a time. Wait for the user's answer before moving on.
- Flag any template placeholder values — never treat them as configured.
- Derive country code from city; confirm before using it.

---

## Before You Start

Read `config/job_hunter.yml`. Note any fields still at template defaults (`Your City`, empty `job_titles`, etc.).

---

## Steps 1-7 — Deterministic Setup

Tell the user:

> The fastest way to set job titles, region, experience levels, filters, and
> quick settings is the dashboard — run `job-hunter dash` in a terminal, it
> opens straight into a guided wizard for all of these, plus a Career Profile
> panel for the steps below. Come back here once the wizard says you're ready,
> or keep going now if you'd rather do this as a conversation.

If the user continues here, walk through each field one topic at a time, waiting
for an answer before moving on. Flag any field still at its template default
(`Your City`, empty `job_titles`, etc.) rather than treating it as configured.

- **Job titles** — ask for all target title variations (e.g. `Senior Product
  Manager`, `Head of Product`, `Director of Product`); replace `job_titles`.
- **Region** — ask for a city. Look up its ISO alpha-2 country code with
  `job-hunter internal region-lookup --city "<city>"` rather than guessing;
  only ask the user directly if that command returns nothing. Confirm the code,
  then ask English-only vs. also local language (default `en`). Update
  `regions.primary` (`enabled: true`, `primary: true`, `mode: agent`). Offer to
  add more regions the same way — city name (lowercased, underscores) as the
  YAML key.
- **Experience Levels** — offer the 16 level ids (`student_intern`,
  `student_working_student`, `student_thesis`, `entry`, `junior`, `associate`,
  `mid`, `senior`, `lead`, `staff`, `principal`, `expert`, `manager`,
  `director`, `vp`, `c_level`); default `associate, mid, senior` on Enter. A
  posting whose stated experience requirement doesn't overlap any chosen level
  is excluded automatically — on top of whatever exclusions come next. Set
  `filters.experience_levels`.
- **Exclusions** — show the *actual current* `filters.*` exclusion lists from
  the config you loaded in "Before You Start" (substituting `(none)` for any
  empty list — never invent example values), ask what to change.
- **Quick settings** — resume layout (double/single column), profile photo,
  `scoring.min_fit_score`, `scoring.batch_size`, and an optional
  `scoring.max_years_experience_required` override (leave unset to default
  from the chosen experience levels).
- **API keys** — agent mode doesn't need an LLM key; Claude Code/Codex handles
  scoring and tailoring. Optional job-board keys (Adzuna, Reed) go in the
  dashboard's Get Started → API Key field, stored in the OS keyring — not a
  `.env` file.

Set `mode: agent`. Show the full updated `config/job_hunter.yml` preview and
confirm before writing:

```
Here is the config I will write:

[full file content]

Ready to write? (yes/no)
```

After confirmation, write the file.

---

## Step 8 — Health Check

Run:

```bash
job-hunter doctor --json
```

Parse and display results in a compact table (✓ pass / ✗ fail with fix hint). If anything is red that blocks the first run, help the user fix it before continuing.

---

## Step 9 — Career Context

Tell the user:

> Config saved. Now let's build your career profile — this is what the pipeline uses to score, tailor, and write cover letters accurately. (You can also do this from the dashboard's Career Profile panel — click Copy command there and paste it back here, or use its any-chatbot path if you don't have this chat open.)
>
> Starting with career context…

Execute `.claude/skills/setup/modes/context.md` inline.

---

## Step 10 — Story Bank

Tell the user:

> Career context saved. Now let's capture your STAR stories — reusable proof points the tailoring step references.

Execute `.claude/skills/setup/modes/stories.md` inline.

---

## Step 11 — Base Resume

Tell the user:

> Stories saved. Now building your base LaTeX resume from your context and stories.

Execute `.claude/skills/setup/modes/resume.md` inline.

---

## Step 12 — Done

Tell the user:

> Setup complete. Run your first hunt:
>
> ```bash
> job-hunter hunt --region primary
> ```
>
> Then open Claude Code or Codex in this workspace and run `/job-hunter batch` to review and tailor candidates.
