# LinkedIn Ideas

Single responsibility: generate a weekly batch of grounded post ideas. Nothing is posted.

## Token Rules

- Start with `job-hunter internal agent-context evidence-context` → `writing_rules.evidence`.
- Then `job-hunter internal agent-context linkedin-weekly`.
- Use `story-index` metadata first; use `stories-final` only when the LLM needs to compare verified achievements for proof-point ideas.
- Do not read all job folders, Draft/raw stories, or full candidate snapshots.

## Steps

1. Review compact weekly jobs/themes and existing `outputs/linkedin/ideas.md`.
2. Generate 5-10 ideas across proof point, observation, career reflection, and engagement hook categories.
3. Append to `outputs/linkedin/ideas.md`.
4. Do not commit here; `/job-hunter finalize` handles reviewed `outputs/linkedin/` drafts.

## Rules

- Every proof point must cite a selected verified story ID or job slug.
- Apply every rule in `writing_rules.evidence` exactly — universal (code-owned), wins over any
  conflicting `career_context.md` preference.
- Do not draft or post.

## Output

```
LinkedIn ideas appended -> outputs/linkedin/ideas.md
Ideas: N
```
