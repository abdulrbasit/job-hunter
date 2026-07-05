from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from job_hunter.cli import app
from job_hunter.metrics.collector import handle_otlp_request
from job_hunter.metrics.telemetry import (
    TelemetryEvent,
    active_run,
    begin_run,
    classify_job_hunter_mode,
    classify_job_hunter_skill_prompt,
    end_phase,
    end_run,
    get_telemetry_summary,
    ingest_otlp,
    prune_unattributed,
    record_outcome,
    start_phase,
    telemetry_status,
)

runner = CliRunner()


def test_classify_job_hunter_modes_without_retaining_prompt() -> None:
    assert classify_job_hunter_mode("/job-hunter batch") == "batch"
    assert classify_job_hunter_mode("/job-hunter score acme-pm") == "scoring"
    assert classify_job_hunter_mode("/job-hunter interview acme-pm") == "interview"
    assert classify_job_hunter_mode("/job-hunter outreach acme-pm") == "outreach"
    assert classify_job_hunter_mode("/job-hunter linkedin draft") == "linkedin_draft"
    assert classify_job_hunter_mode("/linkedin ideas") == "linkedin_ideas"
    assert classify_job_hunter_mode("/job-hunter one https://example.com/jobs/42") == "one"
    assert classify_job_hunter_mode("Run job hunter batch for the next candidates") is None
    assert classify_job_hunter_mode("https://example.com/jobs/42") is None
    assert classify_job_hunter_mode("https://github.com/abdulrbasit/job-hunter") is None
    assert classify_job_hunter_mode("Refactor the job-hunter repository") is None
    assert classify_job_hunter_mode("Review job-hunter code in Codex") is None
    assert classify_job_hunter_mode("/job-hunter dashboard") is None
    assert classify_job_hunter_mode("/job-hunter doctor") is None
    assert classify_job_hunter_mode("/job-hunter setup") is None
    assert classify_job_hunter_mode("explain this traceback") is None
    invocation = classify_job_hunter_skill_prompt("/job-hunter tailor acme")
    assert invocation and invocation.root_skill == "job-hunter"
    assert invocation.skill == "tailoring"


def test_phase_and_job_usage_rolls_up_once(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    run_id = begin_run(db, backend="codex", session_id="session-1", mode="batch")
    phase_id = start_phase(db, run_id=run_id, phase="scoring", job_slug="acme-pm")
    ingest_otlp(
        db,
        [
            TelemetryEvent(
                backend="codex",
                session_id="session-1",
                model="gpt-5.4",
                input_tokens=120,
                output_tokens=30,
                cached_tokens=80,
                reasoning_tokens=12,
                raw_usage={"input_tokens": 120, "secret_prompt": "must not persist"},
            )
        ],
    )
    end_phase(db, phase_id, status="completed")
    end_run(db, run_id, status="completed")

    summary = get_telemetry_summary(db)
    assert summary["totals"]["input_tokens"] == 120
    assert summary["totals"]["output_tokens"] == 30
    assert summary["totals"]["cached_tokens"] == 80
    assert summary["totals"]["reasoning_tokens"] == 12
    assert summary["by_skill"]["batch"]["total_tokens"] == 150
    assert summary["by_phase"]["scoring"]["input_tokens"] == 120
    assert "secret_prompt" not in json.dumps(summary)

    import sqlite3

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT e.input_tokens, e.output_tokens FROM telemetry_events e "
        "JOIN telemetry_phases p ON p.id = e.phase_id WHERE p.phase='scoring' AND p.job_slug='acme-pm'"
    ).fetchone()
    assert row["input_tokens"] == 120
    assert row["output_tokens"] == 30


def test_phase_durations_aggregate_from_recorded_start_end_timestamps(tmp_path: Path) -> None:
    """phase_durations is a pure aggregation over already-recorded started_at/ended_at —
    no new instrumentation, so this pins the aggregation math against direct DB rows."""
    import sqlite3

    db = tmp_path / "metrics.db"
    run_id = begin_run(db, backend="codex", session_id="session-1", mode="batch")
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO telemetry_phases (id, run_id, phase, started_at, ended_at, status) VALUES "
        "('p1', ?, 'scoring', '2026-01-01T00:00:00', '2026-01-01T00:00:10', 'completed')",
        (run_id,),
    )
    conn.execute(
        "INSERT INTO telemetry_phases (id, run_id, phase, started_at, ended_at, status) VALUES "
        "('p2', ?, 'scoring', '2026-01-01T00:00:00', '2026-01-01T00:00:20', 'completed')",
        (run_id,),
    )
    conn.execute(
        "INSERT INTO telemetry_phases (id, run_id, phase, started_at, ended_at, status) VALUES "
        "('p3', ?, 'tailoring', '2026-01-01T00:00:00', NULL, 'running')",
        (run_id,),
    )
    conn.commit()
    conn.close()

    durations = get_telemetry_summary(db)["phase_durations"]

    assert durations["scoring"] == {"count": 2, "total_seconds": 30.0, "avg_seconds": 15.0}
    assert "tailoring" not in durations


