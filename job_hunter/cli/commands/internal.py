"""Internal CLI commands — used by bundled agent skills and maintenance automation, hidden from --help."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from job_hunter.cli import _run_artifacts
from job_hunter.cli.app import app, internal_app, update_safety_app
from job_hunter.cli.options import JSON_OPTION
from job_hunter.cli.output import fail

FINALIZE_PATHS = _run_artifacts.FINALIZE_PATHS
TRANSIENT_STATE_PATHS = _run_artifacts.TRANSIENT_STATE_PATHS
_cleanup_transient_state = _run_artifacts.cleanup_transient_state
_derive_finalize_message = _run_artifacts.derive_finalize_message
_expand_listing_candidate = _run_artifacts.expand_listing_candidate
_sync_processed_from_job_outputs = _run_artifacts.sync_processed_from_job_outputs
_validate_run_artifacts = _run_artifacts.validate_run_artifacts
_discard_job_folder = _run_artifacts.discard_job_folder
_discard_dead_job_folders = _run_artifacts.discard_dead_job_folders


@internal_app.command(name="import-job")
def import_job(
    url: str | None = typer.Option(None, "--url", help="Job posting URL"),
    title: str | None = typer.Option(None, "--title"),
    company: str | None = typer.Option(None, "--company"),
    text: str | None = typer.Option(None, "--text", help="Raw JD text"),
    file: str | None = typer.Option(None, "--file", help="Path to JD text file"),
    queue: str | None = typer.Option(None, "--queue", help="Path to candidate queue JSON"),
    index: int = typer.Option(0, "--index", help="Candidate index in queue"),
    candidate_id: str = typer.Option("", "--candidate-id"),
    region: str = typer.Option("", "--region"),
    location: str = typer.Option("", "--location"),
) -> None:
    """Import a single job posting into the workspace."""
    from job_hunter.tracker import import_job_artifact

    fallback_text = ""
    resolved_url = url or ""
    resolved_title = title or ""
    resolved_company = company or ""
    resolved_location = location or ""
    resolved_region = region or ""

    if queue:
        from job_hunter import agent_context
        from job_hunter.sources.jd_fetcher import is_greenhouse_listing_url

        candidate = agent_context.candidate_from_queue(Path(queue), index, candidate_id=candidate_id)
        resolved_title = resolved_title or candidate.get("title", "")
        resolved_company = resolved_company or candidate.get("company", "")
        resolved_url = resolved_url or candidate.get("url", "")
        resolved_region = resolved_region or candidate.get("region", "")
        resolved_location = resolved_location or candidate.get("location", "")
        fallback_text = candidate.get("snippet", "")
        if resolved_url and is_greenhouse_listing_url(resolved_url):
            expanded = _expand_listing_candidate(resolved_url, resolved_company, resolved_location, resolved_title)
            if expanded:
                resolved_title = resolved_title or expanded.get("title", "")
                resolved_company = resolved_company or expanded.get("company", "")
                resolved_url = expanded.get("url", resolved_url)
                resolved_location = resolved_location or expanded.get("location", "")
                fallback_text = expanded.get("snippet", fallback_text)

    source_path = Path(file) if file else None
    folder = import_job_artifact(
        title=resolved_title,
        company=resolved_company,
        url=resolved_url,
        text=text or "",
        fallback_text=fallback_text,
        source_path=source_path,
        region=resolved_region,
        location=resolved_location,
    )
    typer.echo(folder.as_posix())


@internal_app.command(name="compile-pdf")
def compile_pdf(
    job: str = typer.Option(..., "--job", help="Job folder name under outputs/jobs/"),
) -> None:
    """Compile resume_tailored.tex to PDF for a job folder."""
    import shutil

    from job_hunter.config.loader import ROOT, get_config
    from job_hunter.pipeline.pdf_compiler import compile_tex
    from job_hunter.tracker import repo_path

    tex_path = repo_path("outputs", "jobs", job, "resume_tailored.tex")
    if not tex_path.exists():
        fail(f"[compile-pdf] resume_tailored.tex not found in {job}")

    job_dir = tex_path.parent
    profile = get_config("job_hunter").get("profile", {})
    for key in ("latex_class", "profile_image"):
        rel = profile.get(key, "")
        if not rel:
            continue
        src_file = ROOT / rel
        if src_file.exists():
            dst = job_dir / src_file.name
            if not dst.exists():
                shutil.copy2(src_file, dst)

    pdf = compile_tex(str(tex_path), str(job_dir))
    if pdf:
        typer.echo(f"[compile-pdf] {pdf}")
        return
    fail("[compile-pdf] compilation failed — check the log above")


@internal_app.command(name="commit-job")
def commit_job(
    job: str = typer.Argument(..., help="Job folder name under outputs/jobs/"),
) -> None:
    """Git-commit a tailored job folder and mark it processed."""
    import subprocess

    from job_hunter.tracker import repo_path
    from job_hunter.tracking.processed_urls import load_processed, mark_processed

    folder = repo_path("outputs", "jobs", job)
    if not folder.exists():
        fail(f"[commit-job] job folder not found: {folder}")
    root = str(folder.parent.parent.parent)
    meta_path = folder / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        existing_urls = load_processed()
        mark_processed([meta], existing_urls)

    subprocess.run(["git", "add", str(folder)], check=True, cwd=root)
    result = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=root)
    if result.returncode != 0:
        subprocess.run(["git", "commit", "-m", f"chore(jobs): tailor {job}"], check=True, cwd=root)
        typer.echo(f"[commit-job] committed {job}")
    else:
        typer.echo(f"[commit-job] nothing new to commit for {job}")


@internal_app.command(name="update-readme")
def update_readme(
    job: str = typer.Option(..., "--job", help="Job folder name under outputs/jobs/"),
) -> None:
    """Add or update a job entry in README.md tracking table."""
    from datetime import date

    from job_hunter.core.utils import read_yaml
    from job_hunter.pipeline.stages.readme import update_readme_from_applications
    from job_hunter.tracker import repo_path
    from job_hunter.tracking.applications import _require_apply_score, load_applications, upsert_application_from_job

    folder = repo_path("outputs", "jobs", job)
    meta_path = folder / "meta.json"
    if not meta_path.exists():
        fail(f"[update-readme] meta.json not found in {job}")
    if not (folder / "resume_tailored.tex").exists():
        fail(f"[update-readme] resume_tailored.tex not found in {job}")
    try:
        _require_apply_score(read_yaml(folder / "score.yml"), job)
    except ValueError as exc:
        fail(f"[update-readme] {exc}")

    today = date.today().isoformat()
    root = repo_path()
    upsert_application_from_job(job, root=root, status="tailored")
    all_apps = load_applications(root)["applications"]
    update_readme_from_applications(all_apps, root, today)
    typer.echo(f"[update-readme] README updated for {job}")


@internal_app.command(name="write-research")
def write_research_cmd(
    job: str = typer.Option(..., "--job", help="Job folder name under outputs/jobs/"),
) -> None:
    """Write company_research.md for a job using LLM training-data knowledge."""
    import logging

    from job_hunter.config.loader import get_config
    from job_hunter.llm.stage import LLMStage
    from job_hunter.pipeline._match_processor import write_company_research
    from job_hunter.tracker import repo_path

    logger = logging.getLogger(__name__)
    root = repo_path()
    job_dir = root / "outputs" / "jobs" / job
    meta_path = job_dir / "meta.json"
    if not meta_path.exists():
        fail(f"[write-research] meta.json not found in {job}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    write_company_research(meta, job_dir, get_config=get_config, llm_stage_factory=LLMStage, logger=logger)
    out = job_dir / "company_research.md"
    if out.exists():
        typer.echo(f"[write-research] company_research.md written for {job}")
    else:
        fail(f"[write-research] research failed for {job}")


@internal_app.command(name="mark-processed")
def mark_processed_cmd(
    url: str | None = typer.Option(None, "--url"),
    company: str | None = typer.Option(None, "--company"),
    title: str | None = typer.Option(None, "--title"),
    from_candidates: str | None = typer.Option(None, "--from-candidates", help="Path to candidates file"),
) -> None:
    """Mark a job as processed in the dedup tracker."""
    import yaml

    from job_hunter.tracking.processed_urls import load_processed, mark_processed

    if from_candidates:
        try:
            data = yaml.safe_load(Path(from_candidates).read_text(encoding="utf-8")) or {}
        except OSError as exc:
            typer.echo(f"[mark-processed] cannot read {from_candidates}: {exc}", err=True)
            raise typer.Exit(1) from exc
        candidates = data if isinstance(data, list) else data.get("candidates", [])
        existing_urls = load_processed()
        mark_processed(candidates, existing_urls)
        typer.echo(f"[mark-processed] marked {len(candidates)} candidates from {from_candidates}")
        return
    if not url and not (company and title):
        fail("[mark-processed] provide --from-candidates or --url/--company/--title")
    job = {"url": url or "", "company": company or "", "title": title or ""}
    existing_urls = load_processed()
    mark_processed([job], existing_urls)
    typer.echo(f"[mark-processed] marked: {title} @ {company}")


def _fail_finalize(errors: list[str], *, label: str) -> None:
    typer.echo(f"[finalize-run] {label} failed:", err=True)
    for error in errors[:20]:
        typer.echo(f"- {error}", err=True)
    raise typer.Exit(1)


def _report_finalize_result(result: dict) -> None:
    """Translate a `_run_artifacts.run_finalize_core` result dict into the same stdout
    contract `finalize-run` has always had. Shared by `internal finalize-run` and the
    public `job-hunter finalize` command."""
    if not result["ok"]:
        stage = result.get("stage", "finalize")
        if stage in ("verify", "validation"):
            _fail_finalize(result["error"].split("; "), label=stage)
        fail(f"[finalize-run] {result['error']}")
        return

    if result["discarded"]:
        typer.echo(f"[finalize-run] discarded {result['discarded']} SKIP/missing-JD job folder(s) before commit")
    if result["synced"]:
        typer.echo(f"[finalize-run] synced {result['synced']} processed job tracker entry(s)")
    if result["committed"]:
        typer.echo(f"[finalize-run] committed: {result['message']}")
    else:
        typer.echo("[finalize-run] no finalizable changes to commit")
    if result["pushed"]:
        merge = result.get("merge") or {}
        if merge.get("inserted") or merge.get("updated") or merge.get("deleted"):
            typer.echo(
                f"[finalize-run] merged remote job state: {merge.get('inserted', 0)} new, "
                f"{merge.get('updated', 0)} updated, {merge.get('deleted', 0)} removed"
            )
        typer.echo("[finalize-run] pushed to origin")
    for rel in result.get("cleaned") or []:
        typer.echo(f"[finalize-run] cleaned up {rel}")


@internal_app.command(name="finalize-run")
def finalize_run(
    message: str | None = typer.Option(
        None, "--message", "-m", help="Commit message; derived from changed paths when omitted"
    ),
    push: bool = typer.Option(False, "--push"),
    mode: str = typer.Option("manual", "--mode", help="manual|auto"),
) -> None:
    """Validate, commit, and optionally push durable run artifacts."""
    from job_hunter.agent_context import validate_score_file
    from job_hunter.tracker import repo_path
    from job_hunter.ux.health import verify_repository

    root = repo_path()
    verify_errors = verify_repository(root)["errors"]
    result = _run_artifacts.run_finalize_core(
        root,
        verify_errors=verify_errors,
        validate_score_file=validate_score_file,
        message=message,
        push=push,
        mode=mode,
    )
    _report_finalize_result(result)


@app.command(name="finalize")
def finalize_public(
    message: str | None = typer.Option(
        None, "--message", "-m", help="Commit message; derived from changed paths when omitted"
    ),
    push: bool = typer.Option(False, "--push", help="Also push to origin after committing"),
) -> None:
    """Validate, commit, and optionally push durable run artifacts — README, settings,
    profile, and job/LinkedIn outputs. Same action as the dashboard's Finalize button."""
    finalize_run(message=message, push=push, mode="manual")


