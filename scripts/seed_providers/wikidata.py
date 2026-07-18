"""Wikidata company provider — CC0 data via the public SPARQL endpoint.

Companies headquartered in the given country, with an official website (P856).
Respects the Wikimedia User-Agent policy and stays polite on the shared
rate-limited endpoint (one bounded query per country, small sleep after each).
"""

from __future__ import annotations

import re
import time

import requests

NAME = "wikidata"
ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "job-hunter-seed/1.0 (https://github.com/abdulrbasit/job-hunter; abdulrbbasit@gmail.com)"
TIMEOUT_SECONDS = 90
POLITE_DELAY_SECONDS = 3
LIMIT = 2000

_sleep = time.sleep

# instance-of classes: business, company, public company, enterprise
_QUERY = """SELECT DISTINCT ?companyLabel ?website ?hqLabel ?industryLabel WHERE {{
  ?country wdt:P297 "{country}" .
  VALUES ?cls {{ wd:Q4830453 wd:Q783794 wd:Q891723 wd:Q6881511 }}
  ?company wdt:P31 ?cls ;
           wdt:P856 ?website ;
           wdt:P159 ?hq .
  ?hq wdt:P17 ?country .{city_clause}
  OPTIONAL {{ ?company wdt:P452 ?industry . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}
LIMIT {limit}"""


def _city_clause(country: str, city: str | None) -> str:
    """Constrain hq to the city by exact English label (indexed lookup) — without this a
    country-wide LIMIT slice can starve the requested city entirely. GeoNames-id matching
    (P1566) is unreliable: Wikidata often links a different GeoNames entry for the same city."""
    if not city:
        return ""
    from job_hunter.locations import city_by_name_exact

    resolved = city_by_name_exact(country, city)
    name = (resolved.name if resolved else city).replace('"', "")
    return f'\n  ?hq rdfs:label "{name}"@en .'


def fetch(country: str, city: str | None = None) -> list[dict]:
    query = _QUERY.format(country=country.upper(), limit=LIMIT, city_clause=_city_clause(country.upper(), city))
    response = None
    for attempt in (1, 2):
        response = requests.get(
            ENDPOINT,
            params={"query": query, "format": "json"},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code in (429, 500, 502, 503, 504) and attempt == 1:
            _sleep(10)
            continue
        response.raise_for_status()
        break
    rows: list[dict] = []
    for binding in response.json().get("results", {}).get("bindings", []):
        name = binding.get("companyLabel", {}).get("value", "").strip()
        url = binding.get("website", {}).get("value", "").strip()
        if not name or not url or re.fullmatch(r"Q\d+", name):
            continue  # entities without an English label come back as bare QIDs
        rows.append(
            {
                "name": name,
                "url": url,
                "city": binding.get("hqLabel", {}).get("value", ""),
                "industry_hint": binding.get("industryLabel", {}).get("value", ""),
            }
        )
    _sleep(POLITE_DELAY_SECONDS)
    return rows