def test_claude_and_codex_otlp_json_normalize_identically(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    begin_run(db, backend="claude-code", session_id="claude-1", mode="tailor")
    begin_run(db, backend="codex", session_id="codex-1", mode="tailor")

    claude_payload = {
        "resourceMetrics": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "claude-code"}}]},
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": "claude_code.token.usage",
                                "sum": {
                                    "dataPoints": [
                                        {
                                            "asInt": "25",
                                            "attributes": [
                                                {"key": "session.id", "value": {"stringValue": "claude-1"}},
                                                {"key": "type", "value": {"stringValue": "input"}},
                                                {"key": "model", "value": {"stringValue": "claude-sonnet-4-6"}},
                                            ],
                                        },
                                        {
                                            "asInt": "5",
                                            "attributes": [
                                                {"key": "session.id", "value": {"stringValue": "claude-1"}},
                                                {"key": "type", "value": {"stringValue": "output"}},
                                            ],
                                        },
                                    ]
                                },
                            }
                        ]
                    }
                ],
            }
        ]
    }
    codex_payload = {
        "resourceLogs": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "codex"}}]},
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "body": {"stringValue": "codex.sse_event"},
                                "attributes": [
                                    {"key": "conversation.id", "value": {"stringValue": "codex-1"}},
                                    {"key": "event.kind", "value": {"stringValue": "response.completed"}},
                                    {"key": "input_tokens", "value": {"intValue": "25"}},
                                    {"key": "output_tokens", "value": {"intValue": "5"}},
                                    {"key": "model", "value": {"stringValue": "gpt-5.4"}},
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    assert ingest_otlp(db, claude_payload) == 2
    assert ingest_otlp(db, codex_payload) == 1
    summary = get_telemetry_summary(db)
    assert summary["totals"]["input_tokens"] == 50

    import sqlite3

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = {
        row["backend"]: row["n"]
        for row in conn.execute("SELECT backend, SUM(input_tokens) AS n FROM telemetry_events GROUP BY backend")
    }
    assert rows["claude-code"] == 25
    assert rows["codex"] == 25


def test_end_run_closes_unfinished_phase_as_interrupted(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    run_id = begin_run(db, backend="codex", session_id="s", mode="batch")
    start_phase(db, run_id=run_id, phase="tailoring", job_slug="acme")

    end_run(db, run_id, status="completed")

    import sqlite3

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM telemetry_phases WHERE run_id=? AND status='interrupted'", (run_id,)
    ).fetchone()
    assert row["n"] == 1


def test_outcomes_report_processed_decisions_and_failures(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    run_id = begin_run(db, backend="codex", session_id="s", mode="batch")
    record_outcome(db, run_id=run_id, job_slug="apply-job", decision="APPLY", tailored=True)
    record_outcome(db, run_id=run_id, job_slug="skip-job", decision="SKIP")
    record_outcome(db, run_id=run_id, job_slug="failed-job", failed=True)

    outcomes = get_telemetry_summary(db)["outcomes"]
    assert outcomes == {"processed": 3, "apply": 1, "skip": 1, "tailored": 1, "failed": 1}


def test_malformed_collector_payload_is_non_blocking(tmp_path: Path) -> None:
    status, accepted = handle_otlp_request(tmp_path / "metrics.db", b"{broken")
    assert status == 200
    assert accepted == 0


def test_collector_decodes_gzip_encoded_otlp_body(tmp_path: Path) -> None:
    import gzip

    db = tmp_path / "metrics.db"
    begin_run(db, backend="claude-code", session_id="gz-session", mode="tailor")
    payload = {
        "resourceLogs": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "claude-code"}}]},
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "body": {"stringValue": "api_request"},
                                "attributes": [
                                    {"key": "session.id", "value": {"stringValue": "gz-session"}},
                                    {"key": "input_tokens", "value": {"intValue": "12"}},
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }
    compressed = gzip.compress(json.dumps(payload).encode("utf-8"))

    status, accepted = handle_otlp_request(db, compressed, content_type="application/json", content_encoding="gzip")

    assert status == 200
    assert accepted == 1
    assert get_telemetry_summary(db)["totals"]["input_tokens"] == 12