@internal_app.command(name="sync")
def sync(
    message: str = typer.Option(
        "chore(sync): local changes", "--message", "-m", help="Commit message for local changes"
    ),
) -> None:
    """Commit dirty durable state, merge the remote jobs.db, and push — the GUI Sync button's CLI twin."""
    from job_hunter.tracker import repo_path
    from job_hunter.workspace.git_sync import sync_workspace

    result = sync_workspace(repo_path(), message=message)
    if not result["ok"]:
        fail(f"[sync] {result['error']}")
    typer.echo(
        f"[sync] merged remote job state: {result['inserted']} new, "
        f"{result['updated']} updated, {result['deleted']} removed"
    )
    typer.echo("[sync] pushed to origin")


@internal_app.command(name="cleanup-transient")
def cleanup_transient() -> None:
    """Delete transient agent state files (queues, batch, screen files)."""
    from job_hunter.tracker import repo_path

    cleaned = _cleanup_transient_state(repo_path())
    for rel in cleaned:
        typer.echo(f"[cleanup-transient] cleaned up {rel}")
    if not cleaned:
        typer.echo("[cleanup-transient] no transient state files found")


@internal_app.command(name="discard-job")
def discard_job(
    job: str = typer.Option(..., "--job", help="Job folder name under outputs/jobs/"),
) -> None:
    """Delete a job folder and mark it processed."""
    from job_hunter.tracker import repo_path

    if not _discard_job_folder(repo_path(), job):
        fail(f"[discard-job] folder not found: {repo_path('outputs', 'jobs', job)}")
    typer.echo(f"[discard-job] deleted and marked discarded: {job}")


