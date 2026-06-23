"""Superseded by sources/orchestrator.py.

This module is kept only to avoid breaking any imports that may reference
``sources._scraper`` directly. Use ``sources.orchestrator.scrape()`` instead.
"""

from __future__ import annotations

from job_hunter.sources.orchestrator import scrape

__all__ = ["scrape"]
