# Tailor

Tailor resume and cover letter for one job. After completing, control returns to the calling workflow — caller must immediately continue the next step.

## Inputs

```bash
job-hunter agent-context score --mode full --job <slug>   # JD, resume, stories
```

Also read `profile/career_context.md` for targeting, resume style, cover-letter style, evidence boundaries, and calibration notes.

## Steps

1. **Load research** — read `outputs/jobs/<slug>/company_research.md` if it exists. Use the Application Angle section to inform cover letter positioning and story selection.

2. **Select stories** — pick 3–5 stories from the story bank whose `matched_story_ids` overlap with the job's required skills.

3. **Tailor resume bullets** — rewrite active-role bullets to front-load keywords from the JD. Do not fabricate metrics.

4. **Draft cover letter** — follow cover-letter style from `profile/career_context.md` if present. Default structure (4 paragraphs):
   - Why this role (1–2 sentences, use Application Angle from research)
   - Strongest story (STAR summary, 2 sentences)
   - Second strongest story (STAR summary, 2 sentences)
   - Close with availability and next step

5. **Write outputs**:
   - `outputs/jobs/<slug>/resume_tailored.md` — tailored bullets
   - `outputs/jobs/<slug>/cover_letter.md` — cover letter draft

6. **Compile PDF** (if LaTeX is available):
   ```bash
   job-hunter compile-pdf <slug>
   ```
   PDF failure is non-blocking — log and continue.

7. Return. control returns to the calling workflow — do not prompt the user.

## Rules

- No fabricated metrics or unverified claims.
- Scope anchors only: use titles and org-level language from the resume.
- No em dashes in output text.
- caller must immediately continue the next step after this skill completes.
