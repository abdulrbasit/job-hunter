# Morning Brief

Thin start-of-day orchestrator. Keep output compact; never read raw candidate snapshots directly.

## Steps

1. Run `git pull origin main`.
2. Run `job-hunter agent-context brief` and print the result.
3. Run `job-hunter dashboard --no-interactive` if applications exist, and include only the compact active-application count/table.
4. If candidates are ready, tell the user to run `/job-hunter batch`.

## Output

Print only the compact brief from `agent-context` plus one next action:

- `Run /job-hunter batch.` when candidates are available.
- `Run job-hunter run-daily --region <region>.` when no candidates are available.
