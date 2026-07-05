"""Normalized token telemetry for agent and direct-LLM execution."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

_TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "reasoning_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
)
_UNATTRIBUTED = "unattributed"
_ACTIVE_WINDOW = timedelta(hours=12)
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
# (table, column, declaration) — additive, backward-compatible with existing metrics.db files.
_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("telemetry_events", "cache_read_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("telemetry_events", "cache_creation_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("telemetry_events", "token_source", "TEXT NOT NULL DEFAULT 'unknown'"),
    ("telemetry_events", "app_entrypoint", "TEXT NOT NULL DEFAULT ''"),
    ("telemetry_events", "model_family", "TEXT NOT NULL DEFAULT ''"),
    ("telemetry_runs", "message_count", "INTEGER NOT NULL DEFAULT 1"),
    ("telemetry_runs", "app_entrypoint", "TEXT NOT NULL DEFAULT ''"),
    ("telemetry_runs", "root_skill", "TEXT NOT NULL DEFAULT ''"),
    ("telemetry_runs", "skill", "TEXT NOT NULL DEFAULT ''"),
    ("telemetry_runs", "skill_display", "TEXT NOT NULL DEFAULT ''"),
    ("telemetry_outcomes", "recorded_at", "TEXT NOT NULL DEFAULT ''"),
)


@dataclass(frozen=True)
class TelemetryEvent:
    backend: str
    session_id: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    raw_usage: dict[str, Any] | None = None
    recorded_at: str = ""
    app_entrypoint: str = ""


@dataclass(frozen=True)
class SkillInvocation:
    root_skill: str
    skill: str
    skill_display: str
    source: str = "prompt"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, decl in _MIGRATIONS:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    _migrate(conn)
    return conn


_SKILLS = {
    "batch": ("batch", "Batch"),
    "one": ("one", "One Job"),
    "screen": ("screening", "Screening"),
    "score": ("scoring", "Scoring"),
    "tailor": ("tailoring", "Tailoring"),
    "research": ("research", "Research"),
    "interview": ("interview", "Interview"),
    "outreach": ("outreach", "Outreach"),
    "stories": ("stories", "Stories"),
    "finalize": ("finalize", "Finalize"),
}
_LINKEDIN_SKILLS = {
    "ideas": ("linkedin_ideas", "LinkedIn Ideas"),
    "draft": ("linkedin_draft", "LinkedIn Draft"),
    "engage": ("linkedin_engage", "LinkedIn Engage"),
    "network": ("linkedin_network", "LinkedIn Network"),
}


def classify_job_hunter_skill_prompt(prompt: str) -> SkillInvocation | None:
    """Classify only explicit Job Hunter-owned slash commands."""
    text = " ".join(prompt.strip().split())
    linkedin = re.match(r"^/(?:job-hunter\s+)?linkedin\s+(ideas|draft|engage|network)\b", text, re.IGNORECASE)
    if linkedin:
        skill, display = _LINKEDIN_SKILLS[linkedin.group(1).lower()]
        return SkillInvocation("job-hunter", skill, display)
    match = re.match(
        r"^/job-hunter\s+(batch|one|screen|score|tailor|research|interview|outreach|stories|finalize)\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    command = match.group(1).lower()
    if command == "one" and not re.match(r"^/job-hunter\s+one\s+https?://\S+", text, re.IGNORECASE):
        return None
    skill, display = _SKILLS[command]
    return SkillInvocation("job-hunter", skill, display)


def classify_job_hunter_mode(prompt: str) -> str | None:
    """Backward-compatible wrapper; new callers should use the strict skill classifier."""
    invocation = classify_job_hunter_skill_prompt(prompt)
    return invocation.skill if invocation else None


def model_family(model: str) -> str:
    """Collapse a model string to its family, e.g. claude-sonnet-4-6 -> claude-sonnet."""
    if not model:
        return ""
    return re.sub(r"(?:[-_]v?\d[\d.]*)+$", "", model) or model


def _interrupt_stale_runs(conn: sqlite3.Connection, now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    cutoff = (current - _ACTIVE_WINDOW).isoformat()
    ended = current.isoformat()
    cursor = conn.execute(
        """UPDATE telemetry_runs SET status='interrupted', ended_at=?
           WHERE status='running' AND started_at < ?""",
        (ended, cutoff),
    )
    conn.execute(
        """UPDATE telemetry_phases SET status='interrupted', ended_at=?
           WHERE status='running' AND run_id IN (
               SELECT id FROM telemetry_runs WHERE status='interrupted' AND ended_at=?
           )""",
        (ended, ended),
    )
    return cursor.rowcount


def begin_run(
    db_path: Path,
    *,
    backend: str,
    session_id: str,
    mode: str,
    app_entrypoint: str = "",
    root_skill: str = "job-hunter",
    skill: str = "",
    skill_display: str = "",
) -> str:
    skill = skill or mode
    skill_display = skill_display or skill.replace("_", " ").title()
    with _connect(db_path) as conn:
        _interrupt_stale_runs(conn)
        existing = conn.execute(
            """SELECT id, skill FROM telemetry_runs
               WHERE session_id=? AND backend=? AND status='running'
               AND root_skill!='' AND skill!=''
               ORDER BY started_at DESC LIMIT 1""",
            (session_id, backend),
        ).fetchone()
        if existing and existing["skill"] == skill:
            conn.execute(
                """UPDATE telemetry_runs SET mode=?, root_skill=?, skill=?, skill_display=?,
                   app_entrypoint=?, message_count=message_count+1 WHERE id=?""",
                (mode, root_skill, skill, skill_display, app_entrypoint, existing["id"]),
            )
            return str(existing["id"])
        if existing:
            end_run_id = str(existing["id"])
            conn.execute(
                "UPDATE telemetry_runs SET status='interrupted', ended_at=? WHERE id=?",
                (_now(), end_run_id),
            )
        run_id = uuid.uuid4().hex
        conn.execute(
            """INSERT INTO telemetry_runs(
               id,backend,session_id,mode,started_at,app_entrypoint,root_skill,skill,skill_display)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (run_id, backend, session_id, mode, _now(), app_entrypoint, root_skill, skill, skill_display),
        )
        return run_id


