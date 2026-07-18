"""Inactive student-source adapters retained behind the standard contract."""

from __future__ import annotations

from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources.base import JobSourceAdapter


class _InactiveStudentSource(JobSourceAdapter):
    def is_enabled(self, api_config: dict) -> bool:
        return False

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        return []


class HandshakeSource(_InactiveStudentSource):
    supported_countries = frozenset({"US"})

    @property
    def source_name(self) -> str:
        return "handshake"


class StellenwerkSource(_InactiveStudentSource):
    supported_countries = frozenset({"DE"})

    @property
    def source_name(self) -> str:
        return "stellenwerk"
