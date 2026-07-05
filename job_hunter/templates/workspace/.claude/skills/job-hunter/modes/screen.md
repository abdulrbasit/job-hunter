# Screen

Semantically judge candidates retained by deterministic Python screening.

Run `job-hunter internal telemetry-mark --phase screening --skill screening --state start`
before reading inputs. Telemetry failure is non-blocking and must not be printed.

## Inputs

- `outputs/state/agent_candidate_queue.json`
- `outputs/state/batch_screen.yml`
- `config/job_hunter.yml`
- `outputs/state/compiled/career_context.min.md` if present, else `profile/career_context.md`

Python already removes objective failures: exact excluded title terms, exact excluded
companies, duplicates, invalid URLs, clear stale dates/content, strong excluded-language
matches, and unambiguous structured-location mismatches.

Review every row in `batch_screen.yml:retained`. Use title, company, location, snippet,
and `judgment_signals`.

- `PASS`: plausible target role.
- `SKIP`: excluded employer industry, functionally engineering rather than product,
  too senior, explicit experience exceeds configured limit without strategic override,
  another career-context dealbreaker clearly applies, or the posting shows clear signs
  of being closed/filled (e.g., "position filled", "no longer accepting applications",
  "requisition closed" in snippet — especially when `posting_date_status=missing`).

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

Apply every decision in one deterministic call — do not loop per candidate:

```bash
job-hunter internal agent-context apply-judgment \
  --judgment outputs/state/batch_judgment.yml \
  --screen outputs/state/batch_screen.yml
```

This discards every `SKIP` (status `discarded`, reason `screen_skip`) and returns
`retained_candidate_ids`. Run `job-hunter internal telemetry-mark --phase screening --state end`,
then print counts only.
