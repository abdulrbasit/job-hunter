"""Company data: package-owned seed (job_hunter.companies.seed) imported into a runtime
SQLite store (job_hunter.companies.store) at outputs/state/companies.db, gated by the
user's enabled regions and excluded industries (job_hunter.companies.gating).
"""

from job_hunter.companies.gating import enabled_countries, excluded_industry_ids, hunt_candidates

__all__ = ["enabled_countries", "excluded_industry_ids", "hunt_candidates"]
