"""Tests for ux/web/api.py::DashAPI — the pywebview JS-callable dashboard API."""

from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from job_hunter.metrics.store import record_run
from job_hunter.pipeline.stages.readme import TABLE_END, TABLE_START
from job_hunter.tracking.applications import upsert_application_from_job
from job_hunter.tracking.repository import insert_candidate_urls, insert_jobs, mark_urls_processed
from job_hunter.ux.web import api as api_module
from job_hunter.ux.web.api import DashAPI

_WEB_DIR = Path(__file__).parents[1] / "job_hunter" / "ux" / "web"


def _dashboard_source() -> str:
    """dashboard.html + dashboard.css + dashboard.js concatenated.

    Phase 4 split the single-file dashboard into a shell/CSS/JS trio; tests
    that grep for specific markup/JS content read the concatenation so a
    plain substring search still finds content regardless of which file it
    now lives in.
    """
    return "".join(
        (_WEB_DIR / name).read_text(encoding="utf-8") for name in ("dashboard.html", "dashboard.css", "dashboard.js")
    )


def _write_job(root: Path, slug: str = "2026-06-12_acme_pm") -> Path:
    job_dir = root / "outputs" / "jobs" / slug
    job_dir.mkdir(parents=True)
    (job_dir / "meta.json").write_text(
        json.dumps(
            {
                "date": "2026-06-12",
                "company": "Acme",
                "title": "Product Manager",
                "location": "Berlin",
                "url": "https://x",
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "score.yml").write_text(yaml.safe_dump({"score": 82, "decision": "APPLY"}), encoding="utf-8")
    return job_dir


def test_seen_milestones_round_trip(tmp_path: Path) -> None:
    api = DashAPI(tmp_path)
    assert api.get_seen_milestones() == {"ok": True, "seen": []}

    result = api.mark_milestone_seen("app_1")

    assert result == {"ok": True, "seen": ["app_1"]}
    assert api.get_seen_milestones() == {"ok": True, "seen": ["app_1"]}


def test_mark_milestone_seen_is_idempotent_and_sorted(tmp_path: Path) -> None:
    api = DashAPI(tmp_path)
    api.mark_milestone_seen("app_5")
    api.mark_milestone_seen("app_1")
    api.mark_milestone_seen("app_1")

    assert api.get_seen_milestones() == {"ok": True, "seen": ["app_1", "app_5"]}


def test_get_application_streak_returns_ok_shape_for_empty_workspace(tmp_path: Path) -> None:
    payload = DashAPI(tmp_path).get_application_streak()

    assert payload == {"ok": True, "current_streak": 0, "longest_streak": 0, "active_days": 0}


def test_get_applications_returns_json_serializable_dicts(tmp_path: Path) -> None:
    _write_job(tmp_path)
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)

    payload = DashAPI(tmp_path).get_applications()
    apps = payload["items"]

    assert isinstance(apps, list)
    assert payload["total"] == 1
    assert apps[0]["slug"] == "2026-06-12_acme_pm"
    assert apps[0]["date"] == "2026-06-12"
    assert apps[0]["location"] == "Berlin"
    json.dumps(apps)  # must round-trip through JSON for the JS bridge


def test_get_applications_pages_large_result_set_without_heavy_text(tmp_path: Path) -> None:
    insert_jobs(
        tmp_path,
        [
            {
                "url": f"https://example.com/{index}",
                "title": f"Product Manager {index}",
                "company": "Acme",
                "snippet": "x" * 10_000,
            }
            for index in range(5000)
        ],
    )
    with sqlite3.connect(tmp_path / "outputs" / "state" / "jobs.db") as conn:
        conn.execute("UPDATE jobs SET status='tailored', slug='job-' || id")

    payload = DashAPI(tmp_path).get_applications(page=2, page_size=50)

    assert payload["total"] == 5000
    assert payload["page"] == 2
    assert payload["pages"] == 100
    assert len(payload["items"]) == 50
    assert "jd_text" not in payload["items"][0]
    assert "snippet" not in payload["items"][0]


def test_list_page_size_is_capped_and_sort_column_is_whitelisted(tmp_path: Path) -> None:
    payload = DashAPI(tmp_path).get_applications(page_size=999, sort="score; DROP TABLE jobs")

    assert payload["page_size"] == 200
    assert payload["items"] == []


def test_dashboard_table_renders_application_location_and_date() -> None:
    html = _dashboard_source()

    assert 'data-col="location"' in html
    assert "app.location" in html
    assert "app.date" in html
    assert "debounce(() => { appPage = 1; loadApplications(); })" in html
    assert "get_applications(appPage, 50" in html
    assert "get_unprocessed(" in html


def test_dashboard_has_safe_shared_states_onboarding_and_keyboard_focus() -> None:
    html = _dashboard_source()

    assert 'id="onboarding-banner"' in html
    assert "function loadingHtml(" in html
    assert "function emptyHtml(" in html
    assert "function errorHtml(" in html
    assert ":focus-visible" in html
    assert "${e}" not in html


def test_get_started_is_a_top_level_view_not_a_settings_tab() -> None:
    html = _dashboard_source()

    assert 'data-view="get-started"' in html
    assert 'id="view-get-started"' in html
    assert 'id="gs-checklist"' in html
    assert 'data-settings-tab="get-started"' not in html
    assert 'id="settings-panel-get-started"' not in html
    # First run lands on Get Started; optional items never force it.
    assert "setupIncomplete" in html
    assert "workflow_schedule" in html


def test_dashboard_has_sync_button_and_auto_sync_on_open() -> None:
    html = _dashboard_source()

    assert 'id="sync-btn"' in html
    assert "start_sync" in html
    assert "get_sync_status" in html
    assert "runSync({ silent: true })" in html


def test_get_onboarding_returns_count_without_local_paths(tmp_path: Path) -> None:
    payload = DashAPI(tmp_path).get_onboarding()

    assert payload["ok"] is True
    assert payload["onboardingNeeded"] is True
    assert payload["missing_count"] > 0
    assert str(tmp_path) not in str(payload)


def test_get_onboarding_checklist_returns_itemized_list_without_local_paths(tmp_path: Path) -> None:
    payload = DashAPI(tmp_path).get_onboarding_checklist()

    assert payload["ok"] is True
    assert payload["total_count"] > 0
    assert payload["done_count"] < payload["total_count"]
    ids = {item["id"] for item in payload["items"]}
    assert {"regions", "resume", "career_context", "story_bank", "api_key", "workflow_schedule"} <= ids
    assert str(tmp_path) not in str(payload)


def test_get_bootstrap_reports_readiness_and_checklist(tmp_path: Path) -> None:
    payload = DashAPI(tmp_path).get_bootstrap()

    assert payload["ok"] is True
    assert payload["data"]["readiness"]["ready"] is False
    assert "checklist" in payload["data"]
    assert payload["data"]["config_revision"]
    assert str(tmp_path) not in json.dumps(payload)


def test_save_onboarding_preferences_updates_config(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump(
            {
                "mode": "agent",
                "job_titles": [],
                "regions": {"primary": {"enabled": True, "country": "DE", "location": "Your City"}},
                "exclusions": {},
                "scoring": {"min_fit_score": 70, "batch_size": 15},
                "llm": {"default_provider": "anthropic"},
            }
        ),
        encoding="utf-8",
    )
    api = DashAPI(tmp_path)
    revision = api.get_bootstrap()["data"]["config_revision"]

    result = api.save_onboarding_preferences(
        {
            "career_stage": "early_career",
            "job_titles": ["Associate PM"],
            "country": "de",
            "location": "Munich",
            "search_lang": "en",
        },
        revision,
    )

    assert result["ok"] is True
    on_disk = yaml.safe_load((tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8"))
    assert on_disk["career_stage"] == "early_career"
    assert on_disk["job_titles"] == ["Associate PM"]
    assert on_disk["regions"]["primary"]["location"] == "Munich"


def test_get_onboarding_prompt_returns_copyable_text(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump(
            {
                "mode": "agent",
                "job_titles": ["Product Manager"],
                "regions": {},
                "exclusions": {},
                "scoring": {"min_fit_score": 70, "batch_size": 15},
                "llm": {"default_provider": "anthropic"},
            }
        ),
        encoding="utf-8",
    )

    result = DashAPI(tmp_path).get_onboarding_prompt()

    assert result["ok"] is True
    assert "CAREER_CONTEXT" in result["data"]["prompt"]


def test_import_onboarding_bundle_writes_profile_files(tmp_path: Path) -> None:
    (tmp_path / "profile").mkdir(parents=True)
    bundle = (
        "<<<CAREER_CONTEXT>>>\ntargeting notes\n<<<END_CAREER_CONTEXT>>>\n"
        "<<<STORY_BANK>>>\nstory content\n<<<END_STORY_BANK>>>\n"
        "<<<BASE_RESUME>>>\nresume content\n<<<END_BASE_RESUME>>>\n"
    )

    result = DashAPI(tmp_path).import_onboarding_bundle(bundle)

    assert result["ok"] is True
    assert (tmp_path / "profile" / "career_context.md").read_text(encoding="utf-8") == "targeting notes"
    assert (tmp_path / "profile" / "story_bank.md").read_text(encoding="utf-8") == "story content"
    assert (tmp_path / "profile" / "resume_source.md").read_text(encoding="utf-8") == "resume content"


def test_import_onboarding_bundle_reports_parse_errors_without_writing(tmp_path: Path) -> None:
    (tmp_path / "profile").mkdir(parents=True)

    result = DashAPI(tmp_path).import_onboarding_bundle("not a valid bundle")

    assert result["ok"] is False
    assert result["errors"]
    assert not (tmp_path / "profile" / "career_context.md").exists()


def test_get_api_key_status_reports_not_configured(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump({"llm": {"default_provider": "anthropic"}}), encoding="utf-8"
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    payload = DashAPI(tmp_path).get_api_key_status()

    assert payload == {
        "ok": True,
        "provider": "anthropic",
        "env_var": "ANTHROPIC_API_KEY",
        "required": True,
        "configured": False,
    }


def test_get_api_key_status_reports_configured_from_env(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump({"llm": {"default_provider": "anthropic"}}), encoding="utf-8"
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    payload = DashAPI(tmp_path).get_api_key_status()

    assert payload["configured"] is True


def test_save_api_key_rejects_empty_value(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump({"llm": {"default_provider": "anthropic"}}), encoding="utf-8"
    )

    payload = DashAPI(tmp_path).save_api_key("   ")

    assert payload["ok"] is False


def test_save_api_key_stores_via_keyring(tmp_path: Path, monkeypatch) -> None:
    from unittest.mock import MagicMock

    fake_keyring = MagicMock()
    monkeypatch.setitem(__import__("sys").modules, "keyring", fake_keyring)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump({"llm": {"default_provider": "anthropic"}}), encoding="utf-8"
    )

    payload = DashAPI(tmp_path).save_api_key("sk-real-key")

    assert payload == {"ok": True, "provider": "anthropic", "env_var": "ANTHROPIC_API_KEY"}
    fake_keyring.set_password.assert_called_once_with("job-hunter", "ANTHROPIC_API_KEY", "sk-real-key")


def test_get_github_actions_guide_reports_required_secret_and_schedule_state(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump({"llm": {"default_provider": "anthropic"}}), encoding="utf-8"
    )
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "find-jobs.yml").write_text(
        'on:\n  # schedule:\n  #   - cron: "0 18 * * 0-4"\n', encoding="utf-8"
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    payload = DashAPI(tmp_path).get_github_actions_guide()

    assert payload["ok"] is True
    assert payload["schedule_enabled"] is False
    assert payload["required_secret"] == {"name": "ANTHROPIC_API_KEY", "configured": True}
    assert "sk-test" not in json.dumps(payload)  # secret value must never cross the JS bridge
    assert "ANTHROPIC_API_KEY" not in payload["optional_secret_names"]
    assert "cron" in payload["yaml_diff"]


def test_get_github_actions_guide_detects_enabled_schedule(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump({"llm": {"default_provider": "anthropic"}}), encoding="utf-8"
    )
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "find-jobs.yml").write_text(
        'on:\n  schedule:\n    - cron: "0 18 * * 0-4"\n', encoding="utf-8"
    )

    payload = DashAPI(tmp_path).get_github_actions_guide()

    assert payload["schedule_enabled"] is True


def test_copy_github_actions_secret_writes_to_clipboard_without_returning_it(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump({"llm": {"default_provider": "anthropic"}}), encoding="utf-8"
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    copied = []
    monkeypatch.setattr("job_hunter.ux.web.api._copy_to_clipboard", lambda value: copied.append(value))

    result = DashAPI(tmp_path).copy_github_actions_secret()

    assert result == {"ok": True}
    assert copied == ["sk-test"]


def test_copy_github_actions_secret_reports_error_when_not_configured(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump({"llm": {"default_provider": "ollama"}}), encoding="utf-8"
    )

    result = DashAPI(tmp_path).copy_github_actions_secret()

    assert result["ok"] is False


def test_get_job_detail_reads_from_db(tmp_path: Path) -> None:
    job_dir = _write_job(tmp_path)
    (job_dir / "cover_letter.md").write_text("# Cover letter", encoding="utf-8")
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)

    detail = DashAPI(tmp_path).get_job_detail("2026-06-12_acme_pm")

    assert detail["slug"] == "2026-06-12_acme_pm"
    assert detail["meta"]["company"] == "Acme"
    assert detail["score"]["score"] == 82
    assert [artifact["key"] for artifact in detail["artifacts"]] == [
        "resume",
        "cover_letter",
        "evaluation",
        "research",
        "outreach",
        "interview",
    ]
    assert next(a for a in detail["artifacts"] if a["key"] == "cover_letter")["available"] is True
    assert next(a for a in detail["artifacts"] if a["key"] == "resume")["available"] is False


def test_get_job_detail_falls_back_to_job_folder_when_no_db_record(tmp_path: Path) -> None:
    _write_job(tmp_path, slug="unregistered")

    detail = DashAPI(tmp_path).get_job_detail("unregistered")

    assert detail["slug"] == "unregistered"
    assert detail["meta"]["company"] == "Acme"
    assert len(detail["artifacts"]) == 6


def test_get_artifact_reads_text_and_pdf_lazily(tmp_path: Path) -> None:
    job_dir = _write_job(tmp_path)
    (job_dir / "evaluation.md").write_text("# Strong fit", encoding="utf-8")
    (job_dir / "resume_tailored.pdf").write_bytes(b"%PDF-test")
    api = DashAPI(tmp_path)

    text = api.get_artifact("2026-06-12_acme_pm", "evaluation")
    pdf = api.get_artifact("2026-06-12_acme_pm", "resume")

    assert text == {
        "ok": True,
        "key": "evaluation",
        "kind": "text",
        "filename": "evaluation.md",
        "content": "# Strong fit",
    }
    assert pdf["ok"] is True
    assert pdf["kind"] == "pdf"
    assert base64.b64decode(pdf["content"]) == b"%PDF-test"


def test_artifact_api_rejects_unknown_keys_and_path_traversal(tmp_path: Path) -> None:
    _write_job(tmp_path)
    api = DashAPI(tmp_path)

    assert api.get_artifact("2026-06-12_acme_pm", "secrets")["ok"] is False
    assert api.get_artifact("../outside", "evaluation")["ok"] is False
    assert api.open_job_folder("../outside")["ok"] is False


def test_open_artifact_and_folder_use_validated_paths(tmp_path: Path, monkeypatch) -> None:
    job_dir = _write_job(tmp_path)
    artifact = job_dir / "evaluation.md"
    artifact.write_text("content", encoding="utf-8")
    opened: list[Path] = []
    monkeypatch.setattr("job_hunter.ux.web.api._open_path", lambda path: opened.append(path))
    api = DashAPI(tmp_path)

    assert api.open_artifact("2026-06-12_acme_pm", "evaluation") == {"ok": True}
    assert api.open_job_folder("2026-06-12_acme_pm") == {"ok": True}
    assert opened == [artifact.resolve(), job_dir.resolve()]


def test_open_artifact_reports_missing_file(tmp_path: Path) -> None:
    _write_job(tmp_path)

    result = DashAPI(tmp_path).open_artifact("2026-06-12_acme_pm", "interview")

    assert result == {"ok": False, "error": "Artifact not available."}


def test_get_artifact_reports_unreadable_text(tmp_path: Path) -> None:
    job_dir = _write_job(tmp_path)
    (job_dir / "evaluation.md").write_bytes(b"\xff")

    result = DashAPI(tmp_path).get_artifact("2026-06-12_acme_pm", "evaluation")

    assert result == {"ok": False, "error": "Artifact could not be read."}


@pytest.mark.parametrize(
    ("platform", "command"),
    [("darwin", "open"), ("linux", "xdg-open")],
)
def test_open_path_uses_platform_file_manager(tmp_path: Path, monkeypatch, platform: str, command: str) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(api_module.sys, "platform", platform)
    monkeypatch.setattr(api_module.subprocess, "Popen", lambda args: calls.append(args))

    api_module._open_path(tmp_path)

    assert calls == [[command, str(tmp_path)]]


def test_open_path_uses_windows_shell(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(api_module.sys, "platform", "win32")
    monkeypatch.setattr(api_module.os, "startfile", lambda path: calls.append(path), raising=False)

    api_module._open_path(tmp_path)

    assert calls == [str(tmp_path)]


def test_update_status_updates_state_and_refreshes_readme(tmp_path: Path) -> None:
    _write_job(tmp_path)
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)
    (tmp_path / "README.md").write_text(
        f"{TABLE_START}\n| Date | Job | Location | Score | Files |\n|---|---|---|---|---|\n{TABLE_END}\n",
        encoding="utf-8",
    )

    result = DashAPI(tmp_path).update_status("2026-06-12_acme_pm", "applied")

    assert result["status"] == "applied"
    readme_text = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "outputs/jobs/2026-06-12_acme_pm/" in readme_text


def test_update_status_returns_error_dict_for_invalid_status(tmp_path: Path) -> None:
    _write_job(tmp_path)
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)

    result = DashAPI(tmp_path).update_status("2026-06-12_acme_pm", "not-a-real-status")

    assert "error" in result


def test_delete_application_removes_record_and_returns_ok(tmp_path: Path) -> None:
    _write_job(tmp_path)
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)

    result = DashAPI(tmp_path).delete_application("2026-06-12_acme_pm")

    assert result == {"ok": True, "error": ""}
    assert DashAPI(tmp_path).get_applications()["items"] == []


def test_delete_application_returns_error_on_failure(tmp_path: Path, monkeypatch) -> None:
    def boom(_slug, _root):
        raise OSError("disk full")

    monkeypatch.setattr("job_hunter.tracking.applications.delete_application", boom)

    result = DashAPI(tmp_path).delete_application("2026-06-12_acme_pm")

    assert result == {
        "ok": False,
        "error": "Application could not be deleted.",
        "next_action": "Reload Applications and retry.",
    }
    assert "disk full" not in str(result)


def test_delete_applications_batch_removes_all_and_refreshes_readme_once(tmp_path: Path) -> None:
    _write_job(tmp_path, slug="2026-06-12_acme_pm")
    _write_job(tmp_path, slug="2026-06-13_globex_pm")
    meta_path = tmp_path / "outputs" / "jobs" / "2026-06-13_globex_pm" / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["url"] = "https://example.com/globex"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)
    upsert_application_from_job("2026-06-13_globex_pm", root=tmp_path)
    (tmp_path / "README.md").write_text(
        f"{TABLE_START}\n| Date | Job | Location | Score | Files |\n|---|---|---|---|---|\n{TABLE_END}\n",
        encoding="utf-8",
    )

    result = DashAPI(tmp_path).delete_applications_batch(["2026-06-12_acme_pm", "2026-06-13_globex_pm"])

    assert result["ok"] is True
    assert result["deleted"] == 2
    assert DashAPI(tmp_path).get_applications()["items"] == []


