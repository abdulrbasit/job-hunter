# Tailor

Produce application artifacts for one scored job.

Slug: `$ARGUMENTS`

## Inputs

- `job-hunter agent-context tailor-context --job <slug>` → tailoring_rules, positioning_rules,
  project_rules, keywords, gaps, cover_constraints
- `job-hunter agent-context score --mode full --job <slug>` → story_index, job meta, score.yml
- `outputs/jobs/<slug>/score.yml` — matched_story_ids
- Configured base resume from `config/job_hunter.yml:profile.resume_tex`
- `profile/career_context.md` — resume style, cover-letter style, and evidence boundaries
- `outputs/jobs/<slug>/company_research.md`, when present

## Steps

1. Run `job-hunter agent-context tailor-context --job <slug>`.
   Apply every field exactly as delivered — these are the same constraints that llm-api mode uses.
2. Read `profile/career_context.md` for resume style, cover-letter style, and evidence boundaries.
3. Read the complete configured base resume `.tex`.
4. Read only selected Final stories (from `matched_story_ids` in score.yml).
5. Write `outputs/jobs/<slug>/resume_tailored.tex`:
   - Mirror `keywords` in summary and bullets.
   - Do not emphasize `gaps`.
   - Apply `tailoring_rules`, `positioning_rules`, and `project_rules` exactly.
   - Preserve document class, layout, commands, employers, titles, dates, and verified facts.
6. Write `outputs/jobs/<slug>/cover_letter.md`:
   - Tone: `cover_constraints.tone`.
   - Length: target `cover_constraints.target_words` words,
     hard max `cover_constraints.max_words` words,
     `cover_constraints.paragraphs` paragraphs.
   - Follow `cover_constraints.paragraph_structure` per paragraph (name, max_sentences, purpose).
   - Never include phrases from `cover_constraints.forbidden_phrases`.
   - Follow every rule in `cover_constraints.style_rules`.
   - No story IDs, no markdown headers, no bullet points — plain text only.
   - Start directly with the first sentence of the letter body.
7. Run:
   ```bash
   job-hunter compile-pdf --job <slug>
   ```
   This copies configured `altacv.cls` and profile image into the job folder before compiling.
8. If compilation fails, keep `.tex` and cover letter, report PDF failure, and return.

## Rules

- Never write `resume_tailored.md`.
- Never fabricate metrics, skills, titles, employers, dates, or outcomes.
- Profile image is copied only when configured and present.
- Do not update README or processed state. Caller owns workflow state.

## Output

`<Company> — resume .tex + cover letter written; PDF generated|failed`

Control returns to the calling workflow; caller immediately continues.
