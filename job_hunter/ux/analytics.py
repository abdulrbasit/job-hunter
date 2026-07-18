"""Application pipeline analytics — compute only, consumed by the web dashboard."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from job_hunter.tracking.applications import ApplicationRecord, filtered_applications


def analyze_pipeline(root: Path, *, days: int = 14) -> dict[str, Any]:
    apps = filtered_applications(root=root)
    by_status = Counter(str(app.get("status") or "unknown") for app in apps)
    by_region = Counter(str(app.get("region") or "unknown") or "unknown" for app in apps)
    by_source = Counter(_source_host(str(app.get("url") or "")) for app in apps)
    low_scores = _low_score_reasons(root, apps)
    stale = _stale_active_apps(apps, days=days)
    followups = _followup_candidates(apps, days=days)
    return {
        "total": len(apps),
        "by_status": dict(sorted(by_status.items())),
        "by_region": dict(sorted(by_region.items())),
        "source_quality": dict(sorted(by_source.items())),
        "low_score_reasons": low_scores,
        "stale_postings": stale,
        "followups": followups,
        "funnel": _funnel(root),
        "exclusion_reasons": _exclusion_reasons(root),
        "response_rate": _response_rate(root),
    }


def _funnel(root: Path) -> dict[str, int]:
    """found → screened → scored → tailored → applied → interview, each stage a count
    of jobs that reached at least that far (a superset of every later stage)."""
    from job_hunter.tracking.repository import count_by_status, count_scored

    counts = count_by_status(root)
    found = sum(counts.values())
    discarded = counts.get("discarded", 0)
    tailored = counts.get("tailored", 0)
    applied = counts.get("applied", 0)
    responded = counts.get("responded", 0)
    interview = counts.get("interview", 0)
    offer = counts.get("offer", 0)
    rejected = counts.get("rejected", 0)
    return {
        "found": found,
        "screened": found - discarded,
        "scored": count_scored(root),
        "tailored": tailored + applied + responded + interview + offer + rejected,
        "applied": applied + responded + interview + offer + rejected,
        "interview": interview + offer,
    }


def _exclusion_reasons(root: Path) -> dict[str, int]:
    from job_hunter.tracking.repository import count_by_rejection_reason

    return dict(sorted(count_by_rejection_reason(root).items(), key=lambda kv: -kv[1]))


def _response_rate(root: Path) -> float:
    """(responded + interview + offer) / applied — 0 when nothing has been applied to yet."""
    from job_hunter.tracking.repository import count_by_status

    counts = count_by_status(root)
    applied = (
        counts.get("applied", 0) + counts.get("responded", 0) + counts.get("interview", 0) + counts.get("offer", 0)
    )
    responded_or_further = counts.get("responded", 0) + counts.get("interview", 0) + counts.get("offer", 0)
    return round(responded_or_further / applied, 3) if applied else 0.0


def _source_host(url: str) -> str:
    if not url:
        return "unknown"
    host = urlparse(url).netloc.lower()
    return host.removeprefix("www.") or "unknown"


def _low_score_reasons(root: Path, apps: list[ApplicationRecord]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for app in apps:
        score = app.get("score")
        if not isinstance(score, int | float) or score >= 70:
            continue
        slug = str(app.get("slug") or "")
        score_path = root / "outputs" / "jobs" / slug / "score.yml"
        gaps: list[str] = []
        if score_path.exists():
            data = yaml.safe_load(score_path.read_text(encoding="utf-8")) or {}
            raw_gaps = data.get("gaps") or []
            if isinstance(raw_gaps, list):
                gaps = [str(gap)[:80] for gap in raw_gaps[:3]]
        items.append({"slug": slug, "score": score, "gaps": gaps})
    return items


def _stale_active_apps(apps: list[ApplicationRecord], *, days: int) -> list[dict[str, str]]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stale: list[dict[str, str]] = []
    for app in apps:
        status = str(app.get("status") or "")
        if status not in {"tailored", "applied", "responded", "interview"}:
            continue
        updated = _parse_timestamp(str(app.get("updated_at") or app.get("date") or ""))
        if updated and updated < cutoff:
            stale.append(
                {
                    "slug": str(app.get("slug") or ""),
                    "status": status,
                    "updated_at": str(app.get("updated_at") or app.get("date") or ""),
                }
            )
    return stale


def _followup_candidates(apps: list[ApplicationRecord], *, days: int) -> list[dict[str, str]]:
    by_status_days = defaultdict(lambda: days)
    by_status_days.update({"applied": 7, "responded": 3, "interview": 5})
    now = datetime.now(UTC)
    followups: list[dict[str, str]] = []
    for app in apps:
        status = str(app.get("status") or "")
        if status not in {"applied", "responded", "interview"}:
            continue
        updated = _parse_timestamp(str(app.get("updated_at") or app.get("date") or ""))
        if updated and updated <= now - timedelta(days=by_status_days[status]):
            followups.append(
                {
                    "slug": str(app.get("slug") or ""),
                    "status": status,
                    "updated_at": str(app.get("updated_at") or app.get("date") or ""),
                }
            )
    return followups


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(value[:10] + "T00:00:00+00:00")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
