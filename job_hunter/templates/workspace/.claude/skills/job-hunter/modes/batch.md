# Process Candidate Batch

Process a frozen candidate batch end-to-end. Never wait for a user to type "Continue" between inline phases; each phase hands off to the next automatically.

## Orchestration Rules

- Do not pause between phases. After the user starts `/job-hunter batch`, continue end-to-end through screen, import, full score, research, tailor, README update, and LLM search phases without stopping for user input. A one-line status update is not an end state.
- Execute child skills inline in this same run. To use a child skill, read its mode file, apply its instructions to the current compact context, write the required artifacts, then resume the next step. Do not print slash commands as handoffs.
- When an atomic skill says it returns to the caller, treat that as control returning to this workflow; continue the next step immediately.
- Use frozen batches. Default to 15 candidates; `--batch-size` and `--dry-run` are available.
- Use `screen-batch` for objective Python screening, then `screen.md` for semantic judgment.
- Use `job-hunter agent-context lifecycle` for deterministic candidate/JD lifecycle decisions.
- Do not refresh the active queue inside a batch. Mark terminal decisions by `candidate_id`, then rebuild only after the batch is complete.
- End only when the current frozen batch and any triggered LLM-search batch are processed, or when a hard blocker requires user input.
- Never mark an entire candidate source file processed after systemic fetch failures. Mark only specific terminal job URLs.

## Token Rules

- Build the queue and freeze the next batch in one command.
- Process one queue item at a time with `candidate_id`, never stale numeric indexes.
- One compact line per phase to chat. Never print scoring analysis, matched/gaps blocks, story text, JD excerpts, resume text, or cover letter content.
- Durable data (screening, scores, stories, resume, cover letter) goes to files only.
- Silent for per-job SKIPs; report counts only for batch totals.

## Steps

1. Run `git pull origin main`.

2. Build the queue and freeze the first batch:
   ```bash
   job-hunter agent-context batch --scope briefing-backlog --batch-size 15 \
     --write-queue outputs/state/agent_candidate_queue.json \
     --write-batch outputs/state/agent_candidate_batch.json
   job-hunter agent-context screen-batch \
     --batch outputs/state/agent_candidate_batch.json \
     --write-screen outputs/state/batch_screen.yml
   ```
   Then execute `.claude/skills/job-hunter/modes/screen.md` inline against every retained candidate.
   Print only: `Batch 1: 15 loaded, N screen skips, M retained`.

3. Pre-load shared context once per batch:
   - Read `config/job_hunter.yml` for deterministic thresholds and exclusions.
   - Read `profile/career_context.md` for targeting and writing guidance.
   - `job-hunter agent-context stories-final`

4. For every skipped candidate in `batch_screen.yml`, mark terminal with lifecycle reason `screen_skip` using `candidate_id`. Do not refresh the queue.

5. For each retained candidate, one at a time:
   - Run `job-hunter agent-context lifecycle --queue ... --candidate-id <id>`.
   - Run `job-hunter import-job --queue ... --candidate-id <id>`.
   - Run lifecycle for the created job. If it returns `webfetch_required`, use WebFetch once, write the fetched text to a temporary file, and rerun lifecycle with `--fallback-text-file <path>`. Reimport only when lifecycle returns `reimport_with_fallback`; otherwise mark terminal with reason `missing_full_jd`.
   - Run `job-hunter agent-context score --mode full --job <slug>`.
   - Execute `.claude/skills/job-hunter/modes/score.md` inline in full mode; it writes `score.yml` and `evaluation.md`.
   - Validate the score: `job-hunter agent-context validate-score --path outputs/jobs/<slug>/score.yml`.
   - Discard below-threshold jobs: `job-hunter discard-job --job <slug>`.

6. Tailor all APPLY jobs, descending score, whose score meets the fit threshold from config.
   For each qualifying job, complete all four steps before moving to the next:
   - Execute `.claude/skills/job-hunter/modes/research.md` inline.
   - Execute `.claude/skills/job-hunter/modes/tailor.md` inline.
   - Run `job-hunter update-readme --job <slug>`.
   - Run `job-hunter mark-processed --url "<url>" --company "<company>" --title "<title>"`.
   PDF failure is non-blocking only when `resume_tailored.tex` exists. README update requires the `.tex`.

7. Rebuild the candidate queue before starting the next batch or reporting the final summary:
   ```bash
   job-hunter agent-context candidates --scope briefing-backlog \
     --write-queue outputs/state/agent_candidate_queue.json
   ```

8. LLM job search: run `agent-context llm-search-config`. If disabled, report `LLM search: disabled`.
   If enabled and `tailored_count < trigger_threshold`: execute `.claude/skills/job-hunter/modes/search.md` inline. If it writes `outputs/state/llm_search_queue.json`, immediately screen that queue and apply the same frozen-batch import/full-score/tailor loop before any final summary. `trigger_threshold` means AI web search runs only when normal sources yielded fewer than that many candidates; `max_results_per_run` caps AI web-search candidates added in one run.

9. After all batch work is complete, run `job-hunter cleanup-transient`.
   Removes stale scratch files: `agent_candidate_queue.json`, `agent_candidate_batch.json`, `batch_screen.yml`, `batch_scores.yml`, and `llm_search_queue.json`. Does not delete `applications.yml`, `discovered_urls.yml`, tailored job folders, or candidate snapshots.

## Failure Handling

- PDF/LaTeX compile failures: log to `outputs/jobs/<slug>/errors.log`, mark as `compile_failed`, and continue.
- Import failures: score based on available title + company. Do not drop the candidate unless the title itself is excluded.
- Exclusion rule sources: `config/job_hunter.yml` provides companies, title terms, languages, industries, and scoring limits. Code provides stale indicators and listing URL patterns. Dedup comes from `outputs/state/discovered_urls.yml`.

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