def test_delete_applications_batch_returns_error_on_failure(tmp_path: Path, monkeypatch) -> None:
    def boom(_slugs, root):
        raise OSError("disk full")

    monkeypatch.setattr("job_hunter.tracking.applications.delete_applications_batch", boom)

    result = DashAPI(tmp_path).delete_applications_batch(["a", "b"])

    assert result["ok"] is False
    assert result["error"] == "Applications could not be deleted."
    assert result["next_action"]
    assert "disk full" not in str(result)


def test_discard_unprocessed_batch_discards_all_in_one_call(tmp_path: Path) -> None:
    insert_jobs(
        tmp_path,
        [
            {"url": "https://example.com/a", "title": "PM", "company": "A"},
            {"url": "https://example.com/b", "title": "PM", "company": "B"},
        ],
    )
    api = DashAPI(tmp_path)
    ids = [job["id"] for job in api.get_unprocessed()["items"]]

    result = api.discard_unprocessed_batch(ids)

    assert result == {"ok": True, "error": "", "discarded": 2, "skipped": []}
    assert api.get_unprocessed()["items"] == []
    assert len(api.get_unprocessed("discarded")["items"]) == 2


def test_discard_unprocessed_batch_returns_error_on_failure(tmp_path: Path, monkeypatch) -> None:
    def boom(_root, _ids):
        raise OSError("db locked")

    monkeypatch.setattr("job_hunter.tracking.repository.discard_job_ids", boom)

    result = DashAPI(tmp_path).discard_unprocessed_batch([1, 2])

    assert result["ok"] is False
    assert result["error"] == "Candidates could not be discarded."
    assert result["next_action"]


