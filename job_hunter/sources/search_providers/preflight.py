"""One cheap run-start probe for configured web-search providers."""

from __future__ import annotations

import logging

from job_hunter.sources.search_providers.providers import (
    BraveProvider,
    ExaProvider,
    SearxngProvider,
    TavilyProvider,
)

logger = logging.getLogger(__name__)
_PROBE_QUERY = "software engineer"


def probe_search_providers() -> set[str]:
    disabled: set[str] = set()
    for provider in (SearxngProvider(), BraveProvider(), TavilyProvider(), ExaProvider()):
        if not provider.enabled():
            continue
        try:
            results = provider.search(_PROBE_QUERY, {}, count=1)
            if results:
                logger.info("[preflight] %s: OK", provider.name)
            else:
                logger.warning("[preflight] %s: zero results; disabling for this run", provider.name)
                disabled.add(provider.name.lower())
        except Exception as exc:
            logger.warning("[preflight] %s: %s; disabling for this run", provider.name, exc)
            disabled.add(provider.name.lower())
    return disabled
