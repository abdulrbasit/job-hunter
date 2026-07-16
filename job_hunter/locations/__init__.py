"""Canonical location data, config-time resolution, and runtime allowlisting."""

from __future__ import annotations

import json
import re
import unicodedata
import warnings
from copy import deepcopy
from difflib import SequenceMatcher
from functools import cache, lru_cache
from importlib import resources
from typing import Any

from job_hunter.config.reference_data import load_countries
from job_hunter.models import CanonicalCity, Location, LocationScope

_SPLIT = re.compile(r"\s*(?:[,;/|()]|\s+-\s+)\s*")
_REMOTE = re.compile(r"\b(?:remote|work\s+from\s+home|homeoffice)\b", re.IGNORECASE)


def normalize_location_name(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(char for char in folded if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text).split())


@lru_cache(maxsize=1)
def _countries() -> tuple[dict[str, str], dict[str, str]]:
    by_code: dict[str, str] = {}
    by_name: dict[str, str] = {}
    for country in load_countries():
        by_code[country.code] = country.name
        for name in (country.code, country.name, *country.aliases):
            by_name[normalize_location_name(name)] = country.code
    return by_code, by_name


def countries() -> list[dict[str, str]]:
    return [{"code": code, "name": name} for code, name in sorted(_countries()[0].items(), key=lambda item: item[1])]


@cache
def cities(country: str) -> tuple[CanonicalCity, ...]:
    code = country.strip().upper()
    if code not in _countries()[0]:
        return ()
    path = resources.files("job_hunter.locations").joinpath("data", "cities", f"{code}.json")
    if not path.is_file():
        return ()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        CanonicalCity(
            id=str(item["id"]),
            name=str(item["name"]),
            aliases=[str(v) for v in item["aliases"]],
            population=int(item.get("population") or 0),
        )
        for item in raw
    )


@cache
def _city_index(country: str) -> dict[str, CanonicalCity]:
    index: dict[str, CanonicalCity] = {}
    for city in cities(country):
        for alias in (city.name, *city.aliases):
            index.setdefault(normalize_location_name(alias), city)
    return index


@lru_cache(maxsize=1)
def _global_city_index() -> dict[str, CanonicalCity]:
    # Phase 1 keeps this direct. Phase 4 measures and replaces global eager work
    # with enabled-country loading if it is material.
    index: dict[str, CanonicalCity] = {}
    for code in _countries()[0]:
        for alias, city in _city_index(code).items():
            current = index.get(alias)
            if current is None or city.population > current.population:
                index[alias] = city
    return index


def _validate_country(country: str) -> str:
    code = country.strip().upper()
    if code not in _countries()[0]:
        raise ValueError(f"Unknown ISO alpha-2 country: {country!r}")
    return code


