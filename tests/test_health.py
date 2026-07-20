from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from job_hunter.ux.health import doctor, onboarding_checklist, onboarding_status


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
                "filters": {},
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
        "SEARXNG_BASE_URL",
        "ADZUNA_APP_ID",
        "ADZUNA_API_KEY",
        "REED_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    payload = onboarding_status(tmp_path)

    assert payload["onboardingNeeded"] is True
    assert "config/job_hunter.yml:regions" in payload["missing"]
    assert "profile/resume_double_column.tex" in payload["missing"]
    assert "profile/career_context.md" in payload["missing"]
    assert "profile/story_bank.md:final_stories" in payload["missing"]
    assert "api_keys" not in payload["missing"]


def test_doctor_migrates_legacy_exclusions_once(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    path = tmp_path / "config" / "job_hunter.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.pop("filters", None)
    data["exclusions"] = {"companies": ["Acme"], "languages": ["german"]}
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    doctor(tmp_path)
    migrated = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert "exclusions" not in migrated
    assert migrated["filters"]["excluded_companies"] == ["Acme"]


def test_onboarding_status_passes_when_required_user_files_are_ready(tmp_path: Path, monkeypatch) -> None:
    _write_minimal_repo(tmp_path)
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
                "filters": {},
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


def test_onboarding_checklist_reports_undone_items_for_minimal_repo(tmp_path: Path, monkeypatch) -> None:
    _write_minimal_repo(tmp_path)

    checklist = onboarding_checklist(tmp_path)

    by_id = {item["id"]: item for item in checklist["items"]}
    assert by_id["regions"]["done"] is False
    assert by_id["resume"]["done"] is False
    assert by_id["career_context"]["done"] is False
    assert by_id["story_bank"]["done"] is False
    assert by_id["api_key"]["done"] is True  # agent mode never needs an API key
    assert by_id["workflow_schedule"]["done"] is False
    assert by_id["outputs_writable"]["done"] is True
    assert checklist["done_count"] < checklist["total_count"]
    assert str(tmp_path) not in str(checklist)


def test_onboarding_checklist_all_done_when_repo_is_ready(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
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
                "filters": {},
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
        "\\name{Alex Rivera}\n\\tagline{Senior Product Manager}", encoding="utf-8"
    )
    (tmp_path / "profile" / "career_context.md").write_text(
        "## About Me\n\n- Current role: Senior PM at Example Corp\n"
        "- Experience summary: 5 years in B2B SaaS product management\n"
        "- Strongest proof points: Led product from 0 to 10k users\n",
        encoding="utf-8",
    )
    (tmp_path / "profile" / "story_bank.md").write_text(
        "# Story Bank\n\n# Final - refined STAR stories\n\n## PM-01\nStory.\n", encoding="utf-8"
    )
    (tmp_path / ".github" / "workflows" / "find-jobs.yml").write_text(
        "name: Find Jobs\non:\n  schedule:\n    - cron: '0 6 * * *'\n", encoding="utf-8"
    )

    checklist = onboarding_checklist(tmp_path)

    assert checklist["done_count"] == checklist["total_count"]


def test_career_context_filled_accepts_prose(tmp_path: Path) -> None:
    from job_hunter.ux.health import _career_context_filled

    path = tmp_path / "career_context.md"
    path.write_text(
        "I am a backend engineer with six years of experience building payment systems "
        "in Berlin. I want staff-level roles at product companies with strong platform teams.",
        encoding="utf-8",
    )
    assert _career_context_filled(path) is True


def test_career_context_filled_rejects_pristine_template(tmp_path: Path) -> None:
    from job_hunter.ux.health import _career_context_filled
    from job_hunter.workspace.assets import workspace_assets_root

    template = workspace_assets_root().joinpath("profile/career_context.md").read_text(encoding="utf-8")
    path = tmp_path / "career_context.md"
    path.write_text(template, encoding="utf-8")
    assert _career_context_filled(path) is False


def test_career_context_filled_accepts_indented_and_bold_bullets(tmp_path: Path) -> None:
    from job_hunter.ux.health import _career_context_filled

    path = tmp_path / "career_context.md"
    path.write_text(
        "## About Me\n\n"
        "  - **Current role:** Senior Product Manager at Example Corp in Berlin\n"
        "  - **Experience summary:** 5 years in B2B SaaS product management roles\n",
        encoding="utf-8",
    )
    assert _career_context_filled(path) is True


def test_career_context_filled_rejects_tiny_additions(tmp_path: Path) -> None:
    from job_hunter.ux.health import _career_context_filled

    path = tmp_path / "career_context.md"
    path.write_text("# Career Context\n\n- Current role: PM\n", encoding="utf-8")
    assert _career_context_filled(path) is False


def test_onboarding_checklist_requires_api_key_in_llm_api_mode(tmp_path: Path, monkeypatch) -> None:
    _write_minimal_repo(tmp_path)
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump({"mode": "llm-api", "llm": {"default_provider": "anthropic"}}),
        encoding="utf-8",
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    checklist = onboarding_checklist(tmp_path)
    by_id = {item["id"]: item for item in checklist["items"]}
    assert by_id["api_key"]["done"] is False

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    checklist = onboarding_checklist(tmp_path)
    by_id = {item["id"]: item for item in checklist["items"]}
    assert by_id["api_key"]["done"] is True


def test_agent_mode_does_not_require_docker(tmp_path: Path, monkeypatch) -> None:
    _write_minimal_repo(tmp_path)
    monkeypatch.setattr("job_hunter.ux.health.shutil.which", lambda _name: None)

    payload = doctor(tmp_path)
    docker = next(check for check in payload["checks"] if check["name"] == "docker")

    assert docker["ok"] is True
    assert "optional" in docker["detail"].lower()


def test_doctor_rejects_workspace_owned_filter_definitions(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    filters_dir = tmp_path / "config" / "filters"
    filters_dir.mkdir()
    (filters_dir / "excluded_companies.yml").write_text("- Acme\n", encoding="utf-8")

    payload = doctor(tmp_path)
    check = next(check for check in payload["checks"] if check["name"] == "package_owned_filters")

    assert check["ok"] is False
    assert "job-hunter update" in check["fix"]


def test_doctor_reports_playwright_chromium_check(tmp_path: Path, monkeypatch) -> None:
    _write_minimal_repo(tmp_path)
    monkeypatch.setattr("job_hunter.ux.health.is_chromium_installed", lambda: False)

    payload = doctor(tmp_path)
    checks = {check["name"]: check for check in payload["checks"]}

    assert checks["playwright_chromium"]["ok"] is False
    assert "playwright install chromium" in checks["playwright_chromium"]["fix"]


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


def test_doctor_warns_when_skill_files_missing(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)

    payload = doctor(tmp_path)
    checks = {check["name"]: check for check in payload["checks"]}

    assert checks[".claude/skills/job-hunter/SKILL.md"]["ok"] is False
    assert checks[".agents/skills/job-hunter/SKILL.md"]["ok"] is False
    assert "job-hunter update" in checks[".claude/skills/job-hunter/SKILL.md"]["fix"]


def test_doctor_passes_when_skill_files_present(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    for prefix in (".claude", ".agents"):
        skill_dir = tmp_path / prefix / "skills" / "job-hunter"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Job Hunter", encoding="utf-8")

    payload = doctor(tmp_path)
    checks = {check["name"]: check for check in payload["checks"]}

    assert checks[".claude/skills/job-hunter/SKILL.md"]["ok"] is True
    assert checks[".agents/skills/job-hunter/SKILL.md"]["ok"] is True


def test_doctor_warns_when_agent_mode_has_unused_llm_api_config(tmp_path: Path) -> None:
    """llm.models/max_tokens/rate_limits are only read in llm-api mode — flag them as
    dead weight in agent mode, but never fail the check (they're not wrong, just inert)."""
    _write_minimal_repo(tmp_path)
    config_path = tmp_path / "config" / "job_hunter.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["llm"]["models"] = {"scoring": "claude-haiku-4-5-20251001"}
    data["llm"]["max_tokens"] = {"scoring": 1000}
    config_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    payload = doctor(tmp_path)

    assert any("llm.models, llm.max_tokens" in warning for warning in payload["warnings"])


def test_doctor_does_not_warn_about_llm_api_config_in_llm_api_mode(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    config_path = tmp_path / "config" / "job_hunter.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["mode"] = "llm-api"
    data["llm"]["models"] = {"scoring": "claude-haiku-4-5-20251001"}
    config_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    payload = doctor(tmp_path)

    assert not any("llm.models" in warning for warning in payload["warnings"])


def test_doctor_schema_validation_ignores_workspace_schema_copy(tmp_path: Path) -> None:
    """Validation runs against the packaged schema; a stale/bogus workspace copy under
    config/schemas/ must not change the result (a lagging copy used to reject every save)."""
    _write_minimal_repo(tmp_path)
    schema_dir = tmp_path / "config" / "schemas"
    schema_dir.mkdir()
    schema_dir.joinpath("job_hunter.schema.json").write_text(
        '{"type":"object","required":["required_key"]}',
        encoding="utf-8",
    )

    payload = doctor(tmp_path)
    schema = next(check for check in payload["checks"] if check["name"] == "config_schema")

    assert "required_key" not in schema["detail"]
    assert schema["ok"] is False  # the minimal repo config is genuinely stale (removed keys)
    assert "Removed job_hunter.yml key" in schema["detail"]


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


def test_doctor_warns_when_collector_unreachable(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)

    with patch("job_hunter.metrics.collector.collector_health", return_value=None):
        payload = doctor(tmp_path)

    assert any("collector is not running" in w for w in payload["warnings"])


def test_doctor_warns_on_protocol_mismatch(tmp_path: Path) -> None:
    _write_minimal_repo(tmp_path)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"env": {"OTEL_EXPORTER_OTLP_PROTOCOL": "grpc"}}),
        encoding="utf-8",
    )

    with patch("job_hunter.metrics.collector.collector_health", return_value={"workspace": str(tmp_path)}):
        payload = doctor(tmp_path)

    assert any("OTEL_EXPORTER_OTLP_PROTOCOL=grpc" in w for w in payload["warnings"])


def test_doctor_warns_when_hooks_wired_but_no_otel_events_arrived(tmp_path: Path) -> None:
    from job_hunter.metrics.telemetry import begin_run

    _write_minimal_repo(tmp_path)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        _hooks_json("job-hunter internal telemetry-hook --backend claude-code --event prompt"),
        encoding="utf-8",
    )
    begin_run(tmp_path / "outputs" / "state" / "metrics.db", backend="claude-code", session_id="s", mode="batch")

    with patch("job_hunter.metrics.collector.collector_health", return_value={"workspace": str(tmp_path)}):
        payload = doctor(tmp_path)

    assert any("no OTel token events" in w for w in payload["warnings"])


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


