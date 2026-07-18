"""agent-context sub-commands — registered on agent_context_app from cli.__init__."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from job_hunter.agent_context._types import MAX_JD_CHARS, MAX_SNIPPET_CHARS
from job_hunter.cli.app import agent_context_app


@agent_context_app.command("candidates")
def agent_context_candidates(
    source: str | None = typer.Option(None, "--source"),
    latest: bool = typer.Option(False, "--latest"),
    today: bool = typer.Option(False, "--today"),
    scope: str = typer.Option("candidates", "--scope"),
    limit: int = typer.Option(50, "--limit"),
    max_snippet_chars: int = typer.Option(MAX_SNIPPET_CHARS, "--max-snippet-chars"),
    write_queue: str = typer.Option("outputs/state/agent_candidate_queue.json", "--write-queue"),
    run_id: str = typer.Option("", "--run-id"),
) -> None:
    """Build candidate queue and write it to disk."""
    from job_hunter import agent_context

    queue = agent_context.build_candidate_queue(
        source=Path(source) if source else None,
        latest=latest,
        today_only=today,
        scope=scope,
        limit=limit,
        max_snippet_chars=max_snippet_chars,
        run_id=run_id,
    )
    output_path = Path(write_queue)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    typer.echo(f"Candidate queue: {queue['count']} of {queue['total_seen']} candidate(s) -> {output_path.as_posix()}")


@agent_context_app.command("candidate")
def agent_context_candidate(
    queue: str = typer.Option(..., "--queue"),
    index: int = typer.Option(0, "--index"),
    candidate_id: str = typer.Option("", "--candidate-id"),
) -> None:
    """Print a single candidate from a queue file."""
    from job_hunter import agent_context

    candidate = agent_context.candidate_from_queue(Path(queue), index, candidate_id=candidate_id)
    typer.echo(json.dumps(candidate, indent=2))


@agent_context_app.command("batch")
def agent_context_batch(
    scope: str = typer.Option("candidates", "--scope"),
    today: bool = typer.Option(False, "--today"),
    limit: int = typer.Option(50, "--limit"),
    max_snippet_chars: int = typer.Option(MAX_SNIPPET_CHARS, "--max-snippet-chars"),
    write_queue: str | None = typer.Option(None, "--write-queue"),
    write_batch: str = typer.Option("outputs/state/agent_candidate_batch.json", "--write-batch"),
    batch_size: int = typer.Option(15, "--batch-size"),
    batch_number: int = typer.Option(1, "--batch-number"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Build a scored batch of candidates."""
    from job_hunter import agent_context

    queue = agent_context.build_candidate_queue(
        scope=scope, today_only=today, limit=limit, max_snippet_chars=max_snippet_chars
    )
    if write_queue and not dry_run:
        queue_path = Path(write_queue)
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue_path.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    batch = agent_context.build_candidate_batch(queue, batch_size=batch_size, batch_number=batch_number)
    output_path = Path(write_batch)
    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(batch, indent=2), encoding="utf-8")
    typer.echo(
        f"Batch {batch['batch_number']}: {batch['count']} loaded "
        f"({queue['total_seen']} seen, {queue['skipped_processed']} processed, "
        f"{queue['skipped_duplicate']} duplicate, {queue['skipped_hard_screen']} hard-screened) "
        f"-> {output_path.as_posix()}"
    )


@agent_context_app.command("screen-batch")
def agent_context_screen_batch(
    batch: str = typer.Option(..., "--batch"),
    write_screen: str = typer.Option("outputs/state/batch_screen.yml", "--write-screen"),
) -> None:
    """Screen a candidate batch and write results."""
    import yaml

    from job_hunter import agent_context

    batch_data = json.loads(Path(batch).read_text(encoding="utf-8"))
    result = agent_context.screen_candidate_batch(batch_data)
    output_path = Path(write_screen)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(result, sort_keys=False, allow_unicode=True), encoding="utf-8")
    discarded = agent_context.discard_screened_candidates(result)
    typer.echo(
        f"Batch {result['batch_number']}: {result['loaded']} loaded, "
        f"{result['skipped_count']} hard-screen skips ({discarded} discarded), "
        f"{result['retained_count']} retained"
    )


@agent_context_app.command("apply-judgment")
def agent_context_apply_judgment(
    judgment: str = typer.Option(..., "--judgment"),
    screen: str = typer.Option(..., "--screen"),
) -> None:
    """Apply screen.md's semantic SKIP/PASS decisions in one deterministic pass."""
    import yaml

    from job_hunter import agent_context

    judgment_data = yaml.safe_load(Path(judgment).read_text(encoding="utf-8")) or {}
    screen_data = yaml.safe_load(Path(screen).read_text(encoding="utf-8")) or {}
    result = agent_context.apply_screen_judgment(judgment_data, screen_data)
    typer.echo(
        f"Judgment applied: {result['discarded_count']} screen-skip discarded, "
        f"{len(result['retained_candidate_ids'])} retained"
    )
    typer.echo(json.dumps(result, indent=2))


@agent_context_app.command("profile")
def agent_context_profile() -> None:
    """Print the profile block (career context + resume) score embeds in every job's
    payload. Fetch this once per batch run, then pass --no-profile to `score` per job."""
    from job_hunter import agent_context

    typer.echo(json.dumps(agent_context.profile_context(), indent=2))


