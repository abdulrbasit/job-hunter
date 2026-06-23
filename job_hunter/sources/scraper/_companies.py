"""Company career-site helpers for scraper discovery."""

from __future__ import annotations

from urllib.parse import urlparse


def _url_matches_career_site(career_url: str, result_url: str) -> bool:
    def _parsed(url: str):
        if "://" not in url:
            url = "https://" + url
        return urlparse(url)

    def _etld1(netloc: str) -> str:
        host = netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host

    career = _parsed(career_url)
    result = _parsed(result_url)

    if _etld1(career.netloc) != _etld1(result.netloc):
        return False

    career_path = career.path.rstrip("/")
    if career_path and career_path != "/":
        if not result.path.startswith(career_path):
            return False

    return True
