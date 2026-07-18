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
  ?hq wdt:P17 ?country .
  OPTIONAL {{ ?company wdt:P452 ?industry . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}
LIMIT {limit}"""


def fetch(country: str, city: str | None = None) -> list[dict]:
    """One country-wide query; city filtering happens downstream on canonical city ids."""
    query = _QUERY.format(country=country.upper(), limit=LIMIT)
    response = None
    for attempt in (1, 2):
        response = requests.get(
            ENDPOINT,
            params={"query": query, "format": "json"},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code in (429, 500, 502, 503) and attempt == 1:
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
