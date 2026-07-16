"""Tests for sources/search/preflight.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_provider(name: str, *, enabled: bool = True, results=None, error=None):
    p = MagicMock()
    p.name = name
    p.enabled.return_value = enabled
    if error is not None:
        p.search.side_effect = error
    else:
        p.search.return_value = results if results is not None else [MagicMock()]
    return p


class TestProbeSearchProviders:
    def _run(self, provider):
        from job_hunter.sources.search import preflight

        with patch.object(preflight, "SearxngProvider", return_value=provider):
            return preflight.probe_search_providers()

    def test_working_provider_not_in_disabled(self) -> None:
        disabled = self._run(_make_provider("searxng", results=[MagicMock()]))
        assert "searxng" not in disabled

    def test_disabled_provider_credential_not_probed(self) -> None:
        p = _make_provider("searxng", enabled=False)
        disabled = self._run(p)
        p.search.assert_not_called()
        assert "searxng" not in disabled

    def test_probe_exception_adds_to_disabled(self) -> None:
        disabled = self._run(_make_provider("searxng", error=Exception("connection reset")))
        assert "searxng" in disabled

    def test_probe_zero_results_adds_to_disabled(self) -> None:
        disabled = self._run(_make_provider("searxng", results=[]))
        assert "searxng" in disabled
