# Screen

Semantically judge candidates retained by deterministic Python screening.

## Inputs

- `outputs/state/agent_candidate_queue.json`
- `outputs/state/batch_screen.yml`
- `config/job_hunter.yml`
- `profile/career_context.md`

Python already removes objective failures: exact excluded title terms, exact excluded
companies, duplicates, invalid URLs, clear stale dates/content, strong excluded-language
matches, and unambiguous structured-location mismatches.

Review every row in `batch_screen.yml:retained`. Use title, company, location, snippet,
and `judgment_signals`.

- `PASS`: plausible target role.
- `SKIP`: excluded employer industry, functionally engineering rather than product,
  too senior, explicit experience exceeds configured limit without strategic override,
  or another career-context dealbreaker clearly applies.

Industry terms are signals, never proof. Distinguish employer industry from customers,
features, compliance responsibilities, and prior experience. Ambiguous evidence passes.

Write `outputs/state/batch_judgment.yml`:

```yaml
decisions:
  - candidate_id: cand_...
    decision: PASS
    reason: ""
    rationale: "SaaS employer; banking describes customers."
```

For each `SKIP`, run:

```bash
job-hunter internal agent-context lifecycle --queue outputs/state/agent_candidate_queue.json \
  --candidate-id <id> --mark-terminal screen_skip
```

Return retained candidate IDs. Print counts only.
