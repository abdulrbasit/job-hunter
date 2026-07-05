# LinkedIn Draft

Single responsibility: write one post from one approved idea.

Idea reference: `$ARGUMENTS`

Run `job-hunter internal telemetry-mark --phase linkedin_draft --skill linkedin_draft --state start`.
Telemetry failure is non-blocking and must not be printed.

## Token Rules

- Start with `job-hunter internal agent-context evidence-context` → `writing_rules.evidence`.
- Read only the matched idea from `outputs/linkedin/ideas.md`.
- Read the cited story ID with `job-hunter internal agent-context story --id <ID>`, or use `stories-final` only when the source idea requires comparing verified achievements.
- Do not read Draft/raw stories or all prior drafts.

## Steps

1. Find the requested idea.
2. Load only its cited source evidence.
3. Append one draft to `outputs/linkedin/drafts.md`.
4. Do not commit here; `/job-hunter finalize` handles reviewed `outputs/linkedin/` drafts.

## Rules

- 200-400 words, short paragraphs, no filler.
- Apply every rule in `writing_rules.evidence` exactly — universal (code-owned), wins over any
  conflicting `career_context.md` preference.
- Do not post or call external services.

## Output

Run `job-hunter internal telemetry-mark --phase linkedin_draft --state end` before printing.

```
LinkedIn draft appended -> outputs/linkedin/drafts.md
Source: <idea reference>
```
