# Job Hunter: Universal Rules

These rules apply to every mode: tailor, score, cover letter, batch, and one.

## Evidence Boundary
- Use only: base resume, matched Final stories, company_research.md.
- Never infer, extrapolate, or combine claims across sources.
- No new facts, scope, proof points, or metrics not already in those sources.

## Fabrication Boundary — NEVER
- Invent or modify: metrics (numbers, %, counts), employers, job titles, dates, certifications,
  skills, project names, or outcomes.
- Add content not verifiable against the base resume or matched Final stories.
- Uncomment or add sections solely to fill space.

## Allowed Modifications
- Reorder bullets, skills, or sections.
- Rephrase existing content to front-load JD keywords.
- Remove weak or irrelevant bullets.
- Edit summary/tagline to mirror top JD keywords — using only existing proof points.

## Output Integrity
- Preserve all LaTeX commands, document class, layout, employers, titles, dates exactly as written.
- Cover letter: plain text only — no markdown headers, no bullets, no story IDs in brackets.
- Score output: YAML only — no commentary.

## Character Limits
- Bullet and summary char limits are defined in `career_context.md` (Bullet/Summary guidance).
- Count characters before writing each bullet or summary line. Reject if over limit.

## Score Decisions
- `APPLY` only when score ≥ `min_fit_score` threshold, OR a matching strategic override applies.
- `strategic_overrides[].bypass_max_years_experience: true` skips the years filter for that company.
- Do not credit skills or experience not in the resume or Final stories.

## Industry Exclusions
- Jobs whose industry matches any entry in `excluded_industries` (from config): decision is `SKIP`
  regardless of fit score.
