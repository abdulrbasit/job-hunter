# Process Candidate Batch

**Non-interactive. Runs to completion without stopping.**

## Non-Interactive Contract

`/job-hunter batch` is the only input required. Do not stop or ask questions until one of the two valid exit points:
1. The final `### Summary` block.
2. Hard blocker: empty queue after rebuild, missing `config/job_hunter.yml`, or auth failure blocking all tool access.

Status lines, non-blocking failures, and phase completions are **not** stopping points. Never write "Shall I continue?", "Should I proceed?", or any variant — proceed instead.

## Rules

- Execute child skills inline: read the mode file, apply instructions, write artifacts, resume next step. Do not print slash commands as handoffs.
- When an atomic skill returns to caller, continue the next step immediately.
- Frozen batches only. Default 15 candidates; `--batch-size` and `--dry-run` available.
- Python screening via `screen-batch`; semantic judgment via `screen.md`.
- All lifecycle decisions via `job-hunter internal agent-context lifecycle` using `candidate_id`.
- Do not refresh the queue inside a batch. Rebuild only after the batch is complete.
- Never mark an entire source file processed after systemic fetch failures; mark only specific terminal URLs.
- One compact line per phase to chat. Durable data (scores, stories, resume, cover letter) to files only.
- Silent for per-job SKIPs; report counts in batch totals only.

## Steps

1. `git pull origin main`.

2. Build queue and freeze batch:
   ```bash
   job-hunter internal agent-context batch --scope briefing-backlog --batch-size 15 \
     --write-queue outputs/state/agent_candidate_queue.json \
     --write-batch outputs/state/agent_candidate_batch.json
   job-hunter internal agent-context screen-batch \
     --batch outputs/state/agent_candidate_batch.json \
     --write-screen outputs/state/batch_screen.yml
   ```
   Execute `screen.md` inline against every retained candidate.
   Print only: `Batch 1: 15 loaded, N screen skips, M retained`.

3. Pre-load shared context once:
   - Read `config/job_hunter.yml`
   - Read `profile/career_context.md`
   - `job-hunter internal agent-context stories-final`

4. Mark every skipped candidate in `batch_screen.yml` terminal with reason `screen_skip` using `candidate_id`.

5. For each retained candidate, one at a time:
   - `job-hunter internal agent-context lifecycle --queue ... --candidate-id <id>`
   - `job-hunter internal import-job --queue ... --candidate-id <id>`
   - Lifecycle for the created job. If `webfetch_required`: WebFetch once → temp file → rerun with `--fallback-text-file`. Reimport only on `reimport_with_fallback`; else mark terminal `missing_full_jd`.
   - `job-hunter internal agent-context score --mode full --job <slug>`
   - Execute `score.md` inline (full mode) — writes `score.yml` and `evaluation.md`.
   - `job-hunter internal agent-context validate-score --path outputs/jobs/<slug>/score.yml`
   - `job-hunter internal discard-job --job <slug>` for below-threshold jobs.

6. Tailor all APPLY jobs (descending score, at or above fit threshold). For each:
   - Execute `research.md` inline.
   - Execute `tailor.md` inline.
   - `job-hunter internal update-readme --job <slug>`
   - `job-hunter internal mark-processed --url "<url>" --company "<company>" --title "<title>"`
   PDF failure non-blocking only when `resume_tailored.tex` exists. README update requires the `.tex`.

7. Rebuild queue:
   ```bash
   job-hunter internal agent-context candidates --scope briefing-backlog \
     --write-queue outputs/state/agent_candidate_queue.json
   ```

8. `job-hunter internal cleanup-transient`

## Failure Handling

- PDF/LaTeX: log to `outputs/jobs/<slug>/errors.log`, mark `compile_failed`, continue.
- Import failure: score on title + company; drop only if title is excluded.

## Output

```
### Summary
Batch 1: 15 loaded, N screen skips, M retained
Scored: A APPLY, B SKIP
Tailored: N, marked processed: M
LLM search: enabled (<M> candidates added) | skipped (threshold met) | disabled
Cleaned transient batch files

Tailoring complete. Changes are uncommitted. Run /job-hunter finalize only after review.
Review: `job-hunter dashboard --no-interactive`
Optional: /job-hunter outreach <slug> or /job-hunter interview <slug>
```

No repository commits or pushes in this workflow.
