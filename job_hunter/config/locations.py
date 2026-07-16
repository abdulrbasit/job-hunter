"""Compatibility imports for package-owned location services.

Location data and logic live in :mod:`job_hunter.locations`; this module keeps
older package imports working without putting deterministic data in user config.
"""

from job_hunter.locations import (
    COUNTRY_NAME_TO_CODE,
    canonical_locations_for_job,
    canonicalize_config_regions,
    canonicalize_runtime_location,
    cities,
    countries,
    country_code_for_city,
    enabled_locations,
    job_matches_enabled_locations,
    legacy_location_warnings,
    location_from_region,
    location_matches_any,
    location_to_config,
    normalize_location_name,
    resolve_config_location,
)

__all__ = [
    "COUNTRY_NAME_TO_CODE",
    "canonical_locations_for_job",
    "canonicalize_config_regions",
    "canonicalize_runtime_location",
    "cities",
    "countries",
    "country_code_for_city",
    "enabled_locations",
    "job_matches_enabled_locations",
    "legacy_location_warnings",
    "location_from_region",
    "location_matches_any",
    "location_to_config",
    "normalize_location_name",
    "resolve_config_location",
]