def resolve_config_location(
    country: str,
    city: str | None = None,
    scope: LocationScope | str = LocationScope.CITY,
) -> Location:
    """Resolve user input; fuzzy matching is intentionally confined here."""
    scope = LocationScope(scope)
    if scope == LocationScope.REMOTE_GLOBAL:
        return Location(scope=scope)
    code = _validate_country(country)
    if scope != LocationScope.CITY:
        return Location(country=code, scope=scope)
    name = str(city or "").strip()
    if not name:
        raise ValueError("city scope requires a city name")
    needle = normalize_location_name(name)
    match = _city_index(code).get(needle)
    if match is None:
        scored = sorted(
            (
                (SequenceMatcher(None, needle, alias).ratio(), alias_city)
                for alias, alias_city in _city_index(code).items()
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        if scored and scored[0][0] >= 0.88 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.03):
            match = scored[0][1]
    if match is None:
        suggestions = list(dict.fromkeys(city.name for score, city in scored if score >= 0.7))[:3]
        suffix = f"; suggestions: {', '.join(suggestions)}" if suggestions else ""
        raise ValueError(f"Unknown or ambiguous city {name!r} for {code}{suffix}")
    return Location(country=code, scope=scope, city=match)


def location_to_config(location: Location) -> dict[str, str]:
    data = {"country": location.country, "scope": location.scope.value}
    if location.city is not None:
        data["city_id"] = location.city.id
    return data


def location_from_region(region: dict[str, Any], *, allow_legacy: bool = True) -> Location:  # noqa: C901
    if region.get("scope"):
        scope = LocationScope(str(region.get("scope")))
        if scope == LocationScope.REMOTE_GLOBAL:
            return Location(scope=scope)
        country = _validate_country(str(region.get("country") or ""))
        if scope != LocationScope.CITY:
            return Location(country=country, scope=scope)
        city_id = str(region.get("city_id") or "")
        if not city_id:
            raise ValueError("city scope requires city_id")
        bundled = next((item for item in cities(country) if item.id == city_id), None)
        if bundled is None:
            raise ValueError(f"Unknown city id {city_id!r} for {country}")
        return Location(country=country, scope=scope, city=bundled)
    if not allow_legacy:
        raise ValueError("legacy location string is not allowed")
    raw = region.get("location")
    country = str(region.get("country") or "")
    text = str(raw or "").strip()
    if not text and country:
        return resolve_config_location(country, scope=LocationScope.COUNTRY)
    if normalize_location_name(text) == "remote":
        return resolve_config_location(country, scope=LocationScope.REMOTE_COUNTRY)
    if not country:
        matches = canonicalize_runtime_location(text)
        if matches:
            return matches[0]
    return resolve_config_location(country, text, LocationScope.CITY)


def enabled_locations(config: dict[str, Any]) -> list[Location]:
    result: list[Location] = []
    regions = config.get("regions") or {}
    for region in regions.values() if isinstance(regions, dict) else ():
        if not isinstance(region, dict) or region.get("enabled", True) is False:
            continue
        try:
            result.append(location_from_region(region))
        except ValueError:
            continue
    return result


def canonicalize_config_regions(config: dict[str, Any], *, warn_legacy: bool = False) -> dict[str, Any]:
    """Return a runtime copy whose enabled and disabled regions use canonical locations."""
    result = deepcopy(config)
    regions = result.get("regions") or {}
    if not isinstance(regions, dict):
        return result
    for name, region in regions.items():
        if not isinstance(region, dict) or region.get("scope"):
            continue
        try:
            canonical = location_from_region(region)
        except ValueError:
            continue
        region.update(location_to_config(canonical))
        region.pop("location", None)
        if warn_legacy:
            warnings.warn(
                f"Region {name!r} uses legacy free-text location; resave it to store the package city ID.",
                FutureWarning,
                stacklevel=3,
            )
    return result


def legacy_location_warnings(config: dict[str, Any]) -> list[str]:
    regions = config.get("regions") or {}
    if not isinstance(regions, dict):
        return []
    result: list[str] = []
    for name, region in regions.items():
        if not isinstance(region, dict):
            continue
        legacy = not region.get("scope")
        try:
            location_from_region(region, allow_legacy=legacy)
        except ValueError as exc:
            result.append(f"region {name!r} cannot resolve a package location: {exc}")
        else:
            if legacy:
                result.append(f"region {name!r} uses legacy free-text location; resave it to store the package city ID")
    return result


def canonicalize_runtime_location(value: str, country_hint: str = "") -> list[Location]:  # noqa: C901
    """Resolve source text using exact aliases only; never fuzzy-match jobs."""
    text = str(value or "").strip()
    if not text:
        return []
    normalized = normalize_location_name(text)
    country_codes = {
        code
        for alias, code in _countries()[1].items()
        if alias and re.search(rf"(?:^|\s){re.escape(alias)}(?:$|\s)", normalized)
    }
    if country_hint:
        country_codes.add(_validate_country(country_hint))
    if _REMOTE.search(text):
        if country_codes:
            return [Location(country=code, scope=LocationScope.REMOTE_COUNTRY) for code in sorted(country_codes)]
        return [Location(scope=LocationScope.REMOTE_GLOBAL)]

    segments = [normalize_location_name(part) for part in _SPLIT.split(text) if normalize_location_name(part)]
    found: dict[str, Location] = {}
    indexes = [_city_index(code) for code in sorted(country_codes)] if country_codes else [_global_city_index()]
    for segment in segments:
        for index in indexes:
            city = index.get(segment)
            if city is None:
                continue
            code = next((item for item in country_codes if city in cities(item)), "")
            if not code:
                for candidate_code in _countries()[0]:
                    if _city_index(candidate_code).get(segment) == city:
                        code = candidate_code
                        break
            if code:
                location = Location(country=code, scope=LocationScope.CITY, city=city)
                found[location.id] = location
    if found:
        return list(found.values())
    country_aliases = set(_countries()[1])
    if any(segment not in country_aliases for segment in segments):
        return []
    return [Location(country=code, scope=LocationScope.COUNTRY) for code in sorted(country_codes)]


def _matches(candidate: Location, allowed: Location) -> bool:
    if allowed.scope == LocationScope.REMOTE_GLOBAL:
        return candidate.scope == LocationScope.REMOTE_GLOBAL
    if candidate.country != allowed.country:
        return False
    if allowed.scope == LocationScope.COUNTRY:
        return candidate.scope in {LocationScope.CITY, LocationScope.COUNTRY, LocationScope.REMOTE_COUNTRY}
    if allowed.scope == LocationScope.REMOTE_COUNTRY:
        return candidate.scope == LocationScope.REMOTE_COUNTRY
    return (
        candidate.scope == LocationScope.CITY
        and candidate.city is not None
        and allowed.city is not None
        and candidate.city.id == allowed.city.id
    )


def location_matches_any(candidates: list[Location], allowed: list[Location]) -> bool:
    return bool(candidates) and any(_matches(candidate, target) for candidate in candidates for target in allowed)


def job_matches_enabled_locations(job: dict[str, Any], allowed: list[Location]) -> bool:
    canonical = job.get("canonical_locations") or []
    candidates = (
        [Location.model_validate(item) for item in canonical]
        if canonical
        else canonicalize_runtime_location(str(job.get("location") or ""))
    )
    restrictions = job.get("location_restrictions") or []
    if restrictions:
        remote_prefix = "Remote " if "remote" in str(job.get("location") or "").casefold() else ""
        candidates = [
            item for value in restrictions for item in canonicalize_runtime_location(f"{remote_prefix}{value}")
        ] or candidates
    return location_matches_any(candidates, allowed)


def country_code_for_city(name: str) -> str | None:
    """Compatibility lookup for the setup CLI; exact package data only."""
    matches = canonicalize_runtime_location(name)
    return matches[0].country if matches and matches[0].country else None


# Compatibility for country-restriction phrase detection. Generated from the
# authoritative country resource; city names are handled by canonical indexes.
COUNTRY_NAME_TO_CODE = {name: code for name, code in _countries()[1].items() if len(name) > 2}
