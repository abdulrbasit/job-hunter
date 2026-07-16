"""SearchProvider ABC and concrete provider implementations."""

from __future__ import annotations

import requests

from job_hunter.config.loader import get_api_config, get_timeout
from job_hunter.sources.search._constants import USER_AGENT
from job_hunter.sources.search._result import SearchResult, normalize_web_results


def _timeout(section: str) -> int:
    return get_timeout(section)


def _search_config() -> dict:
    return get_api_config().get("http", {}).get("search_providers", {}) or {}


class SearchProvider:
    """Strategy interface for web-search providers."""

    name = "provider"

    def enabled(self) -> bool:
        return True

    def search(self, query: str, region_config: dict, count: int = 10) -> list[SearchResult]:
        raise NotImplementedError


class SearxngProvider(SearchProvider):
    name = "searxng"

    def __init__(self, config: dict | None = None) -> None:
        self.search_config = config if config is not None else _search_config()
        import os

        self.base_url = (os.environ.get("SEARXNG_BASE_URL") or self.search_config.get("searxng_base_url") or "").rstrip(
            "/"
        )

    def enabled(self) -> bool:
        return bool(self.base_url)

    def search(self, query: str, region_config: dict, count: int = 10) -> list[SearchResult]:
        params = {
            "q": query,
            "format": "json",
            "safesearch": 0,
            "categories": self.search_config.get("searxng_categories", "general"),
        }
        engines = self.search_config.get("searxng_engines")
        if engines:
            params["engines"] = ",".join(engines) if isinstance(engines, list) else str(engines)
        if region_config.get("search_lang"):
            params["language"] = region_config["search_lang"]
        resp = requests.get(
            f"{self.base_url}/search",
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=_timeout("search_providers"),
        )
        resp.raise_for_status()
        raw = resp.json().get("results", [])[:count]
        results = normalize_web_results(raw, "SearXNG")
        return results