def test_resume_language_checks_verifies_each_resumes_entry_file(tmp_path: Path) -> None:
    from job_hunter.ux.health import _resume_language_checks

    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "resume.tex").write_text("x", encoding="utf-8")
    config = {
        "profile": {
            "resumes": {
                "en": {"resume_tex": "profile/resume.tex", "base": True},
                "de": {"resume_tex": "profile/resume_de.tex"},  # missing on disk
            }
        }
    }

    checks = _resume_language_checks(tmp_path, config)
    by_name = {c["name"]: c for c in checks}

    assert by_name["resumes.en"]["ok"] is True
    assert by_name["resumes.de"]["ok"] is False
    assert "resume_de.tex" in by_name["resumes.de"]["detail"]


def test_resume_language_checks_empty_for_shorthand_profile(tmp_path: Path) -> None:
    from job_hunter.ux.health import _resume_language_checks

    assert _resume_language_checks(tmp_path, {"profile": {"resume_tex": "profile/resume.tex"}}) == []


def test_resume_language_coverage_warnings_flags_uncovered_hunt_languages() -> None:
    from job_hunter.ux.health import _resume_language_coverage_warnings

    config = {
        "profile": {"resumes": {"en": {"resume_tex": "profile/resume.tex", "base": True}}},
        "filters": {"hunt_languages": ["en", "de", "fr"]},
    }

    warnings = _resume_language_coverage_warnings(config)

    assert len(warnings) == 2
    assert any("de jobs will be translated from your en base" in w for w in warnings)
    assert any("fr jobs will be translated from your en base" in w for w in warnings)
    assert not any(w.startswith("en ") for w in warnings)  # base language itself is never flagged


def test_resume_language_coverage_warnings_empty_when_fully_covered() -> None:
    from job_hunter.ux.health import _resume_language_coverage_warnings

    config = {
        "profile": {
            "resumes": {
                "en": {"resume_tex": "profile/resume.tex", "base": True},
                "de": {"resume_tex": "profile/resume_de.tex"},
            }
        },
        "filters": {"hunt_languages": ["en", "de"]},
    }

    assert _resume_language_coverage_warnings(config) == []


def test_doctor_surfaces_resume_language_warnings_without_failing(tmp_path: Path) -> None:
    from job_hunter.ux.health import doctor

    _write_minimal_repo(tmp_path)
    config_path = tmp_path / "config" / "job_hunter.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["filters"] = {"hunt_languages": ["en", "de"]}
    config_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    payload = doctor(tmp_path)

    assert any("de jobs will be translated" in w for w in payload["warnings"])
