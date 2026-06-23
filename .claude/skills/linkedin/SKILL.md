---
name: linkedin
description: "LinkedIn content and networking command center. Routes to ideas, drafting, engagement, and connection-building modes."
when_to_use: "Use for all LinkedIn work: generating post ideas, writing drafts, drafting comments, and building a connection queue."
argument-hint: "[ideas|draft <idea>|engage|network]"
disable-model-invocation: true
allowed-tools: Read Write Bash WebSearch
author: "Abdul Basit (@abdulrbasit)"
category: workflow
---

# LinkedIn Command Center

Arguments: `$ARGUMENTS`

## Safety Rules

- Never post, send, connect, follow, like, or comment automatically.
- All output is draft only — user reviews before any action.
- No fabricated proof points, contacts, or outcomes.

## Routing

Normalize the first argument to lowercase. Empty argument → show menu.

- `ideas`, `post`, `content`: execute `.claude/skills/linkedin/modes/ideas.md` inline.
- `draft`, `write`: execute `.claude/skills/linkedin/modes/draft.md` inline with remaining arguments.
- `engage`, `comments`: execute `.claude/skills/linkedin/modes/engage.md` inline with remaining arguments.
- `network`, `connect`: execute `.claude/skills/linkedin/modes/network.md` inline.

Unknown mode → print the command menu and ask the user to choose a listed mode.

## Command Menu

```text
LinkedIn Command Center

/linkedin ideas        Generate weekly post ideas grounded in your job-search evidence
/linkedin draft <ref>  Write one ready-to-post draft from an approved idea
/linkedin engage       Draft comments for posts you paste in
/linkedin network      Build a weekly connection queue from active job targets
```

## Output Rules

- Execute child modes inline from their mode file; do not print a slash command as a handoff.
- Leave all generated content uncommitted. Run /job-hunter finalize after review.
