"""SearchProvider ABC and concrete provider implementations."""

from __future__ import annotations

import requests

from job_hunter.config.loader import (
    BRAVE_API_KEY,
    EXA_API_KEY,
    TAVILY_API_KEY,
    get_timeout,
    load_api_config,
)
from job_hunter.sources.search_providers._constants import (
    BRAVE_SUPPORTED_COUNTRIES,
    BRAVE_URL,
    EXA_URL,
    TAVILY_URL,
    USER_AGENT,
)
from job_hunter.sources.search_providers._result import SearchResult, normalize_web_results


def _timeout(section: str) -> int:
    return get_timeout(section)


def _search_cfg() -> dict:
    return load_api_config().get("http", {}).get("search_providers", {}) or {}


class SearchProvider:
    """Strategy interface for web-search providers."""

    name = "provider"

    def enabled(self) -> bool:
        return True

    def search(self, query: str, region_config: dict, count: int = 10) -> list[SearchResult]:
        raise NotImplementedError


class SearxngProvider(SearchProvider):
    name = "searxng"

    def __init__(self, cfg: dict | None = None) -> None:
        self.search_cfg = cfg if cfg is not None else _search_cfg()
        import os

        self.base_url = (os.environ.get("SEARXNG_BASE_URL") or self.search_cfg.get("searxng_base_url") or "").rstrip(
            "/"
        )

    def enabled(self) -> bool:
        return bool(self.base_url)

    def search(self, query: str, region_config: dict, count: int = 10) -> list[SearchResult]:
        params = {
            "q": query,
            "format": "json",
            "safesearch": 0,
            "categories": self.search_cfg.get("searxng_categories", "general"),
        }
        engines = self.search_cfg.get("searxng_engines")
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


class BraveProvider(SearchProvider):
    name = "brave"

    def enabled(self) -> bool:
        return bool(BRAVE_API_KEY)

    def search(self, query: str, region_config: dict, count: int = 10) -> list[SearchResult]:
        params = {
            "q": query,
            "count": count,
            "text_decorations": False,
            "spellcheck": False,
        }
        if region_config.get("search_lang"):
            params["search_lang"] = region_config["search_lang"]
        country = str(region_config.get("country") or "").upper()
        if country in BRAVE_SUPPORTED_COUNTRIES:
            params["country"] = country
        resp = requests.get(
            BRAVE_URL,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": BRAVE_API_KEY,
            },
            params=params,
            timeout=_timeout("search_providers"),
        )
        resp.raise_for_status()
        return normalize_web_results(resp.json().get("web", {}).get("results", []), "Brave")


class TavilyProvider(SearchProvider):
    name = "tavily"

    def enabled(self) -> bool:
        return bool(TAVILY_API_KEY)

    def search(self, query: str, region_config: dict, count: int = 10) -> list[SearchResult]:
        resp = requests.post(
            TAVILY_URL,
            json={"query": query, "max_results": count},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TAVILY_API_KEY}",
            },
            timeout=_timeout("search_providers"),
        )
        resp.raise_for_status()
        return normalize_web_results(resp.json().get("results", []), "Tavily")


class ExaProvider(SearchProvider):
    name = "exa"

    def enabled(self) -> bool:
        return bool(EXA_API_KEY)

    def search(self, query: str, region_config: dict, count: int = 10) -> list[SearchResult]:
        resp = requests.post(
            EXA_URL,
            json={"query": query, "numResults": count, "contents": {"text": True}},
            headers={
                "Content-Type": "application/json",
                "x-api-key": EXA_API_KEY,
            },
            timeout=_timeout("search_providers"),
        )
        resp.raise_for_status()
        return normalize_web_results(resp.json().get("results", []), "Exa")
