"""SearchResult dataclass and normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass

from job_hunter.sources.search._url_utils import _text


@dataclass
class SearchResult:
    url: str
    title: str
    description: str
    source: str


def normalize_web_results(raw: list[dict], source: str) -> list[SearchResult]:
    results = []
    for item in raw:
        url = item.get("url") or item.get("link")
        if not url:
            continue
        results.append(
            SearchResult(
                url=url,
                title=_text(item.get("title") or item.get("name")),
                description=_text(
                    item.get("description") or item.get("snippet") or item.get("content") or item.get("text")
                ),
                source=source,
            )
        )
    return results
