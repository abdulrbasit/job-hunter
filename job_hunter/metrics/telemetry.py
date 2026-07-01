"""Normalized token telemetry for agent and direct-LLM execution."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_TOKEN_FIELDS = ("input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens")
_DDL = """
CREATE TABLE IF NOT EXISTS telemetry_runs (
    id TEXT PRIMARY KEY, backend TEXT NOT NULL, session_id TEXT NOT NULL,
    mode TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT, status TEXT NOT NULL DEFAULT 'running'
);
CREATE INDEX IF NOT EXISTS telemetry_runs_session ON telemetry_runs(session_id, status);
CREATE TABLE IF NOT EXISTS telemetry_phases (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, phase TEXT NOT NULL, job_slug TEXT,
    started_at TEXT NOT NULL, ended_at TEXT, status TEXT NOT NULL DEFAULT 'running'
);
CREATE TABLE IF NOT EXISTS telemetry_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, phase_id TEXT,
    backend TEXT NOT NULL, session_id TEXT NOT NULL, model TEXT, recorded_at TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0, reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    raw_usage TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS telemetry_outcomes (
    run_id TEXT NOT NULL, job_slug TEXT NOT NULL, decision TEXT,
    tailored INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(run_id, job_slug)
);
CREATE TABLE IF NOT EXISTS telemetry_counters (
    counter_key TEXT PRIMARY KEY, value INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class TelemetryEvent:
    backend: str
    session_id: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    raw_usage: dict[str, Any] | None = None
    recorded_at: str = ""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    return conn


def classify_job_hunter_mode(prompt: str) -> str | None:
    text = " ".join(prompt.lower().replace("_", "-").split())
    if re.search(r"(?:/|\$)?job[\s-]+hunter\s+batch\s+lite\b", text):
        return "batch-lite"
    match = re.search(
        r"(?:/|\$)?job[\s-]+hunter\s+(batch|one|screen|finalize|tailor|score|research|interview|outreach|stories)\b",
        text,
    )
    if match:
        return match.group(1)
    if re.search(r"\b(?:run|start|process)\s+(?:the\s+)?(?:job[\s-]+hunter\s+)?batch\b", text):
        return "batch"
    if re.fullmatch(r"https?://\S+", text):
        return "one"
    return None


def begin_run(db_path: Path, *, backend: str, session_id: str, mode: str) -> str:
    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM telemetry_runs WHERE session_id=? AND status='running' ORDER BY started_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if existing:
            conn.execute("UPDATE telemetry_runs SET mode=?, backend=? WHERE id=?", (mode, backend, existing["id"]))
            return str(existing["id"])
        run_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO telemetry_runs(id,backend,session_id,mode,started_at) VALUES(?,?,?,?,?)",
            (run_id, backend, session_id, mode, _now()),
        )
        return run_id


def active_run(db_path: Path, session_id: str | None = None) -> str | None:
    query = "SELECT id FROM telemetry_runs WHERE status='running'"
    params: tuple[str, ...] = ()
    if session_id:
        query += " AND session_id=?"
        params = (session_id,)
    query += " ORDER BY started_at DESC LIMIT 1"
    with _connect(db_path) as conn:
        row = conn.execute(query, params).fetchone()
    return str(row["id"]) if row else None


def start_phase(db_path: Path, *, run_id: str, phase: str, job_slug: str = "") -> str:
    phase_id = uuid.uuid4().hex
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE telemetry_phases SET status='interrupted', ended_at=? WHERE run_id=? AND status='running'",
            (_now(), run_id),
        )
        conn.execute(
            "INSERT INTO telemetry_phases(id,run_id,phase,job_slug,started_at) VALUES(?,?,?,?,?)",
            (phase_id, run_id, phase, job_slug or None, _now()),
        )
    return phase_id


def end_phase(db_path: Path, phase_id: str, *, status: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE telemetry_phases SET status=?, ended_at=? WHERE id=? AND status='running'",
            (status, _now(), phase_id),
        )


def end_active_phase(db_path: Path, run_id: str, *, status: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE telemetry_phases SET status=?, ended_at=? WHERE run_id=? AND status='running'",
            (status, _now(), run_id),
        )


def end_run(db_path: Path, run_id: str, *, status: str) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE telemetry_phases SET status='interrupted', ended_at=? WHERE run_id=? AND status='running'",
            (_now(), run_id),
        )
        conn.execute(
            "UPDATE telemetry_runs SET status=?, ended_at=? WHERE id=? AND status='running'",
            (status, _now(), run_id),
        )