@agent_context_app.command("score")
def agent_context_score(
    mode: str = typer.Option("snippet", "--mode"),
    job: str | None = typer.Option(None, "--job"),
    queue: str | None = typer.Option(None, "--queue"),
    index: int = typer.Option(0, "--index"),
    candidate_id: str = typer.Option("", "--candidate-id"),
    max_jd_chars: int = typer.Option(MAX_JD_CHARS, "--max-jd-chars"),
    no_profile: bool = typer.Option(
        False, "--no-profile", help="Omit the profile block — already fetched once via `agent-context profile`"
    ),
) -> None:
    """Build scoring context for a job."""
    from job_hunter import agent_context

    payload = agent_context.score_context(
        mode=mode,
        job=job,
        queue=Path(queue) if queue else None,
        index=index,
        candidate_id=candidate_id,
        max_jd_chars=max_jd_chars,
        include_profile=not no_profile,
    )
    typer.echo(json.dumps(payload, indent=2))


@agent_context_app.command("lifecycle")
def agent_context_lifecycle(
    queue: str | None = typer.Option(None, "--queue"),
    index: int = typer.Option(0, "--index"),
    candidate_id: str = typer.Option("", "--candidate-id"),
    job: str | None = typer.Option(None, "--job"),
    mark_terminal: str | None = typer.Option(None, "--mark-terminal"),
    refresh_queue: str | None = typer.Option(None, "--refresh-queue"),
    fallback_text_file: str | None = typer.Option(None, "--fallback-text-file"),
    today: bool = typer.Option(False, "--today"),
    all_candidates: bool = typer.Option(False, "--all-candidates"),
    scope: str = typer.Option("candidates", "--scope"),
) -> None:
    """Get candidate lifecycle context."""
    from job_hunter import agent_context

    fallback_text = ""
    if fallback_text_file:
        fallback_text = Path(fallback_text_file).read_text(encoding="utf-8")
    scope_resolved = "briefing-backlog" if all_candidates else scope
    payload = agent_context.candidate_lifecycle(
        queue=Path(queue) if queue else None,
        index=index,
        candidate_id=candidate_id,
        job=job,
        terminal_reason=mark_terminal,
        refresh_queue=Path(refresh_queue) if refresh_queue else None,
        fallback_text=fallback_text,
        today_only=today,
        scope=scope_resolved,
    )
    typer.echo(json.dumps(payload, indent=2))


@agent_context_app.command("story-index")
def agent_context_story_index() -> None:
    """Print JSON index of all available stories."""
    from job_hunter import agent_context

    typer.echo(json.dumps({"stories": agent_context.story_index()}, indent=2))


@agent_context_app.command("story")
def agent_context_story(
    story_id: str = typer.Option(..., "--id"),
) -> None:
    """Print a single story by ID."""
    from job_hunter import agent_context

    story = agent_context.story_by_id(story_id)
    if not story:
        typer.echo(f"[agent-context] story not found: {story_id}", err=True)
        raise typer.Exit(1)
    print(story.text)


@agent_context_app.command("match-stories")
def agent_context_match_stories(
    job: str = typer.Option(..., "--job"),
    limit: int = typer.Option(5, "--limit"),
) -> None:
    """Print Final stories ranked by keyword overlap with a job's JD."""
    from job_hunter import agent_context

    typer.echo(json.dumps(agent_context.match_stories(job=job, limit=limit), indent=2))


@agent_context_app.command("stories-final")
def agent_context_stories_final() -> None:
    """Print final (approved) stories text."""
    from job_hunter import agent_context

    print(agent_context.final_stories_text())


@agent_context_app.command("linkedin-weekly")
def agent_context_linkedin_weekly(
    days: int = typer.Option(7, "--days"),
    limit: int | None = typer.Option(None, "--limit"),
) -> None:
    """Build LinkedIn weekly context payload."""
    from job_hunter import agent_context

    payload = agent_context.linkedin_weekly_context(days=days, limit=limit)
    typer.echo(json.dumps(payload, indent=2))


@agent_context_app.command("tailor-context")
def agent_context_tailor_context(
    job: str = typer.Option(..., "--job"),
) -> None:
    """Print tailoring + cover-letter constraints for a scored job."""
    from job_hunter import agent_context

    typer.echo(json.dumps(agent_context.tailor_context(job=job), indent=2))


@agent_context_app.command("interview-context")
def agent_context_interview_context(
    job: str = typer.Option(..., "--job"),
) -> None:
    """Print bounded job + matched-story context for interview prep."""
    from job_hunter import agent_context

    typer.echo(json.dumps(agent_context.interview_context(job=job), indent=2))


@agent_context_app.command("outreach-context")
def agent_context_outreach_context(
    job: str | None = typer.Option(None, "--job"),
) -> None:
    """Print universal outreach writing rules, plus bounded job context when --job is given."""
    from job_hunter import agent_context

    typer.echo(json.dumps(agent_context.outreach_context(job=job), indent=2))


@agent_context_app.command("evidence-context")
def agent_context_evidence_context() -> None:
    """Print universal no-fabrication evidence rules."""
    from job_hunter import agent_context

    typer.echo(json.dumps(agent_context.evidence_context(), indent=2))


@agent_context_app.command("validate-score")
def agent_context_validate_score(
    path: str = typer.Option(..., "--path"),
) -> None:
    """Validate a score.yml file."""
    from job_hunter import agent_context

    typer.echo(json.dumps(agent_context.validate_score_file(Path(path)), indent=2))