def test_get_insights_returns_json_serializable_report(tmp_path: Path) -> None:
    _write_job(tmp_path)
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)

    report = DashAPI(tmp_path).get_insights()

    assert report["total"] == 1
    assert "weekly" in report
    json.dumps(report)


def test_get_analytics_reads_metrics_store(tmp_path: Path) -> None:
    db_path = tmp_path / "outputs" / "state" / "metrics.db"
    record_run(
        db_path,
        ts="2026-06-12T00:00:00Z",
        mode="hunt",
        exec_mode="llm-api",
        region="berlin",
        duration_s=1.5,
        jobs_found=3,
        jobs_tailored=1,
        token_totals={},
        total_cost_usd=None,
        scrape_stats={},
    )

    payload = DashAPI(tmp_path).get_analytics()

    assert len(payload["runs"]) == 1
    assert payload["runs"][0]["mode"] == "hunt"


def test_get_analytics_includes_normalized_telemetry(tmp_path: Path) -> None:
    from job_hunter.metrics.telemetry import TelemetryEvent, begin_run, end_run, ingest_otlp

    db_path = tmp_path / "outputs" / "state" / "metrics.db"
    run_id = begin_run(db_path, backend="codex", session_id="s", mode="batch")
    ingest_otlp(db_path, [TelemetryEvent(backend="codex", session_id="s", input_tokens=50, output_tokens=10)])
    end_run(db_path, run_id, status="completed")

    payload = DashAPI(tmp_path).get_analytics()

    assert payload["telemetry"]["totals"]["input_tokens"] == 50
    assert payload["telemetry"]["by_skill"]["batch"]["output_tokens"] == 10
    assert payload["telemetry"]["by_skill_backend"]["batch"]["codex"]["total_tokens"] == 60


