# Interview Prep

Single responsibility: produce a question bank and story mapping for ONE job interview.

Slug: `$ARGUMENTS`

Run `job-hunter internal telemetry-mark --phase interview --skill interview --job <slug> --state start`.
Telemetry failure is non-blocking and must not be printed.

## Token Rules

- Start with `job-hunter internal agent-context interview-context --job <slug>`.
- Story bank: use `job.score.matched_story_ids` first → `matched_stories` (JD-keyword-ranked shortlist) if thin → stories-final for broad comparison. Never use Draft/raw sections.
- Read `outputs/state/compiled/career_context.min.md` if present, else `profile/career_context.md`, for learned interview preferences, dealbreakers, and calibration notes.

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

Run `job-hunter internal telemetry-mark --phase interview --state end` before printing.

```
Interview prep written -> outputs/jobs/{slug}/interview_prep.md
Questions: N | Story gaps: M
```

When called from a workflow, control returns to the calling workflow after printing this output; the caller must immediately continue the next step in the same assistant turn.
