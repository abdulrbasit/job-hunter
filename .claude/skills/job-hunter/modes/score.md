# Score

Score one job against the resume and story bank. Return control to the calling workflow immediately after — do not wait for user input.

## Inputs

Run `job-hunter agent-context score --mode full --job <slug>` to get:
- Job description (full or summary)
- Resume bullets (active role sections)
- Story bank entries (for matching)

## Scoring

Evaluate fit across four dimensions:
1. **Title / level match** — does the role title match seniority and function?
2. **Skill overlap** — required skills present in resume or stories?
3. **Domain fit** — industry, product area, or tech stack alignment?
4. **Location / work mode** — remote/hybrid/on-site vs. candidate preference?

Produce a score 0–100. Read thresholds from `config/job_hunter.yml` at runtime.

## Output Format

```yaml
score: <0-100>
decision: APPLY | SKIP   # APPLY ≥ min_fit_score, SKIP below
matched_story_ids: ["STAR-001", "STAR-004"]
matched:
  - "keyword from JD matched in resume or stories"
gaps:
  - "Requires 5+ years Kubernetes; resume shows 2."
role_summary: "One sentence on what this role requires."
score_rationale: "One sentence explaining why this score was assigned."
recommendation: "Apply / Skip"
```

Write `outputs/jobs/<slug>/score.yml` with the above fields.

Then write `outputs/jobs/<slug>/evaluation.md`:

```markdown
# Evaluation: <slug>

**Score:** <score> / 100 | **Decision:** <decision>

## Fit Summary
<2-3 sentences drawn from score_rationale and role_summary>

## Matched Stories
<list of matched_story_ids with one-line context each>

## Gaps
<list from gaps field>

## Recommendation
<recommendation — one sentence>
```

Control returns to the calling workflow immediately after writing both files.

## Rules

- Read `min_fit_score` from `config/job_hunter.yml` — never hardcode.
- `decision`: APPLY if score ≥ min_fit_score, SKIP otherwise.
- `matched_story_ids` must list only story bank IDs that directly support fit.
- `matched` lists JD keywords present in resume or stories.
- Caller must immediately continue the next step after this skill completes.
- Control returns to the calling workflow — do not prompt the user.