def active_run(db_path: Path, session_id: str | None = None) -> str | None:
    query = "SELECT id FROM telemetry_runs WHERE status='running' AND root_skill!='' AND skill!=''"
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
            """INSERT INTO telemetry_outcomes(run_id,job_slug,decision,tailored,failed,recorded_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(run_id,job_slug) DO UPDATE SET
               decision=CASE WHEN excluded.decision='' THEN telemetry_outcomes.decision ELSE excluded.decision END,
               tailored=MAX(telemetry_outcomes.tailored, excluded.tailored),
               failed=MAX(telemetry_outcomes.failed, excluded.failed)""",
            (run_id, job_slug, decision.upper(), tailored, failed, _now()),
        )


def _safe_raw(event: TelemetryEvent) -> dict[str, int]:
    raw = event.raw_usage or {}
    safe = {key: int(raw.get(key, getattr(event, key, 0)) or 0) for key in _TOKEN_FIELDS}
    return safe


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _find_run_for_event(conn: sqlite3.Connection, event: TelemetryEvent) -> str | None:
    """Correlate only to an active, backend-matched Job Hunter-owned run."""
    event_time = _parse_ts(event.recorded_at) or datetime.now(UTC)
    _interrupt_stale_runs(conn, event_time)
    row = conn.execute(
        """SELECT id, started_at FROM telemetry_runs
           WHERE session_id=? AND backend=? AND status='running'
           AND root_skill!='' AND skill!=''
           ORDER BY started_at DESC LIMIT 1""",
        (event.session_id, event.backend),
    ).fetchone()
    if row and (started := _parse_ts(row["started_at"])) and started <= event_time <= started + _ACTIVE_WINDOW:
        return str(row["id"])

    candidates = conn.execute(
        """SELECT id, started_at FROM telemetry_runs
           WHERE backend=? AND status='running' AND root_skill!='' AND skill!=''""",
        (event.backend,),
    ).fetchall()
    eligible = [
        candidate
        for candidate in candidates
        if (started := _parse_ts(candidate["started_at"])) and started <= event_time <= started + _ACTIVE_WINDOW
    ]
    if len(eligible) == 1:
        return str(eligible[0]["id"])
    return None


