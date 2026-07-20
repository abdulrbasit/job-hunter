from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from job_hunter.config.schema import check
from job_hunter.filters import canonicalize_filter_config

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
WORKSPACE_TEMPLATE = ROOT / "job_hunter" / "templates" / "workspace"


def test_all_config_files_are_valid_yaml() -> None:
    for path in (ROOT / "config").glob("*.yml"):
        yaml.safe_load(path.read_text(encoding="utf-8"))


def test_all_dev_workflow_files_are_valid_yaml() -> None:
    for path in WORKFLOWS.glob("*.yml"):
        yaml.safe_load(path.read_text(encoding="utf-8"))


def test_all_workspace_template_workflow_files_are_valid_yaml() -> None:
    for path in (WORKSPACE_TEMPLATE / ".github" / "workflows").glob("*.yml"):
        yaml.safe_load(path.read_text(encoding="utf-8"))


def test_single_config_validates_against_schema() -> None:
    try:
        import jsonschema
    except ImportError:
        import pytest

        pytest.skip("jsonschema not installed")

    schema = json.loads((ROOT / "config" / "schemas" / "job_hunter.schema.json").read_text(encoding="utf-8"))
    config = canonicalize_filter_config(
        yaml.safe_load((ROOT / "config" / "job_hunter.yml").read_text(encoding="utf-8"))
    )
    jsonschema.validate(instance=config, schema=schema)


def test_batch_size_is_required_by_schema() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = json.loads((ROOT / "config" / "schemas" / "job_hunter.schema.json").read_text(encoding="utf-8"))
    config = canonicalize_filter_config(
        yaml.safe_load((ROOT / "config" / "job_hunter.yml").read_text(encoding="utf-8"))
    )
    stale = dict(config)
    stale["scoring"] = dict(config["scoring"])
    stale["scoring"].pop("batch_size")

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=stale, schema=schema)


def test_config_check_validates_required_keys() -> None:
    assert check() == 0


@pytest.mark.parametrize(
    "data, expected_key",
    [
        ({"about_me": "stale"}, "about_me"),
        ({"sources": []}, "sources"),
        ({"secrets": {}}, "secrets"),
        ({"tailoring": {}}, "tailoring"),
        ({"cover_letter": {}}, "cover_letter"),
        ({"exclusions": {"senior_flags": []}}, "exclusions.senior_flags"),
        ({"exclusions": {"stale_indicators": []}}, "exclusions.stale_indicators"),
        ({"exclusions": {"url_patterns": []}}, "exclusions.url_patterns"),
        ({"exclusions": {"language_indicators": []}}, "exclusions.language_indicators"),
        ({"filters": {"excluded_languages": ["de"]}}, "filters.excluded_languages"),
        ({"scoring": {"prompt_context": "stale"}}, "scoring.prompt_context"),
        ({"linkedin": {"enabled": True, "tone": "casual"}}, "linkedin.tone"),
    ],
)
def test_removed_config_keys_are_rejected(data: dict, expected_key: str) -> None:
    from job_hunter.config.removed_keys import reject_removed_user_config

    with pytest.raises(ValueError, match=re.escape(expected_key)) as exc_info:
        reject_removed_user_config(data)

    # Task 3: error message must show migration guidance, not just name the key.
    assert any(
        guidance in str(exc_info.value)
        for guidance in ("v1 compact config shape", "job-hunter doctor", "filters.hunt_languages")
    )


def test_removed_config_keys_accepts_current_shape() -> None:
    from job_hunter.config.removed_keys import reject_removed_user_config

    reject_removed_user_config(
        {
            "mode": "agent",
            "filters": {},
            "scoring": {"min_fit_score": 70, "batch_size": 15},
            "linkedin": {"enabled": False},
        }
    )


def test_schema_files_are_valid_json() -> None:
    schemas = list((ROOT / "config" / "schemas").glob("*.schema.json"))
    assert schemas, "No schema files found in config/schemas/"
    for path in schemas:
        json.loads(path.read_text(encoding="utf-8"))


def test_release_workflow_publishes_current_release_commit() -> None:
    workflow = yaml.safe_load((WORKFLOWS / "release.yml").read_text(encoding="utf-8"))
    # PyYAML parses `on:` as boolean True, not the string "on"
    triggers = workflow.get(True, {}) or {}
    assert "workflow_dispatch" in triggers, "release.yml must have workflow_dispatch trigger"
    assert set(triggers) == {"workflow_dispatch"}

    jobs = workflow["jobs"]
    assert set(jobs) == {"verify", "build-installers", "release"}
    text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    assert "git tag" in text
    assert "git push origin" in text
    assert "git commit" not in text
    assert "git switch" not in text
    assert "gh pr create" not in text
    assert "pull-requests: write" not in text


def test_development_checks_exposes_required_aggregate_job() -> None:
    workflow = yaml.safe_load((WORKFLOWS / "development-checks.yml").read_text(encoding="utf-8"))
    triggers = workflow.get(True, {}) or {}
    jobs = workflow["jobs"]
    aggregate = jobs["development-checks"]

    assert triggers["push"]["branches"] == ["main"]
    assert triggers["pull_request"]["branches"] == ["main"]
    assert aggregate["name"] == "development-checks"
    assert set(aggregate["needs"]) == {"lint", "tests", "validate-config", "build", "security", "sbom"}


