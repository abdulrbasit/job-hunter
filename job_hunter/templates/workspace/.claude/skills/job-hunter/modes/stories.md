# Stories to STAR

Single responsibility: convert raw notes into Draft STAR stories. This is one of the few skills allowed to inspect the story bank structure.

## Token Rules

- Read only the allocation log and relevant role section when assigning IDs.
- Process one role's raw notes at a time.
- Do not repeat the raw notes back.
- Print compact story drafts; append durable detail to `profile/story_bank.md`.

## Steps

1. Ask for role title, employer, and date range if not already provided.
2. Derive the story ID prefix from employer and role, then find the next free number.
3. For each raw note, produce a rated STAR draft with feedback, tags, and archetype fit.
4. Append drafts under that role's Draft section.
5. Update the allocation log.

## Rules

- Never fabricate metrics, titles, employers, dates, or outcomes.
- Weak stories should stay weak and be labeled clearly.
- Do not write to the Final section; the user promotes stories manually.

## Output

```
Stories appended to Draft section in profile/story_bank.md.
Drafts: N | Strong: N | Needs work: N
```

When called from a workflow, control returns to the calling workflow after printing this output; the caller must immediately continue the next step in the same assistant turn.
