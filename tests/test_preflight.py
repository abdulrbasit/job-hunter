"""Tests for sources/search_providers/preflight.py."""

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
    def _run(self, providers):
        from job_hunter.sources.search_providers import preflight

        with (
            patch.object(
                preflight,
                "SearxngProvider",
                return_value=providers.get("searxng", _make_provider("searxng", enabled=False)),
            ),
            patch.object(
                preflight,
                "BraveProvider",
                return_value=providers.get("brave", _make_provider("brave", enabled=False)),
            ),
            patch.object(
                preflight,
                "TavilyProvider",
                return_value=providers.get("tavily", _make_provider("tavily", enabled=False)),
            ),
            patch.object(
                preflight,
                "ExaProvider",
                return_value=providers.get("exa", _make_provider("exa", enabled=False)),
            ),
        ):
            return preflight.probe_search_providers()

    def test_working_provider_not_in_disabled(self) -> None:
        disabled = self._run({"brave": _make_provider("brave", results=[MagicMock()])})
        assert "brave" not in disabled

    def test_disabled_provider_credential_not_probed(self) -> None:
        p = _make_provider("brave", enabled=False)
        disabled = self._run({"brave": p})
        p.search.assert_not_called()
        assert "brave" not in disabled

    def test_probe_exception_adds_to_disabled(self) -> None:
        p = _make_provider("tavily", error=Exception("connection reset"))
        disabled = self._run({"tavily": p})
        assert "tavily" in disabled

    def test_probe_zero_results_adds_to_disabled(self) -> None:
        p = _make_provider("exa", results=[])
        disabled = self._run({"exa": p})
        assert "exa" in disabled

    def test_all_providers_disabled_returns_full_set(self) -> None:
        providers = {
            "searxng": _make_provider("searxng", error=Exception("timeout")),
            "brave": _make_provider("brave", results=[]),
            "tavily": _make_provider("tavily", error=Exception("403")),
            "exa": _make_provider("exa", results=[]),
        }
        disabled = self._run(providers)
        assert disabled >= {"searxng", "brave", "tavily", "exa"}
