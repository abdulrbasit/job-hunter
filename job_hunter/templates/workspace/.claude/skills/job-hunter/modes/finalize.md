# Finalize

Single responsibility: finalize reviewed durable completed outputs and optionally push to origin. Interactive finalize remains review-oriented; auto-run uses `finalize-run --mode auto` to commit routine state.

## Token Rules

- Show `git status --short` and `git diff --stat` only.
- Do not paste full diffs unless the user asks.
- Keep the confirmation prompt to durable paths and the commit message.

Commit message: use `$ARGUMENTS` verbatim if provided (excluding `--push`); otherwise derive from staged paths (see step 4).

Push: include `--push` in `$ARGUMENTS` or the user replies "yes and push" to send to origin.

## Steps

1. Show current changes:
   ```bash
   git status --short
   git diff --stat
   ```

2. **Pre-flight:** Scan modified files for secrets. FAIL and stop if any match `*.env`, `*.key`, `*.pem`, `*secret*`, `*credential*`, `*password*`.

3. Do not stage files manually. Finalization is handled by `job-hunter finalize-run`, which stages durable repo state:
   - setup/config/profile files
   - job, candidate, LinkedIn, API-usage, token-metrics, and processed-job outputs
   - transient queue, screen, and batch-score scratch files are cleaned up, not pushed
   It ignores files outside the finalization allowlist.

4. Draft commit message:
   - If provided in `$ARGUMENTS`, use it verbatim.
   - Otherwise inspect `git status --short` and apply the first matching rule:

   | Dominant pending paths | Commit message |
   |---|---|
   | `outputs/jobs/<slug>/` — exactly one job folder | `feat(jobs): tailor <slug>` |
   | `outputs/jobs/` — multiple job folders | `feat(jobs): tailor batch YYYY-MM-DD` |
   | `profile/story_bank.md` (no jobs) | `feat(stories): update story bank` |
   | `outputs/linkedin/` (no jobs) | `feat(linkedin): add drafts YYYY-MM-DD` |
   | `config/` only | `chore(config): update search config` |
   | `profile/` only (non-story) | `chore(setup): update profile` |
   | `README.md` only | `chore(docs): update README` |
   | jobs + other paths | use the `feat(jobs)` message |
   | anything else | `chore: update YYYY-MM-DD` |

5. Present the durable path set and commit message. Ask: "Finalize and push durable changes? Reply yes to confirm, or yes and push to also push."

6. On confirmation:
   ```bash
   job-hunter finalize-run --mode interactive --message "<message>"
   ```
   Append `--push` only if the user explicitly requested a push.

7. Print: `Finalized.` or `Finalized and pushed to origin/main.`
