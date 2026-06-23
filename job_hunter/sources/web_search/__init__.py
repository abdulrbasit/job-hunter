"""Web search provider layer — public API for querying external search engines.

Supported providers: SearXNG (self-hosted), Brave, Tavily, Exa.
Providers are configured via environment variables (see config/job_hunter.yml secrets).
Preflight probing disables failing providers for the duration of a run.

Typical usage (for custom queries — board/ATS discovery goes through orchestrator):

    from job_hunter.sources.web_search import search_web, BraveProvider
"""

from __future__ import annotations

from job_hunter.sources.search_providers.providers import (
    BraveProvider,
    ExaProvider,
    SearchProvider,
    SearxngProvider,
    TavilyProvider,
)
from job_hunter.sources.search_providers.router import (
    ProviderSearchRouter,
    SearchRouter,
    all_providers_exhausted,
    search_web,
)

__all__ = [
    "BraveProvider",
    "ExaProvider",
    "SearchProvider",
    "SearxngProvider",
    "TavilyProvider",
    "ProviderSearchRouter",
    "SearchRouter",
    "all_providers_exhausted",
    "search_web",
]