def test_get_analytics_distinguishes_observed_from_unavailable_tokens(tmp_path: Path) -> None:
    from job_hunter.metrics.telemetry import begin_run, end_run, record_outcome

    db_path = tmp_path / "outputs" / "state" / "metrics.db"
    run_id = begin_run(db_path, backend="codex", session_id="s", mode="batch")
    record_outcome(db_path, run_id=run_id, job_slug="acme", decision="APPLY")
    end_run(db_path, run_id, status="completed")

    payload = DashAPI(tmp_path).get_analytics()

    assert payload["telemetry"]["token_status"] == "unavailable"
    assert payload["telemetry"]["outcomes"]["processed"] == 1


def test_get_analytics_operational_summary_present(tmp_path: Path) -> None:
    from job_hunter.metrics.telemetry import TelemetryEvent, begin_run, end_run, ingest_otlp

    db_path = tmp_path / "outputs" / "state" / "metrics.db"
    run_id = begin_run(db_path, backend="codex", session_id="s", mode="batch")
    ingest_otlp(db_path, [TelemetryEvent(backend="codex", session_id="s", model="gpt-5.4", input_tokens=10)])
    end_run(db_path, run_id, status="completed")

    payload = DashAPI(tmp_path).get_analytics()

    op = payload["telemetry"]["operational"]
    assert op["sessions"] == 1
    assert "current_streak" in op and "longest_streak" in op and "active_days" in op


def test_dashboard_renders_tokens_by_skill_with_backend_split() -> None:
    html = _dashboard_source()

    assert "Tokens by Skill" in html
    assert "Tokens by Mode" not in html
    assert "Claude Code Tokens" in html
    assert "Codex Tokens" in html
    assert "telemetry.by_skill_backend" in html


