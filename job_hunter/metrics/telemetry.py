"""Normalized token telemetry for agent and direct-LLM execution."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from collections import Counter
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
_CORRELATION_WINDOW = timedelta(hours=2)
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


def model_family(model: str) -> str:
    """Collapse a model string to its family, e.g. claude-sonnet-4-6 -> claude-sonnet."""
    if not model:
        return ""
    return re.sub(r"(?:[-_]v?\d[\d.]*)+$", "", model) or model


def begin_run(db_path: Path, *, backend: str, session_id: str, mode: str, app_entrypoint: str = "") -> str:
    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM telemetry_runs WHERE session_id=? AND status='running' ORDER BY started_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE telemetry_runs SET mode=?, backend=?, message_count=message_count+1 WHERE id=?",
                (mode, backend, existing["id"]),
            )
            return str(existing["id"])
        run_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO telemetry_runs(id,backend,session_id,mode,started_at,app_entrypoint) VALUES(?,?,?,?,?,?)",
            (run_id, backend, session_id, mode, _now(), app_entrypoint),
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
    """Correlate an incoming event to a run: exact session id, then safe fallbacks.

    Claude/Codex hook session ids and OTLP resource session ids are not guaranteed
    to be byte-identical (different fields, different processes exporting late), so
    an exact-match-only lookup silently drops legitimate token events. Fall back
    conservatively rather than attributing to an unrelated run.
    """
    row = conn.execute(
        "SELECT id FROM telemetry_runs WHERE session_id=? ORDER BY started_at DESC LIMIT 1",
        (event.session_id,),
    ).fetchone()
    if row:
        return str(row["id"])

    now = _parse_ts(event.recorded_at) or datetime.now(UTC)
    candidates = conn.execute(
        "SELECT id, started_at FROM telemetry_runs WHERE backend=? ORDER BY started_at DESC LIMIT 1",
        (event.backend,),
    ).fetchall()
    for candidate in candidates:
        started = _parse_ts(candidate["started_at"])
        if started and abs(now - started) <= _CORRELATION_WINDOW:
            return str(candidate["id"])

    running = conn.execute("SELECT id FROM telemetry_runs WHERE status='running'").fetchall()
    if len(running) == 1:
        return str(running[0]["id"])
    return None


def _record_event(conn: sqlite3.Connection, event: TelemetryEvent, *, source: str = "unknown") -> bool:
    run_id = _find_run_for_event(conn, event) or _UNATTRIBUTED
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


def _peak_hour(events: list[sqlite3.Row]) -> int | None:
    hours = [dt.hour for ts in [e["recorded_at"] for e in events] if (dt := _parse_ts(str(ts)))]
    return Counter(hours).most_common(1)[0][0] if hours else None


def _favorite_model(events: list[sqlite3.Row]) -> str:
    model_tokens: Counter[str] = Counter()
    for e in events:
        model = str(e["model"] or "")
        if model:
            model_tokens[model] += int(e["input_tokens"] or 0) + int(e["output_tokens"] or 0)
    return model_tokens.most_common(1)[0][0] if model_tokens else ""


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
        "peak_hour": _peak_hour(events),
        "favorite_model": _favorite_model(events),
        "daily": _daily_buckets(runs, events, outcomes or []),
    }


def _model_breakdown(events: list[sqlite3.Row]) -> dict[str, dict[str, Any]]:
    by_model: dict[str, list[sqlite3.Row]] = {}
    for row in events:
        label = str(row["model"] or "unknown")
        by_model.setdefault(label, []).append(row)
    total_tokens = sum(int(row["input_tokens"] or 0) + int(row["output_tokens"] or 0) for row in events) or 1
    result: dict[str, dict[str, Any]] = {}
    for model, rows in by_model.items():
        totals = _token_totals(rows)
        model_total = totals["input_tokens"] + totals["output_tokens"]
        result[model] = {**totals, "share": round(model_total / total_tokens * 100, 1)}
    return result


def get_telemetry_summary(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {
            "runs": [],
            "totals": _token_totals([]),
            "by_backend": {},
            "by_mode": {},
            "by_phase": {},
            "by_job": {},
            "by_model": {},
            "unattributed": {"count": 0, **_token_totals([])},
            "outcomes": {"processed": 0, "apply": 0, "skip": 0, "tailored": 0, "failed": 0},
            "operational": _operational_summary([], []),
            "token_status": "unavailable",
        }
    with _connect(db_path) as conn:
        events = conn.execute(
            """SELECT e.*, r.mode, r.backend AS run_backend, p.phase, p.job_slug
               FROM telemetry_events e LEFT JOIN telemetry_runs r ON r.id=e.run_id
               LEFT JOIN telemetry_phases p ON p.id=e.phase_id"""
        ).fetchall()
        runs_raw = conn.execute(
            """SELECT r.*, COUNT(CASE WHEN p.status='interrupted' THEN 1 END) AS incomplete_phases
               FROM telemetry_runs r LEFT JOIN telemetry_phases p ON p.run_id=r.id
               GROUP BY r.id ORDER BY r.started_at DESC"""
        ).fetchall()
        outcomes = conn.execute("SELECT decision,tailored,failed,recorded_at FROM telemetry_outcomes").fetchall()

    events_by_run: dict[str, int] = Counter(str(row["run_id"]) for row in events if row["run_id"] != _UNATTRIBUTED)
    runs = []
    for row in runs_raw:
        run = dict(row)
        run["token_status"] = "observed" if events_by_run.get(str(row["id"])) else "unavailable"
        runs.append(run)

    unattributed_events = [row for row in events if row["run_id"] == _UNATTRIBUTED]

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
        "by_model": _model_breakdown(events),
        "unattributed": {"count": len(unattributed_events), **_token_totals(unattributed_events)},
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
    events_total = sum(summary["totals"].values())
    latest_run = summary["runs"][0] if summary["runs"] else None
    active_runs = event_count = 0
    by_backend: list[sqlite3.Row] = []
    latest_event = latest_phase = None
    if db_path.exists():
        with _connect(db_path) as conn:
            active_runs = conn.execute("SELECT COUNT(*) AS n FROM telemetry_runs WHERE status='running'").fetchone()[
                "n"
            ]
            event_count = conn.execute("SELECT COUNT(*) AS n FROM telemetry_events").fetchone()["n"]
            by_backend = conn.execute("SELECT backend, COUNT(*) AS n FROM telemetry_events GROUP BY backend").fetchall()
            latest_event = conn.execute(
                "SELECT backend, session_id, model, recorded_at, token_source, run_id FROM telemetry_events "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()
            latest_phase = conn.execute(
                "SELECT phase, status, job_slug FROM telemetry_phases ORDER BY started_at DESC LIMIT 1"
            ).fetchone()

    hooks_but_no_events = (claude_hooks or codex_hooks) and event_count == 0 and (active_runs > 0 or latest_run)

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
        "token_total_observed": events_total,
        "latest_event": dict(latest_event) if latest_event else None,
        "claude_hooks_wired": claude_hooks,
        "codex_hooks_wired": codex_hooks,
        "codex_otel_configured": codex_otel,
        "hooks_wired_but_no_otel_events": bool(hooks_but_no_events),
    }
