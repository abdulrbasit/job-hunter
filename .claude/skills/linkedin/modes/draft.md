# LinkedIn Draft

Single responsibility: write one post from one approved idea.

Idea reference: `$ARGUMENTS`

## Token Rules

- Read only the matched idea from `outputs/linkedin/ideas.md`.
- Read the cited story ID with `job-hunter agent-context story --id <ID>`, or use `stories-final` only when the source idea requires comparing verified achievements.
- Do not read Draft/raw stories or all prior drafts.

## Steps

1. Find the requested idea.
2. Load only its cited source evidence.
3. Append one draft to `outputs/linkedin/drafts.md`.
4. Do not commit here; `/job-hunter finalize` handles reviewed `outputs/linkedin/` drafts.

## Rules

- 200-400 words, short paragraphs, no filler.
- Every claim must be traceable to selected evidence.
- Do not post or call external services.

## Output

```
LinkedIn draft appended -> outputs/linkedin/drafts.md
Source: <idea reference>
```
