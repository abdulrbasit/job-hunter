# Agent Mode

`mode: agent` in `config/job_hunter.yml`. Beginner setup:
[SETUP_AGENT.md](../job_hunter/templates/workspace/SETUP_AGENT.md).

## Division of labor

Python (`job-hunter hunt`) does discovery only: scrape sources, screen
against your config, write candidates to `outputs/state/jobs.db`. It does
not score, tailor, or write anything under `outputs/jobs/<slug>/`.

Claude Code or Codex — via the bundled `.claude/skills/job-hunter/` skill
(mirrored to `.agents/skills/` for Codex) — does the rest: scoring against
`profile/career_context.md` and `profile/story_bank.md`, tailoring the
resume, drafting the cover letter, and updating the tracker.

`job_hunter/agent_context/` is the module that builds the context objects
the skill reads (`batch.py`, `candidates.py`, `lifecycle.py`,
`score_context.py`, `stories.py`, `tailor_context.py`, `briefing.py`) —
it's the one package allowed to import both `pipeline/` and `sources/`
directly, since it's assembling agent-facing views over both.

## Skill entry points

`.claude/skills/job-hunter/SKILL.md` routes `/job-hunter <mode>` to a file
under `.claude/skills/job-hunter/modes/`:

| Mode | What it does |
|---|---|
| `batch` | Process up to `scoring.batch_size` frozen candidates end-to-end. |
| `one <url>` | Process a single job URL outside the batch flow |
| `screen` | Pre-screen a frozen batch against config exclusion rules only |
| `finalize` | No mode file — routes straight to `job-hunter finalize`, the same validate/commit/push logic behind the dashboard's Finalize button |
| `tailor <job>`, `score <job>`, `research <job>`, `interview <job>`, `outreach <job>` | Per-job actions |
| `stories` | Turn raw notes into rated STAR stories |
| `linkedin ...` | Routes into `.claude/skills/linkedin/SKILL.md` |
| `setup ...` | Routes into `.claude/skills/setup/SKILL.md` — `doctor`/`region`/`style` have no mode files either, and point at `job-hunter doctor` or the dashboard |

## Batch, concretely

`batch.md`'s steps, in order: pull, fetch the profile context (career
context + resume) once via `job-hunter internal agent-context profile` —
kept in context for the whole run, never re-fetched per candidate — then
build+freeze a batch via `job-hunter internal agent-context batch`, screen
it, then per candidate: import → lifecycle check → score with
`--no-profile` (reuses the already-fetched profile) → validate-score →
discard if below threshold. Then, for every job scored APPLY: optional
company research → tailor → update README → mark processed. No commits or
pushes happen during batch — that's `job-hunter finalize`'s job (CLI or the
dashboard's Finalize button), and only on request.

## Non-interactive contract

Batch mode is designed to run to completion without pausing for
confirmation on ordinary status lines — only a genuine hard blocker (empty
queue, missing config, auth failure) stops it early. Enabling this in your
editor (Claude Code's Auto mode, Codex's auto-approve) is what lets
`/job-hunter batch` process 15 candidates unattended; see
[SETUP_AGENT.md](../job_hunter/templates/workspace/SETUP_AGENT.md#6-daily-workflow)
for the per-extension toggle.

## Safety boundary

Agent mode never commits, pushes, or applies on your behalf. Auto mode's
scope is `outputs/` writes, `job-hunter internal ...` commands, and
WebFetch — nothing else.

## Shared writing policy

`job_hunter/writing/rules.py` is the single source of truth for fabrication,
evidence, ATS, cover-letter, and outreach safety rules. `agent_context.tailor_context`
and `agent_context.outreach_context` deliver them as `writing_rules` via
`job-hunter internal agent-context tailor-context`/`outreach-context`;
`tailor.md` and `outreach.md` apply the delivered rules alongside
`career_context.md` style preferences, and the universal rules win on any
conflict. See [llm-api-mode.md](llm-api-mode.md#shared-writing-policy).

## Profile compilation

Before a run, `job_hunter/tools/compile_profile.py` compiles
`career_context.md`/`story_bank.md`/your resume into
`outputs/state/compiled/*.min.md` and `resume.compact.txt`. Context loaders
prefer these compiled files when present; the directory is cleaned up
after each run, so it's transient, not a second source of truth.

## Token and skill metrics

Workspace setup installs Claude Code and Codex lifecycle hooks plus a localhost-only
OpenTelemetry receiver. Existing `/job-hunter ...` commands do not change. For each
run, `outputs/state/metrics.db` records input, output, cached, and reasoning tokens
by backend, explicit Job Hunter skill, nested phase, and job slug. It also records APPLY/SKIP,
tailored, failed, and interrupted outcomes. The dashboard's Settings → Diagnostics tab surfaces
session/message/streak counts and Tokens by Skill with Claude Code/Codex columns,
plus a batch phase breakdown. The fuller per-job breakdown remains queryable via
`job-hunter internal telemetry-status --json` or `metrics.db` directly.

Prompt text, model responses, resume contents, and tool arguments are never stored.
Only token counts, model/session identifiers, phase labels, slugs, and outcome
counters are retained. Only explicit `/job-hunter ...` and `/linkedin ...` commands
start owned runs; coding/review prompts, repository mentions, and raw URLs are ignored.
Telemetry errors never block job processing. Remove legacy polluted rows once with
`job-hunter internal telemetry-prune --unattributed`.

`job-hunter init` configures project hooks automatically. Codex requires its OTel
exporter in `$CODEX_HOME/config.toml` (normally `~/.codex/config.toml`); an existing
unrelated `[otel]` section is preserved and reported instead of overwritten.

**You must fully quit and relaunch Claude Code or Codex after setup** — hooks take
effect immediately, but the `OTEL_*` environment variables/`[otel]` config are only
read at process startup, so a reloaded window or an already-running session will
keep showing "not observed" token counts until you quit the app completely (not just
close the window) and reopen it. After relaunching, run a skill once, then check the
dashboard Settings → Diagnostics tab or `job-hunter internal telemetry-status --json`.
