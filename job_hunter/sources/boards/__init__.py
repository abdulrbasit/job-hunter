"""Job board adapter registry.

Maps source name → JobSourceAdapter subclass for every board source.
The orchestrator uses this to instantiate and dispatch sources without
importing each adapter individually.
"""

from __future__ import annotations

from job_hunter.sources.adzuna_source import AdzunaSource
from job_hunter.sources.arbeitsagentur_source import ArbeitsagenturSource
from job_hunter.sources.careerjet_source import CareerjetSource
from job_hunter.sources.gulftalent_source import GulfTalentSource
from job_hunter.sources.himalayas_source import HimalayasSource
from job_hunter.sources.job_boards import ArbeitnowSource, JSearchSource
from job_hunter.sources.jobbank_source import JobBankSource
from job_hunter.sources.jobicy_source import JobicySource
from job_hunter.sources.jobspy_source import JobSpySource
from job_hunter.sources.jobstreet_source import JobStreetSource
from job_hunter.sources.jooble_source import JoobleSource
from job_hunter.sources.mycareersfuture_source import MyCareersFutureSource
from job_hunter.sources.reed_source import ReedSource
from job_hunter.sources.remoteok_source import RemoteOKSource
from job_hunter.sources.remotive_source import RemotiveSource
from job_hunter.sources.the_muse_source import TheMuseSource
from job_hunter.sources.weworkremotely_source import WeWorkRemotelySource
from job_hunter.sources.workingnomads_source import WorkingNomadsSource

BOARD_REGISTRY: dict[str, type] = {
    "adzuna": AdzunaSource,
    "arbeitsagentur": ArbeitsagenturSource,
    "arbeitnow": ArbeitnowSource,
    "careerjet": CareerjetSource,
    "gulftalent": GulfTalentSource,
    "himalayas": HimalayasSource,
    "jobbank": JobBankSource,
    "jobicy": JobicySource,
    "jobspy": JobSpySource,
    "jobstreet": JobStreetSource,
    "jooble": JoobleSource,
    "jsearch": JSearchSource,
    "mycareersfuture": MyCareersFutureSource,
    "reed": ReedSource,
    "remoteok": RemoteOKSource,
    "remotive": RemotiveSource,
    "the_muse": TheMuseSource,
    "weworkremotely": WeWorkRemotelySource,
    "workingnomads": WorkingNomadsSource,
}

__all__ = [
    "BOARD_REGISTRY",
    "AdzunaSource",
    "ArbeitsagenturSource",
    "ArbeitnowSource",
    "CareerjetSource",
    "GulfTalentSource",
    "HimalayasSource",
    "JobBankSource",
    "JobicySource",
    "JobSpySource",
    "JobStreetSource",
    "JoobleSource",
    "JSearchSource",
    "MyCareersFutureSource",
    "ReedSource",
    "RemoteOKSource",
    "RemotiveSource",
    "TheMuseSource",
    "WeWorkRemotelySource",
    "WorkingNomadsSource",
]
