# Skill audit: minimize LLM surface, hard-gate token spend — TDD evidence

## Scope

Audited every bundled skill (`.claude/skills/job-hunter/`, `linkedin/`, `setup/`) against
the deterministic machinery already in `job_hunter/` (internal CLI, `agent_context/`,
dashboard `DashAPI`). Decisions and per-skill verdicts are in the plan file this session
worked from; summarized here with the delivered evidence.

## Verdicts delivered

| Skill/mode | Verdict | Evidence |
|---|---|---|
| `job-hunter/modes/finalize.md` | Deleted — all bookkeeping already lived in `cli/commands/internal.py::finalize_run` + `git_sync.py`. Router now runs `job-hunter finalize` directly (new public CLI command, also wired to a dashboard button). | `tests/test_cli.py::test_public_finalize_command_delegates_to_finalize_run`, `test_finalize_run_discards_dead_job_folders_before_commit`; `tests/test_web_api.py::test_start_finalize_runs_worker_and_reports_result` |
| `setup/modes/doctor.md` | Deleted — router runs `job-hunter doctor --json` directly; points at dashboard Diagnostics for one-click fixes. | `tests/test_skills.py`, `tests/test_skill_contracts.py` (mirror/menu assertions) |
| `setup/modes/region.md` | Deleted — dashboard Settings → Guided → Regions already covers it; router keeps a one-line `internal region-lookup` pointer for headless use. | same |
| `setup/modes/stories.md` (setup's duplicate) | Deleted — consolidated onto the one canonical `job-hunter/modes/stories.md`. | `tests/test_skill_cli_contracts.py::test_skill_referenced_mode_files_exist` |
| `setup/modes/style.md` | Deleted — replaced with a deterministic `config/resume_style.py` (regex-based AltaCV/article preamble editor) + dashboard Settings → Resume Style form. | `tests/test_resume_style.py` (13 tests), `tests/test_web_api.py` (4 tests) |
| `tailor`, `interview`, `outreach`, `research` | Kept, hard-gated: added a `## Preconditions` block each (score.yml/job-folder existence checked before any work starts, with the exact fix command to run). | `.claude/skills/job-hunter/modes/{tailor,interview,outreach,research}.md` |
| `batch`, `screen` | Kept, reordered: profile context (career context + resume) is now fetched once per batch run instead of once per job. | see Token measurement below |

## Token measurement (Phase 4 — the actual target metric)

Simulated a 15-job batch scoring pass against realistic-but-synthetic fixtures (~15KB
career context, ~21KB base resume, ~26KB job description per posting, 8 Final stories) —
large enough to exercise every clip budget, not hand-picked to flatter the result.

**Profile dedup** (`job_hunter/agent_context/score_context.py::score_context`'s new
`include_profile` parameter + `profile_context()`, wired into `batch.md` step 2 and every
per-job `score --mode full --no-profile` call in step 4):

```
BEFORE (profile re-embedded in every job's score payload): 269,540 chars (~67,385 tokens)
AFTER  (profile fetched once, omitted per job):            110,809 chars (~27,702 tokens)
SAVED:                                                      158,731 chars (~39,683 tokens, 58.9%)
```

Measured with `tests`-equivalent fixtures via a one-off script calling the real
`score_context`/`profile_context` functions (not estimated from clip constants) — script
not committed, numbers reproducible by calling `score_context(..., max_jd_chars=6000)` for
15 jobs (old default, profile always embedded) vs. `profile_context()` once +
`score_context(..., include_profile=False)` for 15 jobs (new default).

**Clip-budget unification**: `MAX_SNIPPET_CHARS` 700→500, `MAX_JD_CHARS` 6000→3000 in
`agent_context/_types.py`, now the single source the CLI's `--max-snippet-chars`/
`--max-jd-chars` defaults point at (previously the CLI silently used tighter literals than
the module's own defaults — same numbers, two sources of truth). This tightens
`interview_context`/`outreach_context`/candidate lifecycle JD excerpts too, since those
callers never exposed a CLI override and always used the module default.

**Deleted skill-file bodies** (one-time per-invocation cost, not multiplied per batch job —
these files were loaded inline by the router on every `/job-hunter finalize` / `/setup
doctor` / `/setup region` / `/setup stories` / `/setup style` invocation):

```
finalize.md   2,192 chars
doctor.md     2,004 chars
region.md     2,121 chars
stories.md    1,635 chars
style.md      7,300 chars
Total:       15,252 chars (~3,813 tokens) per invocation, now ~0 (one-line CLI/dashboard pointer)
```

**New budget guard** (`tests/test_agent_context_budgets.py`, did not exist before this
task): asserts a fixed serialized-JSON ceiling per agent-facing payload — score (with and
without profile), snippet score, profile, tailor-context, interview-context,
outreach-context, evidence-context — built against the same oversized fixtures. Complements
the pre-existing per-field clip tests (`test_agent_context.py`) with an overall payload
ceiling, which is what actually bounds a run's token spend; nothing enforced this before.

## Dependency-boundary fix found while wiring the dashboard Finalize button

Initial implementation had `job_hunter.ux.web.api::DashAPI._run_finalize_worker` import
`job_hunter.cli._run_artifacts.run_finalize_core` directly — caught immediately by
`tests/test_dependency_boundaries.py::test_ux_does_not_depend_on_cli` (ux/ must not depend
on cli/, the composition root). Fixed by moving the finalize orchestration into
`job_hunter/workspace/finalize.py` (a layer both `cli/` and `ux/` already legitimately
depend on, same as `git_sync.py`), and by injecting `verify_errors`
(`ux.health.verify_repository`) and `validate_score_file` (`agent_context.validate_score_file`)
as caller-supplied parameters rather than importing `ux`/`agent_context` from `workspace/`
itself — both of those are banned from `workspace/` the same way they're banned from
`pipeline/`/`tracking/`. Added `tests/test_dependency_boundaries.py::
test_workspace_does_not_depend_on_ux_cli_or_agent_context` to lock this in (matching the
existing per-layer boundary-test pattern) since nothing guarded `workspace/`'s layering before.

## Sync/deletion mechanics verified

- `job_hunter/workspace/operations.py::update_skills` already deletes stale system-owned
  skill files on `job-hunter update` (manifest-hash-guarded — a user's hand-edited copy of
  a deleted skill is preserved and reported, not silently destroyed). No change needed;
  verified by reading the existing implementation, not a new test (would duplicate existing
  coverage of that function).
- `scripts/sync_workspace_template.py` previously only copied forward, never pruned —
  a skill deleted from `.claude/skills/` would leave an orphaned copy in the shipped
  `job_hunter/templates/workspace/.claude/skills/` template forever. Added `_prune_stale()`
  (per-file, within an existing skill dir) and a whole-skill-directory prune pass; verified
  live against this session's own five deletions (`python scripts/sync_workspace_template.py`
  output showed `pruned  .claude/skills/.../finalize.md` etc. for each).

## Final validation

- `pytest tests/ -q --tb=short` — 1584 passed, 0 failed, across five commits (finalize
  absorption + doctor/region/stories deletion; style absorption; context hard-gating +
  budget tests; tailor/interview/outreach/research preconditions; docs; workspace boundary
  test).
- `ruff format --check`, `ruff check`, `ty check` — all clean after every commit.
- `scripts/sync_workspace_template.py --check`-equivalent: ran the real sync (not
  `--check`) after every skill edit in this session; zero drift remained before each commit.
- No version bump.
