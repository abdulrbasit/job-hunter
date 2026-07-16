"""Compatibility imports for package-owned location services.

Location data and logic live in :mod:`job_hunter.locations`; this module keeps
older package imports working without putting deterministic data in user config.
"""

from job_hunter.locations import *  # noqa: F403
