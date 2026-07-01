"""Job board adapters — one file per source. See registry.py for the source list."""

from __future__ import annotations

from job_hunter.sources.boards.registry import BOARD_REGISTRY

__all__ = ["BOARD_REGISTRY"]
