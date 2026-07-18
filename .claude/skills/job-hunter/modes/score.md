# Score

Score one imported job against bounded JD context, configured base resume, and verified Final stories.

Run (skip both if the caller — e.g. batch — already fetched this job's scoring context with `--no-profile`; reuse that payload plus the profile already loaded once for the batch):

```bash
job-hunter internal telemetry-mark --phase scoring --skill scoring --job <slug> --state start
job-hunter internal agent-context score --mode full --job <slug>
```

Use `resume_tex`, `career_context`, `story_index`, live thresholds, `profile.excluded_industries`,
and strategic overrides from that payload. Note: `resume_tex` in the payload is already the
compact plain-text version of the resume when `outputs/state/compiled/resume.compact.txt` is
present — no need to load the full `.tex` for scoring. Start from `matched_stories`
(keyword-ranked shortlist against the JD) before scanning the full `story_index`. Read
selected stories with `agent-context story --id`.

Apply `decision_rules` from the payload exactly — they govern the APPLY/SKIP call, the
`bypass_max_years_experience` override, and the industry exclusion.

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
Then validate (see `required_outputs` in the payload for both paths):

```bash
job-hunter internal agent-context validate-score --path outputs/jobs/<slug>/score.yml
```

Run `job-hunter internal telemetry-mark --phase scoring --state end` after validation.
Run `job-hunter internal telemetry-outcome --job <slug> --decision <APPLY|SKIP>` with the validated decision.
Telemetry marker failures are non-blocking.
