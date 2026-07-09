"""Package-owned company catalog.

Seed data today (see companies.json); target is 1,000-2,000 verified official
career pages. Merged with a workspace's custom career_pages.yml entries by
job_hunter.catalog.merge.effective_companies — custom entries always win on a
duplicate career_url.
"""

from job_hunter.catalog.loader import CompanyEntry, load_companies
from job_hunter.catalog.merge import effective_companies

__all__ = ["CompanyEntry", "effective_companies", "load_companies"]
