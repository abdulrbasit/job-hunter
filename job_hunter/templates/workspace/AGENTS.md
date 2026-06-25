# Job Hunter Workspace

This is your personal Job Hunter workspace. Keep project-specific context here:
target roles, regions, profile files, outputs, and how to run the workflow.
Product code lives in the `job-hunter` Python package, not in this workspace.

## Modes

- `agent`: Python gathers candidates; agent skills process them (Claude Code, Codex, Gemini CLI).
- `llm-api`: Python runs scoring, tailoring, cover letters, PDFs, README, and
  tracking without an agent session.

Set `mode:` in `config/job_hunter.yml`.

## Daily Commands

```bash
job-hunter config check
job-hunter doctor
job-hunter hunt --region primary
job-hunter brief
job-hunter dashboard --no-interactive
```

## Agent Skills

```text
/job-hunter brief
/job-hunter batch
/job-hunter one <url>
/job-hunter search
/job-hunter finalize
/linkedin ideas
/setup doctor
```

Skills are in `.claude/skills/`. Open the workspace in Claude Code or Gemini CLI to use them.

## Files To Edit

- `config/job_hunter.yml`: deterministic settings like mode, titles, regions,
  exclusions, scoring thresholds, LLM search gate, provider/model choices.
- `profile/career_context.md`: positioning, resume style, cover-letter style,
  outreach tone, LinkedIn voice, calibration notes.
- `profile/story_bank.md`: reusable STAR stories.
- `.env`: local secrets copied from `.env.example`.

Generated files live under `outputs/`. URL dedup is
`outputs/state/discovered_urls.yml`; same company with a different URL is not
blocked.

Main package and docs: https://github.com/abdulrbasit/job-hunter
