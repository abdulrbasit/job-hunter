from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from job_hunter.ux.health import doctor, onboarding_status


@pytest.fixture(autouse=True)
def _isolated_codex_home(tmp_path: Path, monkeypatch) -> None:
    """Default to a CODEX_HOME that doesn't exist, so doctor() never reads this machine's real ~/.codex."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "default-codex-home"))


def _write_minimal_repo(root: Path) -> None:
    (root / "config").mkdir()
    (root / "profile").mkdir()
    (root / "outputs").mkdir()
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump(
            {
                "mode": "agent",
                "profile": {
                    "resume_tex": "profile/resume_double_column.tex",
                    "story_bank": "profile/story_bank.md",
                },
                "job_titles": [],
                "regions": {},
                "exclusions": {},
                "sources": {},
                "scoring": {"min_fit_score": 70},
                "linkedin": {"enabled": False},
                "llm": {"default_provider": "anthropic"},
                "secrets": {},
            }
        ),
        encoding="utf-8",
    )
    (root / "profile" / "story_bank.md").write_text(
        "# Story Bank\n\n# Final - refined STAR stories\n<!-- none -->\n",
        encoding="utf-8",
    )
    (root / ".github" / "workflows" / "find-jobs.yml").write_text(
        "name: Find Jobs\non:\n  workflow_dispatch:\n",
        encoding="utf-8",
    )


def test_onboarding_status_reports_missing_items(tmp_path: Path, monkeypatch) -> None:
    _write_minimal_repo(tmp_path)
    for key in (
        "BRAVE_API_KEY",
        "TAVILY_API_KEY",
        "EXA_API_KEY",
        "SEARXNG_BASE_URL",
        "ADZUNA_APP_ID",
        "ADZUNA_API_KEY",
        "REED_API_KEY",
        "RAPIDAPI_KEY",
        "JOOBLE_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    payload = onboarding_status(tmp_path)

    assert payload["onboardingNeeded"] is True
    assert "config/job_hunter.yml:regions" in payload["missing"]
    assert "profile/resume_double_column.tex" in payload["missing"]
    assert "profile/career_context.md" in payload["missing"]
    assert "profile/story_bank.md:final_stories" in payload["missing"]
    assert "api_keys" not in payload["missing"]


def test_onboarding_status_passes_when_required_user_files_are_ready(tmp_path: Path, monkeypatch) -> None:
    _write_minimal_repo(tmp_path)
    monkeypatch.setenv("BRAVE_API_KEY", "test")
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump(
            {
                "mode": "agent",
                "profile": {
                    "resume_tex": "profile/resume_double_column.tex",
                    "story_bank": "profile/story_bank.md",
                },
                "job_titles": ["Product Manager"],
                "regions": {"berlin": {"enabled": True, "location": "Berlin", "country": "DE"}},
                "exclusions": {},
                "sources": {},
                "scoring": {"min_fit_score": 70},
                "linkedin": {"enabled": False},
                "llm": {"default_provider": "anthropic"},
                "secrets": {},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "profile" / "resume_double_column.tex").write_text(
        "\\name{Alex Rivera}\n\\tagline{Senior Product Manager}",
        encoding="utf-8",
    )
    (tmp_path / "profile" / "career_context.md").write_text(
        "## About Me\n\n- Current role: Senior PM at Example Corp\n"
        "- Experience summary: 5 years in B2B SaaS product management\n"
        "- Strongest proof points: Led product from 0 to 10k users\n",
        encoding="utf-8",
    )
    (tmp_path / "profile" / "story_bank.md").write_text(
        "# Story Bank\n\n# Final - refined STAR stories\n\n## PM-01\nStory.\n",
        encoding="utf-8",
    )

    payload = onboarding_status(tmp_path)

    assert payload["onboardingNeeded"] is False
    assert payload["missing"] == []


def test_agent_mode_does_not_require_docker(tmp_path: Path, monkeypatch) -> None:
    _write_minimal_repo(tmp_path)
    monkeypatch.setattr("job_hunter.ux.health.shutil.which", lambda _name: None)

    payload = doctor(tmp_path)
    docker = next(check for check in payload["checks"] if check["name"] == "docker")

    assert docker["ok"] is True
    assert "optional" in docker["detail"].lower()


def test_llm_api_mode_requires_docker_and_provider_sdk(tmp_path: Path, monkeypatch) -> None:
    _write_minimal_repo(tmp_path)
    config = yaml.safe_load((tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8"))
    config["mode"] = "llm-api"
    (tmp_path / "config" / "job_hunter.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr("job_hunter.ux.health.shutil.which", lambda _name: None)
    monkeypatch.setattr("job_hunter.ux.health._module_available", lambda name: name == "job_hunter")

    payload = doctor(tmp_path)
    checks = {check["name"]: check for check in payload["checks"]}

    assert checks["docker"]["ok"] is False
    assert checks["llm_provider:anthropic"]["ok"] is False
    assert "Reinstall job-hunter-kit" in checks["llm_provider:anthropic"]["fix"]


def test_doctor_runs_json_schema_validation(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    schema_dir = tmp_path / "config" / "schemas"
    schema_dir.mkdir()
    schema_dir.joinpath("job_hunter.schema.json").write_text(
        '{"type":"object","required":["required_key"]}',
        encoding="utf-8",
    )

    payload = doctor(tmp_path)
    schema = next(check for check in payload["checks"] if check["name"] == "config_schema")

    assert schema["ok"] is False
    assert "required_key" in schema["detail"]


def _hooks_json(command: str) -> str:
    import json

    return json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": command}]}]}})


def test_telemetry_hook_check_fails_when_hooks_missing(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)

    payload = doctor(tmp_path)
    checks = {check["name"]: check for check in payload["checks"]}

    assert checks["telemetry_hooks_claude"]["ok"] is False
    assert checks["telemetry_hooks_codex"]["ok"] is False
    assert "job-hunter update" in checks["telemetry_hooks_claude"]["fix"]


def test_telemetry_hook_check_passes_when_wired(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        _hooks_json("job-hunter internal telemetry-hook --backend claude-code --event prompt"),
        encoding="utf-8",
    )
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "hooks.json").write_text(
        _hooks_json("job-hunter internal telemetry-hook --backend codex --event prompt"),
        encoding="utf-8",
    )

    payload = doctor(tmp_path)
    checks = {check["name"]: check for check in payload["checks"]}

    assert checks["telemetry_hooks_claude"]["ok"] is True
    assert checks["telemetry_hooks_codex"]["ok"] is True


def test_telemetry_hook_check_fails_on_wrong_backend_command(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "hooks.json").write_text(
        _hooks_json("job-hunter internal telemetry-hook --backend claude-code --event prompt"),
        encoding="utf-8",
    )

    payload = doctor(tmp_path)
    checks = {check["name"]: check for check in payload["checks"]}

    assert checks["telemetry_hooks_codex"]["ok"] is False


def test_codex_otel_check_skipped_when_codex_home_absent(tmp_path: Path, monkeypatch) -> None:
    _write_minimal_repo(tmp_path)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "no-such-codex-home"))

    payload = doctor(tmp_path)
    names = {check["name"] for check in payload["checks"]}

    assert "telemetry_codex_otel" not in names


def test_codex_otel_check_fails_when_endpoint_not_job_hunter_collector(tmp_path: Path, monkeypatch) -> None:
    _write_minimal_repo(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        '[otel]\nexporter = { otlp-http = { endpoint = "https://example.com/v1/logs" } }\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    payload = doctor(tmp_path)
    checks = {check["name"]: check for check in payload["checks"]}

    assert checks["telemetry_codex_otel"]["ok"] is False


def test_codex_otel_check_passes_when_pointed_at_job_hunter_collector(tmp_path: Path, monkeypatch) -> None:
    _write_minimal_repo(tmp_path)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        '[otel]\nexporter = { otlp-http = { endpoint = "http://127.0.0.1:4318/v1/logs", protocol = "json" } }\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    payload = doctor(tmp_path)
    checks = {check["name"]: check for check in payload["checks"]}

    assert checks["telemetry_codex_otel"]["ok"] is True
