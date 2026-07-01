"""Internal CLI commands — used by bundled agent skills and maintenance automation, hidden from --help."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from job_hunter.cli import _run_artifacts
from job_hunter.cli.app import internal_app, update_safety_app
from job_hunter.cli.options import JSON_OPTION
from job_hunter.cli.output import fail

FINALIZE_PATHS = _run_artifacts.FINALIZE_PATHS
TRANSIENT_STATE_PATHS = _run_artifacts.TRANSIENT_STATE_PATHS
_cleanup_transient_state = _run_artifacts.cleanup_transient_state
_expand_listing_candidate = _run_artifacts.expand_listing_candidate
_sync_processed_from_job_outputs = _run_artifacts.sync_processed_from_job_outputs
_validate_run_artifacts = _run_artifacts.validate_run_artifacts


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
    from job_hunter.tracking.tracker import load_processed, mark_processed

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

    from job_hunter.pipeline.readme_writer import update_readme_from_applications
    from job_hunter.tracker import repo_path
    from job_hunter.ux.applications import load_applications, upsert_application_from_job

    folder = repo_path("outputs", "jobs", job)
    meta_path = folder / "meta.json"
    if not meta_path.exists():
        fail(f"[update-readme] meta.json not found in {job}")
    if not (folder / "resume_tailored.tex").exists():
        fail(f"[update-readme] resume_tailored.tex not found in {job}")

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
    from job_hunter.pipeline._match_processor import write_company_research
    from job_hunter.pipeline.llm_stage import LLMStage
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

    from job_hunter.tracking.tracker import load_processed, mark_processed

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


def _commit_finalizable_changes(root: Path, finalize_paths: tuple[str, ...], message: str) -> bool:
    import subprocess

    status = subprocess.run(
        ["git", "status", "--porcelain", "--", *finalize_paths],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if status.returncode != 0:
        typer.echo(status.stderr.strip() or "[finalize-run] git status failed", err=True)
        raise typer.Exit(status.returncode)
    if not status.stdout.strip():
        typer.echo("[finalize-run] no finalizable changes to commit")
        return False

    existing_paths = [path for path in finalize_paths if (root / path).exists()]
    subprocess.run(["git", "add", "--force", "--", *existing_paths], check=True, cwd=root)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root, check=False)
    if staged.returncode == 0:
        typer.echo("[finalize-run] no staged durable changes to commit")
        return False
    subprocess.run(["git", "commit", "-m", message], check=True, cwd=root)
    typer.echo(f"[finalize-run] committed: {message}")
    return True


def _push_finalized_run(root: Path, *, push: bool, mode: str) -> None:
    import subprocess

    if mode == "auto":
        subprocess.run(["git", "push", "origin", "HEAD:main"], check=True, cwd=root)
        typer.echo("[finalize-run] pushed HEAD to origin/main")
    elif push:
        subprocess.run(["git", "push"], check=True, cwd=root)
        typer.echo("[finalize-run] pushed to origin")


@internal_app.command(name="finalize-run")
def finalize_run(
    message: str = typer.Option("chore: finalize hunt run", "--message", "-m"),
    push: bool = typer.Option(False, "--push"),
    mode: str = typer.Option("manual", "--mode", help="manual|auto"),
) -> None:
    """Validate, commit, and optionally push durable run artifacts."""
    from job_hunter.tracker import repo_path
    from job_hunter.ux.health import verify_repository

    root = repo_path()
    verify_payload = verify_repository(root)
    if verify_payload["errors"]:
        _fail_finalize(verify_payload["errors"], label="verify")

    validation_errors = _validate_run_artifacts(root)
    if validation_errors:
        _fail_finalize(validation_errors, label="validation")

    synced = _sync_processed_from_job_outputs(root)
    if synced:
        typer.echo(f"[finalize-run] synced {synced} processed job tracker entry(s)")

    if not _commit_finalizable_changes(root, FINALIZE_PATHS, message):
        return
    _push_finalized_run(root, push=push, mode=mode)
    _cleanup_transient_state(root, label="finalize-run")


@internal_app.command(name="cleanup-transient")
def cleanup_transient() -> None:
    """Delete transient agent state files (queues, batch, screen files)."""
    from job_hunter.tracker import repo_path

    cleaned = _cleanup_transient_state(repo_path(), label="cleanup-transient")
    if cleaned == 0:
        typer.echo("[cleanup-transient] no transient state files found")


@internal_app.command(name="discard-job")
def discard_job(
    job: str = typer.Option(..., "--job", help="Job folder name under outputs/jobs/"),
) -> None:
    """Delete a job folder and mark it processed."""
    import shutil

    from job_hunter.tracker import repo_path
    from job_hunter.tracking.tracker import load_processed, mark_processed

    folder = repo_path("outputs", "jobs", job)
    if not folder.exists():
        fail(f"[discard-job] folder not found: {folder}")
    meta_path = folder / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        existing_urls = load_processed()
        mark_processed([meta], existing_urls)
    shutil.rmtree(folder)
    typer.echo(f"[discard-job] deleted and marked processed: {job}")


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
