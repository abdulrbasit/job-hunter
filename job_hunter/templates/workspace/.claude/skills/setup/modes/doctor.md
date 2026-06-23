# Doctor

Single responsibility: run `job-hunter doctor` and surface the results in a clear, actionable format.

## Steps

1. Run the health checker:
   ```bash
   job-hunter doctor --json
   ```

2. Parse the JSON output and render:

   ```
   System Check  ── <date>
   ──────────────────────────────────────────
   ✓  python_version                  3.12.x
   ✓  editable_package                installed
   ✓  docker                          Docker CLI
   ✓  config/job_hunter.yml
   ...
   ✗  profile/resume.tex:filled       → Run /setup resume to populate
   ✗  profile/career_context.md       → Run /setup context to fill
   ✗  profile/story_bank.md:final_stories → Run /setup stories
   ──────────────────────────────────────────
   Status: READY  (or SETUP NEEDED)
   ```

   The `:filled` suffix means the file exists but still has template placeholder values. The `:final_stories` suffix means the story bank has no approved stories yet.

   Print PASS (✓) rows first, grouped, then FAIL (✗) rows with their fix hint.

3. If `onboardingNeeded` is true, append:
   ```
   Onboarding incomplete — missing:
     • profile/story_bank.md
     • ...
   Run /setup onboard to complete first-time configuration.
   ```

4. If `warnings` is non-empty, append the list with a "non-blocking" label.

## Token Rules

- Print the table; do not re-explain each check in prose.
- Do not print the raw JSON.
- If all checks pass and onboarding is complete: `All checks passed — ready to hunt.`
