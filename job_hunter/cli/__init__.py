"""Job Hunter CLI — Typer-based command dispatcher."""

from __future__ import annotations

import json
from pathlib import Path

import typer

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FINALIZE_PATHS = (
    "README.md",
    "config",
    "profile",
    "outputs/applications.yml",
    "outputs/candidates",
    "outputs/jobs",
    "outputs/linkedin",
    "outputs/state/api_usage.json",
    "outputs/state/dev_token_metrics.json",
    "outputs/state/discovered_urls.yml",
)
TRANSIENT_STATE_PATHS = (
    "outputs/state/agent_candidate_queue.json",
    "outputs/state/agent_candidate_batch.json",
    "outputs/state/batch_scores.yml",
    "outputs/state/batch_screen.yml",
    "outputs/state/batch_judgment.yml",
)

# ---------------------------------------------------------------------------
# Typer apps
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="job-hunter",
    help="Job search automation — agent mode and LLM-API mode.",
    add_completion=False,
    no_args_is_help=True,
)

internal_app = typer.Typer(
    help="Commands used by bundled agent skills and maintenance automation.", no_args_is_help=True
)
app.add_typer(internal_app, name="internal", hidden=True)

agent_context_app = typer.Typer(help="Build agent context objects for Claude Code skills.", no_args_is_help=True)
internal_app.add_typer(agent_context_app, name="agent-context")

applications_app = typer.Typer(help="Manage application lifecycle.", no_args_is_help=True)
app.add_typer(applications_app, name="applications")

linkedin_app = typer.Typer(help="Run LinkedIn content and networking pipelines.", no_args_is_help=True)
internal_app.add_typer(linkedin_app, name="linkedin")

update_safety_app = typer.Typer(help="Classify paths by update safety layer.", no_args_is_help=True)
internal_app.add_typer(update_safety_app, name="update-safety")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cleanup_transient_state(root: Path, *, label: str) -> int:
    cleaned = 0
    for rel in TRANSIENT_STATE_PATHS:
        p = root / rel
        if p.exists():
            p.unlink()
            cleaned += 1
            typer.echo(f"[{label}] cleaned up {rel}")
    return cleaned