def test_get_analytics_reports_agent_mode_from_workspace_config(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text("mode: agent\n", encoding="utf-8")

    payload = DashAPI(tmp_path).get_analytics()

    assert payload["mode"] == "agent"


def test_get_analytics_reports_llm_api_mode_from_workspace_config(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text("mode: llm-api\n", encoding="utf-8")

    payload = DashAPI(tmp_path).get_analytics()

    assert payload["mode"] == "llm-api"


def test_get_analytics_defaults_to_agent_mode_when_config_missing(tmp_path: Path) -> None:
    payload = DashAPI(tmp_path).get_analytics()

    assert payload["mode"] == "agent"


def test_get_unprocessed_separates_real_candidates_from_history_and_hides_url_cache(tmp_path: Path) -> None:
    insert_jobs(
        tmp_path,
        [
            {
                "url": "https://example.com/active",
                "title": "Product Manager",
                "company": "Active Co",
                "location": "Berlin",
            },
            {
                "url": "https://example.com/processed",
                "title": "Senior Product Manager",
                "company": "Past Co",
                "location": "Dublin",
            },
        ],
    )
    mark_urls_processed(tmp_path, {"https://example.com/processed", "https://example.com/url-only-processed"})
    insert_candidate_urls(tmp_path, {"https://example.com/url-only-active"})

    payload = DashAPI(tmp_path).get_unprocessed()

    assert [job["company"] for job in payload["items"]] == ["Active Co"]
    assert [job["company"] for job in DashAPI(tmp_path).get_unprocessed("discarded")["items"]] == ["Past Co"]
    assert payload["counts"] == {"active": 1, "discarded": 1, "total": 2}


def test_discard_unprocessed_moves_a_candidate_to_discarded(tmp_path: Path) -> None:
    insert_jobs(
        tmp_path,
        [{"url": "https://example.com/discard-me", "title": "PM", "company": "Discard Co", "location": "Berlin"}],
    )
    api = DashAPI(tmp_path)
    job_id = api.get_unprocessed()["items"][0]["id"]

    assert api.discard_unprocessed(job_id) == {"ok": True, "error": ""}

    assert api.get_unprocessed()["items"] == []
    assert [job["url"] for job in api.get_unprocessed("discarded")["items"]] == ["https://example.com/discard-me"]


def test_discard_unprocessed_returns_error_on_failure(tmp_path: Path, monkeypatch) -> None:
    def boom(_root, _job_id, _status):
        raise OSError("db locked")

    monkeypatch.setattr("job_hunter.tracking.repository.set_status_by_id", boom)

    result = DashAPI(tmp_path).discard_unprocessed(1)

    assert result["ok"] is False
    assert result["error"] == "Candidate could not be discarded."
    assert result["next_action"]


def test_delete_unprocessed_returns_error_on_failure(tmp_path: Path, monkeypatch) -> None:
    def boom(_root, _job_id):
        raise OSError("db locked")

    monkeypatch.setattr("job_hunter.tracking.repository.delete_job_by_id", boom)

    result = DashAPI(tmp_path).delete_unprocessed(1)

    assert result["ok"] is False
    assert result["error"] == "Candidate could not be deleted."
    assert result["next_action"]


def _write_career_hunt_config(root: Path, companies: list[dict]) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump({"job_titles": ["Product Manager"], "exclusions": {}}), encoding="utf-8"
    )
    (root / "config" / "career_pages.yml").write_text(yaml.safe_dump({"companies": companies}), encoding="utf-8")


def test_run_company_hunt_starts_worker_and_persists_summary(tmp_path: Path, monkeypatch) -> None:
    _write_career_hunt_config(tmp_path, [{"name": "Acme", "career_url": "https://acme.example.com/jobs"}])
    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.ROOT", tmp_path)
    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.ensure_chromium_installed", lambda: True)
    monkeypatch.setattr(
        "job_hunter.pipeline.browser_hunt.extract_career_page_jobs",
        lambda company, titles, exclusions: [
            {"title": titles[0], "company": company["name"], "url": "https://acme.example.com/jobs/1"}
        ],
    )
    api = DashAPI(tmp_path)

    result = api.run_company_hunt()
    assert result == {"started": True}
    assert api.run_company_hunt() == {"already_running": True}
    api._hunt_thread.join(timeout=5)

    summary = api.get_company_hunt_summary()
    assert summary["ok"] is True
    assert summary["running"] is False
    run = summary["run"]
    assert run["status"] == "done"
    assert run["total"] == 1
    assert run["succeeded"] == 1
    assert run["failed"] == 0
    assert run["jobs_inserted"] == 1
    assert "1 new candidate found" in summary["message"]
    json.dumps(summary)

    # a second call can start a fresh run now that the worker has finished
    assert api.run_company_hunt() == {"started": True}
    api._hunt_thread.join(timeout=5)


def test_run_company_hunt_worker_crash_resets_running_flag(tmp_path: Path, monkeypatch) -> None:
    def boom(*, mode="new_changed", cooldown_hours=24, on_progress=None) -> int:
        raise RuntimeError("scrape failed")

    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.run", boom)
    api = DashAPI(tmp_path)

    api.run_company_hunt()
    api._hunt_thread.join(timeout=5)

    assert api.run_company_hunt() == {"started": True}
    api._hunt_thread.join(timeout=5)


def test_get_company_hunt_summary_message_reports_partial_failures(tmp_path: Path, monkeypatch) -> None:
    _write_career_hunt_config(
        tmp_path,
        [
            {"name": "A", "career_url": "https://a.example.com/jobs"},
            {"name": "B", "career_url": "https://b.example.com/jobs"},
            {"name": "C", "career_url": "https://c.example.com/jobs"},
        ],
    )
    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.ROOT", tmp_path)
    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.ensure_chromium_installed", lambda: True)

    def fake_extract(company, titles, exclusions):
        if company["name"] == "C":
            raise ConnectionError("couldn't connect")
        return [{"title": titles[0], "company": company["name"], "url": f"https://example.com/{company['name']}"}]

    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.extract_career_page_jobs", fake_extract)
    api = DashAPI(tmp_path)

    api.run_company_hunt()
    api._hunt_thread.join(timeout=5)

    summary = api.get_company_hunt_summary()
    assert summary["message"] == "2 of 3 companies checked (1 couldn't be reached). 2 new candidates found."
    assert summary["run"]["failed"] == 1


def test_get_company_hunt_updates_returns_tasks_incrementally_since_cursor(tmp_path: Path, monkeypatch) -> None:
    _write_career_hunt_config(
        tmp_path,
        [
            {"name": "A", "career_url": "https://a.example.com/jobs"},
            {"name": "B", "career_url": "https://b.example.com/jobs"},
        ],
    )
    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.ROOT", tmp_path)
    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.ensure_chromium_installed", lambda: True)
    monkeypatch.setattr(
        "job_hunter.pipeline.browser_hunt.extract_career_page_jobs",
        lambda company, titles, exclusions: [],
    )
    api = DashAPI(tmp_path)

    api.run_company_hunt()
    api._hunt_thread.join(timeout=5)
    run_id = api.get_company_hunt_summary()["run"]["id"]

    all_updates = api.get_company_hunt_updates(run_id, after_id=0)
    assert [t["company_name"] for t in all_updates["tasks"]] == ["A", "B"]
    cursor = all_updates["cursor"]

    further = api.get_company_hunt_updates(run_id, after_id=cursor)
    assert further["tasks"] == []
    assert further["cursor"] == cursor


def test_run_company_hunt_reflects_running_state_while_in_progress(tmp_path: Path, monkeypatch) -> None:
    import threading

    release = threading.Event()
    _write_career_hunt_config(tmp_path, [{"name": "Acme", "career_url": "https://acme.example.com/jobs"}])
    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.ROOT", tmp_path)
    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.ensure_chromium_installed", lambda: True)

    def blocking_extract(company, titles, exclusions):
        release.wait(timeout=5)
        return []

    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.extract_career_page_jobs", blocking_extract)
    api = DashAPI(tmp_path)

    api.run_company_hunt()
    try:
        assert api.get_company_hunt_summary()["running"] is True
    finally:
        release.set()
        api._hunt_thread.join(timeout=5)

    assert api.get_company_hunt_summary()["running"] is False


def _fake_hunt_output(**overrides):
    from job_hunter.models import HuntOutput, ScrapeStats

    stats = ScrapeStats(total_fetched=10, total_after_policy=3)
    return HuntOutput(jobs=[], stats=stats, run_id="run-1", mode="agent", **overrides)


def test_get_hunt_status_reports_idle_before_any_run(tmp_path: Path) -> None:
    assert DashAPI(tmp_path).get_hunt_status() == {"ok": True, "status": "idle"}


def test_start_hunt_runs_worker_and_reports_succeeded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("job_hunter.config.get_mode", lambda: "agent")
    monkeypatch.setattr("job_hunter.pipeline.hunt.run", lambda inp: _fake_hunt_output())
    api = DashAPI(tmp_path)

    result = api.start_hunt()
    assert result == {"ok": True, "status": "running", "started_at": result["started_at"]}

    for _ in range(50):
        if api.get_hunt_status()["status"] != "running":
            break
        import time

        time.sleep(0.05)

    status = api.get_hunt_status()
    assert status["status"] == "succeeded"
    assert status["fetched"] == 10
    assert status["candidates"] == 3
    assert status["tailored"] == 0
    assert status["next_action"]
    json.dumps(status)


def test_start_hunt_rejects_concurrent_start(tmp_path: Path, monkeypatch) -> None:
    import threading

    release = threading.Event()

    def blocking_run(inp):
        release.wait(timeout=5)
        return _fake_hunt_output()

    monkeypatch.setattr("job_hunter.config.get_mode", lambda: "agent")
    monkeypatch.setattr("job_hunter.pipeline.hunt.run", blocking_run)
    api = DashAPI(tmp_path)

    first = api.start_hunt()
    try:
        assert first["ok"] is True
        second = api.start_hunt()
        assert second["ok"] is False
        assert second["status"] == "running"
    finally:
        release.set()
        for _ in range(50):
            if api.get_hunt_status()["status"] != "running":
                break
            import time

            time.sleep(0.05)


def test_start_hunt_and_company_hunt_share_the_same_lock(tmp_path: Path, monkeypatch) -> None:
    """Prevent overlapping normal/company runs against the same workspace."""
    import threading

    release = threading.Event()

    def blocking_run(inp):
        release.wait(timeout=5)
        return _fake_hunt_output()

    monkeypatch.setattr("job_hunter.config.get_mode", lambda: "agent")
    monkeypatch.setattr("job_hunter.pipeline.hunt.run", blocking_run)
    _write_career_hunt_config(tmp_path, [])
    api = DashAPI(tmp_path)

    api.start_hunt()
    try:
        assert api.start_company_hunt() == {"already_running": True}
    finally:
        release.set()
        for _ in range(50):
            if api.get_hunt_status()["status"] != "running":
                break
            import time

            time.sleep(0.05)


def test_start_hunt_worker_crash_reports_failed_and_resets_lock(tmp_path: Path, monkeypatch) -> None:
    def boom(inp):
        raise RuntimeError("scrape failed")

    monkeypatch.setattr("job_hunter.config.get_mode", lambda: "agent")
    monkeypatch.setattr("job_hunter.pipeline.hunt.run", boom)
    api = DashAPI(tmp_path)

    api.start_hunt()
    for _ in range(50):
        if api.get_hunt_status()["status"] != "running":
            break
        import time

        time.sleep(0.05)

    status = api.get_hunt_status()
    assert status["status"] == "failed"
    assert "scrape failed" not in status["message"]  # detailed exceptions stay out of the UI-facing message
    assert api.start_hunt()["ok"] is True  # lock was released despite the crash


def test_get_sync_status_reports_idle_before_any_run(tmp_path: Path) -> None:
    assert DashAPI(tmp_path).get_sync_status() == {"ok": True, "status": "idle"}


def test_start_sync_runs_worker_and_reports_result(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "job_hunter.workspace.git_sync.sync_workspace",
        lambda root: {"ok": True, "inserted": 2, "updated": 1, "pushed": True},
    )
    api = DashAPI(tmp_path)

    result = api.start_sync()
    assert result == {"ok": True, "status": "running"}

    for _ in range(50):
        if api.get_sync_status()["status"] != "running":
            break
        import time

        time.sleep(0.05)

    status = api.get_sync_status()
    assert status["status"] == "succeeded"
    assert status["inserted"] == 2
    assert status["updated"] == 1
    json.dumps(status)


def test_start_sync_rejects_concurrent_start_with_hunt(tmp_path: Path, monkeypatch) -> None:
    import threading

    release = threading.Event()

    def blocking_run(inp):
        release.wait(timeout=5)
        return _fake_hunt_output()

    monkeypatch.setattr("job_hunter.config.get_mode", lambda: "agent")
    monkeypatch.setattr("job_hunter.pipeline.hunt.run", blocking_run)
    api = DashAPI(tmp_path)

    api.start_hunt()
    try:
        second = api.start_sync()
        assert second["ok"] is False
        assert second["status"] == "running"
    finally:
        release.set()
        for _ in range(50):
            if api.get_hunt_status()["status"] != "running":
                break
            import time

            time.sleep(0.05)


def test_start_sync_worker_crash_reports_failed_and_resets_lock(tmp_path: Path, monkeypatch) -> None:
    def boom(root):
        raise RuntimeError("git exploded")

    monkeypatch.setattr("job_hunter.workspace.git_sync.sync_workspace", boom)
    api = DashAPI(tmp_path)

    api.start_sync()
    for _ in range(50):
        if api.get_sync_status()["status"] != "running":
            break
        import time

        time.sleep(0.05)

    status = api.get_sync_status()
    assert status["status"] == "failed"
    assert "git exploded" not in status["error"]  # detailed exceptions stay out of the UI-facing message
    assert api.start_sync()["ok"] is True  # lock was released despite the crash


def test_start_company_hunt_is_alias_for_run_company_hunt(tmp_path: Path) -> None:
    _write_career_hunt_config(tmp_path, [])
    api = DashAPI(tmp_path)

    result = api.start_company_hunt()

    assert result == {"started": True}
    api._hunt_thread.join(timeout=5)


def test_get_company_hunt_status_is_alias_for_get_company_hunt_summary(tmp_path: Path) -> None:
    api = DashAPI(tmp_path)

    assert api.get_company_hunt_status() == api.get_company_hunt_summary()


def test_get_user_name_extracts_from_resume_tex(tmp_path: Path, monkeypatch) -> None:
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / "resume_double_column.tex").write_text("\\name{Alex Rivera}", encoding="utf-8")
    monkeypatch.setattr(
        "job_hunter.config.loader.get_config",
        lambda _name: {"profile": {"resume_tex": "profile/resume_double_column.tex"}},
    )

    name = DashAPI(tmp_path).get_user_name()

    assert name == "Alex Rivera"


