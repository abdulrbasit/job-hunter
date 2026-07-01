"""Monthly API call budget tracking.

Tracks HTTP API call counts per source against code/default budget settings.
State is persisted to outputs/state/api_usage.json and auto-resets each calendar month.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_lock = threading.Lock()

try:
    from job_hunter.config.loader import ROOT
except Exception:
    ROOT = Path(".")


def _current_month() -> str:
    return datetime.now().strftime("%Y-%m")


def _resolve_budget_config(api_config: dict | None) -> dict:
    if api_config is not None:
        return api_config.get("http", {}).get("api_budgets", {}) or {}
    try:
        from job_hunter.config.loader import get_api_config

        config = get_api_config()
        return config.get("http", {}).get("api_budgets", {}) or {}
    except Exception:
        return {}


def _state_path(budget_config: dict) -> Path:
    rel = budget_config.get("state_path", "outputs/state/api_usage.json")
    path = Path(rel)
    if path.is_absolute():
        return path
    return ROOT / rel


def _load(budget_config: dict) -> dict:
    path = _state_path(budget_config)
    month = _current_month()
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("month") == month:
                return data
    except Exception as exc:
        logger.debug("[api_budget] failed to load state: %s", exc)
    return {"month": month, "providers": {}, "exhausted": {}}


def _save(state: dict, budget_config: dict) -> None:
    try:
        path = _state_path(budget_config)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.debug("[api_budget] failed to save state: %s", exc)


def reserve_api_call(source: str, *, api_config: dict | None = None) -> bool:
    """Reserve one API call for source. Returns False if monthly budget is exhausted."""
    budget_config = _resolve_budget_config(api_config)
    if not budget_config.get("enabled", True):
        return True

    with _lock:
        state = _load(budget_config)
        exhausted = state.get("exhausted", {})
        if source in exhausted:
            logger.debug("[api_budget] %s is exhausted for this month", source)
            return False

        limit = budget_config.get("monthly_limits", {}).get(source)
        if limit is None:
            return True

        providers = state.setdefault("providers", {})
        current = providers.get(source, 0)
        if current >= limit:
            exhausted[source] = {"reason": "monthly_limit", "marked_on": date.today().isoformat()}
            state["exhausted"] = exhausted
            logger.warning("[api_budget] %s monthly limit (%d) reached", source, limit)
            _save(state, budget_config)
            return False
        providers[source] = current + 1
        _save(state, budget_config)
        return True


def mark_api_exhausted(
    source: str, *, reason: str = "", api_config: dict | None = None, exc: Exception | None = None
) -> None:
    """Mark source as quota-exhausted for the rest of this calendar month."""
    budget_config = _resolve_budget_config(api_config)
    if not budget_config.get("enabled", True):
        return

    effective_reason = reason or (str(exc) if exc else "quota_exhausted")
    with _lock:
        state = _load(budget_config)
        exhausted = state.setdefault("exhausted", {})
        if source not in exhausted:
            exhausted[source] = {"reason": effective_reason, "marked_on": date.today().isoformat()}
            logger.warning("[api_budget] marking %s exhausted: %s", source, effective_reason)
            _save(state, budget_config)


def is_provider_exhausted_for_month(source: str, *, api_config: dict | None = None) -> bool:
    """Return True if source has been marked quota-exhausted for this calendar month."""
    budget_config = _resolve_budget_config(api_config)
    if not budget_config.get("enabled", True):
        return False
    state = _load(budget_config)
    return source in state.get("exhausted", {})


def is_api_quota_exhausted(exc: Exception) -> bool:
    """True if exception indicates monthly quota (not just rate limit) has been hit."""
    response = getattr(exc, "response", None)
    if response is None:
        return False
    status = getattr(response, "status_code", None)
    if status in (402, 432):
        return True
    if status == 429:
        body = str(getattr(response, "text", "") or "").lower()
        return "monthly quota" in body or "monthly limit" in body or "quota exhausted" in body
    return False
