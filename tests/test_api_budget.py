"""Tests for job_hunter.core.api_budget."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    tmp_path: Path,
    *,
    enabled: bool = True,
    monthly_limits: dict | None = None,
) -> dict:
    state_file = tmp_path / "api_usage.json"
    return {
        "enabled": enabled,
        "state_path": str(state_file),
        "monthly_limits": monthly_limits or {},
    }


def _import_budget():
    """Import the module under test, bypassing module-level config loading."""
    from job_hunter.core import api_budget

    return api_budget


# ---------------------------------------------------------------------------
# reserve_api_call — under limit
# ---------------------------------------------------------------------------


def test_reserve_returns_true_when_under_limit(tmp_path: Path) -> None:
    budget = _import_budget()
    config = _make_config(tmp_path, monthly_limits={"sourcex": 10})
    result = budget.reserve_api_call("sourcex", api_config={"http": {"api_budgets": config}})
    assert result is True


def test_reserve_increments_counter(tmp_path: Path) -> None:
    budget = _import_budget()
    config = _make_config(tmp_path, monthly_limits={"sourcex": 10})
    api_config = {"http": {"api_budgets": config}}
    budget.reserve_api_call("sourcex", api_config=api_config)
    budget.reserve_api_call("sourcex", api_config=api_config)
    state_file = Path(config["state_path"])
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["providers"]["sourcex"] == 2


# ---------------------------------------------------------------------------
# reserve_api_call — at/over limit
# ---------------------------------------------------------------------------


def test_reserve_returns_false_at_limit(tmp_path: Path) -> None:
    budget = _import_budget()
    config = _make_config(tmp_path, monthly_limits={"sourcex": 2})
    api_config = {"http": {"api_budgets": config}}
    budget.reserve_api_call("sourcex", api_config=api_config)
    budget.reserve_api_call("sourcex", api_config=api_config)
    # third call should be blocked
    result = budget.reserve_api_call("sourcex", api_config=api_config)
    assert result is False


def test_reserve_returns_true_for_unlimited_provider(tmp_path: Path) -> None:
    budget = _import_budget()
    config = _make_config(tmp_path, monthly_limits={})  # no limit for "sourcey"
    api_config = {"http": {"api_budgets": config}}
    for _ in range(50):
        assert budget.reserve_api_call("sourcey", api_config=api_config) is True


# ---------------------------------------------------------------------------
# Monthly reset
# ---------------------------------------------------------------------------


def test_monthly_reset_clears_state(tmp_path: Path) -> None:
    budget = _import_budget()
    state_file = tmp_path / "api_usage.json"
    # Write state from a previous month
    old_state = {
        "month": "2000-01",
        "providers": {"sourcex": 999},
        "exhausted": {"sourcex": {"reason": "old", "marked_on": "2000-01-01"}},
    }
    state_file.write_text(json.dumps(old_state), encoding="utf-8")

    config = _make_config(tmp_path, monthly_limits={"sourcex": 10})
    api_config = {"http": {"api_budgets": config}}

    # reserve_api_call should see a fresh state for the current month
    result = budget.reserve_api_call("sourcex", api_config=api_config)
    assert result is True
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["providers"]["sourcex"] == 1
    assert "sourcex" not in data.get("exhausted", {})


# ---------------------------------------------------------------------------
# mark_api_exhausted
# ---------------------------------------------------------------------------


def test_mark_exhausted_prevents_future_calls(tmp_path: Path) -> None:
    budget = _import_budget()
    config = _make_config(tmp_path, monthly_limits={"reed": 1000})
    api_config = {"http": {"api_budgets": config}}

    budget.mark_api_exhausted("reed", reason="quota hit", api_config={"http": {"api_budgets": config}})
    result = budget.reserve_api_call("reed", api_config=api_config)
    assert result is False


def test_mark_exhausted_writes_reason(tmp_path: Path) -> None:
    budget = _import_budget()
    config = _make_config(tmp_path)
    budget.mark_api_exhausted("adzuna", reason="402 Payment Required", api_config={"http": {"api_budgets": config}})
    state_file = Path(config["state_path"])
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert "adzuna" in data["exhausted"]
    assert data["exhausted"]["adzuna"]["reason"] == "402 Payment Required"


def test_mark_exhausted_idempotent(tmp_path: Path) -> None:
    """Calling mark_api_exhausted twice does not raise or corrupt state."""
    budget = _import_budget()
    config = _make_config(tmp_path)
    budget.mark_api_exhausted("sourcez", reason="first", api_config={"http": {"api_budgets": config}})
    budget.mark_api_exhausted("sourcez", reason="second", api_config={"http": {"api_budgets": config}})
    state_file = Path(config["state_path"])
    data = json.loads(state_file.read_text(encoding="utf-8"))
    # reason should remain from first call
    assert data["exhausted"]["sourcez"]["reason"] == "first"


# ---------------------------------------------------------------------------
# is_api_quota_exhausted
# ---------------------------------------------------------------------------


def _make_exc(status_code: int | None, body: str = "") -> Exception:
    exc = Exception("api error")
    if status_code is not None:
        response = MagicMock()
        response.status_code = status_code
        response.text = body
        response.reason = "Error"
        exc.response = response
    return exc


def test_402_is_quota_exhausted() -> None:
    budget = _import_budget()
    exc = _make_exc(402)
    assert budget.is_api_quota_exhausted(exc) is True


def test_429_with_quota_text_is_exhausted() -> None:
    budget = _import_budget()
    exc = _make_exc(429, body="monthly quota exceeded for your plan")
    assert budget.is_api_quota_exhausted(exc) is True


def test_429_without_quota_text_is_not_exhausted() -> None:
    budget = _import_budget()
    exc = _make_exc(429, body="rate limit hit, please slow down")
    assert budget.is_api_quota_exhausted(exc) is False


def test_500_is_not_quota_exhausted() -> None:
    budget = _import_budget()
    exc = _make_exc(500, body="internal server error quota exceeded")
    assert budget.is_api_quota_exhausted(exc) is False


def test_no_response_is_not_quota_exhausted() -> None:
    budget = _import_budget()
    exc = Exception("connection timeout")
    assert budget.is_api_quota_exhausted(exc) is False


# ---------------------------------------------------------------------------
# Disabled budget — always allows calls
# ---------------------------------------------------------------------------


def test_disabled_budget_always_allows(tmp_path: Path) -> None:
    budget = _import_budget()
    config = _make_config(tmp_path, enabled=False, monthly_limits={"sourcex": 0})
    api_config = {"http": {"api_budgets": config}}
    assert budget.reserve_api_call("sourcex", api_config=api_config) is True


def test_disabled_budget_ignores_mark_exhausted(tmp_path: Path) -> None:
    budget = _import_budget()
    config = _make_config(tmp_path, enabled=False)
    budget.mark_api_exhausted("sourcex", reason="test", api_config={"http": {"api_budgets": config}})
    state_file = Path(config["state_path"])
    # File should NOT have been written (budget is disabled)
    assert not state_file.exists()
