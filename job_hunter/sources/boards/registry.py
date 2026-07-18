"""Job board adapter registry.

Maps source name → JobSourceAdapter subclass for every board source.
The orchestrator uses this to instantiate and dispatch sources without
importing each adapter individually. This is the one place source list
membership is declared — do not duplicate this list elsewhere.
"""

from __future__ import annotations

from job_hunter.sources.boards.adzuna import AdzunaSource
from job_hunter.sources.boards.arbeitnow import ArbeitnowSource
from job_hunter.sources.boards.arbeitsagentur import ArbeitsagenturSource
from job_hunter.sources.boards.bayt import BaytSource
from job_hunter.sources.boards.careerjet import CareerjetSource
from job_hunter.sources.boards.gulftalent import GulfTalentSource
from job_hunter.sources.boards.hh import HHSource
from job_hunter.sources.boards.himalayas import HimalayasSource
from job_hunter.sources.boards.jobbank import JobBankSource
from job_hunter.sources.boards.jobicy import JobicySource
from job_hunter.sources.boards.jobspy import JobSpySource
from job_hunter.sources.boards.jobstreet import JobStreetSource
from job_hunter.sources.boards.jobteaser import JobTeaserSource
from job_hunter.sources.boards.mycareersfuture import MyCareersFutureSource
from job_hunter.sources.boards.reed import ReedSource
from job_hunter.sources.boards.remoteok import RemoteOKSource
from job_hunter.sources.boards.remotive import RemotiveSource
from job_hunter.sources.boards.start_munich import StartMunichSource
from job_hunter.sources.boards.startup_jobs import StartupJobsSource
from job_hunter.sources.boards.the_muse import TheMuseSource
from job_hunter.sources.boards.weworkremotely import WeWorkRemotelySource
from job_hunter.sources.boards.workingnomads import WorkingNomadsSource
from job_hunter.sources.boards.yc_jobs import YCJobsSource

BOARD_REGISTRY: dict[str, type] = {
    "adzuna": AdzunaSource,
    "arbeitsagentur": ArbeitsagenturSource,
    "arbeitnow": ArbeitnowSource,
    "bayt": BaytSource,
    "careerjet": CareerjetSource,
    "gulftalent": GulfTalentSource,
    "hh": HHSource,
    "himalayas": HimalayasSource,
    "jobbank": JobBankSource,
    "jobicy": JobicySource,
    "jobspy": JobSpySource,
    "jobstreet": JobStreetSource,
    "jobteaser": JobTeaserSource,
    "mycareersfuture": MyCareersFutureSource,
    "reed": ReedSource,
    "remoteok": RemoteOKSource,
    "remotive": RemotiveSource,
    "the_muse": TheMuseSource,
    "weworkremotely": WeWorkRemotelySource,
    "workingnomads": WorkingNomadsSource,
    "startup_jobs": StartupJobsSource,
    "yc_jobs": YCJobsSource,
    "start_munich": StartMunichSource,
}

__all__ = [
    "BOARD_REGISTRY",
    "AdzunaSource",
    "ArbeitsagenturSource",
    "ArbeitnowSource",
    "BaytSource",
    "CareerjetSource",
    "GulfTalentSource",
    "HHSource",
    "HimalayasSource",
    "JobBankSource",
    "JobicySource",
    "JobSpySource",
    "JobStreetSource",
    "JobTeaserSource",
    "MyCareersFutureSource",
    "ReedSource",
    "RemoteOKSource",
    "RemotiveSource",
    "TheMuseSource",
    "WeWorkRemotelySource",
    "WorkingNomadsSource",
    "StartupJobsSource",
    "YCJobsSource",
    "StartMunichSource",
]