def test_workspace_template_find_jobs_exports_job_board_secrets() -> None:
    workflow = yaml.safe_load(
        (WORKSPACE_TEMPLATE / ".github" / "workflows" / "find-jobs.yml").read_text(encoding="utf-8")
    )
    env = workflow["jobs"]["find-jobs"]["env"]

    assert env["ANTHROPIC_API_KEY"] == "${{ secrets.ANTHROPIC_API_KEY }}"
    assert env["OPENAI_API_KEY"] == "${{ secrets.OPENAI_API_KEY }}"
    assert env["GOOGLE_API_KEY"] == "${{ secrets.GOOGLE_API_KEY }}"
    assert env["ADZUNA_APP_ID"] == "${{ secrets.ADZUNA_APP_ID }}"
    assert env["ADZUNA_API_KEY"] == "${{ secrets.ADZUNA_API_KEY }}"
    assert env["REED_API_KEY"] == "${{ secrets.REED_API_KEY }}"
    assert env["SEARXNG_BASE_URL"]
    # Removed paid/free-tier sources must not creep back into the template.
    for removed in (
        "BRAVE_API_KEY",
        "TAVILY_API_KEY",
        "EXA_API_KEY",
        "RAPIDAPI_KEY",
        "JOOBLE_API_KEY",
        "FIRECRAWL_API_KEY",
    ):
        assert removed not in env


def test_python_import_package_is_job_hunter() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'job-hunter = "job_hunter.cli:app"' in pyproject
    assert 'include = ["job_hunter", "job_hunter.*"]' in pyproject


def test_no_legacy_module_commands_in_tracked_files() -> None:
    tracked = [ROOT / "pyproject.toml"]
    # Also check workspace template workflows
    for wf in (WORKSPACE_TEMPLATE / ".github" / "workflows").glob("*.yml"):
        tracked.append(wf)
    old_module = "".join(("s", "r", "c"))
    old_module_command = f"python -m {old_module}."
    for path in tracked:
        text = path.read_text(encoding="utf-8")
        assert old_module_command not in text, f"{path}: stale legacy module command"
        assert "job_hunter.cli:main" not in text, f"{path}: stale CLI entry point"


def test_deterministic_scraping_functions_exist() -> None:
    orchestrator = (ROOT / "job_hunter" / "sources" / "orchestrator.py").read_text(encoding="utf-8")
    boards = (ROOT / "job_hunter" / "sources" / "boards" / "registry.py").read_text(encoding="utf-8")
    search = (ROOT / "job_hunter" / "sources" / "search" / "__init__.py").read_text(encoding="utf-8")
    for symbol in (
        "JobSpySource",
        "HimalayasSource",
        "ArbeitsagenturSource",
        "AdzunaSource",
        "ReedSource",
    ):
        assert symbol in boards, f"{symbol} missing from source registry"
    for symbol in ("discover_ats_jobs_by_search",):
        assert symbol in orchestrator, f"{symbol} missing from active orchestrator"
    for symbol in ("search_web",):
        assert symbol in search, f"{symbol} missing from sources.search"


def test_config_directory_has_only_expected_files() -> None:
    """config/career_pages.yml is retired — the only editable config file is job_hunter.yml."""
    config_dir = ROOT / "config"
    yml_files = {p.name for p in config_dir.glob("*.yml")}
    expected = {"job_hunter.yml"}
    unexpected = yml_files - expected
    assert not unexpected, f"Unexpected files in config/: {unexpected}"


def test_no_workflows_reference_deleted_scripts() -> None:
    stale_patterns = (
        "merge_upstream.py",
        "migrate_config.py",
        "preserve_workflow_schedule.py",
        "merge_tracker",
    )
    all_workflows = list(WORKFLOWS.glob("*.yml"))
    all_workflows += list((WORKSPACE_TEMPLATE / ".github" / "workflows").glob("*.yml"))
    for path in all_workflows:
        text = path.read_text(encoding="utf-8")
        for pattern in stale_patterns:
            assert pattern not in text, f"{path.name}: references deleted artifact '{pattern}'"


def test_runtime_code_does_not_reference_deleted_config_or_state_files() -> None:
    stale_patterns = (
        "config/search_config.yml",
        "config/api_config.yml",
        "processed_jobs.yml",
        "discovery_cache.yml",
    )
    offenders: list[str] = []
    for path in (ROOT / "job_hunter").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in stale_patterns:
            if pattern in text:
                offenders.append(f"{path.relative_to(ROOT)}: {pattern}")

    assert offenders == []


def test_workflows_do_not_use_broad_git_add() -> None:
    all_workflows = list(WORKFLOWS.glob("*.yml"))
    all_workflows += list((WORKSPACE_TEMPLATE / ".github" / "workflows").glob("*.yml"))
    for path in all_workflows:
        content = path.read_text(encoding="utf-8")
        assert "git add -A" not in content, f"{path.name}: uses broad git add -A"
        assert "git add ." not in content, f"{path.name}: uses broad git add ."