def test_dashboard_renders_markdown_artifacts_instead_of_raw_source() -> None:
    """Regression: cover letter/evaluation/research/outreach/interview artifacts are
    LLM-authored .md files and were previously dumped as raw markdown source in a <pre>
    — they must be rendered as formatted HTML, with the raw text kept only for Copy."""
    js = (_WEB_DIR / "dashboard.js").read_text(encoding="utf-8")

    assert "function renderMarkdown" in js
    assert "function mdInline" in js
    assert "artifact-markdown" in js
    assert "activeArtifactRawText" in js
    assert "'artifact-text'" not in js  # old raw-<pre> class must be gone, not just unused


def test_dashboard_contains_artifact_workspace_controls() -> None:
    html = _dashboard_source()

    for artifact in ("resume", "cover_letter", "evaluation", "research", "outreach", "interview"):
        assert f'data-artifact="{artifact}"' in html
    assert 'id="dp-artifact-preview"' in html
    assert 'id="dp-copy-artifact"' in html
    assert "['dp-copy-artifact', copyArtifact]" in html
    assert 'id="dp-open-folder-btn"' in html
    assert "['dp-open-folder-btn', openJobFolder]" in html
    assert "URL.revokeObjectURL" in html
    assert "@media (max-width: 900px)" in html
    assert 'data-candidate-scope="active"' in html
    assert 'data-candidate-scope="discarded"' in html
    assert 'data-candidate-scope="company-hunt"' in html
    assert 'id="company-hunt-panel"' in html
    assert 'id="run-company-hunt-btn"' in html
    assert 'id="candidate-search"' in html
    assert ".badge-rejected  { background: rgba(248,81,73" in html


def test_dashboard_company_hunt_uses_persisted_summary_polling_with_run_modes() -> None:
    html = _dashboard_source()

    assert 'id="company-hunt-mode"' in html
    for mode in ("new_changed", "failed_only", "force_all", "resume"):
        assert f'value="{mode}"' in html
    assert "get_company_hunt_summary" in html
    assert "get_company_hunt_updates" in html
    assert "get_company_hunt_status" not in html
    assert "function appendCompanyHuntUpdates" in html


def test_dashboard_has_no_inline_handlers_with_interpolated_row_values() -> None:
    """Untrusted scrape data (slugs, ids) must travel via data-* attributes and
    delegated listeners, not string-interpolated into inline onclick/onchange —
    interpolating into a single-quoted JS literal inside a double-quoted HTML
    attribute is a JS-injection vector that a plain HTML-escaper doesn't cover."""
    html = _dashboard_source()

    assert 'onclick="selectApp(' not in html
    assert 'onclick="deleteUnprocessed(${' not in html
    assert 'onchange="toggleCandidateSelected(${' not in html
    assert "data-delete-id=" in html
    assert "data-slug=" in html
    assert "function companyHuntRowHtml" in html
    assert "esc(task.company_name" in html


def test_dashboard_uses_safe_url_for_scraped_job_links() -> None:
    html = _dashboard_source()

    assert "function safeUrl(" in html
    assert 'href="${esc(job.url)}"' not in html
    assert "linkEl.href = meta.url" not in html


# ---------------------------------------------------------------------------
# Settings: job_hunter.yml (guided form + advanced raw) and career_context.md
# ---------------------------------------------------------------------------

_SETTINGS_CONFIG = {
    "mode": "agent",
    "profile": {
        "resume_tex": "profile/resume_double_column.tex",
        "story_bank": "profile/story_bank.md",
        "career_context": "profile/career_context.md",
    },
    "job_titles": ["Product Manager"],
    "regions": {"berlin": {"enabled": True, "country": "DE", "location": "Berlin"}},
    "exclusions": {},
    "scoring": {"min_fit_score": 70, "batch_size": 15},
    "llm": {"default_provider": "anthropic", "providers": {"scoring": "anthropic"}},
}


def _write_settings_config(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "job_hunter.yml").write_text(yaml.safe_dump(_SETTINGS_CONFIG), encoding="utf-8")


def test_get_job_hunter_config_form_returns_guided_fields_and_revision(tmp_path: Path) -> None:
    _write_settings_config(tmp_path)

    result = DashAPI(tmp_path).get_job_hunter_config_form()

    assert result["ok"] is True
    assert result["data"]["form"]["mode"] == "agent"
    assert result["data"]["form"]["job_titles"] == ["Product Manager"]
    assert "providers" not in result["data"]["form"]
    assert result["data"]["revision"]
    json.dumps(result)


