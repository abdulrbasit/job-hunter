import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_llm_sdks_ship_with_standard_install() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    optional = project["project"]["optional-dependencies"]

    assert "anthropic>=0.50.0" in dependencies
    assert "openai>=1.68.0" in dependencies
    assert "google-genai>=1.0.0" in dependencies
    assert "llm" not in optional
    assert optional["all"] == ["job-hunter-kit[browser,secrets]"]


def test_declared_template_package_data_globs_resolve_to_real_files() -> None:
    """Every job_hunter.templates package-data glob must match at least one file on disk.

    Catches stale/typo'd entries left behind by a rename, so package-data drift is caught
    at test time instead of silently shipping an incomplete wheel.
    """
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    globs = project["tool"]["setuptools"]["package-data"]["job_hunter.templates"]
    templates_root = ROOT / "job_hunter" / "templates"

    empty = [g for g in globs if not list(templates_root.glob(g))]
    assert empty == [], f"package-data glob(s) matched no files: {empty}"


def test_every_user_facing_skill_has_a_package_data_glob() -> None:
    """Guards the caveman-skill bug: a skill dir can exist in the workspace template and still
    be silently dropped from real wheel installs if pyproject.toml's package-data list forgets it.
    """
    from job_hunter.workspace.assets import _DEV_SKILL_DIRS

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    globs = set(project["tool"]["setuptools"]["package-data"]["job_hunter.templates"])

    skills_dir = ROOT / "job_hunter" / "templates" / "workspace" / ".claude" / "skills"
    user_facing = {p.name for p in skills_dir.iterdir() if p.is_dir() and p.name not in _DEV_SKILL_DIRS}

    missing = [name for name in user_facing if f"workspace/.claude/skills/{name}/**/*" not in globs]
    assert missing == [], f"skill(s) present in template but missing from package-data: {missing}"


def test_list_module_imports_script_runs_and_finds_known_edge() -> None:
    """Smoke test for scripts/list_module_imports.py — a refactor-support helper, not shipped code."""
    result = subprocess.run(
        [sys.executable, "scripts/list_module_imports.py", "--target", "job_hunter.pipeline"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "job_hunter.tracker -> job_hunter.pipeline.enrichment" in result.stdout
