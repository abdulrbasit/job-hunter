# Tailor

Produce application artifacts for one scored job.

Slug: `$ARGUMENTS`

## Inputs

- `job-hunter internal agent-context tailor-context --job <slug>` → tailoring_rules, positioning_rules,
  project_rules, keywords, gaps, cover_constraints, writing_rules
- `job-hunter internal agent-context score --mode full --job <slug>` → story_index, job meta, score.yml
- `outputs/jobs/<slug>/score.yml` — matched_story_ids
- Configured base resume from `config/job_hunter.yml:profile.resume_tex`
- `outputs/state/compiled/career_context.min.md` if present, else `profile/career_context.md` — resume style, cover-letter style, and evidence boundaries
- `outputs/state/compiled/resume.compact.txt` if present — plain text of resume for planning
- `outputs/jobs/<slug>/company_research.md`, when present

## Steps

1. Run `job-hunter internal telemetry-mark --phase tailoring --skill tailoring --job <slug> --state start`, then
   `job-hunter internal agent-context tailor-context --job <slug>`.
   Apply every field exactly as delivered — these are the same constraints that llm-api mode uses.
   `writing_rules` are universal (code-owned): apply them plus any `career_context.md` style
   preferences, and the universal rules win on any conflict.
2. Read `outputs/state/compiled/career_context.min.md` (if present) else `profile/career_context.md`
   for resume style, cover-letter style, and evidence boundaries.
3. Resolve the configured resume path from `config/job_hunter.yml:profile.resume_tex`
   (e.g. `profile/resume.tex` or `profile/resume_double_column.tex`).
   Copy it to the job folder without reading it into context:
   ```bash
   cp <resolved-resume-path> outputs/jobs/<slug>/resume_tailored.tex
   ```
   Then read `outputs/state/compiled/resume.compact.txt` (if present) to understand existing content
   and plan which sections to change. Do NOT load the full `.tex` into context.
4. Read only selected Final stories (from `matched_story_ids` in score.yml).
5. Tailor `outputs/jobs/<slug>/resume_tailored.tex` via surgical edits — do NOT regenerate the full file:
   - For each section that needs changing: Read only the specific target lines (use offset/limit),
     then Edit in place with the tailored text.
   - Summary (`\cvtagline` or equivalent): mirror top `keywords` from tailor-context.
   - Experience bullets: edit `\item` lines that are weak on `keywords`; do not touch untargeted bullets.
   - Skills section: reorder to front-load `keywords`.
   - Apply `tailoring_rules`, `positioning_rules`, and `project_rules` exactly.
   - Verify char limits from `career_context.min.md` Bullet/Summary guidance before each edit.
   - Preserve document class, layout, commands, employers, titles, dates, and verified facts.
   - If an Edit fails (old_string not found): Read the affected section by line range, then retry.
   - Never fall back to regenerating the full file.
   - Before writing each `\item` or summary line: count characters. If it exceeds the limit
     in career_context.md, shorten until it fits. Do not write the edit if it still exceeds.
   - After all edits: read back each changed line. If any employer, title, date, metric, or
     skill appears that was not in the base resume or matched Final stories, revert that line
     to the original base resume text. Do not substitute an alternative — revert.
6. Run `job-hunter internal telemetry-mark --phase tailoring --state end`, then
   `job-hunter internal telemetry-mark --phase cover_letter --skill cover_letter --job <slug> --state start`.
   Write `outputs/jobs/<slug>/cover_letter.md`:
   - Apply `writing_rules.cover_letter` and `writing_rules.evidence` — universal, win over any conflicting style preference.
   - Tone: `cover_constraints.tone`.
   - Length: target `cover_constraints.target_words` words,
     hard max `cover_constraints.max_words` words,
     `cover_constraints.paragraphs` paragraphs.
   - Follow `cover_constraints.paragraph_structure` per paragraph (name, max_sentences, purpose).
   - Never include phrases from `cover_constraints.forbidden_phrases`.
   - Follow every rule in `cover_constraints.style_rules`.
   - No story IDs, no markdown headers, no bullet points — plain text only.
   - Start directly with the first sentence of the letter body.
7. Run `job-hunter internal telemetry-mark --phase cover_letter --state end`, then
   `job-hunter internal telemetry-mark --phase pdf --skill pdf --job <slug> --state start`, then:
   ```bash
   job-hunter internal compile-pdf --job <slug>
   ```
   This copies configured `altacv.cls` and profile image into the job folder before compiling.
8. Run `job-hunter internal telemetry-mark --phase pdf --state end` after compilation.
   Run `job-hunter internal telemetry-outcome --job <slug> --tailored` when the tailored `.tex` exists.
   If compilation fails, keep `.tex` and cover letter, report PDF failure, and return.
   Telemetry marker failures are non-blocking.

## Rules

Universal fabrication, evidence, and character-limit rules apply (`_rules.md`, inherited
automatically, plus `writing_rules` from the tailor-context payload) — they win over any
conflicting style preference. Tailor-specific procedure on top of those:

- Never regenerate the full file. Surgical edits only.
- If post-edit verification detects fabrication: revert the line to the original base resume text, not substitute.
- Never write `resume_tailored.md`.
- Profile image is copied only when configured and present.
- Do not update README or processed state. Caller owns workflow state.

## Output

`<Company> — resume .tex + cover letter written; PDF generated|failed`

Control returns to the calling workflow; caller immediately continues.
