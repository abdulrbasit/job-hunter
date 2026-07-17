# Job Hunter Workspace

This is your personal Job Hunter workspace. Keep project-specific context here:
target roles, regions, profile files, outputs, and how to run the workflow.
Product code lives in the `job-hunter` Python package, not in this workspace.

## Modes

- `agent`: Python gathers candidates; agent skills process them (Claude Code or Codex).
- `llm-api`: Python runs scoring, tailoring, cover letters, PDFs, README, and
  tracking without an agent session.

Set `mode:` in `config/job_hunter.yml`.

## Daily Commands

```bash
job-hunter doctor
job-hunter hunt --region primary
job-hunter dash
```

## Agent Skills

```text
/job-hunter batch
/job-hunter one <url>
/job-hunter finalize
/linkedin ideas
/setup doctor
```

Skills are in `.claude/skills/`. Open the workspace in Claude Code or Codex to use them.

## Files To Edit

- `config/job_hunter.yml`: deterministic settings like mode, titles, regions,
  exclusions, scoring thresholds, provider/model choices.
- `profile/career_context.md`: positioning, resume style, cover-letter style,
  outreach tone, LinkedIn voice, calibration notes.
- `profile/story_bank.md`: reusable STAR stories.

API keys are stored in your OS keyring via `job-hunter dash`'s setup
wizard — not in a local file. `.env.example` is a template for GitHub
Actions Secrets only.

Generated files live under `outputs/`. Job state (URL dedup, candidates,
application lifecycle) is in `outputs/state/jobs.db`. Same company with a
different URL is not blocked.

Main package and docs: https://github.com/abdulrbasit/job-hunter
