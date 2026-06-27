# Score

Score one imported job against bounded JD context, configured base resume, and verified Final stories.

Run:

```bash
job-hunter internal agent-context score --mode full --job <slug>
```

Use `resume_tex`, `career_context`, `story_index`, live thresholds, and strategic overrides
from that payload. Note: `resume_tex` in the payload is already the compact plain-text
version of the resume when `outputs/state/compiled/resume.compact.txt` is present — no
need to load the full `.tex` for scoring. Read selected stories with `agent-context story --id`.

Also apply from the score payload:
- `strategic_overrides[].bypass_max_years_experience` — `true` means skip the years-of-experience
  filter entirely for that company.
- `profile.scoring.excluded_industries` — job in an excluded industry → `SKIP` regardless of score.

`matched_story_ids` in score.yml: list the IDs of all Final stories used as evidence.
Empty list is valid (means no story evidence was consulted).

Write `outputs/jobs/<slug>/score.yml`:

```yaml
score: 0
decision: APPLY
matched_story_ids: []
matched: []
gaps: []
role_summary: ""
score_rationale: ""
recommendation: ""
```

Write `evaluation.md` with Fit Summary, Verified Evidence, Gaps, and Recommendation.
Then validate:

```bash
job-hunter internal agent-context validate-score --path outputs/jobs/<slug>/score.yml
```

`APPLY` only when score meets live threshold or strategic override; otherwise `SKIP`.
Credit only evidence present in base resume or selected Final stories. Never fabricate.
