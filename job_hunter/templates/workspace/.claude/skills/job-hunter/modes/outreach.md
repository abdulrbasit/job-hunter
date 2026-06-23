# Outreach

Single responsibility: draft outreach for one job. Nothing is submitted or sent.

Slug: `$ARGUMENTS`

## Token Rules

- Start with `job-hunter agent-context score --mode full --job <slug>`.
- Use `matched_story_ids` from `score.yml`; read selected stories only with `agent-context story --id`.
- Read `profile/career_context.md` when present for writing-style and targeting preferences.
- Search for at most three public profiles and print only the output path.

## Steps

1. Extract company, title, URL, team/product area, and matched story IDs from bounded context.
2. Search public LinkedIn profile pages for likely hiring manager, team lead, or recruiter contacts.
3. Write up to three connection requests and follow-ups to `outputs/jobs/{slug}/outreach_drafts.md`.

## Rules

- Public web search only; no login or scraping.
- Never invent contacts or claims.
- Ground fit claims in selected stories or the JD.
- No external action beyond writing drafts.

## Output

```
Outreach drafts written -> outputs/jobs/{slug}/outreach_drafts.md
Profiles found: N
```

When called from a workflow, control returns to the calling workflow after printing this output; the caller must immediately continue the next step in the same assistant turn.
