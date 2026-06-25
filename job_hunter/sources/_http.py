"""Shared HTTP fetch helpers for job source adapters."""

from __future__ import annotations

import logging
from collections.abc import Callable, Generator

import requests

from job_hunter.sources.source_config import terminal_http_status

logger = logging.getLogger(__name__)


def fetch_title_pages(
    url: str,
    titles: list[str],
    build_params: Callable[[str, int], dict],
    extract_key: str | None,
    *,
    timeout: int,
    max_pages: int,
    source_name: str,
) -> Generator[tuple[str, list], None, None]:
    """Yield (title, items) for each successful page across all titles.

    Stops per-title on empty page or non-terminal error.
    Stops entirely on terminal HTTP status (401/402/403/429/432).
    """
    for title in titles:
        for page in range(1, max_pages + 1):
            try:
                resp = requests.get(url, params=build_params(title, page), timeout=timeout)
                resp.raise_for_status()
                data = resp.json()
                items: list = data if extract_key is None else data.get(extract_key, [])
            except Exception as exc:
                logger.warning("[%s] request failed for %r page %d: %s", source_name, title, page, exc)
                if terminal_http_status(exc):
                    return
                break
            if not items:
                break
            yield title, items