def test_collector_rejects_unsupported_protobuf_content_type(tmp_path: Path) -> None:
    from job_hunter.metrics import collector

    status, accepted = handle_otlp_request(
        tmp_path / "metrics.db", b"\x08\x96\x01", content_type="application/x-protobuf"
    )

    assert status == 200
    assert accepted == 0
    assert collector.LAST_REJECTED_CONTENT_TYPE == "application/x-protobuf"


def test_hook_and_marker_commands_attribute_usage(tmp_path: Path) -> None:
    payload = json.dumps(
        {
            "session_id": "codex-session",
            "cwd": str(tmp_path),
            "prompt": "/job-hunter batch",
        }
    )
    with patch("job_hunter.metrics.collector.ensure_collector", return_value=True):
        result = runner.invoke(
            app,
            ["internal", "telemetry-hook", "--backend", "codex", "--event", "prompt", "--workspace", str(tmp_path)],
            input=payload,
        )
    assert result.exit_code == 0

    result = runner.invoke(
        app,
        [
            "internal",
            "telemetry-mark",
            "--phase",
            "scoring",
            "--job",
            "acme-pm",
            "--state",
            "start",
            "--workspace",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    ingest_otlp(
        tmp_path / "outputs" / "state" / "metrics.db",
        [TelemetryEvent(backend="codex", session_id="codex-session", input_tokens=10)],
    )
    result = runner.invoke(
        app,
        [
            "internal",
            "telemetry-mark",
            "--phase",
            "scoring",
            "--state",
            "end",
            "--workspace",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0
    db = tmp_path / "outputs" / "state" / "metrics.db"
    assert get_telemetry_summary(db)["totals"]["input_tokens"] == 10

    import sqlite3

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT e.input_tokens FROM telemetry_events e "
        "JOIN telemetry_phases p ON p.id = e.phase_id WHERE p.job_slug='acme-pm'"
    ).fetchone()
    assert row["input_tokens"] == 10


def test_telemetry_hook_writes_heartbeat_even_when_inner_logic_fails(tmp_path: Path) -> None:
    """The heartbeat marker must be written before the fragile telemetry work runs, so it
    still lands even if that work raises — this is what lets doctor tell "hook never
    fires" apart from "hook fires but crashes before writing a run"."""
    payload = json.dumps({"session_id": "s", "cwd": str(tmp_path), "prompt": "/job-hunter batch"})

    with patch("job_hunter.metrics.collector.ensure_collector", side_effect=RuntimeError("boom")):
        result = runner.invoke(
            app,
            ["internal", "telemetry-hook", "--backend", "codex", "--event", "prompt", "--workspace", str(tmp_path)],
            input=payload,
        )

    assert result.exit_code == 0
    assert (tmp_path / "outputs" / "state" / ".telemetry_hook_heartbeat").exists()


def test_stop_hook_keeps_run_open_while_waiting_for_confirmation(tmp_path: Path) -> None:
    db = tmp_path / "outputs" / "state" / "metrics.db"
    begin_run(db, backend="codex", session_id="s", mode="one")
    payload = json.dumps(
        {
            "session_id": "s",
            "cwd": str(tmp_path),
            "last_assistant_message": "Tailor resume and write cover letter? Reply yes to continue.",
        }
    )

    result = runner.invoke(
        app,
        ["internal", "telemetry-hook", "--backend", "codex", "--event", "stop", "--workspace", str(tmp_path)],
        input=payload,
    )

    assert result.exit_code == 0
    assert active_run(db, "s") is not None


def test_late_otlp_event_does_not_attach_to_completed_run(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    run_id = begin_run(db, backend="codex", session_id="late", mode="batch")
    end_run(db, run_id, status="completed")

    assert ingest_otlp(db, [TelemetryEvent(backend="codex", session_id="late", input_tokens=7)]) == 0
    summary = get_telemetry_summary(db)
    assert summary["totals"]["input_tokens"] == 0
    assert summary["ignored"]["events"] == 1


def test_claude_metric_cumulative_counters_emit_only_the_delta(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    begin_run(db, backend="claude-code", session_id="claude-1", mode="tailor")

    def payload(cumulative: int) -> dict:
        return {
            "resourceMetrics": [
                {
                    "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "claude-code"}}]},
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "claude_code.token.usage",
                                    "sum": {
                                        "dataPoints": [
                                            {
                                                "asInt": str(cumulative),
                                                "attributes": [
                                                    {"key": "session.id", "value": {"stringValue": "claude-1"}},
                                                    {"key": "type", "value": {"stringValue": "input"}},
                                                ],
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    ],
                }
            ]
        }

    ingest_otlp(db, payload(100))
    ingest_otlp(db, payload(140))

    assert get_telemetry_summary(db)["totals"]["input_tokens"] == 140


def test_claude_log_span_ingests_cache_read_and_creation_tokens(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    begin_run(db, backend="claude-code", session_id="claude-2", mode="tailor")
    payload = {
        "resourceLogs": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "claude-code"}}]},
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "body": {"stringValue": "api_request"},
                                "attributes": [
                                    {"key": "session.id", "value": {"stringValue": "claude-2"}},
                                    {"key": "input_tokens", "value": {"intValue": "10"}},
                                    {"key": "output_tokens", "value": {"intValue": "4"}},
                                    {"key": "cache_read_tokens", "value": {"intValue": "50"}},
                                    {"key": "cache_creation_tokens", "value": {"intValue": "8"}},
                                    {"key": "model", "value": {"stringValue": "claude-sonnet-4-6"}},
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    assert ingest_otlp(db, payload) == 1
    totals = get_telemetry_summary(db)["totals"]
    assert totals["cache_read_tokens"] == 50
    assert totals["cache_creation_tokens"] == 8


def test_codex_otel_payload_with_gen_ai_usage_fields(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    begin_run(db, backend="codex", session_id="codex-gen-ai", mode="batch")
    payload = {
        "resourceLogs": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "codex"}}]},
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "body": {"stringValue": "codex.sse_event"},
                                "attributes": [
                                    {"key": "conversation.id", "value": {"stringValue": "codex-gen-ai"}},
                                    {"key": "event.kind", "value": {"stringValue": "response.completed"}},
                                    {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "33"}},
                                    {"key": "gen_ai.usage.output_tokens", "value": {"intValue": "9"}},
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    assert ingest_otlp(db, payload) == 1
    totals = get_telemetry_summary(db)["totals"]
    assert totals["input_tokens"] == 33
    assert totals["output_tokens"] == 9


def test_codex_otel_payload_with_token_count_fields(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    begin_run(db, backend="codex", session_id="codex-count", mode="batch")
    payload = {
        "resourceLogs": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "codex"}}]},
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "body": {"stringValue": "codex.sse_event"},
                                "attributes": [
                                    {"key": "conversation.id", "value": {"stringValue": "codex-count"}},
                                    {"key": "event.kind", "value": {"stringValue": "response.completed"}},
                                    {"key": "input_token_count", "value": {"intValue": "21"}},
                                    {"key": "output_token_count", "value": {"intValue": "6"}},
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    assert ingest_otlp(db, payload) == 1
    totals = get_telemetry_summary(db)["totals"]
    assert totals["input_tokens"] == 21
    assert totals["output_tokens"] == 6


def test_hook_only_run_has_unavailable_token_status(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    run_id = begin_run(db, backend="codex", session_id="hook-only", mode="batch")
    phase_id = start_phase(db, run_id=run_id, phase="scoring", job_slug="acme")
    end_phase(db, phase_id, status="completed")
    record_outcome(db, run_id=run_id, job_slug="acme", decision="APPLY")
    end_run(db, run_id, status="completed")

    summary = get_telemetry_summary(db)
    assert summary["token_status"] == "unavailable"
    assert summary["outcomes"]["processed"] == 1


def test_event_with_nonmatching_session_links_to_latest_same_backend_run(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    begin_run(db, backend="claude-code", session_id="hook-session-id", mode="batch")

    # OTLP resource reports a different session id than the hook payload did.
    assert ingest_otlp(db, [TelemetryEvent(backend="claude-code", session_id="otel-session-id", input_tokens=42)]) == 1
    assert get_telemetry_summary(db)["totals"]["input_tokens"] == 42


def test_fallback_rejects_multiple_active_owned_runs(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    begin_run(db, backend="codex", session_id="one", mode="batch")
    begin_run(db, backend="codex", session_id="two", mode="batch")

    assert ingest_otlp(db, [TelemetryEvent(backend="codex", session_id="different", input_tokens=42)]) == 0
    assert get_telemetry_summary(db)["ignored"]["events"] == 1


def test_stale_running_run_is_interrupted_and_not_used(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "metrics.db"
    run_id = begin_run(db, backend="codex", session_id="stale", mode="batch")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE telemetry_runs SET started_at='2025-01-01T00:00:00+00:00' WHERE id=?",
            (run_id,),
        )

    assert ingest_otlp(db, [TelemetryEvent(backend="codex", session_id="stale", input_tokens=9)]) == 0
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT status FROM telemetry_runs WHERE id=?", (run_id,)).fetchone()[0] == "interrupted"


def test_events_without_active_job_hunter_run_are_ignored(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    # No run exists at all yet for this backend.
    assert ingest_otlp(db, [TelemetryEvent(backend="codex", session_id="orphan", input_tokens=15)]) == 0

    summary = get_telemetry_summary(db)
    assert summary["ignored"]["events"] == 1
    assert summary["ignored"]["input_tokens"] == 15
    assert summary["totals"]["input_tokens"] == 0

    import sqlite3

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM telemetry_events WHERE run_id='unattributed'").fetchone()[0] == 0


def test_summary_splits_skill_tokens_by_backend(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    begin_run(db, backend="claude-code", session_id="claude", mode="tailoring")
    begin_run(db, backend="codex", session_id="codex", mode="tailoring")
    ingest_otlp(db, [TelemetryEvent(backend="claude-code", session_id="claude", input_tokens=10)])
    ingest_otlp(db, [TelemetryEvent(backend="codex", session_id="codex", output_tokens=5)])

    summary = get_telemetry_summary(db)

    assert summary["by_backend"]["claude-code"]["input_tokens"] == 10
    assert summary["by_backend"]["codex"]["output_tokens"] == 5
    assert summary["by_skill_backend"]["tailoring"]["claude-code"]["total_tokens"] == 10
    assert summary["by_skill_backend"]["tailoring"]["codex"]["total_tokens"] == 5
    assert summary["by_skill_backend"]["tailoring"]["total"]["total_tokens"] == 15
    assert "by_mode" not in summary


def test_prune_unattributed_deletes_only_legacy_rows(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "metrics.db"
    run_id = begin_run(db, backend="codex", session_id="owned", mode="batch")
    ingest_otlp(db, [TelemetryEvent(backend="codex", session_id="owned", input_tokens=3)])
    with sqlite3.connect(db) as conn:
        conn.execute(
            """INSERT INTO telemetry_events(run_id,backend,session_id,recorded_at,input_tokens)
               VALUES('unattributed','codex','old','2026-01-01T00:00:00+00:00',99)"""
        )

    assert prune_unattributed(db) == 1
    assert get_telemetry_summary(db)["totals"]["input_tokens"] == 3
    assert run_id


def test_telemetry_prune_cli_reports_deleted_rows(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "outputs" / "state" / "metrics.db"
    begin_run(db, backend="codex", session_id="owned", mode="batch")
    with sqlite3.connect(db) as conn:
        conn.execute(
            """INSERT INTO telemetry_events(run_id,backend,session_id,recorded_at,input_tokens)
               VALUES('unattributed','codex','old','2026-01-01T00:00:00+00:00',99)"""
        )

    result = runner.invoke(
        app,
        ["internal", "telemetry-prune", "--unattributed", "--workspace", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert "Deleted 1 unattributed telemetry event(s)." in result.stdout


def test_operational_summary_computes_sessions_messages_and_tokens(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    run_id = begin_run(db, backend="codex", session_id="s1", mode="batch")
    begin_run(db, backend="codex", session_id="s1", mode="batch")  # same session, second prompt
    ingest_otlp(
        db,
        [
            TelemetryEvent(backend="codex", session_id="s1", model="gpt-5.4", input_tokens=10, output_tokens=5),
            TelemetryEvent(backend="codex", session_id="s1", model="gpt-5.4", input_tokens=90, output_tokens=5),
        ],
    )
    end_run(db, run_id, status="completed")

    op = get_telemetry_summary(db)["operational"]
    assert op["sessions"] == 1
    assert op["messages"] == 2
    assert sum(day["tokens"] for day in op["daily"].values()) == 110


def test_raw_prompt_content_is_never_persisted(tmp_path: Path) -> None:
    payload = json.dumps(
        {
            "session_id": "priv-session",
            "cwd": str(tmp_path),
            "prompt": "/job-hunter batch — my secret job search plan for Acme Corp",
        }
    )
    with patch("job_hunter.metrics.collector.ensure_collector", return_value=True):
        runner.invoke(
            app,
            ["internal", "telemetry-hook", "--backend", "codex", "--event", "prompt", "--workspace", str(tmp_path)],
            input=payload,
        )

    raw_db_text = (tmp_path / "outputs" / "state" / "metrics.db").read_bytes()
    assert b"Acme" not in raw_db_text
    assert b"secret job search plan" not in raw_db_text


def test_telemetry_status_reports_privacy_safe_diagnostics(tmp_path: Path) -> None:
    with patch("job_hunter.metrics.collector.collector_health", return_value=None):
        run_id = begin_run(tmp_path / "outputs" / "state" / "metrics.db", backend="codex", session_id="s", mode="batch")
        start_phase(tmp_path / "outputs" / "state" / "metrics.db", run_id=run_id, phase="scoring")

        status = telemetry_status(tmp_path)

    assert status["collector_healthy"] is False
    assert status["active_runs"] == 1
    assert status["latest_phase"]["phase"] == "scoring"
    assert status["claude_hooks_wired"] is False
    assert "prompt" not in json.dumps(status)


def test_telemetry_status_reports_app_entrypoint_breakdown(tmp_path: Path) -> None:
    """Distinguishes cli/sdk-vscode/desktop sessions in the metrics so a Desktop-app
    telemetry gap can be confirmed from data instead of guessed at."""
    db_path = tmp_path / "outputs" / "state" / "metrics.db"
    run_id = begin_run(db_path, backend="claude-code", session_id="s", mode="batch")
    ingest_otlp(
        db_path,
        {
            "resourceMetrics": [
                {
                    "resource": {"attributes": [{"key": "app.entrypoint", "value": {"stringValue": "cli"}}]},
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    "name": "claude_code.token.usage",
                                    "sum": {
                                        "dataPoints": [
                                            {
                                                "asInt": "10",
                                                "attributes": [
                                                    {"key": "type", "value": {"stringValue": "input"}},
                                                    {"key": "session.id", "value": {"stringValue": "s"}},
                                                    {"key": "model", "value": {"stringValue": "claude-x"}},
                                                ],
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    ],
                }
            ]
        },
    )

    with patch("job_hunter.metrics.collector.collector_health", return_value=None):
        status = telemetry_status(tmp_path)

    assert status["event_count_by_app_entrypoint"] == {"cli": 1}
    assert run_id


def _write_claude_hook(root: Path) -> None:
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "job-hunter internal telemetry-hook --backend claude-code --event prompt",
                                }
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


def test_telemetry_status_flags_hook_that_fires_but_never_writes_a_run(tmp_path: Path) -> None:
    """The hook heartbeat proves Claude Code invoked the hook process; zero runs ever
    existing despite that means the process is failing before it can write to metrics.db —
    a blind spot the existing hooks_wired_but_no_otel_events check can't see."""
    _write_claude_hook(tmp_path)
    (tmp_path / "outputs" / "state").mkdir(parents=True)
    (tmp_path / "outputs" / "state" / ".telemetry_hook_heartbeat").write_text("2026-07-01T00:00:00", encoding="utf-8")

    with patch("job_hunter.metrics.collector.collector_health", return_value=None):
        status = telemetry_status(tmp_path)

    assert status["hooks_invoked_but_no_runs_ever"] is True


def test_telemetry_status_does_not_flag_fresh_workspace_with_no_heartbeat(tmp_path: Path) -> None:
    """A workspace that's never invoked the hook at all (fresh install) must not be flagged —
    only a hook that's firing yet failing to record anything is a real problem."""
    _write_claude_hook(tmp_path)

    with patch("job_hunter.metrics.collector.collector_health", return_value=None):
        status = telemetry_status(tmp_path)

    assert status["hooks_invoked_but_no_runs_ever"] is False
