# Process One Job URL

Single-URL orchestrator. Use compact scoring context and selected story reads only.

URL: `$ARGUMENTS` (ask the user if empty)

Run `job-hunter internal telemetry-mark --phase one --skill one --state start`.
Telemetry failure is non-blocking and must not be printed.

Parse `$ARGUMENTS` for optional `--region <r>` and `--location <l>`. If missing, ask for region and location before importing.

## Orchestration Rules

- Execute child skills inline in this same run. Do not print slash commands as handoffs and stop.
- To use a child skill, read its mode file, apply its instructions to the current compact context, write the required artifacts, then resume the next step below.
- After the user confirms tailoring, continue through research, tailoring, README update, processed-state update, and final commit without pausing between phases.
- Use `job-hunter internal agent-context lifecycle --job <slug>` after import. If it reports a failed fetch, resolve that before scoring.

## Steps

1. Run `job-hunter internal import-job --url "<url>" --region "<region>" --location "<location>"` and capture the slug.
2. Run `job-hunter internal agent-context lifecycle --job <slug>`, then run the returned full-score command when lifecycle reports `full_score`.
3. Execute `.claude/skills/job-hunter/modes/score.md` inline in full mode. It writes `score.yml` with `matched_story_ids`.
4. If below threshold with no override, run `job-hunter internal discard-job --job <slug>`, print the reason, and stop.
5. Ask: `Tailor resume and write cover letter? Reply yes to continue.`
6. On confirmation:
   - Execute `.claude/skills/job-hunter/modes/research.md` inline.
   - Execute `.claude/skills/job-hunter/modes/tailor.md` inline.
   - Run `job-hunter internal update-readme --job <slug>`.
   - Run `job-hunter internal mark-processed --url "<url>" --company "<company>" --title "<title>"`.
   - Ask before final commit; if confirmed, run `job-hunter internal finalize-run --mode interactive --message "chore(jobs): tailor <slug>"` and add `--push` only when the user explicitly asks to push.

## Output

Run `job-hunter internal telemetry-mark --phase one --state end` before printing.

Print a compact status only:

```
## <Title> @ <Company>
Score: XX/100 - APPLY | SKIP
Matched: <short list>
Gaps: <short list>
Artifacts: outputs/jobs/{slug}/
```