def record_outcome(
    db_path: Path,
    *,
    run_id: str,
    job_slug: str,
    decision: str = "",
    tailored: bool = False,
    failed: bool = False,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """INSERT INTO telemetry_outcomes(run_id,job_slug,decision,tailored,failed) VALUES(?,?,?,?,?)
               ON CONFLICT(run_id,job_slug) DO UPDATE SET
               decision=CASE WHEN excluded.decision='' THEN telemetry_outcomes.decision ELSE excluded.decision END,
               tailored=MAX(telemetry_outcomes.tailored, excluded.tailored),
               failed=MAX(telemetry_outcomes.failed, excluded.failed)""",
            (run_id, job_slug, decision.upper(), tailored, failed),
        )


def _safe_raw(event: TelemetryEvent) -> dict[str, int]:
    raw = event.raw_usage or {}
    safe = {key: int(raw.get(key, getattr(event, key, 0)) or 0) for key in _TOKEN_FIELDS}
    return safe


def _record_event(conn: sqlite3.Connection, event: TelemetryEvent) -> bool:
    run = conn.execute(
        "SELECT id FROM telemetry_runs WHERE session_id=? ORDER BY started_at DESC LIMIT 1",
        (event.session_id,),
    ).fetchone()
    if not run:
        return False
    phase = conn.execute(
        """SELECT id FROM telemetry_phases WHERE run_id=?
           ORDER BY CASE WHEN status='running' THEN 0 ELSE 1 END, started_at DESC LIMIT 1""",
        (run["id"],),
    ).fetchone()
    raw = _safe_raw(event)
    conn.execute(
        """INSERT INTO telemetry_events(
           run_id,phase_id,backend,session_id,model,recorded_at,
           input_tokens,output_tokens,cached_tokens,reasoning_tokens,raw_usage)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            run["id"],
            phase["id"] if phase else None,
            event.backend,
            event.session_id,
            event.model,
            event.recorded_at or _now(),
            event.input_tokens,
            event.output_tokens,
            event.cached_tokens,
            event.reasoning_tokens,
            json.dumps(raw),
        ),
    )
    return True


def _attrs(items: list[dict[str, Any]] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items or []:
        value = item.get("value", {})
        result[str(item.get("key", ""))] = next(iter(value.values()), None) if isinstance(value, dict) else value
    return result


def _claude_events(payload: dict[str, Any]) -> list[tuple[TelemetryEvent, str, int]]:
    result: list[tuple[TelemetryEvent, str, int]] = []
    for resource in payload.get("resourceMetrics", []):
        resource_attrs = _attrs(resource.get("resource", {}).get("attributes"))
        backend = "claude-code" if resource_attrs.get("service.name") == "claude-code" else "claude-code"
        for scope in resource.get("scopeMetrics", []):
            for metric in scope.get("metrics", []):
                if metric.get("name") != "claude_code.token.usage":
                    continue
                points = metric.get("sum", {}).get("dataPoints", [])
                for point in points:
                    attrs = _attrs(point.get("attributes"))
                    token_type = str(attrs.get("type", ""))
                    value = int(point.get("asInt", point.get("asDouble", 0)) or 0)
                    field = {
                        "input": "input_tokens",
                        "output": "output_tokens",
                        "cacheRead": "cached_tokens",
                        "cache_read": "cached_tokens",
                        "cacheCreation": "cached_tokens",
                        "cache_creation": "cached_tokens",
                    }.get(token_type)
                    if not field or not attrs.get("session.id"):
                        continue
                    values = {name: 0 for name in _TOKEN_FIELDS}
                    values[field] = value
                    event = TelemetryEvent(
                        backend=backend,
                        session_id=str(attrs["session.id"]),
                        model=str(attrs.get("model", "")),
                        **values,
                    )
                    key = f"{backend}:{event.session_id}:{event.model}:{token_type}"
                    result.append((event, key, value))
    return result


def _log_events(payload: dict[str, Any]) -> list[TelemetryEvent]:
    result: list[TelemetryEvent] = []
    for resource in payload.get("resourceLogs", []):
        resource_attrs = _attrs(resource.get("resource", {}).get("attributes"))
        service = str(resource_attrs.get("service.name", "codex"))
        backend = "claude-code" if service in {"claude-code", "claude_code"} else "codex"
        for scope in resource.get("scopeLogs", []):
            for record in scope.get("logRecords", []):
                attrs = _attrs(record.get("attributes"))
                kind = attrs.get("event.kind") or attrs.get("kind")
                body = record.get("body", {})
                event_name = (next(iter(body.values()), "") if isinstance(body, dict) else str(body)) or attrs.get(
                    "event.name"
                )
                is_codex_usage = kind == "response.completed"
                is_claude_usage = "api_request" in str(event_name) and backend == "claude-code"
                if not (is_codex_usage or is_claude_usage):
                    continue
                session_id = attrs.get("conversation.id") or attrs.get("session.id")
                if not session_id:
                    continue
                result.append(
                    TelemetryEvent(
                        backend=backend,
                        session_id=str(session_id),
                        model=str(attrs.get("model", "")),
                        input_tokens=int(
                            attrs.get(
                                "input_tokens",
                                attrs.get("input_token_count", attrs.get("gen_ai.usage.input_tokens", 0)),
                            )
                            or 0
                        ),
                        output_tokens=int(
                            attrs.get(
                                "output_tokens",
                                attrs.get("output_token_count", attrs.get("gen_ai.usage.output_tokens", 0)),
                            )
                            or 0
                        ),
                        cached_tokens=int(
                            attrs.get("cached_input_tokens", attrs.get("cached_input_token_count", 0)) or 0
                        ),
                        reasoning_tokens=int(
                            attrs.get("reasoning_output_tokens", attrs.get("reasoning_output_token_count", 0)) or 0
                        ),
                        recorded_at=_otlp_time(record.get("timeUnixNano")),
                    )
                )
    return result


def _otlp_time(value: Any) -> str:
    try:
        return datetime.fromtimestamp(int(value) / 1_000_000_000, UTC).isoformat() if value else ""
    except (TypeError, ValueError, OSError):
        return ""


def ingest_otlp(db_path: Path, payload: dict[str, Any] | list[TelemetryEvent]) -> int:
    with _connect(db_path) as conn:
        if isinstance(payload, list):
            return sum(_record_event(conn, event) for event in payload)
        count = 0
        for event, counter_key, value in _claude_events(payload):
            old = conn.execute("SELECT value FROM telemetry_counters WHERE counter_key=?", (counter_key,)).fetchone()
            delta = max(0, value - int(old["value"])) if old else value
            conn.execute(
                "INSERT INTO telemetry_counters(counter_key,value) VALUES(?,?) "
                "ON CONFLICT(counter_key) DO UPDATE SET value=excluded.value",
                (counter_key, value),
            )
            if delta:
                values = asdict(event)
                field = next(name for name in _TOKEN_FIELDS if values[name])
                values[field] = delta
                count += _record_event(conn, TelemetryEvent(**values))
        for event in _log_events(payload):
            count += _record_event(conn, event)
        return count


def _token_totals(rows: list[sqlite3.Row]) -> dict[str, int]:
    return {field: sum(int(row[field] or 0) for row in rows) for field in _TOKEN_FIELDS}


def get_telemetry_summary(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {
            "runs": [],
            "totals": _token_totals([]),
            "by_backend": {},
            "by_mode": {},
            "by_phase": {},
            "by_job": {},
            "outcomes": {"processed": 0, "apply": 0, "skip": 0, "tailored": 0, "failed": 0},
        }
    with _connect(db_path) as conn:
        events = conn.execute(
            """SELECT e.*, r.mode, p.phase, p.job_slug
               FROM telemetry_events e JOIN telemetry_runs r ON r.id=e.run_id
               LEFT JOIN telemetry_phases p ON p.id=e.phase_id"""
        ).fetchall()
        runs = [
            dict(row)
            for row in conn.execute(
                """SELECT r.*, COUNT(CASE WHEN p.status='interrupted' THEN 1 END) AS incomplete_phases
                   FROM telemetry_runs r LEFT JOIN telemetry_phases p ON p.run_id=r.id
                   GROUP BY r.id ORDER BY r.started_at DESC"""
            ).fetchall()
        ]
        outcomes = conn.execute("SELECT decision,tailored,failed FROM telemetry_outcomes").fetchall()

    def grouped(key: str) -> dict[str, dict[str, int]]:
        values: dict[str, list[sqlite3.Row]] = {}
        for row in events:
            label = str(row[key] or "unattributed")
            values.setdefault(label, []).append(row)
        return {label: _token_totals(group) for label, group in values.items()}

    return {
        "runs": runs,
        "totals": _token_totals(events),
        "by_backend": grouped("backend"),
        "by_mode": grouped("mode"),
        "by_phase": grouped("phase"),
        "by_job": grouped("job_slug"),
        "outcomes": {
            "processed": len(outcomes),
            "apply": sum(row["decision"] == "APPLY" for row in outcomes),
            "skip": sum(row["decision"] == "SKIP" for row in outcomes),
            "tailored": sum(bool(row["tailored"]) for row in outcomes),
            "failed": sum(bool(row["failed"]) for row in outcomes),
        },
    }
