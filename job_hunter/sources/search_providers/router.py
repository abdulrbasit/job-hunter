"""SearchRouter, search_web, provider registry, and all mutable module-level state."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from job_hunter.core.api_budget import is_api_quota_exhausted
from job_hunter.sources.search_providers.providers import (
    BraveProvider,
    ExaProvider,
    SearchProvider,
    SearxngProvider,
    TavilyProvider,
    _search_cfg,
)

if TYPE_CHECKING:
    from job_hunter.sources.search_providers._result import SearchResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mutable module-level state — all lives here
# ---------------------------------------------------------------------------
@dataclass
class ProviderState:
    failures: dict[str, int] = field(default_factory=dict)
    failures_lock: threading.Lock = field(default_factory=threading.Lock)
    searxng_zero_threshold: int = 5
    searxng_consecutive_zeros: int = 0
    searxng_zero_lock: threading.Lock = field(default_factory=threading.Lock)
    ats_only_logged: bool = False
    run_disabled: set[str] = field(default_factory=set)

    def set_run_disabled(self, disabled: set[str]) -> None:
        self.run_disabled = {p.lower() for p in disabled}

    def add_run_disabled(self, provider_name: str) -> None:
        with self.failures_lock:
            self.run_disabled.add(provider_name.lower())

    def failure_count(self, name: str) -> int:
        with self.failures_lock:
            return self.failures.get(name, 0)

    def reset_failure(self, name: str) -> None:
        with self.failures_lock:
            self.failures[name] = 0

    def record_failure(self, name: str) -> int:
        with self.failures_lock:
            failures = self.failures.get(name, 0) + 1
            self.failures[name] = failures
            return failures


_PROVIDER_STATE = ProviderState()


def set_run_disabled(disabled: set[str]) -> None:
    """Replace the run-level disabled set (called once at pipeline start)."""
    _PROVIDER_STATE.set_run_disabled(disabled)


def _add_run_disabled(provider_name: str) -> None:
    """Disable one provider for the rest of this run (quota hit mid-run)."""
    _PROVIDER_STATE.add_run_disabled(provider_name)


def _provider_failure_count(name: str) -> int:
    return _PROVIDER_STATE.failure_count(name)


def _reset_provider_failure(name: str) -> None:
    _PROVIDER_STATE.reset_failure(name)


def _record_provider_failure(name: str) -> int:
    return _PROVIDER_STATE.record_failure(name)


def _provider_registry() -> dict[str, SearchProvider]:
    return {
        "searxng": SearxngProvider(),
        "brave": BraveProvider(),
        "tavily": TavilyProvider(),
        "exa": ExaProvider(),
    }


def _provider_order() -> list[str]:
    # Keep general search on SearXNG → Brave so semantic-provider quotas are
    # available to explicit callers. Users can override search_providers.order.
    return list(_search_cfg().get("order") or ["searxng", "brave"])


def _ats_discovery_provider_order() -> list[str]:
    # Exa semantic search finds ATS job-board URLs well; include it after brave.
    return list(_search_cfg().get("ats_discovery_order") or ["searxng", "brave", "exa"])


def _providers_from_order(provider_names: list[str]) -> list[SearchProvider]:
    available = _provider_registry()
    return [available[name] for name in provider_names if name in available]


def all_providers_exhausted(api_cfg: dict | None = None) -> bool:  # noqa: ARG001
    """Return True when all ATS-discovery providers are unavailable this run."""
    registry = _provider_registry()
    result = all(
        name in _PROVIDER_STATE.run_disabled or not registry[name].enabled()
        for name in _ats_discovery_provider_order()
        if name in registry
    )

    if result:
        with _PROVIDER_STATE.searxng_zero_lock:
            if not _PROVIDER_STATE.ats_only_logged:
                logger.info("[search] all providers exhausted — switching to ATS-only mode")
                _PROVIDER_STATE.ats_only_logged = True

    return result


@dataclass
class SearchRouterHealth:
    exhausted_providers: set[str] = field(default_factory=set)
    skipped_no_key: set[str] = field(default_factory=set)
    transient_failures: set[str] = field(default_factory=set)
    providers_used: set[str] = field(default_factory=set)


class SearchRouter:
    """Tries enabled search providers in configured order."""

    def __init__(
        self,
        providers: list[SearchProvider] | None = None,
        *,
        disabled: set[str] | None = None,
        allowed: set[str] | None = None,
    ) -> None:
        self.providers = providers if providers is not None else _providers_from_order(_provider_order())
        self.max_consecutive_failures = int(_search_cfg().get("max_consecutive_failures", 3))
        self._disabled: set[str] = {p.lower() for p in (disabled or set())}
        self._allowed: set[str] | None = {p.lower() for p in allowed} if allowed is not None else None

    def _is_suppressed(self, provider: SearchProvider) -> bool:
        if self.max_consecutive_failures <= 0:
            return False
        failures = _provider_failure_count(provider.name)
        if failures < self.max_consecutive_failures:
            return False
        logger.warning(
            "[search] %s suppressed after %s consecutive transient failure(s); "
            "will resume after a successful call from another provider",
            provider.name,
            failures,
        )
        return True

    @staticmethod
    def _is_exhausted(provider: SearchProvider) -> bool:
        """Return True when the provider was disabled by the pre-flight probe or failed mid-run."""
        return provider.name.lower() in _PROVIDER_STATE.run_disabled

    def _search_core(
        self, query: str, region_config: dict, count: int
    ) -> tuple[list[SearchResult], SearchRouterHealth]:
        """Shared provider-iteration loop used by search() and search_with_health()."""
        health = SearchRouterHealth()
        all_results: list[SearchResult] = []
        any_keyed_provider_tried = False

        for provider in self.providers:
            pname = provider.name.lower()
            if self._allowed is not None and pname not in self._allowed:
                logger.debug("[search] %s skipped: not in allowed set", provider.name)
                continue
            if pname in self._disabled:
                logger.debug("[search] %s skipped: pre-flight exhausted this run", provider.name)
                continue

            if not provider.enabled():
                logger.debug("[search] %s disabled or missing credentials", provider.name)
                health.skipped_no_key.add(pname)
                continue

            if self._is_exhausted(provider):
                logger.info(
                    "[search] %s skipped: monthly quota already exhausted for this month",
                    provider.name,
                )
                health.exhausted_providers.add(pname)
                continue

            if self._is_suppressed(provider):
                health.transient_failures.add(pname)
                continue

            any_keyed_provider_tried = True
            try:
                logger.info("[search] %s: %s", provider.name, query[:80])
                results = provider.search(query, region_config, count=count)
                _reset_provider_failure(provider.name)
                if results:
                    all_results.extend(results)
                    health.providers_used.add(pname)
                    break
            except Exception as exc:
                if is_api_quota_exhausted(exc):
                    _add_run_disabled(provider.name)
                    _reset_provider_failure(provider.name)
                    health.exhausted_providers.add(pname)
                    logger.warning(
                        "[search] %s quota exhausted mid-run; disabling for this run",
                        provider.name,
                    )
                    continue
                failures = _record_provider_failure(provider.name)
                health.transient_failures.add(pname)
                logger.warning(
                    "[search] %s transient failure (%s/%s): %s",
                    provider.name,
                    failures,
                    self.max_consecutive_failures,
                    exc,
                )

        if not any_keyed_provider_tried and not all_results:
            logger.debug("[search] no enabled providers with credentials; returning empty result set")

        return all_results[:count], health

    def search(self, query: str, region_config: dict, count: int = 10) -> list[SearchResult]:
        results, _ = self._search_core(query, region_config, count)
        return results

    def search_with_health(
        self, query: str, region_config: dict, count: int = 10
    ) -> tuple[list[SearchResult], SearchRouterHealth]:
        """Like search() but also returns a SearchRouterHealth summary."""
        return self._search_core(query, region_config, count)


class ProviderSearchRouter(SearchRouter):
    """Search router constrained to a caller-provided provider name order."""

    def __init__(
        self,
        provider_names: list[str],
        *,
        disabled: set[str] | None = None,
        allowed: set[str] | None = None,
    ) -> None:
        super().__init__(_providers_from_order(provider_names), disabled=disabled, allowed=allowed)


def search_web(
    query: str,
    region_config: dict,
    count: int = 10,
    *,
    disabled: set[str] | None = None,
    allowed: set[str] | None = None,
) -> list[dict]:
    """Compatibility helper returning Brave-like dictionaries."""
    return [
        {
            "url": result.url,
            "title": result.title,
            "description": result.description,
            "source": result.source,
        }
        for result in SearchRouter(disabled=disabled, allowed=allowed).search(query, region_config, count=count)
    ]
