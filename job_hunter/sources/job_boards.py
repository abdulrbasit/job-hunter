"""Compatibility imports for board adapters moved under :mod:`sources.boards`."""

from job_hunter.sources.boards.arbeitnow import ArbeitnowSource
from job_hunter.sources.boards.jsearch import JSearchSource

__all__ = ["ArbeitnowSource", "JSearchSource"]
