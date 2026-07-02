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
    end_phase,
    end_run,
    get_telemetry_summary,
    ingest_otlp,
    record_outcome,
    start_phase,
    telemetry_status,
)

runner = CliRunner()


def test_classify_job_hunter_modes_without_retaining_prompt() -> None:
    assert classify_job_hunter_mode("/job-hunter batch lite") == "batch-lite"
    assert classify_job_hunter_mode("$job-hunter score acme-pm") == "score"
    assert classify_job_hunter_mode("Run job hunter batch for the next candidates") == "batch"
    assert classify_job_hunter_mode("https://example.com/jobs/42") == "one"
    assert classify_job_hunter_mode("explain this traceback") is None


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
    assert summary["totals"] == {
        "input_tokens": 120,
        "output_tokens": 30,
        "cached_tokens": 80,
        "reasoning_tokens": 12,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
    }
    assert summary["by_phase"]["scoring"]["input_tokens"] == 120
    assert summary["by_job"]["acme-pm"]["output_tokens"] == 30
    assert "secret_prompt" not in json.dumps(summary)


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
    assert summary["by_backend"]["claude-code"]["input_tokens"] == 25
    assert summary["by_backend"]["codex"]["input_tokens"] == 25


def test_end_run_closes_unfinished_phase_as_interrupted(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    run_id = begin_run(db, backend="codex", session_id="s", mode="batch")
    start_phase(db, run_id=run_id, phase="tailoring", job_slug="acme")

    end_run(db, run_id, status="completed")

    summary = get_telemetry_summary(db)
    assert summary["runs"][0]["incomplete_phases"] == 1


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
    assert (
        get_telemetry_summary(tmp_path / "outputs" / "state" / "metrics.db")["by_job"]["acme-pm"]["input_tokens"] == 10
    )


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


def test_late_otlp_event_attaches_to_just_completed_run(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    run_id = begin_run(db, backend="codex", session_id="late", mode="batch")
    end_run(db, run_id, status="completed")

    assert ingest_otlp(db, [TelemetryEvent(backend="codex", session_id="late", input_tokens=7)]) == 1
    assert get_telemetry_summary(db)["totals"]["input_tokens"] == 7


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
    assert summary["runs"][0]["token_status"] == "unavailable"
    assert summary["token_status"] == "unavailable"
    assert summary["outcomes"]["processed"] == 1


def test_event_with_nonmatching_session_links_to_latest_same_backend_run(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    begin_run(db, backend="claude-code", session_id="hook-session-id", mode="batch")

    # OTLP resource reports a different session id than the hook payload did.
    assert ingest_otlp(db, [TelemetryEvent(backend="claude-code", session_id="otel-session-id", input_tokens=42)]) == 1
    assert get_telemetry_summary(db)["totals"]["input_tokens"] == 42


def test_unattributed_events_are_preserved_not_dropped(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    # No run exists at all yet for this backend.
    assert ingest_otlp(db, [TelemetryEvent(backend="codex", session_id="orphan", input_tokens=15)]) == 1

    summary = get_telemetry_summary(db)
    assert summary["unattributed"]["count"] == 1
    assert summary["unattributed"]["input_tokens"] == 15
    # Still shows up in overall totals — nothing is silently discarded.
    assert summary["totals"]["input_tokens"] == 15


def test_operational_summary_computes_sessions_messages_tokens_and_favorite_model(tmp_path: Path) -> None:
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
    assert op["favorite_model"] == "gpt-5.4"
    assert sum(day["tokens"] for day in op["daily"].values()) == 110


def test_model_breakdown_computes_share_of_total_tokens(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    begin_run(db, backend="claude-code", session_id="s2", mode="tailor")
    ingest_otlp(
        db,
        [
            TelemetryEvent(backend="claude-code", session_id="s2", model="model-a", input_tokens=80),
            TelemetryEvent(backend="claude-code", session_id="s2", model="model-b", input_tokens=20),
        ],
    )

    by_model = get_telemetry_summary(db)["by_model"]
    assert by_model["model-a"]["share"] == 80.0
    assert by_model["model-b"]["share"] == 20.0


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
