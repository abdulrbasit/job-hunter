"""Smoke tests for YAML files and workflow structure."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).parent.parent
WORKSPACE_TEMPLATE = _REPO_ROOT / "job_hunter" / "templates" / "workspace"


def test_workspace_template_find_jobs_is_cron_disabled_by_default() -> None:
    text = (WORKSPACE_TEMPLATE / ".github" / "workflows" / "find-jobs.yml").read_text(encoding="utf-8")
    # cron must be commented out in the template so users activate it intentionally
    assert "# schedule:" in text
    assert "workflow_dispatch:" in text
    # No active (uncommented) schedule block
    lines = text.splitlines()
    active_schedules = [ln for ln in lines if ln.strip() == "schedule:"]
    assert not active_schedules, "find-jobs.yml template must not have an active schedule trigger"


def test_workspace_template_tailor_job_workflow_present() -> None:
    path = WORKSPACE_TEMPLATE / ".github" / "workflows" / "tailor-job.yml"
    assert path.exists(), "tailor-job.yml must be present in workspace template"
    yaml.safe_load(path.read_text(encoding="utf-8"))


def test_bundled_workflows_install_package_in_activated_venv() -> None:
    workflows = WORKSPACE_TEMPLATE / ".github" / "workflows"
    for name in ("find-jobs.yml", "career-hunt.yml", "tailor-job.yml"):
        text = (workflows / name).read_text(encoding="utf-8")
        assert "uv venv --python 3.12" in text
        assert 'uv pip install "job-hunter-kit[browser]"' in text
        assert "uv run --no-project playwright install --with-deps chromium" in text
        assert 'echo "$PWD/.venv/bin" >> "$GITHUB_PATH"' in text
        assert "uv pip install --system" not in text
        assert "job-hunter brief" not in text


def test_company_hunt_handles_empty_results_and_tailor_preserves_state() -> None:
    workflows = WORKSPACE_TEMPLATE / ".github" / "workflows"
    company = (workflows / "career-hunt.yml").read_text(encoding="utf-8")
    tailor = (workflows / "tailor-job.yml").read_text(encoding="utf-8")

    assert "git diff --staged --quiet && exit 0" in company
    assert "URL1: ${{ inputs.url1 }}" in tailor
    assert 'links="${{ inputs.url1 }}"' not in tailor
    assert "outputs/state/jobs.db" in tailor


def test_workspace_template_searxng_config_supports_json() -> None:
    path = WORKSPACE_TEMPLATE / ".github" / "searxng" / "settings.yml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert config["use_default_settings"] is True
    assert "json" in config["search"]["formats"]


def test_generated_job_latex_assets_are_trackable() -> None:
    if not Path(".git").exists() or not Path(".gitignore").exists():
        return

    for path in ("jobs/example/Profile-2025.png", "jobs/example/altacv.cls"):
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", path],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1


def test_workspace_template_claude_md_present() -> None:
    path = WORKSPACE_TEMPLATE / "CLAUDE.md"
    assert path.exists(), "CLAUDE.md must be present in workspace template"


def test_workspace_template_gemini_md_present() -> None:
    path = WORKSPACE_TEMPLATE / "GEMINI.md"
    assert path.exists(), "GEMINI.md must be present in workspace template"


def test_workspace_template_agents_md_present() -> None:
    path = WORKSPACE_TEMPLATE / "AGENTS.md"
    assert path.exists(), "AGENTS.md must be present in workspace template"


def test_no_deleted_workflows_exist_in_dev_workflows() -> None:
    dev_workflows = _REPO_ROOT / ".github" / "workflows"
    deleted = {"ci.yml", "preflight_publish.yml", "sync-upstream.yml", "find-jobs.yml", "tailor-job.yml"}
    existing = {p.name for p in dev_workflows.glob("*.yml")}
    found = deleted & existing
    assert not found, f"Deleted workflow file(s) still exist in .github/workflows/: {found}"


def test_no_deleted_scripts_exist_in_github_scripts() -> None:
    scripts_dir = _REPO_ROOT / ".github" / "scripts"
    deleted = {"merge_upstream.py", "migrate_config.py", "preserve_workflow_schedule.py"}
    existing = {p.name for p in scripts_dir.glob("*.py")} if scripts_dir.exists() else set()
    found = deleted & existing
    assert not found, f"Deleted script file(s) still exist in .github/scripts/: {found}"
