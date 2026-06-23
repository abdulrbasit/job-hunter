# Screen

Single responsibility: apply configured exclusion rules before scoring. Do not fetch JDs, score, rank, or inspect full snapshots.

## Inputs

- Bounded queue from `job-hunter agent-context candidates`.
- Exclusion rules from the table below, live config (`config/job_hunter.yml`), and code-owned stale/language indicators.

## Token Rules

- Read one compact queue file, not raw `outputs/candidates/*`.
- Print the summary line and indexes only. Never print per-candidate analysis, PASS rows, or full snippets.
- Ambiguous candidates get an index only; no inline reasoning.

## Steps

1. Apply the 7 rejection rules below against each candidate's compact metadata.
2. When evidence is unclear, keep the candidate as ambiguous/pass.
3. Return retained queue indexes for the calling workflow.

## Rejection Rules

| # | Rule | Source | Check |
|---|---|---|---|
| 1 | Excluded title | `exclusions.title_terms` | Title contains a user-excluded term, including unwanted level terms such as junior, principal, intern, or working student if configured |
| 2 | Excluded industry | `exclusions.industries` | Snippet clearly describes an excluded employer industry |
| 3 | Stale posting | Code-owned stale indicators + posted date | Exact stale phrase or clearly old posted date |
| 4 | Excluded language | `exclusions.languages` + code-owned indicators | Multiple language markers or predominantly excluded language |
| 5 | Excluded company | `exclusions.companies` | Exact normalized company match |
| 6 | Wrong location | Enabled region locations + candidate location | Structured location clearly outside target and not remote/hybrid |
| 7 | Experience over limit | `scoring.max_years_experience_required` | Explicit years requirement exceeds configured limit |

Notes: Ambiguous evidence passes. Check structured location before title/snippet text. There is no separate seniority rule; users own level filtering through `exclusions.title_terms`.

## Output

```
Pre-screen done: <N> passed, <M> skipped from <total>.
Retained indexes: <comma-separated queue indexes>
Ambiguous indexes: <comma-separated queue indexes or none>
```

When called from a workflow, return to the caller immediately after printing this output. Do not pause or wait for user input.
