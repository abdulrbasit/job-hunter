# Stories

Convert raw work notes into rated STAR drafts in `profile/story_bank.md`.

Run `job-hunter internal telemetry-mark --phase stories --skill stories --state start`.
Telemetry failure is non-blocking and must not be printed.

Canonical structure:

```markdown
# <Role — Employer (dates)>
## Draft — raw notes and reviews
## Final — refined STAR stories
```

1. Ask for role, employer, and dates when missing.
2. Read existing IDs and choose the next unused `{ROLE}-{NN}` ID.
3. Convert each note into a rated STAR draft with feedback, tags, and archetype fit.
4. Append under that role’s Draft section. Create the role section when absent.
5. Never write to Final; user promotes verified stories manually.

Never fabricate metrics, titles, employers, dates, or outcomes.
Run `job-hunter internal telemetry-mark --phase stories --state end` after writing.
