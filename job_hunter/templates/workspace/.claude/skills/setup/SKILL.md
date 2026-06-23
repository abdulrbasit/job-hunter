---
name: setup
description: "Workspace setup and health command center. Routes to onboarding, region management, health checks, resume styling, and story creation."
when_to_use: "Use for first-time workspace setup, health checks, config changes, and story bank management."
argument-hint: "[onboard|doctor|region <add|remove> <name>|style|stories]"
disable-model-invocation: true
allowed-tools: Read Edit Write Bash WebSearch
author: "Abdul Basit (@abdulrbasit)"
category: workflow
---

# Setup Command Center

Arguments: `$ARGUMENTS`

## Routing

Normalize the first argument to lowercase. Empty argument → show menu.

- `onboard`, `init`, `start`: execute `.claude/skills/setup/modes/onboard.md` inline.
- `doctor`, `health`, `check`: execute `.claude/skills/setup/modes/doctor.md` inline.
- `region`, `add-region`: execute `.claude/skills/setup/modes/region.md` inline with remaining arguments.
- `style`: execute `.claude/skills/setup/modes/style.md` inline.
- `stories`, `star`: execute `.claude/skills/setup/modes/stories.md` inline.

Unknown mode → print the command menu and ask the user to choose a listed mode.

## Command Menu

```text
Setup Command Center

/setup onboard         One-time workspace initialization (config, keys, profile, regions)
/setup doctor          Run health checker and show setup status
/setup region add <n>  Add a new search region to config
/setup region remove <n>  Remove an existing search region
/setup style           Change resume color scheme or font
/setup stories         Convert raw work notes into rated STAR stories
```
