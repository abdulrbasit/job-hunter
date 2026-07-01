"""Shared date-text helpers for board adapters."""

from __future__ import annotations

from typing import Any


def truncate_date_text(value: Any) -> str:
    """Return the first 10 characters of a raw posted-date value, or "" if absent.

    Only for sources whose raw field is already date-first-10-chars shaped (an ISO
    date/datetime string). Sources needing real format conversion (Unix timestamp,
    RFC2822, DD/MM/YYYY) keep their own dedicated parser instead.
    """
    return str(value or "")[:10]
