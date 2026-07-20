# Tailor

Produce application artifacts for one scored job.

Slug: `$ARGUMENTS`

## Preconditions

- `outputs/jobs/<slug>/score.yml` must exist with `decision: APPLY`. If missing or `SKIP`,
  stop and print: "No APPLY score for `<slug>` — run `/job-hunter score <slug>` first."
- The configured `profile.resume_tex` file (`config/job_hunter.yml`) must exist. If missing,
  stop and print: "Base resume not found at `<path>` — run `/setup resume` or the dashboard's
  Career Profile panel first."

## Inputs

- `job-hunter internal agent-context tailor-context --job <slug>` → tailoring_rules, positioning_rules,
  project_rules, keywords, gaps, cover_constraints, writing_rules, language (job/output/base language,
  language_rules), base_resume (source resume path for the routed language), required_outputs
  (language-suffixed artifact paths — always write to exactly these paths)
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
3. Copy the payload's `base_resume` (the source resume for the routed output language —
   the target language's own base when one exists, else the base-language resume) to the
   payload's resume `required_outputs` path (language-suffixed, e.g.
   `outputs/jobs/<slug>/resume_tailored.de.tex`):
   ```bash
   cp <base_resume> <required_outputs resume path>
   ```
   Then read `outputs/state/compiled/resume.compact.txt` (if present) to understand existing content
   and plan which sections to change. Do NOT load the full `.tex` into context — except when
   `language.language_rules` is non-empty (translate-and-tailor): then the output language differs
   from the source resume's language, `resume.compact.txt` reflects the base language only, and
   every edited line must be written in the output language per `language.language_rules`.
4. Read only selected Final stories (from `matched_story_ids` in score.yml).
5. Tailor the copied resume `.tex` via surgical edits — do NOT regenerate the full file.
   When `language.language_rules` is non-empty, apply those rules to every edit: the human-readable
   text you write must be in `language.output_language`; LaTeX commands, structure, employers, and
   dates stay exactly as in the source.
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
   Write the cover letter to the payload's cover `required_outputs` path (language-suffixed,
   e.g. `outputs/jobs/<slug>/cover_letter.de.md`) in `language.output_language`:
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
- Write artifacts only to the payload's `required_outputs` paths — the language suffix is part of the contract.
- The cover letter is always written in `language.output_language` (same language as the resume output).
- Profile image is copied only when configured and present.
- Do not update README or processed state. Caller owns workflow state.

## Output

`<Company> — resume .tex + cover letter written; PDF generated|failed`

Control returns to the calling workflow; caller immediately continues.
