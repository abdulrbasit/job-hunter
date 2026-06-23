"""Search configuration utilities for source-first scraping."""

from __future__ import annotations

import logging

from job_hunter.core.config import get_config

logger = logging.getLogger(__name__)


def load_search_config() -> dict:
    config = get_config("job_hunter")
    logger.info("[scraper] Loaded search configuration from config/job_hunter.yml")
    return config


def enabled_regions(config: dict, region: str | None = None) -> dict[str, dict]:
    """Return enabled search regions, optionally scoped to one region key."""
    regions = config.get("regions", {}) or {}

    if region:
        region_config = regions.get(region)
        if not region_config:
            logger.warning("[scraper] Region %r not found in config/job_hunter.yml", region)
            return {}
        if not region_config.get("enabled", True):
            logger.info("[scraper] Region %r is disabled. Skipping.", region)
            return {}
        return {region: region_config}

    return {
        name: region_config
        for name, region_config in regions.items()
        if isinstance(region_config, dict) and region_config.get("enabled", True)
    }
