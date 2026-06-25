# Score

Score one imported job against bounded JD context, configured base resume, and verified Final stories.

Run:

```bash
job-hunter internal agent-context score --mode full --job <slug>
```

Use `resume_tex`, `career_context`, `story_index`, live thresholds, and strategic overrides
from that payload. Read selected stories with `agent-context story --id`.

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
