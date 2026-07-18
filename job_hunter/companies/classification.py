"""Conservative package-owned company classification rules."""

from __future__ import annotations

from job_hunter.models import CompanyType, FundingStage

_STARTUP_STAGES = {FundingStage.PRE_SEED, FundingStage.SEED, FundingStage.SERIES_A}
_SCALEUP_STAGES = {FundingStage.SERIES_B, FundingStage.SERIES_C_PLUS, FundingStage.GROWTH}


def classify_company(
    *,
    company_type: str = "",
    funding_stage: str = "",
    status: str = "",
    headcount: int | None = None,
    ecosystem: str = "",
) -> CompanyType:
    """Prefer explicit facts; leave weak small-company signals unknown."""
    if company_type:
        return CompanyType(company_type)
    if status.casefold() in {"public", "acquired"} or (headcount is not None and headcount >= 1000):
        return CompanyType.ENTERPRISE
    stage = FundingStage(funding_stage) if funding_stage else None
    if stage in _SCALEUP_STAGES or (headcount is not None and 100 <= headcount < 1000):
        return CompanyType.SCALEUP
    if stage in _STARTUP_STAGES:
        return CompanyType.STARTUP
    if ecosystem and status.casefold() in {"active", "private"}:
        return CompanyType.STARTUP
    return CompanyType.UNKNOWN