@internal_app.command(name="region-lookup")
def region_lookup(
    city: str = typer.Option(..., "--city"),
) -> None:
    """Look up the ISO 3166-1 alpha-2 country code for a city or country name."""
    from job_hunter.config.locations import country_code_for_city, location_to_config, resolve_config_location

    country = country_code_for_city(city)
    location = location_to_config(resolve_config_location(country, city)) if country else None
    typer.echo(json.dumps({"city": city, "country": country, "location": location}))


@internal_app.command(name="compile-profile")
def compile_profile_cmd() -> None:
    """Compile profile files into minified versions for the current run."""
    from job_hunter.config.loader import ROOT
    from job_hunter.tools.compile_profile import compile_all

    compile_all(ROOT)


@update_safety_app.command("classify")
def update_safety_classify(
    paths: Annotated[list[str], typer.Argument()],
    json_output: bool = JSON_OPTION,
) -> None:
    """Classify file paths by update safety layer."""
    from job_hunter.ux.health import dump_json
    from job_hunter.workspace.safety import classify_paths

    payload = {"paths": classify_paths(paths)}
    if json_output:
        typer.echo(dump_json(payload))
    else:
        for item in payload["paths"]:
            typer.echo(f"{item['layer']:<7} {item['path']}")


@update_safety_app.command("report")
def update_safety_report_cmd(
    paths: Annotated[list[str] | None, typer.Argument()] = None,
    json_output: bool = JSON_OPTION,
) -> None:
    """Show full update-safety report for given paths."""
    from job_hunter.tracker import repo_path
    from job_hunter.ux.health import dump_json
    from job_hunter.workspace.safety import update_safety_report

    payload = update_safety_report(
        repo_path(),
        paths=paths or None,
    )
    if json_output:
        typer.echo(dump_json(payload))
    else:
        for item in payload["paths"]:
            typer.echo(f"{item['layer']:<7} {item['path']}")
        if payload["unsafe"]:
            typer.echo("[update-safety] refused user/unknown paths:", err=True)
            for path in payload["unsafe"]:
                typer.echo(f"- {path}", err=True)
    raise typer.Exit(0 if payload["ok"] else 1)