def _increment_ignored(conn: sqlite3.Connection, event: TelemetryEvent) -> None:
    counters = {
        "telemetry_ignored_events": 1,
        "telemetry_ignored_input_tokens": event.input_tokens,
        "telemetry_ignored_output_tokens": event.output_tokens,
        "telemetry_ignored_reason_not_job_hunter_skill": 1,
    }
    for key, value in counters.items():
        conn.execute(
            """INSERT INTO telemetry_counters(counter_key,value) VALUES(?,?)
               ON CONFLICT(counter_key) DO UPDATE SET value=value+excluded.value""",
            (key, int(value or 0)),
        )


def _record_event(conn: sqlite3.Connection, event: TelemetryEvent, *, source: str = "unknown") -> bool:
    run_id = _find_run_for_event(conn, event)
    if not run_id:
        _increment_ignored(conn, event)
        return False
    phase = conn.execute(
        """SELECT id FROM telemetry_phases WHERE run_id=?
           ORDER BY CASE WHEN status='running' THEN 0 ELSE 1 END, started_at DESC LIMIT 1""",
        (run_id,),
    ).fetchone()
    raw = _safe_raw(event)
    conn.execute(
        """INSERT INTO telemetry_events(
           run_id,phase_id,backend,session_id,model,recorded_at,
           input_tokens,output_tokens,cached_tokens,reasoning_tokens,
           cache_read_tokens,cache_creation_tokens,token_source,app_entrypoint,model_family,raw_usage)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            run_id,
            phase["id"] if phase else None,
            event.backend,
            event.session_id,
            event.model,
            event.recorded_at or _now(),
            event.input_tokens,
            event.output_tokens,
            event.cached_tokens,
            event.reasoning_tokens,
            event.cache_read_tokens,
            event.cache_creation_tokens,
            source,
            event.app_entrypoint,
            model_family(event.model),
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
        entrypoint = str(resource_attrs.get("app.entrypoint", ""))
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
                        "cacheRead": "cache_read_tokens",
                        "cache_read": "cache_read_tokens",
                        "cacheCreation": "cache_creation_tokens",
                        "cache_creation": "cache_creation_tokens",
                    }.get(token_type)
                    if not field or not attrs.get("session.id"):
                        continue
                    values = {name: 0 for name in _TOKEN_FIELDS}
                    values[field] = value
                    event = TelemetryEvent(
                        backend=backend,
                        session_id=str(attrs["session.id"]),
                        model=str(attrs.get("model", "")),
                        app_entrypoint=str(attrs.get("app.entrypoint", entrypoint)),
                        **values,
                    )
                    key = f"{backend}:{event.session_id}:{event.model}:{token_type}"
                    result.append((event, key, value))
    return result


def _log_events(payload: dict[str, Any]) -> list[tuple[TelemetryEvent, str]]:
    result: list[tuple[TelemetryEvent, str]] = []
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
                source = "claude_otel_log" if backend == "claude-code" else "codex_otel"
                result.append(
                    (
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
                            cache_read_tokens=int(
                                attrs.get(
                                    "cache_read_tokens",
                                    attrs.get("cached_input_tokens", attrs.get("cached_input_token_count", 0)),
                                )
                                or 0
                            ),
                            cache_creation_tokens=int(attrs.get("cache_creation_tokens", 0) or 0),
                            reasoning_tokens=int(
                                attrs.get("reasoning_output_tokens", attrs.get("reasoning_output_token_count", 0)) or 0
                            ),
                            app_entrypoint=str(attrs.get("app.entrypoint", "")),
                            recorded_at=_otlp_time(record.get("timeUnixNano")),
                        ),
                        source,
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
            return sum(_record_event(conn, event, source="api") for event in payload)
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
                count += _record_event(conn, TelemetryEvent(**values), source="claude_otel_metric")
        for event, event_source in _log_events(payload):
            count += _record_event(conn, event, source=event_source)
        return count


def _token_totals(rows: list[sqlite3.Row]) -> dict[str, int]:
    return {field: sum(int(row[field] or 0) for row in rows) for field in _TOKEN_FIELDS}


def _active_dates(timestamps: list[str]) -> list[date]:
    dates = set()
    for ts in timestamps:
        parsed = _parse_ts(ts)
        if parsed:
            dates.add(parsed.date())
    return sorted(dates)


def _streaks(active_days: list[date]) -> tuple[int, int]:
    if not active_days:
        return 0, 0
    longest = current = 1
    best = 1
    for prev, curr in zip(active_days, active_days[1:], strict=False):
        if (curr - prev).days == 1:
            current += 1
        else:
            current = 1
        best = max(best, current)
    longest = best
    today = datetime.now(UTC).date()
    last = active_days[-1]
    if last not in (today, today - timedelta(days=1)):
        current_streak = 0
    else:
        current_streak = 1
        for prev, curr in zip(reversed(active_days[:-1]), reversed(active_days[1:]), strict=False):
            if (curr - prev).days == 1:
                current_streak += 1
            else:
                break
    return current_streak, longest


def _apply_outcome_to_bucket(entry: dict[str, int], outcome: sqlite3.Row) -> None:
    if outcome["decision"] == "APPLY":
        entry["apply"] += 1
    elif outcome["decision"] == "SKIP":
        entry["skip"] += 1
    if outcome["tailored"]:
        entry["tailored"] += 1
    if outcome["failed"]:
        entry["failed"] += 1


def _daily_buckets(
    runs: list[sqlite3.Row], events: list[sqlite3.Row], outcomes: list[sqlite3.Row]
) -> dict[str, dict[str, int]]:
    daily: dict[str, dict[str, int]] = {}

    def bucket(key: str) -> dict[str, int]:
        return daily.setdefault(key, {"runs": 0, "tokens": 0, "apply": 0, "skip": 0, "tailored": 0, "failed": 0})

    for r in runs:
        d = _parse_ts(str(r["started_at"]))
        if d:
            bucket(d.date().isoformat())["runs"] += 1
    for e in events:
        d = _parse_ts(str(e["recorded_at"]))
        if d:
            bucket(d.date().isoformat())["tokens"] += int(e["input_tokens"] or 0) + int(e["output_tokens"] or 0)
    for o in outcomes:
        d = _parse_ts(str(o["recorded_at"] or ""))
        if d:
            _apply_outcome_to_bucket(bucket(d.date().isoformat()), o)
    return daily


def _phase_durations(conn: sqlite3.Connection) -> dict[str, dict[str, float]]:
    """Aggregate wall-clock duration per phase name from already-recorded start/end
    timestamps — no new instrumentation, just a summary over telemetry_phases."""
    rows = conn.execute(
        "SELECT phase, started_at, ended_at FROM telemetry_phases WHERE ended_at IS NOT NULL"
    ).fetchall()
    buckets: dict[str, list[float]] = {}
    for row in rows:
        started = _parse_ts(str(row["started_at"]))
        ended = _parse_ts(str(row["ended_at"]))
        if not started or not ended:
            continue
        seconds = (ended - started).total_seconds()
        if seconds < 0:
            continue
        buckets.setdefault(str(row["phase"]), []).append(seconds)
    return {
        phase: {
            "count": len(seconds_list),
            "total_seconds": round(sum(seconds_list), 2),
            "avg_seconds": round(sum(seconds_list) / len(seconds_list), 2),
        }
        for phase, seconds_list in buckets.items()
    }


def _operational_summary(
    runs: list[sqlite3.Row], events: list[sqlite3.Row], outcomes: list[sqlite3.Row] | None = None
) -> dict[str, Any]:
    active_days = _active_dates([str(r["started_at"]) for r in runs])
    current_streak, longest_streak = _streaks(active_days)

    return {
        "sessions": len({str(r["session_id"]) for r in runs}),
        "messages": sum(int(r["message_count"] or 1) for r in runs),
        "active_days": len(active_days),
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "daily": _daily_buckets(runs, events, outcomes or []),
    }


def _event_stats(rows: list[sqlite3.Row]) -> dict[str, int]:
    totals = _token_totals(rows)
    run_rows: dict[str, sqlite3.Row] = {}
    for row in rows:
        run_rows[str(row["run_id"])] = row
    return {
        **totals,
        "total_tokens": totals["input_tokens"] + totals["output_tokens"],
        "sessions": len({str(row["session_id"]) for row in run_rows.values()}),
        "messages": sum(int(row["message_count"] or 1) for row in run_rows.values()),
    }


def _ignored_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT counter_key,value FROM telemetry_counters WHERE counter_key LIKE 'telemetry_ignored_%'"
    ).fetchall()
    values = {str(row["counter_key"]): int(row["value"]) for row in rows}
    return {
        "events": values.get("telemetry_ignored_events", 0),
        "input_tokens": values.get("telemetry_ignored_input_tokens", 0),
        "output_tokens": values.get("telemetry_ignored_output_tokens", 0),
        "reason": "not_job_hunter_skill",
    }


def get_telemetry_summary(db_path: Path) -> dict[str, Any]:
    empty = {
        "totals": _event_stats([]),
        "by_skill": {},
        "by_backend": {},
        "by_skill_backend": {},
        "by_phase": {},
        "phase_durations": {},
        "ignored": {"events": 0, "input_tokens": 0, "output_tokens": 0, "reason": "not_job_hunter_skill"},
        "outcomes": {"processed": 0, "apply": 0, "skip": 0, "tailored": 0, "failed": 0},
        "operational": _operational_summary([], []),
        "token_status": "unavailable",
    }
    if not db_path.exists():
        return empty
    with _connect(db_path) as conn:
        events = conn.execute(
            """SELECT e.*, r.root_skill, r.skill, r.skill_display, r.message_count,
                      r.backend AS run_backend, p.phase, p.job_slug
               FROM telemetry_events e
               JOIN telemetry_runs r ON r.id=e.run_id
               LEFT JOIN telemetry_phases p ON p.id=e.phase_id
               WHERE e.run_id!='unattributed' AND r.root_skill!='' AND r.skill!=''"""
        ).fetchall()
        runs_raw = conn.execute(
            """SELECT r.*, COUNT(CASE WHEN p.status='interrupted' THEN 1 END) AS incomplete_phases
               FROM telemetry_runs r LEFT JOIN telemetry_phases p ON p.run_id=r.id
               WHERE r.root_skill!='' AND r.skill!=''
               GROUP BY r.id ORDER BY r.started_at DESC"""
        ).fetchall()
        outcomes = conn.execute(
            """SELECT o.decision,o.tailored,o.failed,o.recorded_at
               FROM telemetry_outcomes o JOIN telemetry_runs r ON r.id=o.run_id
               WHERE r.root_skill!='' AND r.skill!=''"""
        ).fetchall()
        ignored = _ignored_summary(conn)
        phase_durations = _phase_durations(conn)

    def grouped(key: str, *, skip_empty: bool = False) -> dict[str, dict[str, int]]:
        values: dict[str, list[sqlite3.Row]] = {}
        for row in events:
            label = str(row[key] or "")
            if skip_empty and not label:
                continue
            values.setdefault(label, []).append(row)
        return {label: _event_stats(group) for label, group in values.items()}

    by_skill = grouped("skill")
    by_backend = grouped("run_backend")
    by_phase = grouped("phase", skip_empty=True)
    by_skill_backend: dict[str, dict[str, dict[str, int]]] = {}
    for skill in by_skill:
        skill_rows = [row for row in events if row["skill"] == skill]
        backends = {
            backend: _event_stats([row for row in skill_rows if row["run_backend"] == backend])
            for backend in ("claude-code", "codex")
        }
        by_skill_backend[skill] = {**backends, "total": _event_stats(skill_rows)}

    return {
        "totals": _event_stats(events),
        "by_skill": by_skill,
        "by_backend": by_backend,
        "by_skill_backend": by_skill_backend,
        "by_phase": by_phase,
        "phase_durations": phase_durations,
        "ignored": ignored,
        "outcomes": {
            "processed": len(outcomes),
            "apply": sum(row["decision"] == "APPLY" for row in outcomes),
            "skip": sum(row["decision"] == "SKIP" for row in outcomes),
            "tailored": sum(bool(row["tailored"]) for row in outcomes),
            "failed": sum(bool(row["failed"]) for row in outcomes),
        },
        "operational": _operational_summary(runs_raw, events, outcomes),
        "token_status": "observed" if events else "unavailable",
    }


def prune_unattributed(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    with _connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM telemetry_events WHERE run_id=?", (_UNATTRIBUTED,))
        return cursor.rowcount


def _hooks_present(path: Path, backend: str) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    needle = f"job-hunter internal telemetry-hook --backend {backend} --event prompt"
    prompt_hooks = (data.get("hooks") or {}).get("UserPromptSubmit") or []
    return any(
        needle in str(hook.get("command", ""))
        for group in prompt_hooks
        if isinstance(group, dict)
        for hook in group.get("hooks", [])
        if isinstance(hook, dict)
    )


def _codex_otel_configured(codex_home: Path) -> bool:
    import tomllib

    config_path = codex_home / "config.toml"
    if not config_path.exists():
        return False
    try:
        parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return False
    return "127.0.0.1:4318" in json.dumps(parsed.get("otel") or {})


def telemetry_status(root: Path) -> dict[str, Any]:
    """Privacy-safe diagnostic snapshot backing `job-hunter internal telemetry-status`
    and doctor's telemetry warnings — never includes prompt/response/tool content.
    """
    import os

    from job_hunter.metrics.collector import collector_health

    db_path = root / "outputs" / "state" / "metrics.db"
    health = collector_health()
    claude_hooks = _hooks_present(root / ".claude" / "settings.json", "claude-code")
    codex_hooks = _hooks_present(root / ".codex" / "hooks.json", "codex")
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    codex_otel = _codex_otel_configured(codex_home) if codex_home.exists() else None

    summary = get_telemetry_summary(db_path)
    events_total = summary["totals"]["total_tokens"]
    latest_run = None
    active_runs = event_count = unattributed_rows = 0
    by_backend: list[sqlite3.Row] = []
    backend_tokens: list[sqlite3.Row] = []
    by_entrypoint: list[sqlite3.Row] = []
    latest_event = latest_phase = None
    if db_path.exists():
        with _connect(db_path) as conn:
            active_runs = conn.execute(
                """SELECT COUNT(*) AS n FROM telemetry_runs
                   WHERE status='running' AND root_skill!='' AND skill!=''"""
            ).fetchone()["n"]
            event_count = conn.execute(
                """SELECT COUNT(*) AS n FROM telemetry_events e JOIN telemetry_runs r ON r.id=e.run_id
                   WHERE r.root_skill!='' AND r.skill!='' AND e.run_id!='unattributed'"""
            ).fetchone()["n"]
            unattributed_rows = conn.execute(
                "SELECT COUNT(*) AS n FROM telemetry_events WHERE run_id='unattributed'"
            ).fetchone()["n"]
            by_backend = conn.execute(
                """SELECT e.backend, COUNT(*) AS n FROM telemetry_events e
                   JOIN telemetry_runs r ON r.id=e.run_id
                   WHERE r.root_skill!='' AND r.skill!='' AND e.run_id!='unattributed'
                   GROUP BY e.backend"""
            ).fetchall()
            backend_tokens = conn.execute(
                """SELECT e.backend,
                          SUM(e.input_tokens) AS input_tokens,
                          SUM(e.output_tokens) AS output_tokens
                   FROM telemetry_events e JOIN telemetry_runs r ON r.id=e.run_id
                   WHERE r.root_skill!='' AND r.skill!='' AND e.run_id!='unattributed'
                   GROUP BY e.backend"""
            ).fetchall()
            by_entrypoint = conn.execute(
                """SELECT e.app_entrypoint, COUNT(*) AS n FROM telemetry_events e
                   JOIN telemetry_runs r ON r.id=e.run_id
                   WHERE r.root_skill!='' AND r.skill!='' AND e.run_id!='unattributed'
                   GROUP BY e.app_entrypoint"""
            ).fetchall()
            latest_event = conn.execute(
                """SELECT e.backend, e.session_id, e.model, e.recorded_at, e.token_source, e.run_id
                   FROM telemetry_events e JOIN telemetry_runs r ON r.id=e.run_id
                   WHERE r.root_skill!='' AND r.skill!='' AND e.run_id!='unattributed'
                   ORDER BY e.id DESC LIMIT 1"""
            ).fetchone()
            latest_phase = conn.execute(
                "SELECT phase, status, job_slug FROM telemetry_phases ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            latest_run_row = conn.execute(
                """SELECT * FROM telemetry_runs WHERE root_skill!='' AND skill!=''
                   ORDER BY started_at DESC LIMIT 1"""
            ).fetchone()
            latest_run = dict(latest_run_row) if latest_run_row else None

    hooks_but_no_events = (claude_hooks or codex_hooks) and event_count == 0 and (active_runs > 0 or latest_run)
    heartbeat_path = root / "outputs" / "state" / ".telemetry_hook_heartbeat"
    # The hook process writes this marker unconditionally, before any telemetry work that
    # could fail — so "heartbeat exists but zero runs ever recorded" proves the hook fires
    # (Claude Code/Codex IS invoking it) yet the Python process never manages to write a
    # run row. hooks_but_no_events can't see this: it requires a run to already exist.
    hooks_invoked_but_no_runs_ever = (
        (claude_hooks or codex_hooks) and heartbeat_path.exists() and active_runs == 0 and latest_run is None
    )

    return {
        "workspace_root": str(root),
        "metrics_db": str(db_path),
        "collector_healthy": health is not None,
        "collector_workspace": (health or {}).get("workspace", ""),
        "last_rejected_content_type": (health or {}).get("last_rejected_content_type", ""),
        "active_runs": active_runs,
        "latest_run": latest_run,
        "latest_phase": dict(latest_phase) if latest_phase else None,
        "event_count": event_count,
        "event_count_by_backend": {row["backend"]: row["n"] for row in by_backend},
        "tokens_by_backend": {
            row["backend"]: {
                "input_tokens": int(row["input_tokens"] or 0),
                "output_tokens": int(row["output_tokens"] or 0),
            }
            for row in backend_tokens
        },
        "event_count_by_app_entrypoint": {(row["app_entrypoint"] or "unknown"): row["n"] for row in by_entrypoint},
        "token_total_observed": events_total,
        "ignored_event_count": summary["ignored"]["events"],
        "old_unattributed_row_count": unattributed_rows,
        "pruning_recommended": unattributed_rows > 0,
        "latest_event": dict(latest_event) if latest_event else None,
        "claude_hooks_wired": claude_hooks,
        "codex_hooks_wired": codex_hooks,
        "codex_otel_configured": codex_otel,
        "hooks_wired_but_no_otel_events": bool(hooks_but_no_events),
        "hooks_invoked_but_no_runs_ever": bool(hooks_invoked_but_no_runs_ever),
    }
