# Job Hunter

This is the agent context source of truth for the product repo. CLAUDE.md and any other per-agent files defer here. Keep durable operating context in this file, skills, config, or code; do not add separate architecture docs.

This repo combines the Python engine (`job_hunter/`) and the agent skill layer (`.claude/skills/`, `.agents/skills/`).

## Execution Modes

| Mode | What runs | When to use |
|---|---|---|
| `agent` | Agent skills handle scoring, tailoring, cover letters. Python prepares context. | Default interactive review. |
| `llm-api` | Full autonomous pipeline; LLM APIs called directly inside Python. | Unattended runs and GitHub Actions. |

Set `mode:` in `config/job_hunter.yml`.

## Repo Map

- `job_hunter/`: Python package, CLI, pipeline, source adapters, LLM API mode.
- `.claude/skills/`: skills for Claude Code (mirrored to `.agents/skills/` for Codex).
- `config/job_hunter.yml`: user-editable machine config.
- `config/schemas/job_hunter.schema.json`: schema for `job_hunter.yml`.
- `job_hunter/templates/workspace/profile/`: canonical starter profile and resume templates.
- `examples/profile/`: filled fictional examples; not a template source.
- `outputs/state/jobs.db`: SQLite — single source of truth for all job state (URL dedup, scraped candidates, application lifecycle).
- `docs/architecture.md`: current package ownership, dependency boundaries, pipeline, state, and template architecture.

## Skills

```text
/job-hunter          job search command center (batch, one, finalize, screen,
                     tailor, score, research, interview, outreach, stories, linkedin)
/linkedin            LinkedIn content center (ideas, draft, engage, network)
/setup               workspace setup center (onboard, doctor, region, style, stories)
```

Developer contributor context:

```text
/commit              preflight checks, safe staging, and commit format
```

Use `/commit` before developer commits. It still requires full preflight:

```bash
python -m pytest tests/ -q --tb=short
python -m ruff format --check job_hunter tests .github/scripts
python -m ruff check job_hunter tests .github/scripts
ty check job_hunter tests
```

## Common Commands

```bash
job-hunter hunt --region primary
job-hunter dash
job-hunter doctor

uv sync --extra dev
uv run pytest tests/ -q --tb=short
uv run ruff format --check job_hunter tests
uv run ruff check job_hunter tests
uv run ty check job_hunter tests
```

## Development Conventions

- Always use `/ponytail` + `/caveman` for coding tasks. Ponytail: build smallest correct thing, no speculative abstractions. Caveman: terse prose.
- TDD: write tests before implementing non-trivial Python changes.
- **Always use `/commit` before every commit.** Skill is at `.claude/skills/commit/SKILL.md`. It runs preflight checks and stages only specific files.
- **Never add `Co-Authored-By` or any AI attribution trailer** to commit messages. This repo does not use co-author tags.

## Skill Architecture

`.claude/skills/job-hunter/_rules.md` is the canonical universal rules file (evidence boundary, fabrication prevention, char limits, score decisions, industry exclusions). SKILL.md loads it inline so every mode inherits it automatically. Mirror all changes to the bundled copy at `job_hunter/templates/workspace/.claude/skills/job-hunter/_rules.md`.

Profile compilation (`job_hunter/tools/compile_profile.py`) runs at pipeline start and writes `outputs/state/compiled/{career_context.min.md,story_bank.min.md,resume.compact.txt}`. Context loaders prefer compiled files when present. The compiled dir is transient — cleaned up after each run.

## Rules

- **Never bump the version (`pyproject.toml`) or publish to PyPI** (trigger `release.yml`, `gh workflow run release.yml`, `uv publish`, etc.) unless the user explicitly asks. Push commits freely; do not release as a follow-on step.

## Config And State

Machine config lives in `config/job_hunter.yml`. Only deterministic choices
belong there: profile paths, job titles, regions, exclusions, scoring thresholds,
mode, and provider/model settings.

Product defaults, source lists, ATS platforms, stale/listing filters, prompt
internals, and fixed secret env-var names live in code.

Human career and writing guidance lives in `profile/career_context.md`: about-me
notes, targeting, resume style, cover-letter style, LinkedIn positioning,
outreach tone, and calibration.

`outputs/state/jobs.db` is the single source of truth for all job state. Same company with a
different URL is never blocked.

## LLM API Mode

Token compression via headroom runs automatically in `llm-api` mode through
`job_hunter/llm/client.py`. Keep `max_tokens` in config because it still controls
the model output budget.
