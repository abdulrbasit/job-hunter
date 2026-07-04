"""Tests for ux/web/api.py::DashAPI — the pywebview JS-callable dashboard API."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
import yaml

from job_hunter.metrics.store import record_run
from job_hunter.pipeline.stages.readme import TABLE_END, TABLE_START
from job_hunter.tracking.applications import upsert_application_from_job
from job_hunter.tracking.repository import insert_candidate_urls, insert_jobs, mark_urls_processed
from job_hunter.ux.web import api as api_module
from job_hunter.ux.web.api import DashAPI


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


def test_get_applications_returns_json_serializable_dicts(tmp_path: Path) -> None:
    _write_job(tmp_path)
    upsert_application_from_job("2026-06-12_acme_pm", root=tmp_path)

    apps = DashAPI(tmp_path).get_applications()

    assert isinstance(apps, list)
    assert apps[0]["slug"] == "2026-06-12_acme_pm"
    assert apps[0]["date"] == "2026-06-12"
    assert apps[0]["location"] == "Berlin"
    json.dumps(apps)  # must round-trip through JSON for the JS bridge


def test_dashboard_table_renders_application_location_and_date() -> None:
    dashboard = Path(__file__).parents[1] / "job_hunter" / "ux" / "web" / "dashboard.html"
    html = dashboard.read_text(encoding="utf-8")

    assert 'data-col="location"' in html
    assert "app.location" in html
    assert "app.date" in html


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
    assert DashAPI(tmp_path).get_applications() == []


def test_delete_application_returns_error_on_failure(tmp_path: Path, monkeypatch) -> None:
    def boom(_slug, _root):
        raise OSError("disk full")

    monkeypatch.setattr("job_hunter.tracking.applications.delete_application", boom)

    result = DashAPI(tmp_path).delete_application("2026-06-12_acme_pm")

    assert result == {"ok": False, "error": "disk full"}


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
    assert payload["telemetry"]["by_mode"]["batch"]["output_tokens"] == 10


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

    assert [job["company"] for job in payload["active"]] == ["Active Co"]
    assert [job["company"] for job in payload["discarded"]] == ["Past Co"]
    assert payload["counts"] == {"active": 1, "discarded": 1, "total": 2}


def test_discard_unprocessed_moves_a_candidate_to_discarded(tmp_path: Path) -> None:
    insert_jobs(
        tmp_path,
        [{"url": "https://example.com/discard-me", "title": "PM", "company": "Discard Co", "location": "Berlin"}],
    )
    api = DashAPI(tmp_path)
    job_id = api.get_unprocessed()["active"][0]["id"]

    assert api.discard_unprocessed(job_id) == {"ok": True, "error": ""}

    payload = api.get_unprocessed()
    assert payload["active"] == []
    assert [job["url"] for job in payload["discarded"]] == ["https://example.com/discard-me"]


def test_discard_unprocessed_returns_error_on_failure(tmp_path: Path, monkeypatch) -> None:
    def boom(_root, _job_id, _status):
        raise OSError("db locked")

    monkeypatch.setattr("job_hunter.tracking.repository.set_status_by_id", boom)

    result = DashAPI(tmp_path).discard_unprocessed(1)

    assert result == {"ok": False, "error": "db locked"}


def test_delete_unprocessed_returns_error_on_failure(tmp_path: Path, monkeypatch) -> None:
    def boom(_root, _job_id):
        raise OSError("db locked")

    monkeypatch.setattr("job_hunter.tracking.repository.delete_job_by_id", boom)

    result = DashAPI(tmp_path).delete_unprocessed(1)

    assert result == {"ok": False, "error": "db locked"}


def test_run_company_hunt_starts_worker_and_reports_done_with_inserted_count(tmp_path: Path, monkeypatch) -> None:
    def fake_run(*, on_progress=None) -> int:
        if on_progress:
            on_progress({"step": "started", "total": 1})
            on_progress({"step": "company-checking", "index": 1, "total": 1, "company": "Acme"})
            on_progress({"step": "company-done", "index": 1, "total": 1, "company": "Acme", "jobs_found": 1})
            on_progress({"step": "finished", "total": 1, "succeeded": 1, "failed": 0, "jobs_found": 1})
        insert_jobs(
            tmp_path,
            [{"url": "https://example.com/new", "title": "PM", "company": "Acme", "location": "Berlin"}],
        )
        return 0

    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.run", fake_run)
    api = DashAPI(tmp_path)

    result = api.run_company_hunt()
    assert result == {"started": True}
    assert api.run_company_hunt() == {"already_running": True}
    api._hunt_thread.join(timeout=5)

    status = api.get_company_hunt_status()
    assert status["state"] == "done"
    assert status["inserted"] == 1
    assert status["total"] == 1
    assert status["succeeded"] == 1
    assert status["failed"] == 0
    assert status["companies"] == [{"company": "Acme", "status": "ok", "jobs_found": 1}]
    assert "1 new candidate found" in status["message"]


def test_run_company_hunt_reports_error_status_on_failure(tmp_path: Path, monkeypatch) -> None:
    def boom(*, on_progress=None) -> int:
        raise RuntimeError("scrape failed")

    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.run", boom)
    api = DashAPI(tmp_path)

    api.run_company_hunt()
    api._hunt_thread.join(timeout=5)

    status = api.get_company_hunt_status()
    assert status["state"] == "error"
    assert "scrape failed" not in status["error"]
    assert "went wrong" in status["error"]


def test_run_company_hunt_reports_fatal_reason_from_progress_event(tmp_path: Path, monkeypatch) -> None:
    def fake_run(*, on_progress) -> int:
        on_progress({"step": "fatal", "reason": "Company list is missing."})
        return 1

    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.run", fake_run)
    api = DashAPI(tmp_path)

    api.run_company_hunt()
    api._hunt_thread.join(timeout=5)

    assert api.get_company_hunt_status() == {"state": "error", "error": "Company list is missing."}


def test_run_company_hunt_summarizes_partial_failures_in_message(tmp_path: Path, monkeypatch) -> None:
    def fake_run(*, on_progress) -> int:
        on_progress({"step": "started", "total": 3})
        on_progress({"step": "company-done", "company": "A", "jobs_found": 1})
        on_progress({"step": "company-done", "company": "B", "jobs_found": 1})
        on_progress({"step": "company-failed", "company": "C", "reason": "couldn't be reached"})
        on_progress({"step": "finished", "total": 3, "succeeded": 2, "failed": 1, "jobs_found": 2})
        insert_jobs(
            tmp_path,
            [
                {"url": "https://example.com/a", "title": "PM", "company": "A"},
                {"url": "https://example.com/b", "title": "PM", "company": "B"},
            ],
        )
        return 0

    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.run", fake_run)
    api = DashAPI(tmp_path)

    api.run_company_hunt()
    api._hunt_thread.join(timeout=5)

    status = api.get_company_hunt_status()
    assert status["message"] == "2 of 3 companies checked (1 couldn't be reached). 2 new candidates found."
    assert status["failed"] == 1


def test_get_company_hunt_status_companies_list_is_a_snapshot_copy(tmp_path: Path, monkeypatch) -> None:
    def fake_run(*, on_progress) -> int:
        on_progress({"step": "started", "total": 1})
        on_progress({"step": "company-done", "company": "Acme", "jobs_found": 0})
        on_progress({"step": "finished", "total": 1, "succeeded": 1, "failed": 0, "jobs_found": 0})
        return 0

    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.run", fake_run)
    api = DashAPI(tmp_path)

    api.run_company_hunt()
    api._hunt_thread.join(timeout=5)

    first = api.get_company_hunt_status()
    first["companies"].append({"company": "injected", "status": "ok", "jobs_found": 0})

    second = api.get_company_hunt_status()
    assert second["companies"] == [{"company": "Acme", "status": "ok", "jobs_found": 0}]


def test_run_company_hunt_status_reflects_live_progress_while_running(tmp_path: Path, monkeypatch) -> None:
    import threading

    release = threading.Event()

    def fake_run(*, on_progress) -> int:
        on_progress({"step": "started", "total": 2})
        on_progress({"step": "company-checking", "index": 1, "total": 2, "company": "Acme"})
        release.wait(timeout=5)
        on_progress({"step": "company-done", "company": "Acme", "jobs_found": 0})
        on_progress({"step": "finished", "total": 2, "succeeded": 1, "failed": 0, "jobs_found": 0})
        return 0

    monkeypatch.setattr("job_hunter.pipeline.browser_hunt.run", fake_run)
    api = DashAPI(tmp_path)

    api.run_company_hunt()
    try:
        for _ in range(50):
            mid_status = api.get_company_hunt_status()
            if mid_status.get("current_company") == "Acme":
                break
            import time

            time.sleep(0.05)
        else:
            raise AssertionError("worker never reported live progress")
        assert mid_status["state"] == "running"
        assert mid_status["total"] == 2
        assert mid_status["checked"] == 0
    finally:
        release.set()
        api._hunt_thread.join(timeout=5)


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


def test_dashboard_contains_artifact_workspace_controls() -> None:
    dashboard = Path(__file__).parents[1] / "job_hunter" / "ux" / "web" / "dashboard.html"
    html = dashboard.read_text(encoding="utf-8")

    for artifact in ("resume", "cover_letter", "evaluation", "research", "outreach", "interview"):
        assert f'data-artifact="{artifact}"' in html
    assert 'id="dp-artifact-preview"' in html
    assert 'onclick="copyArtifact()"' in html
    assert 'onclick="openJobFolder()"' in html
    assert "URL.revokeObjectURL" in html
    assert "@media (max-width: 900px)" in html
    assert 'data-candidate-scope="active"' in html
    assert 'data-candidate-scope="discarded"' in html
    assert 'data-candidate-scope="company-hunt"' in html
    assert 'id="company-hunt-panel"' in html
    assert 'id="run-company-hunt-btn"' in html
    assert 'id="candidate-search"' in html
    assert ".badge-rejected  { background: rgba(248,81,73" in html


def test_dashboard_has_no_inline_handlers_with_interpolated_row_values() -> None:
    """Untrusted scrape data (slugs, ids) must travel via data-* attributes and
    delegated listeners, not string-interpolated into inline onclick/onchange —
    interpolating into a single-quoted JS literal inside a double-quoted HTML
    attribute is a JS-injection vector that a plain HTML-escaper doesn't cover."""
    dashboard = Path(__file__).parents[1] / "job_hunter" / "ux" / "web" / "dashboard.html"
    html = dashboard.read_text(encoding="utf-8")

    assert 'onclick="selectApp(' not in html
    assert 'onclick="deleteUnprocessed(${' not in html
    assert 'onchange="toggleCandidateSelected(${' not in html
    assert "data-delete-id=" in html
    assert "data-slug=" in html
    assert "function companyHuntRowHtml" in html
    assert "esc(row.company" in html


def test_dashboard_uses_safe_url_for_scraped_job_links() -> None:
    dashboard = Path(__file__).parents[1] / "job_hunter" / "ux" / "web" / "dashboard.html"
    html = dashboard.read_text(encoding="utf-8")

    assert "function safeUrl(" in html
    assert 'href="${esc(job.url)}"' not in html
    assert "linkEl.href = meta.url" not in html