def _sync_processed_from_job_outputs(root: Path) -> int:
    import yaml

    jobs_dir = root / "outputs" / "jobs"
    if not jobs_dir.exists():
        return 0

    state_path = root / "outputs" / "state" / "discovered_urls.yml"
    if state_path.exists():
        state = yaml.safe_load(state_path.read_text(encoding="utf-8")) or {}
    else:
        state = {}
    urls = set(state.get("discovered", []) or [])
    before = len(urls)

    for meta_path in sorted(jobs_dir.glob("*/meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        url = str(meta.get("url") or "")
        if url:
            urls.add(url)

    added = len(urls) - before
    if not added:
        return 0

    state_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# URL-only dedup state. Each entry is a canonical job URL.\n"
        "# Automatically updated after each run.\n"
        "# Remove a URL manually to rediscover or reprocess that job.\n\n"
    )
    state_path.write_text(
        header + yaml.safe_dump({"discovered": sorted(urls)}, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    return added


def _validate_run_artifacts(root: Path) -> list[str]:
    import re
    from datetime import date

    import yaml

    from job_hunter import agent_context
    from job_hunter.sources._policy import JobPolicy

    errors: list[str] = []
    job_hunter_config = yaml.safe_load((root / "config" / "job_hunter.yml").read_text(encoding="utf-8")) or {}
    policy = JobPolicy(job_hunter_config)
    seen_application_keys: dict[str, str] = {}
    today = date.today().isoformat()

    for job_dir in sorted((root / "outputs" / "jobs").glob("*")):
        if not job_dir.is_dir():
            continue
        meta_path = job_dir / "meta.json"
        score_path = job_dir / "score.yml"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            errors.append(f"{meta_path.as_posix()}: invalid meta.json: {exc}")
            continue
        is_today = job_dir.name.startswith(today) or meta.get("date") == today
        if not is_today:
            continue
        key = f"{meta.get('company', '').lower()}::{meta.get('title', '').lower()}"
        if key != "::" and key in seen_application_keys:
            errors.append(f"{job_dir.as_posix()}: duplicate application title also in {seen_application_keys[key]}")
        elif key != "::":
            seen_application_keys[key] = job_dir.as_posix()

        if score_path.exists():
            try:
                raw_score = yaml.safe_load(score_path.read_text(encoding="utf-8")) or {}
            except (yaml.YAMLError, UnicodeDecodeError) as exc:
                errors.append(f"{score_path.as_posix()}: invalid score.yml: {exc}")
                continue
            if str(raw_score.get("status") or "").lower() == "pending":
                continue
            validation = agent_context.validate_score_file(score_path)
            if not validation["valid"]:
                errors.append(f"{score_path.as_posix()}: invalid score.yml: {validation['error']}")
                continue
            if str(raw_score.get("decision") or "").upper() == "APPLY" and policy.is_excluded_company(
                str(meta.get("company") or "")
            ):
                errors.append(f"{job_dir.as_posix()}: APPLY job is from excluded company {meta.get('company')}")

    readme_path = root / "README.md"
    if readme_path.exists():
        readme = readme_path.read_text(encoding="utf-8", errors="replace")
        for rel in re.findall(r"\[Files\]\((outputs/jobs/[^)]+/)\)", readme):
            if not (root / rel).exists():
                errors.append(f"README.md: broken Files link {rel}")
    return errors


def _expand_listing_candidate(url: str, company: str, location: str, title: str) -> dict | None:
    from job_hunter.config import get_config
    from job_hunter.sources.search_providers import fetch_playwright_career_jobs

    search_cfg = get_config("job_hunter")
    title_filters = search_cfg.get("job_titles", [])
    excluded_terms = (search_cfg.get("exclusions", {}) or {}).get("title_terms", [])
    try:
        jobs = fetch_playwright_career_jobs(
            {"name": company or "Unknown Company", "career_url": url, "location": location},
            title_filters,
            excluded_terms,
        )
    except Exception:
        return None
    if not jobs:
        return None
    wanted = title.lower().strip()
    for job in jobs:
        found = str(job.get("title") or "").lower()
        if wanted and (wanted in found or found in wanted):
            return job
    return jobs[0] if len(jobs) == 1 else None


# ---------------------------------------------------------------------------
# Hunt commands
# ---------------------------------------------------------------------------


@app.command()
def brief() -> None:
    """Generate today's job search briefing."""
    from job_hunter.briefing import write_today_briefing

    artifact = write_today_briefing()
    typer.echo(artifact.as_posix())


@app.command()
def hunt(
    region: str | None = typer.Option(None, "--region", "-r", help="Region key from config/job_hunter.yml"),
    depth: str = typer.Option("standard", "--depth", help="Scan depth: fast|standard|deep"),
    scrape_only: bool = typer.Option(False, "--scrape-only", help="Scrape and snapshot only; skip scoring"),
    from_snapshot: str | None = typer.Option(None, "--from-snapshot", help="Path to snapshot file"),
    skip_score: bool = typer.Option(False, "--skip-score"),
    skip_validate: bool = typer.Option(False, "--skip-validate"),
    force: bool = typer.Option(False, "--force", help="Reprocess already-seen jobs"),
) -> None:
    """Run job discovery and enrichment pipeline."""
    from job_hunter.cli._dispatch import dispatch_hunt

    dispatch_hunt(
        region_key=region,
        depth=depth,
        scrape_only=scrape_only,
        from_snapshot=from_snapshot,
        skip_score=skip_score,
        skip_validate=skip_validate,
        force=force,
    )


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


@app.command()
def tailor(
    links: str | None = typer.Option(None, "--links", help="Comma-separated job URLs"),
    jd_file: str | None = typer.Option(None, "--jd-file", help="Path to JD text file"),
    title: str | None = typer.Option(None, "--title"),
    company: str | None = typer.Option(None, "--company"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Tailor resume for one or more job postings."""
    from job_hunter.cli._dispatch import dispatch_tailor

    if links:
        dispatch_tailor(links=links, title=title, company=company, force=force)
        return
    if jd_file:
        jd_text = Path(jd_file).read_text(encoding="utf-8")
        dispatch_tailor(jd_text=jd_text, title=title, company=company, force=force)
        return
    typer.echo("[tailor] provide --links or --jd-file", err=True)
    raise typer.Exit(1)


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
        typer.echo(f"[compile-pdf] resume_tailored.tex not found in {job}", err=True)
        raise typer.Exit(1)

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
    typer.echo("[compile-pdf] compilation failed — check the log above", err=True)
    raise typer.Exit(1)


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
        typer.echo(f"[commit-job] job folder not found: {folder}", err=True)
        raise typer.Exit(1)
    root = str(folder.parent.parent.parent)
    meta_path = folder / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        existing_urls = load_processed()
        mark_processed([meta], existing_urls)

    subprocess.run(["git", "add", str(folder)], check=True, cwd=root)
    subprocess.run(
        ["git", "add", str(repo_path("outputs", "state", "discovered_urls.yml"))],
        check=True,
        cwd=root,
    )
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
    from job_hunter.ux.applications import upsert_application_from_job

    folder = repo_path("outputs", "jobs", job)
    meta_path = folder / "meta.json"
    if not meta_path.exists():
        typer.echo(f"[update-readme] meta.json not found in {job}", err=True)
        raise typer.Exit(1)
    if not (folder / "resume_tailored.tex").exists():
        typer.echo(f"[update-readme] resume_tailored.tex not found in {job}", err=True)
        raise typer.Exit(1)

    today = date.today().isoformat()
    root = repo_path()
    application = upsert_application_from_job(job, root=root, status="tailored")
    update_readme_from_applications([application], root, today)
    typer.echo(f"[update-readme] README updated for {job}")


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
        typer.echo("[mark-processed] provide --from-candidates or --url/--company/--title", err=True)
        raise typer.Exit(1)
    job = {"url": url or "", "company": company or "", "title": title or ""}
    existing_urls = load_processed()
    mark_processed([job], existing_urls)
    typer.echo(f"[mark-processed] marked: {title} @ {company}")


@internal_app.command(name="finalize-run")
def finalize_run(
    message: str = typer.Option("chore: finalize hunt run", "--message", "-m"),
    push: bool = typer.Option(False, "--push"),
    mode: str = typer.Option("manual", "--mode", help="manual|auto"),
) -> None:
    """Validate, commit, and optionally push durable run artifacts."""
    import subprocess

    from job_hunter.tracker import repo_path
    from job_hunter.ux.health import verify_repository

    root = repo_path()
    verify_payload = verify_repository(root)
    if verify_payload["errors"]:
        typer.echo("[finalize-run] verify failed:", err=True)
        for error in verify_payload["errors"][:20]:
            typer.echo(f"- {error}", err=True)
        raise typer.Exit(1)

    validation_errors = _validate_run_artifacts(root)
    if validation_errors:
        typer.echo("[finalize-run] validation failed:", err=True)
        for error in validation_errors[:20]:
            typer.echo(f"- {error}", err=True)
        raise typer.Exit(1)

    synced = _sync_processed_from_job_outputs(root)
    if synced:
        typer.echo(f"[finalize-run] synced {synced} processed job tracker entry(s)")

    finalize_paths = FINALIZE_PATHS
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
        return

    existing_paths = [path for path in finalize_paths if (root / path).exists()]
    subprocess.run(["git", "add", "--force", "--", *existing_paths], check=True, cwd=root)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root, check=False)
    if staged.returncode == 0:
        typer.echo("[finalize-run] no staged durable changes to commit")
        return
    subprocess.run(["git", "commit", "-m", message], check=True, cwd=root)
    typer.echo(f"[finalize-run] committed: {message}")
    if mode == "auto":
        subprocess.run(["git", "push", "origin", "HEAD:main"], check=True, cwd=root)
        typer.echo("[finalize-run] pushed HEAD to origin/main")
    elif push:
        subprocess.run(["git", "push"], check=True, cwd=root)
        typer.echo("[finalize-run] pushed to origin")
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
        typer.echo(f"[discard-job] folder not found: {folder}", err=True)
        raise typer.Exit(1)
    meta_path = folder / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        existing_urls = load_processed()
        mark_processed([meta], existing_urls)
    shutil.rmtree(folder)
    typer.echo(f"[discard-job] deleted and marked processed: {job}")


# ---------------------------------------------------------------------------
# Dashboard / analytics / health
# ---------------------------------------------------------------------------


@app.command()
def dashboard(
    status: str | None = typer.Option(None, "--status"),
    region: str | None = typer.Option(None, "--region"),
    since: str | None = typer.Option(None, "--since"),
    no_interactive: bool = typer.Option(False, "--no-interactive"),
) -> None:
    """Show application dashboard."""
    from job_hunter.tracker import repo_path
    from job_hunter.ux.applications import filtered_applications
    from job_hunter.ux.dashboard import render_dashboard, run_interactive_dashboard

    root = repo_path()
    apps = filtered_applications(root=root, status=status, region=region, since=since)
    if no_interactive:
        typer.echo(render_dashboard(apps))
    else:
        raise typer.Exit(run_interactive_dashboard(apps, root))


@internal_app.command()
def analytics(
    days: int = typer.Option(30, "--days"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show pipeline analytics."""
    from job_hunter.tracker import repo_path
    from job_hunter.ux.analytics import analyze_pipeline, render_analytics
    from job_hunter.ux.health import dump_json

    payload = analyze_pipeline(repo_path(), days=days)
    if json_output:
        typer.echo(dump_json(payload))
    else:
        typer.echo(render_analytics(payload))


@app.command()
def doctor(
    workspace: str = typer.Option(".", "--workspace", "-w"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Run health checks on the workspace and report setup status."""
    from job_hunter.tracker import repo_path
    from job_hunter.ux.health import doctor as run_doctor
    from job_hunter.ux.health import dump_json

    ws = repo_path() if workspace == "." else Path(workspace)
    payload = run_doctor(ws)
    if json_output:
        typer.echo(dump_json(payload))
    else:
        for check in payload["checks"]:
            mark = "OK  " if check["ok"] else "FAIL"
            typer.echo(f"{mark} {check['name']} — {check.get('detail', '')}")
            if not check["ok"] and check.get("fix"):
                typer.echo(f"     fix: {check['fix']}")
    raise typer.Exit(0 if payload["ok"] else 1)


from job_hunter.cli import _workspace as _workspace_commands  # noqa: E402,F401


@internal_app.command()
def verify(
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Verify repository integrity."""
    from job_hunter.tracker import repo_path
    from job_hunter.ux.health import dump_json, verify_repository

    payload = verify_repository(repo_path())
    if json_output:
        typer.echo(dump_json(payload))
    else:
        for warning in payload["warnings"]:
            typer.echo(f"WARN {warning}")
        for error in payload["errors"]:
            typer.echo(f"FAIL {error}", err=True)
        if payload["ok"]:
            typer.echo("[verify] ok")
    raise typer.Exit(0 if payload["ok"] else 1)


# ---------------------------------------------------------------------------
# applications sub-app
# ---------------------------------------------------------------------------


@applications_app.command("list")
def applications_list(
    status: str | None = typer.Option(None, "--status"),
    region: str | None = typer.Option(None, "--region"),
    since: str | None = typer.Option(None, "--since"),
) -> None:
    """List applications, optionally filtered."""
    from job_hunter.tracker import repo_path
    from job_hunter.ux.applications import filtered_applications, render_applications_table

    apps = filtered_applications(root=repo_path(), status=status, region=region, since=since)
    typer.echo(render_applications_table(apps))


@applications_app.command("update")
def applications_update(
    job: str = typer.Argument(...),
    status: str = typer.Argument(...),
    note: str | None = typer.Option(None, "--note"),
) -> None:
    """Update an application's lifecycle status."""
    from job_hunter.tracker import repo_path
    from job_hunter.ux.applications import update_application_status

    app_rec = update_application_status(job, status, root=repo_path(), note=note)
    typer.echo(f"[applications] {app_rec['slug']} -> {app_rec['status']}")


# ---------------------------------------------------------------------------
# linkedin sub-app
# ---------------------------------------------------------------------------


@linkedin_app.command("ideas")
def linkedin_ideas() -> None:
    """Generate raw LinkedIn content ideas."""
    from job_hunter.linkedin.ideas import generate

    created = generate()
    typer.echo(f"[linkedin] ideas: {len(created)}")


@linkedin_app.command("draft")
def linkedin_draft() -> None:
    """Draft LinkedIn posts from unconverted ideas."""
    from job_hunter.linkedin.drafts import draft

    created = draft()
    typer.echo(f"[linkedin] drafts: {len(created)}")


@linkedin_app.command("network")
def linkedin_network() -> None:
    """Discover LinkedIn networking suggestions and draft review text."""
    from job_hunter.linkedin.engagement import discover

    payload = discover()
    typer.echo(f"[linkedin] recruiters: {len(payload['recruiters'])}; people: {len(payload['people'])}")


@linkedin_app.command("all")
def linkedin_all() -> None:
    """Run LinkedIn ideas, drafts, and networking."""
    from job_hunter.linkedin.drafts import draft
    from job_hunter.linkedin.engagement import discover
    from job_hunter.linkedin.ideas import generate

    ideas = generate()
    drafts = draft()
    network = discover()
    typer.echo(
        f"[linkedin] ideas: {len(ideas)}; drafts: {len(drafts)}; "
        f"recruiters: {len(network['recruiters'])}; people: {len(network['people'])}"
    )


# ---------------------------------------------------------------------------
# update-safety sub-app
# ---------------------------------------------------------------------------


@update_safety_app.command("classify")
def update_safety_classify(
    paths: list[str] = typer.Argument(...),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Classify file paths by update safety layer."""
    from job_hunter.update_safety import classify_paths
    from job_hunter.ux.health import dump_json

    payload = {"paths": classify_paths(paths)}
    if json_output:
        typer.echo(dump_json(payload))
    else:
        for item in payload["paths"]:
            typer.echo(f"{item['layer']:<7} {item['path']}")


@update_safety_app.command("report")
def update_safety_report_cmd(
    paths: list[str] = typer.Argument(default=None),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show full update-safety report for given paths."""
    from job_hunter.tracker import repo_path
    from job_hunter.update_safety import update_safety_report
    from job_hunter.ux.health import dump_json

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
            for p in payload["unsafe"]:
                typer.echo(f"- {p}", err=True)
    raise typer.Exit(0 if payload["ok"] else 1)


from job_hunter.cli import _agent_context as _  # noqa: E402,F401 — registers agent-context commands
