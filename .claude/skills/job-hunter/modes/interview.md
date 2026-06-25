# Interview Prep

Single responsibility: produce a question bank and story mapping for ONE job interview.

Slug: `$ARGUMENTS`

## Token Rules

- Start with `job-hunter internal agent-context score --mode full --job <slug>`.
- Story bank: use matched_story_ids first → story-index if thin → stories-final for broad comparison. Never use Draft/raw sections.
- Read `profile/career_context.md` when present for learned interview preferences, dealbreakers, and calibration notes.

## Steps

1. Identify role level and interview themes from bounded job context and score gaps.
2. Generate 8-12 questions across behavioral, technical/product, and company/culture categories.
3. Map each question to a selected story, partial story, or "No story - prepare fresh".
4. Write `outputs/jobs/{slug}/interview_prep.md`.

## Rules

- Questions must be grounded in the JD and selected verified stories.
- Never invent story titles or story content.
- Do not commit; leave the artifact for review.

## Output

```
Interview prep written -> outputs/jobs/{slug}/interview_prep.md
Questions: N | Story gaps: M
```

When called from a workflow, control returns to the calling workflow after printing this output; the caller must immediately continue the next step in the same assistant turn.
