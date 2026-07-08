# Outreach

Single responsibility: draft outreach for one job. Nothing is submitted or sent.

Slug: `$ARGUMENTS`

Run `job-hunter internal telemetry-mark --phase outreach --skill outreach --job <slug> --state start`.
Telemetry failure is non-blocking and must not be printed.

## Token Rules

- Start with `job-hunter internal agent-context outreach-context --job <slug>` → `writing_rules.outreach`, `job`, `matched_stories`.
- Use `job.score.matched_story_ids` first, falling back to `matched_stories`; read selected stories only with `agent-context story --id`.
- Read `outputs/state/compiled/career_context.min.md` if present, else `profile/career_context.md`, for writing-style and targeting preferences.
- Search for at most three public profiles and print only the output path.

## Steps

1. Extract company, title, URL, team/product area, and matched story IDs from bounded context.
2. Search public LinkedIn profile pages for likely hiring manager, team lead, or recruiter contacts.
3. Write up to three connection requests and follow-ups to `outputs/jobs/{slug}/outreach_drafts.md`.

## Rules

- Apply every rule in `writing_rules.outreach` exactly — universal (code-owned), wins over any
  conflicting `career_context.md` preference.
- No external action beyond writing drafts.

## Output

Run `job-hunter internal telemetry-mark --phase outreach --state end` before printing.

```
Outreach drafts written -> outputs/jobs/{slug}/outreach_drafts.md
Profiles found: N
```

When called from a workflow, control returns to the calling workflow after printing this output; the caller must immediately continue the next step in the same assistant turn.
