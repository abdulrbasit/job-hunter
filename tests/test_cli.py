from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_TEMPLATE = ROOT / "job_hunter" / "templates" / "workspace"
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _is_upstream_repo_context(root: Path = ROOT) -> bool:
    github_repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if github_repository:
        return github_repository == "JobHunterPath/job-hunter"
    return root.name == "job-hunter"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUTF8"] = "1"
    env["NO_COLOR"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "job_hunter.cli", *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    result.stdout = ANSI_ESCAPE.sub("", result.stdout)
    result.stderr = ANSI_ESCAPE.sub("", result.stderr)
    return result


def test_help_loads() -> None:
    result = run_cli("--help")
    assert result.returncode == 0
    assert "Job search automation" in result.stdout
    assert "hunt" in result.stdout


def test_hunt_command_exists_in_help() -> None:
    result = run_cli("--help")
    assert result.returncode == 0
    assert "hunt" in result.stdout


def test_user_contract_commands_run(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    result = run_cli("init", str(workspace))
    assert result.returncode == 0
    assert (workspace / "config" / "job_hunter.yml").exists()

    result = run_cli("doctor", "--workspace", str(workspace), "--json")
    assert result.returncode in (0, 1)
    assert "checks" in result.stdout


def test_find_jobs_workflow_runs_supported_hunt_command() -> None:
    workflow = (WORKSPACE_TEMPLATE / ".github" / "workflows" / "find-jobs.yml").read_text(encoding="utf-8")

    assert "name: Scrape jobs" in workflow
    assert "id: scrape" in workflow
    assert "timeout-minutes: 55" in workflow
    assert "job-hunter hunt ${{ steps.region.outputs.arg }}" in workflow
    assert "job-hunter brief" not in workflow
    assert "always() && steps.region.outputs.should_run == 'true'" in workflow
    assert "texlive/texlive:latest" in workflow
    assert "texlive.tar" not in workflow


def test_setup_doc_explains_company_hunt_feeds_the_main_jobs_db() -> None:
    """The dashboard's browser-hunt button output was previously undocumented anywhere a
    user would read — SETUP.md must explain it writes into the same jobs.db as the
    regular hunt."""
    setup = (WORKSPACE_TEMPLATE / "SETUP.md").read_text(encoding="utf-8")

    assert "Company Hunt" in setup
    assert "outputs/state/jobs.db" in setup


def test_tailor_job_workflow_push_retries_like_find_jobs() -> None:
    """tailor-job.yml's push must retry/rebase on race, matching find-jobs.yml — a bare
    `git push` previously failed hard if find-jobs and tailor-job ran close together."""
    workflow = (WORKSPACE_TEMPLATE / ".github" / "workflows" / "tailor-job.yml").read_text(encoding="utf-8")

    assert "for i in 1 2 3; do" in workflow
    assert "git rebase origin/main" in workflow


def test_upstream_repo_context_uses_github_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "abdul/Abdul.Basit_Resume")
    assert _is_upstream_repo_context(Path("job-hunter")) is False

    monkeypatch.setenv("GITHUB_REPOSITORY", "JobHunterPath/job-hunter")
    assert _is_upstream_repo_context(Path("Abdul.Basit_Resume")) is True


def test_upstream_repo_context_falls_back_to_checkout_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    assert _is_upstream_repo_context(Path("job-hunter")) is True
    assert _is_upstream_repo_context(Path("Abdul.Basit_Resume")) is False


def test_removed_commands_not_in_help() -> None:
    result = run_cli("--help")
    assert result.returncode == 0
    for public in (
        "applications",
        "dashboard",
        "doctor",
        "hunt",
        "init",
        "tailor",
        "update",
        "version",
    ):
        assert public in result.stdout
    for removed in (
        "agent-context",
        "analytics",
        "cleanup-transient",
        "compile-pdf",
        "config",
        "discard-job",
        "finalize-run",
        "import-job",
        "linkedin",
        "mark-processed",
        "update-info",
        "update-readme",
        "update-safety",
        "update-skills",
        "update-workflows",
        "verify",
    ):
        assert removed not in result.stdout, f"removed command still present in help: {removed}"


def test_agent_context_help_loads() -> None:
    result = run_cli("internal", "agent-context", "--help")
    assert result.returncode == 0
    assert "story-index" in result.stdout
    assert "stories-final" in result.stdout
    assert "lifecycle" in result.stdout


def test_internal_commands_remain_available_but_hidden() -> None:
    top_level = run_cli("--help")
    internal = run_cli("internal", "--help")

    assert top_level.returncode == 0
    assert "internal" not in top_level.stdout
    assert internal.returncode == 0
    assert "import-job" in internal.stdout
    assert "finalize-run" in internal.stdout
    assert "agent-context" in internal.stdout


# Full registered command surface — every public and internal command name.
# Update this set deliberately when a command is added, renamed, or removed.
KNOWN_PUBLIC_COMMANDS = {
    "applications",
    "dash",
    "dashboard",
    "doctor",
    "hunt",
    "init",
    "tailor",
    "update",
    "version",
}
KNOWN_INTERNAL_COMMANDS = {
    "agent-context",
    "linkedin",
    "update-safety",
    "import-job",
    "compile-pdf",
    "commit-job",
    "update-readme",
    "write-research",
    "mark-processed",
    "telemetry-hook",
    "telemetry-mark",
    "telemetry-outcome",
    "finalize-run",
    "cleanup-transient",
    "discard-job",
    "compile-profile",
    "analytics",
    "verify",
}


def test_cli_command_registration_matches_known_surface() -> None:
    top_level = run_cli("--help")
    internal = run_cli("internal", "--help")
    assert top_level.returncode == 0
    assert internal.returncode == 0

    for name in KNOWN_PUBLIC_COMMANDS:
        assert name in top_level.stdout, f"expected public command missing from --help: {name}"
    for name in KNOWN_INTERNAL_COMMANDS:
        assert name in internal.stdout, f"expected internal command missing from `internal --help`: {name}"


def test_internal_commands_referenced_by_skills_are_all_registered() -> None:
    """Guards skill/CLI drift: every `job-hunter internal <cmd>` a skill calls must exist."""
    import re

    skills_root = ROOT / ".claude" / "skills"
    referenced: set[str] = set()
    for path in skills_root.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        referenced.update(re.findall(r"job-hunter internal ([a-z][a-z-]*)", text))

    unregistered = referenced - KNOWN_INTERNAL_COMMANDS
    assert not unregistered, f"skills reference unregistered internal command(s): {unregistered}"
    assert referenced, "expected at least one skill to reference an internal command"


def test_update_replaces_specialized_update_commands() -> None:
    result = run_cli("update", "--help")

    assert result.returncode == 0
    assert "--skills-only" in result.stdout
    assert "--workflows-only" in result.stdout


def test_version_includes_update_guidance() -> None:
    result = run_cli("version")

    assert result.returncode == 0
    assert "uv tool upgrade job-hunter-kit" in result.stdout


def test_commit_job_marks_url_as_processed() -> None:
    import shutil

    import job_hunter.cli as cli_module
    from job_hunter.tracker import import_job_artifact
    from job_hunter.tracking.processed_urls import load_processed

    folder = import_job_artifact(
        title="Product Manager",
        company="TrackerTestCo",
        url="https://example.com/jobs/tracker-test-unit",
    )
    try:
        with patch("subprocess.run", return_value=MagicMock(returncode=1)):
            from typer.testing import CliRunner

            runner = CliRunner()
            runner.invoke(cli_module.app, ["internal", "commit-job", folder.name])

        urls = load_processed()
        assert "https://example.com/jobs/tracker-test-unit" in urls
    finally:
        if folder.exists():
            shutil.rmtree(folder)


def test_import_raw_job_uses_fallback_without_fetching() -> None:
    import shutil

    from job_hunter.tracker import import_job_artifact

    fallback = "Responsibilities and requirements for a product management role. " * 10
    with patch("job_hunter.sources.jd_fetcher.fetch_jd") as fetch:
        folder = import_job_artifact(
            title="Product Manager",
            company="Simulation Labs",
            url="raw://simulation",
            fallback_text=fallback,
        )
    try:
        fetch.assert_not_called()
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        assert meta["job_description_fetch_status"] == "fallback_snippet"
        assert fallback.strip() in (folder / "jd.md").read_text(encoding="utf-8")
    finally:
        if folder.exists():
            shutil.rmtree(folder)


def test_mark_processed_from_candidates() -> None:
    import tempfile

    import yaml

    from job_hunter.tracking.processed_urls import load_processed

    candidates = [
        {
            "url": "https://example.com/mark-test-1",
            "company": "MarkCo",
            "title": "PM",
        },
    ]
    with tempfile.NamedTemporaryFile(suffix=".yml", mode="w", delete=False, encoding="utf-8") as f:
        yaml.safe_dump(candidates, f)
        tmp = f.name
    try:
        result = run_cli("internal", "mark-processed", "--from-candidates", tmp)
        assert result.returncode == 0
        urls = load_processed()
        assert "https://example.com/mark-test-1" in urls
    finally:
        Path(tmp).unlink(missing_ok=True)


def test_applications_list_dashboard_doctor_and_verify_commands_load() -> None:
    result = run_cli("applications", "list")
    assert result.returncode == 0
    assert "Status" in result.stdout

    result = run_cli("dashboard", "--no-interactive")
    assert result.returncode == 0
    assert "Job Hunter Dashboard" in result.stdout

    result = run_cli("internal", "analytics", "--json")
    assert result.returncode == 0
    assert "by_status" in result.stdout

    result = run_cli("internal", "update-safety", "classify", "job_hunter/cli/__init__.py", "--json")
    assert result.returncode == 0
    assert "system" in result.stdout

    result = run_cli("doctor", "--json")
    assert result.returncode in (0, 1)
    assert "checks" in result.stdout

    result = run_cli("internal", "verify", "--json")
    assert result.returncode in (0, 1)
    assert "errors" in result.stdout


def test_finalize_syncs_job_outputs_into_processed_tracker(tmp_path: Path) -> None:
    from job_hunter.cli.commands import internal as cli_module
    from job_hunter.tracking.repository import get_all_known_urls

    job_dir = tmp_path / "outputs" / "jobs" / "2026-06-04_toast_product-manager-reporting-platform"
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(
        json.dumps(
            {
                "company": "Toast",
                "title": "Product Manager, Reporting Platform",
                "url": "https://careers.toasttab.com/jobs?gh_jid=7814998",
            }
        ),
        encoding="utf-8",
    )

    added = cli_module._sync_processed_from_job_outputs(tmp_path)

    known = get_all_known_urls(tmp_path)
    assert added == 1
    assert "https://careers.toasttab.com/jobs?gh_jid=7814998" in known


def test_finalize_validation_blocks_excluded_apply_and_broken_readme_link(
    tmp_path: Path,
) -> None:
    from datetime import date

    import yaml

    from job_hunter.cli.commands import internal as cli_module

    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump({"exclusions": {"companies": ["Delivery Hero"]}}),
        encoding="utf-8",
    )
    job_dir = tmp_path / "outputs" / "jobs" / f"{date.today().isoformat()}_excluded"
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(
        json.dumps(
            {
                "company": "Delivery Hero SE",
                "title": "Product Manager",
                "url": "https://example.com/dh",
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "score.yml").write_text(
        yaml.safe_dump(
            {
                "score": 80,
                "decision": "APPLY",
                "role_summary": "Product role.",
                "score_rationale": "Strong match.",
                "recommendation": "Apply.",
                "matched_story_ids": ["ST-01"],
                "matched": ["product"],
                "gaps": [],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "[Files](outputs/jobs/missing/)",
        encoding="utf-8",
    )

    errors = cli_module._validate_run_artifacts(tmp_path)

    assert any("excluded company" in error for error in errors)
    assert any("broken Files link" in error for error in errors)


def test_update_readme_uses_score_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import yaml
    from typer.testing import CliRunner

    import job_hunter.cli as cli_module
    import job_hunter.tracker as tracker

    job = "2026-06-12_acme_pm"
    job_dir = tmp_path / "outputs" / "jobs" / job
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(
        json.dumps(
            {
                "date": "2026-06-12",
                "company": "Acme",
                "title": "Product Manager",
                "url": "https://example.com/acme",
                "location": "Berlin",
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "score.yml").write_text(
        yaml.safe_dump({"score": 82, "decision": "APPLY"}),
        encoding="utf-8",
    )
    (job_dir / "resume_tailored.tex").write_text("\\documentclass{altacv}", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "<!-- JOBS_TABLE_START -->\n"
        "| Date | Job | Location | Score | Files |\n"
        "|---|---|---|---|---|\n"
        "<!-- JOBS_TABLE_END -->\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tracker, "repo_path", lambda *parts: tmp_path.joinpath(*parts))

    result = CliRunner().invoke(cli_module.app, ["internal", "update-readme", "--job", job])

    assert result.exit_code == 0, result.output
    text = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "| 82 (tailored) |" in text
    assert f"outputs/jobs/{job}/" in text


def test_update_readme_preserves_existing_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling update-readme for one job must not drop rows for other already-tracked jobs."""
    import yaml
    from typer.testing import CliRunner

    import job_hunter.cli as cli_module
    import job_hunter.tracker as tracker

    def _make_job(slug: str, score: int, url: str) -> None:
        job_dir = tmp_path / "outputs" / "jobs" / slug
        job_dir.mkdir(parents=True)
        (job_dir / "meta.json").write_text(
            json.dumps({"date": "2026-06-26", "company": "Co", "title": slug, "url": url, "location": "Berlin"}),
            encoding="utf-8",
        )
        (job_dir / "score.yml").write_text(yaml.safe_dump({"score": score, "decision": "APPLY"}), encoding="utf-8")
        (job_dir / "resume_tailored.tex").write_text("\\documentclass{altacv}", encoding="utf-8")

    existing_slug = "2026-06-26_existing_co_job-a"
    new_slug = "2026-06-26_new_co_job-b"
    _make_job(existing_slug, 80, "https://example.com/a")
    _make_job(new_slug, 75, "https://example.com/b")

    (tmp_path / "README.md").write_text(
        "<!-- JOBS_TABLE_START -->\n"
        "| Date | Job | Location | Score | Files |\n"
        "|---|---|---|---|---|\n"
        "<!-- JOBS_TABLE_END -->\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tracker, "repo_path", lambda *parts: tmp_path.joinpath(*parts))

    # First job — seeds applications.yml
    CliRunner().invoke(cli_module.app, ["internal", "update-readme", "--job", existing_slug])
    # Second job — must not erase the first row
    result = CliRunner().invoke(cli_module.app, ["internal", "update-readme", "--job", new_slug])

    assert result.exit_code == 0, result.output
    text = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert existing_slug in text, "first job row was lost after second update-readme call"
    assert new_slug in text, "second job row missing"


def test_update_readme_rejects_missing_tailored_tex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    import job_hunter.cli as cli_module
    import job_hunter.tracker as tracker

    job = "2026-06-12_acme_pm"
    job_dir = tmp_path / "outputs" / "jobs" / job
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(
        json.dumps({"company": "Acme", "title": "Product Manager", "url": "https://example.com/acme"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(tracker, "repo_path", lambda *parts: tmp_path.joinpath(*parts))

    result = CliRunner().invoke(cli_module.app, ["internal", "update-readme", "--job", job])

    assert result.exit_code == 1
    assert "resume_tailored.tex not found" in result.output


def test_update_readme_rejects_skip_decisioned_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: a SKIP or unscored job must never produce a 'tailored' application row."""
    import yaml
    from typer.testing import CliRunner

    import job_hunter.cli as cli_module
    import job_hunter.tracker as tracker

    job = "2026-06-12_acme_pm"
    job_dir = tmp_path / "outputs" / "jobs" / job
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(
        json.dumps({"company": "Acme", "title": "Product Manager", "url": "https://example.com/acme"}),
        encoding="utf-8",
    )
    (job_dir / "score.yml").write_text(yaml.safe_dump({"score": 40, "decision": "SKIP"}), encoding="utf-8")
    (job_dir / "resume_tailored.tex").write_text("\\documentclass{altacv}", encoding="utf-8")
    monkeypatch.setattr(tracker, "repo_path", lambda *parts: tmp_path.joinpath(*parts))

    result = CliRunner().invoke(cli_module.app, ["internal", "update-readme", "--job", job])

    assert result.exit_code == 1
    assert "decision is not APPLY" in result.output


def test_update_readme_rejects_missing_score_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    import job_hunter.cli as cli_module
    import job_hunter.tracker as tracker

    job = "2026-06-12_acme_pm"
    job_dir = tmp_path / "outputs" / "jobs" / job
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(
        json.dumps({"company": "Acme", "title": "Product Manager", "url": "https://example.com/acme"}),
        encoding="utf-8",
    )
    (job_dir / "resume_tailored.tex").write_text("\\documentclass{altacv}", encoding="utf-8")
    monkeypatch.setattr(tracker, "repo_path", lambda *parts: tmp_path.joinpath(*parts))

    result = CliRunner().invoke(cli_module.app, ["internal", "update-readme", "--job", job])

    assert result.exit_code == 1
    assert "score.yml is missing" in result.output


def test_write_research_writes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    import job_hunter.cli as cli_module
    import job_hunter.tracker as tracker

    job = "2026-06-12_acme_pm"
    job_dir = tmp_path / "outputs" / "jobs" / job
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(
        json.dumps({"company": "Acme", "title": "Product Manager", "url": "https://example.com/acme"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(tracker, "repo_path", lambda *parts: tmp_path.joinpath(*parts))

    def fake_write_research(job, job_dir, *, get_config, llm_stage_factory, logger):
        (job_dir / "company_research.md").write_text("# Acme Research\n\ncontent", encoding="utf-8")

    monkeypatch.setattr("job_hunter.pipeline._match_processor.write_company_research", fake_write_research)

    result = CliRunner().invoke(cli_module.app, ["internal", "write-research", "--job", job])

    assert result.exit_code == 0
    assert "company_research.md written" in result.output
    assert (job_dir / "company_research.md").exists()


def test_write_research_exits_1_when_research_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    import job_hunter.cli as cli_module
    import job_hunter.tracker as tracker

    job = "2026-06-12_acme_pm"
    job_dir = tmp_path / "outputs" / "jobs" / job
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(
        json.dumps({"company": "Acme", "title": "Product Manager", "url": "https://example.com/acme"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(tracker, "repo_path", lambda *parts: tmp_path.joinpath(*parts))
    monkeypatch.setattr("job_hunter.pipeline._match_processor.write_company_research", lambda *a, **kw: None)

    result = CliRunner().invoke(cli_module.app, ["internal", "write-research", "--job", job])

    assert result.exit_code == 1


def test_write_research_exits_1_when_meta_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    import job_hunter.cli as cli_module
    import job_hunter.tracker as tracker

    monkeypatch.setattr(tracker, "repo_path", lambda *parts: tmp_path.joinpath(*parts))
    (tmp_path / "outputs" / "jobs" / "2026-06-12_acme_pm").mkdir(parents=True)

    result = CliRunner().invoke(cli_module.app, ["internal", "write-research", "--job", "2026-06-12_acme_pm"])

    assert result.exit_code == 1


def test_discard_job_removes_folder_and_tracks() -> None:
    import shutil

    from job_hunter.tracker import import_job_artifact
    from job_hunter.tracking.processed_urls import load_processed

    folder = import_job_artifact(
        title="Product Owner",
        company="DiscardTestCo",
        url="https://example.com/discard-test",
    )
    try:
        result = run_cli("internal", "discard-job", "--job", folder.name)
        assert result.returncode == 0
        assert not folder.exists()
        urls = load_processed()
        assert "https://example.com/discard-test" in urls
    finally:
        if folder.exists():
            shutil.rmtree(folder)


def test_cleanup_transient_removes_batch_scratch_files(tmp_path: Path, monkeypatch) -> None:
    from job_hunter.cli.commands import internal as cli_module

    monkeypatch.setattr("job_hunter.tracker.repo_path", lambda *p: tmp_path.joinpath(*p))
    for rel in cli_module.TRANSIENT_STATE_PATHS:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    cleaned = cli_module._cleanup_transient_state(tmp_path, label="test")

    assert cleaned == len(cli_module.TRANSIENT_STATE_PATHS)
    assert all(not (tmp_path / rel).exists() for rel in cli_module.TRANSIENT_STATE_PATHS)


def test_cli_run_artifact_helpers_live_in_dedicated_module(tmp_path: Path) -> None:
    from job_hunter.cli import _run_artifacts

    assert "outputs/state/agent_candidate_queue.json" in _run_artifacts.TRANSIENT_STATE_PATHS
    assert "outputs/state/jobs.db" in _run_artifacts.FINALIZE_PATHS
    assert "outputs/state/metrics.db" not in _run_artifacts.FINALIZE_PATHS

    transient = tmp_path / "outputs" / "state" / "agent_candidate_queue.json"
    transient.parent.mkdir(parents=True)
    transient.write_text("{}", encoding="utf-8")

    assert _run_artifacts.cleanup_transient_state(tmp_path, label="test") == 1
    assert not transient.exists()


def test_discard_dead_job_folders_removes_skip_and_missing_jd_but_not_apply(tmp_path: Path) -> None:
    from job_hunter.cli._run_artifacts import discard_dead_job_folders

    jobs_dir = tmp_path / "outputs" / "jobs"

    skip_job = jobs_dir / "skip-co"
    skip_job.mkdir(parents=True)
    (skip_job / "score.yml").write_text("decision: SKIP\nscore: 40\n", encoding="utf-8")
    (skip_job / "meta.json").write_text(json.dumps({"url": "https://example.com/skip"}), encoding="utf-8")

    missing_jd_job = jobs_dir / "missing-jd-co"
    missing_jd_job.mkdir(parents=True)
    (missing_jd_job / "meta.json").write_text(
        json.dumps({"url": "https://example.com/missing-jd", "job_description_fetch_status": "fetch_failed"}),
        encoding="utf-8",
    )

    apply_job = jobs_dir / "apply-co"
    apply_job.mkdir(parents=True)
    (apply_job / "score.yml").write_text("decision: APPLY\nscore: 85\n", encoding="utf-8")
    (apply_job / "resume_tailored.tex").write_text("tex", encoding="utf-8")

    discarded = discard_dead_job_folders(tmp_path)

    assert sorted(discarded) == ["missing-jd-co", "skip-co"]
    assert not skip_job.exists()
    assert not missing_jd_job.exists()
    assert apply_job.exists()


def test_finalize_run_discards_dead_job_folders_before_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: SKIP/missing-JD job folders left behind by a missed agent discard
    step must never reach a finalize commit."""
    from typer.testing import CliRunner

    import job_hunter.cli as cli_module
    from job_hunter.cli.commands import internal

    jobs_dir = tmp_path / "outputs" / "jobs"
    skip_job = jobs_dir / "skip-co"
    skip_job.mkdir(parents=True)
    (skip_job / "score.yml").write_text("decision: SKIP\nscore: 40\n", encoding="utf-8")
    (skip_job / "meta.json").write_text(json.dumps({"url": "https://example.com/skip"}), encoding="utf-8")

    monkeypatch.setattr("job_hunter.tracker.repo_path", lambda *p: tmp_path.joinpath(*p))
    monkeypatch.setattr("job_hunter.ux.health.verify_repository", lambda _root: {"errors": []})
    monkeypatch.setattr(internal, "_validate_run_artifacts", lambda _root: [])
    monkeypatch.setattr(internal, "_sync_processed_from_job_outputs", lambda _root: 0)
    monkeypatch.setattr(internal, "_commit_finalizable_changes", lambda *_args: False)

    result = CliRunner().invoke(cli_module.app, ["internal", "finalize-run"])

    assert result.exit_code == 0
    assert not skip_job.exists()
    assert "discarded 1 SKIP/missing-JD job folder" in result.stdout


def test_finalize_run_cleans_transient_state_when_nothing_is_committed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    import job_hunter.cli as cli_module
    from job_hunter.cli.commands import internal

    compiled = tmp_path / "outputs" / "state" / "compiled"
    compiled.mkdir(parents=True)
    (compiled / "career_context.min.md").write_text("compact", encoding="utf-8")

    monkeypatch.setattr("job_hunter.tracker.repo_path", lambda *p: tmp_path.joinpath(*p))
    monkeypatch.setattr("job_hunter.ux.health.verify_repository", lambda _root: {"errors": []})
    monkeypatch.setattr(internal, "_validate_run_artifacts", lambda _root: [])
    monkeypatch.setattr(internal, "_sync_processed_from_job_outputs", lambda _root: 0)
    monkeypatch.setattr(internal, "_commit_finalizable_changes", lambda *_args: False)

    result = CliRunner().invoke(cli_module.app, ["internal", "finalize-run"])

    assert result.exit_code == 0
    assert not compiled.exists()


# --- version ---


def test_version_command_runs() -> None:
    from typer.testing import CliRunner

    from job_hunter.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "job-hunter" in result.output


def test_version_command_shows_update_info() -> None:
    from typer.testing import CliRunner

    from job_hunter.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "uv tool upgrade" in result.output


def test_update_command_adds_workspace_assets(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from job_hunter.cli import app

    companies = tmp_path / "config" / "career_pages.yml"
    companies.parent.mkdir()
    companies.write_text("companies:\n  - name: Keep Me\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["update", "--workspace", str(tmp_path)])

    import yaml

    assert result.exit_code == 0
    assert (tmp_path / "SETUP.md").exists()
    assert yaml.safe_load(companies.read_bytes())["companies"] == [{"name": "Keep Me"}]


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_update_command_prompts_and_aborts_on_dirty_system_file(tmp_path: Path) -> None:
    """A local edit to a system-layer file (skill/workflow) the update is about to
    overwrite must be surfaced and confirmed, not silently discarded."""
    from typer.testing import CliRunner

    from job_hunter.cli import app
    from job_hunter.workspace.operations import run_init

    run_init(tmp_path)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    skill = tmp_path / ".claude" / "skills" / "job-hunter" / "SKILL.md"
    original = skill.read_text(encoding="utf-8")
    skill.write_text(original + "\n# local edit\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["update", "--workspace", str(tmp_path)], input="n\n")

    assert result.exit_code == 1
    assert "local edits" in result.output
    assert skill.read_text(encoding="utf-8") == original + "\n# local edit\n"


def test_update_command_yes_flag_skips_prompt_and_overwrites(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from job_hunter.cli import app
    from job_hunter.workspace.operations import run_init

    run_init(tmp_path)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    skill = tmp_path / ".claude" / "skills" / "job-hunter" / "SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\n# local edit\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["update", "--workspace", str(tmp_path), "--yes"])

    assert result.exit_code == 0
    assert "# local edit" not in skill.read_text(encoding="utf-8")
