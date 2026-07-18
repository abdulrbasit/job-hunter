---
name: setup
description: "Workspace setup command center. Routes to onboarding, career context, resume building, and resume styling; health checks and regions are dashboard/CLI now."
when_to_use: "Use for first-time workspace setup, career context, resume building, resume styling, and story bank management."
argument-hint: "[onboard|context|resume|doctor|region|style|stories]"
disable-model-invocation: true
allowed-tools: Read Edit Write Bash WebSearch
author: "Abdul Basit (@abdulrbasit)"
category: workflow
---

Execute `.claude/skills/caveman/SKILL.md` inline before processing any command.

# Setup Command Center

Arguments: `$ARGUMENTS`

## Routing

Normalize the first argument to lowercase. Empty argument → show menu.

- `onboard`, `init`, `start`: execute `.claude/skills/setup/modes/onboard.md` inline.
- `context`, `career`, `career-context`: execute `.claude/skills/setup/modes/context.md` inline.
- `resume`, `build`, `build-resume`: execute `.claude/skills/setup/modes/resume.md` inline.
- `stories`, `star`: execute `.claude/skills/job-hunter/modes/stories.md` inline.
- `doctor`, `health`, `check`: run `job-hunter doctor --json`, render the ✓/✗ table. Point the user at `job-hunter dash` → Settings → Diagnostics for one-click fixes.
- `region`, `add-region`: no skill for this — tell the user to open `job-hunter dash` → Settings → Guided → Regions. If they have no GUI access, edit the named region block in `config/job_hunter.yml` directly (use `job-hunter internal region-lookup --city "<city>"` for the country code).
- `style`: execute `.claude/skills/setup/modes/style.md` inline.

Unknown mode → print the command menu and ask the user to choose a listed mode.

## Command Menu

```text
Setup Command Center

/setup onboard         One-time workspace initialization (config, keys, profile, regions)
/setup context         Interactive guided setup for profile/career_context.md
/setup resume          Build the base resume from career context and story bank
/setup stories         Convert raw work notes into rated STAR stories
/setup doctor          Run health checker and show setup status
/setup region           Points you at dash → Settings → Guided → Regions
/setup style            Change resume color scheme or font
```