def test_save_job_hunter_config_form_updates_job_titles_and_preserves_advanced_llm(tmp_path: Path) -> None:
    _write_settings_config(tmp_path)
    api = DashAPI(tmp_path)
    loaded = api.get_job_hunter_config_form()
    form = loaded["data"]["form"]
    form["job_titles"] = ["Staff Engineer"]

    result = api.save_job_hunter_config_form(form, loaded["data"]["revision"])

    assert result["ok"] is True
    on_disk = yaml.safe_load((tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8"))
    assert on_disk["job_titles"] == ["Staff Engineer"]
    assert on_disk["llm"]["providers"] == {"scoring": "anthropic"}


def test_save_job_hunter_config_form_rejects_stale_revision(tmp_path: Path) -> None:
    _write_settings_config(tmp_path)
    api = DashAPI(tmp_path)
    loaded = api.get_job_hunter_config_form()

    result = api.save_job_hunter_config_form(loaded["data"]["form"], "0" * 64)

    assert result["ok"] is False
    assert result["data"] is None
    assert result["errors"]


def test_get_job_hunter_config_raw_and_save_round_trip(tmp_path: Path) -> None:
    _write_settings_config(tmp_path)
    api = DashAPI(tmp_path)

    loaded = api.get_job_hunter_config_raw()
    new_text = loaded["data"]["text"].replace("mode: agent", "mode: llm-api")
    result = api.save_job_hunter_config_raw(new_text, loaded["data"]["revision"])

    assert result["ok"] is True
    on_disk = yaml.safe_load((tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8"))
    assert on_disk["mode"] == "llm-api"


def test_save_job_hunter_config_raw_rejects_invalid_yaml_and_reports_errors(tmp_path: Path) -> None:
    _write_settings_config(tmp_path)
    api = DashAPI(tmp_path)
    loaded = api.get_job_hunter_config_raw()

    result = api.save_job_hunter_config_raw("not: valid: yaml: [", loaded["data"]["revision"])

    assert result["ok"] is False
    assert result["errors"]


def test_undo_job_hunter_config_restores_previous_save(tmp_path: Path) -> None:
    _write_settings_config(tmp_path)
    api = DashAPI(tmp_path)
    original = (tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8")
    loaded = api.get_job_hunter_config_raw()
    api.save_job_hunter_config_raw(original.replace("mode: agent", "mode: llm-api"), loaded["data"]["revision"])

    result = api.undo_job_hunter_config()

    assert result["ok"] is True
    assert (tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8") == original


def test_save_job_hunter_config_surfaces_doctor_warnings_without_failing(tmp_path: Path) -> None:
    _write_settings_config(tmp_path)
    api = DashAPI(tmp_path)
    loaded = api.get_job_hunter_config_raw()

    result = api.save_job_hunter_config_raw(loaded["data"]["text"], loaded["data"]["revision"])

    assert result["ok"] is True
    # this bare tmp_path workspace is missing the resume/story bank doctor checks for —
    # they must show up as warnings, never as errors that would roll back a good save.
    assert any("resume_double_column.tex" in w for w in result["warnings"])
    assert result["errors"] == []


def test_get_and_save_career_context_round_trip(tmp_path: Path) -> None:
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "career_context.md").write_text("## About Me\n", encoding="utf-8")
    api = DashAPI(tmp_path)

    loaded = api.get_career_context()
    result = api.save_career_context("## About Me\n\n- Updated", loaded["data"]["revision"])

    assert result["ok"] is True
    assert (tmp_path / "profile" / "career_context.md").read_text(encoding="utf-8") == "## About Me\n\n- Updated"


def test_save_career_context_rejects_stale_revision(tmp_path: Path) -> None:
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "career_context.md").write_text("original", encoding="utf-8")
    api = DashAPI(tmp_path)

    result = api.save_career_context("changed", "0" * 64)

    assert result["ok"] is False
    assert (tmp_path / "profile" / "career_context.md").read_text(encoding="utf-8") == "original"


def test_undo_career_context_restores_previous_save(tmp_path: Path) -> None:
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "career_context.md").write_text("original", encoding="utf-8")
    api = DashAPI(tmp_path)
    loaded = api.get_career_context()
    api.save_career_context("changed", loaded["data"]["revision"])

    result = api.undo_career_context()

    assert result["ok"] is True
    assert (tmp_path / "profile" / "career_context.md").read_text(encoding="utf-8") == "original"


def test_dashboard_contains_settings_nav_and_panels() -> None:
    html = _dashboard_source()

    assert 'data-view="settings"' in html
    assert 'id="view-settings"' in html
    assert 'data-settings-tab="guided"' in html
    assert 'data-settings-tab="advanced"' in html
    assert 'data-settings-tab="career-context"' in html
    assert 'id="settings-panel-guided"' in html
    assert 'id="settings-panel-advanced"' in html
    assert 'id="settings-panel-career-context"' in html
    assert 'id="settings-raw-yaml"' in html
    assert 'id="settings-career-context"' in html
    assert "function saveGuidedConfig" in html
    assert "function saveRawConfig" in html
    assert "function saveCareerContext" in html
    assert "function undoJobHunterConfig" in html
    assert "function undoCareerContext" in html
    assert "function settingsHasUnsavedChanges" in html
    assert "get_job_hunter_config_form" in html
    assert "save_job_hunter_config_form" in html
    assert "get_job_hunter_config_raw" in html
    assert "save_job_hunter_config_raw" in html
    assert "get_career_context" in html
    assert "save_career_context" in html


def test_dashboard_contains_diagnostics_tab_with_doctor_and_analytics() -> None:
    """Analytics folded into Settings -> Diagnostics (no standalone top-level nav item),
    alongside a doctor-derived setup health checklist."""
    html = _dashboard_source()

    assert 'data-view="analytics"' not in html
    assert 'id="view-analytics"' not in html
    assert 'data-settings-tab="diagnostics"' in html
    assert 'id="settings-panel-diagnostics"' in html
    assert 'id="diag-checklist"' in html
    assert 'id="analytics-header"' in html
    assert "function loadDiagnosticsChecklist" in html
    assert "function loadAnalytics" in html
    assert "function renderAnalytics" in html


def test_today_tab_removed_manual_hunt_lives_in_diagnostics() -> None:
    """Regression: hunting runs on GitHub Actions' schedule, not by a user clicking a
    button — Today was a standalone landing tab nobody used for that. The manual/local
    run trigger still exists (for testing config changes) but now lives inside Settings →
    Diagnostics, not as a top-level nav destination or the default view."""
    html = _dashboard_source()

    assert 'data-view="today"' not in html
    assert 'id="view-today"' not in html
    assert 'id="find-jobs-btn"' in html
    assert 'id="today-hunt-status-value"' in html
    assert '<div class="settings-panel" id="settings-panel-diagnostics">' in html
    diagnostics_panel = html.split('id="settings-panel-diagnostics"', 1)[1].split('<section id="view-get-started"', 1)[
        0
    ]
    assert 'id="find-jobs-btn"' in diagnostics_panel
    assert "function findJobs" in html
    assert "function loadTodayHuntStatus" in html
    assert "function pollTodayHuntStatus" in html
    assert "start_hunt" in html
    assert "get_hunt_status" in html


def test_applications_is_the_default_landing_view() -> None:
    html = _dashboard_source()

    assert '<button class="nav-btn active" data-view="applications">' in html
    assert '<section id="view-applications" class="view active">' in html


def test_dashboard_contains_search_setup_and_chatbot_import_sections() -> None:
    html = _dashboard_source()

    assert 'id="gs-section-search-setup"' in html
    assert 'id="gs-search-mode"' in html
    assert 'id="gs-career-stage"' in html
    assert 'id="gs-search-job-titles"' in html
    assert 'id="gs-search-country"' in html
    assert 'id="gs-search-location"' in html
    assert 'id="gs-search-lang"' in html
    assert 'id="gs-search-excl-industries"' in html
    assert 'id="save-search-setup-btn"' in html
    assert "function saveSearchSetup" in html
    assert "save_onboarding_preferences" in html

    assert 'id="gs-section-chatbot-import"' in html
    assert 'id="copy-onboarding-prompt-btn"' in html
    assert 'id="gs-chatbot-response"' in html
    assert 'id="import-chatbot-bundle-btn"' in html
    assert "function copyOnboardingPrompt" in html
    assert "function importChatbotBundle" in html
    assert "get_onboarding_prompt" in html
    assert "import_onboarding_bundle" in html


def test_dashboard_settings_disables_save_buttons_during_save() -> None:
    html = _dashboard_source()

    assert "btn.disabled = true;" in html
    assert "btn.disabled = false;" in html


def test_dashboard_settings_warns_before_losing_unsaved_changes() -> None:
    html = _dashboard_source()

    assert "settingsHasUnsavedChanges()" in html
    assert "Leave without saving" in html


# ---------------------------------------------------------------------------
# Companies (career_pages.yml management)
# ---------------------------------------------------------------------------

_REAL_CAREER_PAGES = (Path(__file__).parents[1] / "config" / "career_pages.yml").read_text(encoding="utf-8")


def _write_career_pages(root: Path, text: str = _REAL_CAREER_PAGES) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "career_pages.yml").write_text(text, encoding="utf-8")


def test_get_career_pages_returns_companies_and_revision(tmp_path: Path) -> None:
    _write_career_pages(tmp_path)

    result = DashAPI(tmp_path).get_career_pages()

    assert result["ok"] is True
    assert result["data"]["companies"] == []
    assert result["data"]["revision"]
    json.dumps(result)


def test_get_career_pages_decorates_with_latest_hunt_result(tmp_path: Path) -> None:
    from job_hunter.tracking import company_hunts

    _write_career_pages(
        tmp_path, yaml.safe_dump({"companies": [{"name": "Stripe", "career_url": "https://stripe.com/jobs"}]})
    )
    run_id = company_hunts.begin_run(tmp_path, company_hunts.MODE_NEW_CHANGED)
    company_hunts.create_tasks(
        tmp_path, run_id, [{"name": "Stripe", "career_url": "https://stripe.com/jobs"}], status=company_hunts.PENDING
    )
    task_id = company_hunts.get_pending_tasks(tmp_path, run_id)[0]["id"]
    company_hunts.finish_task(tmp_path, task_id, run_id, status=company_hunts.OK, jobs_observed=2, jobs_inserted=1)

    result = DashAPI(tmp_path).get_career_pages()

    latest = result["data"]["companies"][0]["latest_result"]
    assert latest["status"] == "ok"
    assert latest["jobs_inserted"] == 1
    json.dumps(result)


def test_get_career_pages_reports_none_for_never_checked_company(tmp_path: Path) -> None:
    _write_career_pages(
        tmp_path, yaml.safe_dump({"companies": [{"name": "Stripe", "career_url": "https://stripe.com/jobs"}]})
    )

    result = DashAPI(tmp_path).get_career_pages()

    assert result["data"]["companies"][0]["latest_result"] is None


def test_save_career_pages_adds_a_company(tmp_path: Path) -> None:
    _write_career_pages(tmp_path)
    api = DashAPI(tmp_path)
    loaded = api.get_career_pages()

    result = api.save_career_pages(
        [{"name": "Stripe", "career_url": "https://stripe.com/jobs", "location": "Berlin"}],
        loaded["data"]["revision"],
    )

    assert result["ok"] is True
    assert result["data"]["companies"] == [
        {"name": "Stripe", "career_url": "https://stripe.com/jobs", "location": "Berlin", "latest_result": None}
    ]


def test_save_career_pages_rejects_invalid_entry_without_touching_disk(tmp_path: Path) -> None:
    _write_career_pages(tmp_path)
    api = DashAPI(tmp_path)
    loaded = api.get_career_pages()
    before_text = (tmp_path / "config" / "career_pages.yml").read_text(encoding="utf-8")

    result = api.save_career_pages([{"name": "", "career_url": "not-a-url"}], loaded["data"]["revision"])

    assert result["ok"] is False
    assert result["data"] is None
    assert (tmp_path / "config" / "career_pages.yml").read_text(encoding="utf-8") == before_text


def test_save_career_pages_rejects_stale_revision(tmp_path: Path) -> None:
    _write_career_pages(tmp_path)
    api = DashAPI(tmp_path)

    result = api.save_career_pages([{"name": "Stripe", "career_url": "https://stripe.com/jobs"}], "0" * 64)

    assert result["ok"] is False


def test_save_career_pages_bulk_disable_existing_companies(tmp_path: Path) -> None:
    _write_career_pages(tmp_path)
    api = DashAPI(tmp_path)
    loaded = api.get_career_pages()
    api.save_career_pages(
        [
            {"name": "Stripe", "career_url": "https://stripe.com/jobs"},
            {"name": "N26", "career_url": "https://n26.com/careers"},
        ],
        loaded["data"]["revision"],
    )
    reloaded = api.get_career_pages()

    disabled = [dict(c, enabled=False) for c in reloaded["data"]["companies"]]
    result = api.save_career_pages(disabled, reloaded["data"]["revision"])

    assert result["ok"] is True
    assert all(c["enabled"] is False for c in result["data"]["companies"])


def test_undo_career_pages_restores_previous_companies(tmp_path: Path) -> None:
    _write_career_pages(tmp_path)
    api = DashAPI(tmp_path)
    loaded = api.get_career_pages()
    api.save_career_pages([{"name": "Stripe", "career_url": "https://stripe.com/jobs"}], loaded["data"]["revision"])

    result = api.undo_career_pages()

    assert result["ok"] is True
    assert result["data"]["companies"] == []


def test_open_career_page_allows_known_https_url(tmp_path: Path, monkeypatch) -> None:
    _write_career_pages(
        tmp_path, yaml.safe_dump({"companies": [{"name": "Stripe", "career_url": "https://stripe.com/jobs"}]})
    )
    opened: list[str] = []
    monkeypatch.setattr("job_hunter.ux.web.api._open_url", lambda url: opened.append(url))

    result = DashAPI(tmp_path).open_career_page("https://stripe.com/jobs")

    assert result == {"ok": True}
    assert opened == ["https://stripe.com/jobs"]


def test_open_career_page_rejects_url_not_in_config(tmp_path: Path) -> None:
    _write_career_pages(tmp_path)

    result = DashAPI(tmp_path).open_career_page("https://evil.example.com")

    assert result["ok"] is False


def test_open_career_page_rejects_non_http_scheme_even_if_present_in_yaml(tmp_path: Path) -> None:
    _write_career_pages(tmp_path, "companies:\n  - name: Evil\n    career_url: 'file:///etc/passwd'\n")

    result = DashAPI(tmp_path).open_career_page("file:///etc/passwd")

    assert result["ok"] is False
    assert "http" in result["error"]


def test_open_career_pages_file_and_config_folder_use_validated_paths(tmp_path: Path, monkeypatch) -> None:
    _write_career_pages(tmp_path)
    opened: list[Path] = []
    monkeypatch.setattr("job_hunter.ux.web.api._open_path", lambda path: opened.append(path))
    api = DashAPI(tmp_path)

    assert api.open_career_pages_file() == {"ok": True}
    assert api.open_config_folder() == {"ok": True}
    assert opened == [(tmp_path / "config" / "career_pages.yml").resolve(), (tmp_path / "config").resolve()]


def test_dashboard_contains_companies_nav_and_table() -> None:
    """Companies management is folded into Candidates -> Company Hunt (no standalone
    top-level nav item), reachable inside #company-hunt-panel."""
    html = _dashboard_source()

    assert 'data-view="companies"' not in html
    assert 'id="view-companies"' not in html
    assert 'id="company-hunt-panel"' in html
    assert 'data-company-hunt-view="run"' in html
    assert 'data-company-hunt-view="manage"' in html
    assert 'id="company-hunt-run-view"' in html
    assert 'id="company-hunt-manage-view"' in html
    assert 'id="companies-tbody"' in html
    assert 'id="company-search"' in html
    assert 'data-company-filter="enabled"' in html
    assert 'data-company-filter="disabled"' in html
    assert "function submitCompanyForm" in html
    assert "function bulkDeleteCompanies" in html
    assert "function bulkSetCompaniesEnabled" in html
    assert "get_career_pages" in html
    assert "save_career_pages" in html
    assert "undo_career_pages" in html
    assert "open_career_page" in html
    assert "open_career_pages_file" in html
    assert "open_config_folder" in html
    assert "function companyLatestResultHtml" in html
    assert "company.latest_result" in html


def test_dashboard_companies_table_windows_large_lists_instead_of_rendering_everything() -> None:
    """A 2,000-company career_pages.yml must not build one giant innerHTML string up
    front — the initial render is capped, with a "Show more" affordance to grow it."""
    html = _dashboard_source()

    assert "companyRenderLimit" in html
    assert "function showMoreCompanies" in html
    assert "filtered.slice(0, companyRenderLimit)" in html


def test_dashboard_companies_table_uses_delegated_listeners_not_inline_row_handlers() -> None:
    html = _dashboard_source()

    assert "function companyRowHtml" in html
    assert "data-edit-url=" in html
    assert "data-delete-url=" in html
    assert 'onclick="editCompany(${' not in html
    assert 'onclick="deleteCompany(${' not in html


def test_dashboard_applications_have_bulk_delete_checkboxes() -> None:
    html = _dashboard_source()

    assert 'id="app-select-all"' in html
    assert 'id="app-bulk-delete-btn"' in html
    assert 'class="app-checkbox"' in html
    assert "function bulkDeleteApplications" in html
    assert "function toggleSelectAllApps" in html
    assert "delete_applications_batch" in html
    assert 'onclick="deleteApp(${' not in html


def test_dashboard_status_save_and_deletes_reload_current_page_not_page_one() -> None:
    """saveStatus/deleteApp/bulkDeleteApplications must not bump the user back to
    page 1 of the applications list — they should reload in place via
    loadApplications(), not applyFilters() (which resets appPage to 1)."""
    html = _dashboard_source()

    def function_body(name: str) -> str:
        start = html.index(f"async function {name}(")
        end = html.index("\n}\n", start)
        return html[start:end]

    for name in ("saveStatus", "deleteApp", "bulkDeleteApplications"):
        body = function_body(name)
        assert "loadApplications();" in body, f"{name} must reload via loadApplications()"
        assert "applyFilters();" not in body, f"{name} must not reset pagination via applyFilters()"


def test_dashboard_candidate_bulk_discard_uses_one_batch_call_not_promise_all() -> None:
    html = _dashboard_source()

    assert "discard_unprocessed_batch" in html
    assert "Promise.all(ids.map(id => window.pywebview.api.discard_unprocessed(" not in html
