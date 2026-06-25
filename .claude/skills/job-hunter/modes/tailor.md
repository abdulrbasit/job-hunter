# Tailor

Produce application artifacts for one scored job.

Slug: `$ARGUMENTS`

## Inputs

- `job-hunter agent-context score --mode full --job <slug>`
- `outputs/jobs/<slug>/score.yml`
- Configured base resume from `config/job_hunter.yml:profile.resume_tex`
- Selected Final stories from `matched_story_ids`
- `profile/career_context.md` for resume style, cover-letter style, and evidence boundaries
- `outputs/jobs/<slug>/company_research.md`, when present

## Steps

1. Read the complete configured base resume `.tex`.
2. Read only selected Final stories. Use `stories-final` only when score evidence is thin.
3. Write the complete tailored LaTeX document to `outputs/jobs/<slug>/resume_tailored.tex`.
   Preserve document class, layout, commands, employers, titles, dates, and verified facts.
   Tailor summary, relevant bullets, skills order, and active projects only.
4. Write `outputs/jobs/<slug>/cover_letter.md`.
5. Run:
   ```bash
   job-hunter compile-pdf --job <slug>
   ```
   This copies configured `altacv.cls` and profile image into the job folder before compiling.
6. If compilation fails, keep `.tex` and cover letter, report PDF failure, and return.

## Rules

- Never write `resume_tailored.md`.
- Never fabricate metrics, skills, titles, employers, dates, or outcomes.
- Profile image is copied only when configured and present.
- Do not update README or processed state. Caller owns workflow state.

## Output

`<Company> — resume .tex + cover letter written; PDF generated|failed`

Control returns to the calling workflow; caller immediately continues.
