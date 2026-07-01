from types import SimpleNamespace
from typing import Never
from unittest.mock import patch

from conftest import mk_params

from job_hunter.sources.boards.jobspy import _ISO_TO_INDEED, JobSpySource

_BASE_CFG = {
    "http": {
        "job_boards": {
            "jobspy": {
                "enabled": True,
                "results_per_query": 5,
                "hours_old": 72,
            }
        }
    }
}

_DE = {"DE": {"country": "DE", "location": "Berlin"}}
_ZZ = {"ZZ": {"country": "ZZ", "location": "Somewhere"}}
_US = {"US": {"country": "US", "location": "Austin"}}

_JOBSPY_INDEED_COUNTRIES = {
    "AR": "argentina",
    "AU": "australia",
    "AT": "austria",
    "BH": "bahrain",
    "BD": "bangladesh",
    "BE": "belgium",
    "BG": "bulgaria",
    "BR": "brazil",
    "CA": "canada",
    "CL": "chile",
    "CN": "china",
    "CO": "colombia",
    "CR": "costa rica",
    "HR": "croatia",
    "CY": "cyprus",
    "CZ": "czech republic",
    "DK": "denmark",
    "EC": "ecuador",
    "EG": "egypt",
    "EE": "estonia",
    "FI": "finland",
    "FR": "france",
    "DE": "germany",
    "GR": "greece",
    "HK": "hong kong",
    "HU": "hungary",
    "IN": "india",
    "ID": "indonesia",
    "IE": "ireland",
    "IL": "israel",
    "IT": "italy",
    "JP": "japan",
    "KW": "kuwait",
    "LV": "latvia",
    "LT": "lithuania",
    "LU": "luxembourg",
    "MY": "malaysia",
    "MT": "malta",
    "MX": "mexico",
    "MA": "morocco",
    "NL": "netherlands",
    "NZ": "new zealand",
    "NG": "nigeria",
    "NO": "norway",
    "OM": "oman",
    "PK": "pakistan",
    "PA": "panama",
    "PE": "peru",
    "PH": "philippines",
    "PL": "poland",
    "PT": "portugal",
    "QA": "qatar",
    "RO": "romania",
    "SA": "saudi arabia",
    "SG": "singapore",
    "SK": "slovakia",
    "SI": "slovenia",
    "ZA": "south africa",
    "KR": "south korea",
    "ES": "spain",
    "SE": "sweden",
    "CH": "switzerland",
    "TW": "taiwan",
    "TH": "thailand",
    "TR": "turkey",
    "UA": "ukraine",
    "AE": "united arab emirates",
    "GB": "uk",
    "US": "usa",
    "UY": "uruguay",
    "VE": "venezuela",
    "VN": "vietnam",
}


class _Rows:
    def __init__(self, rows) -> None:
        self._rows = rows
        self.empty = not rows

    def iterrows(self):
        return iter(enumerate(self._rows))


class TestJobSpySource:
    def test_name(self) -> None:
        assert JobSpySource().source_name == "jobspy"

    def test_is_enabled_false_when_disabled(self) -> None:
        disabled = {"http": {"job_boards": {"jobspy": {"enabled": False}}}}
        with patch("job_hunter.sources.boards.jobspy.get_api_config", return_value=disabled):
            assert JobSpySource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self, monkeypatch) -> None:
        from job_hunter.models import JobPosting

        fake_row = {
            "title": "Software Engineer",
            "company": "SpyCo",
            "job_url": "https://jobspy.com/1",
            "date_posted": "2026-06-01",
            "description": "A role.",
            "location": "Berlin, DE",
            "site": "google",
        }

        class _Rows:
            empty = False

            def iterrows(self):
                return iter([(0, fake_row)])

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=lambda **kw: _Rows()),
        )

        with patch("job_hunter.sources.boards.jobspy.get_api_config", return_value=_BASE_CFG):
            jobs = JobSpySource().fetch(mk_params(["Software Engineer"], _DE))
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "JobSpy/Google"
        assert jobs[0].location == "Berlin, DE"

    def test_fetch_does_not_early_filter_jobs_outside_region_location(self, monkeypatch) -> None:
        """JobSpy no longer drops a job locally just because its location string
        doesn't match the region — the upstream `location` kwarg already scopes the
        Google/Indeed query server-side, and wrong-region stragglers are caught by
        JobPolicy/quality_gate downstream via the job's location field."""
        onsite_row = {
            "title": "Software Engineer",
            "company": "SpyCo",
            "job_url": "https://jobspy.com/2",
            "date_posted": "2026-06-01",
            "description": "A role.",
            "location": "San Francisco, CA",
            "site": "google",
        }

        class _RowsFixed:
            empty = False

            def iterrows(self):
                return iter([(0, onsite_row)])

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=lambda **kw: _RowsFixed()),
        )

        with patch("job_hunter.sources.boards.jobspy.get_api_config", return_value=_BASE_CFG):
            jobs = JobSpySource().fetch(mk_params(["Software Engineer"], _DE))
        # _DE maps to both google and indeed sites, so the same row is returned per site.
        assert len(jobs) >= 1
        assert all(job.location == "San Francisco, CA" for job in jobs)


class TestJobSpyCircuitBreaker:
    def test_403_disables_site_after_first_failure(self, monkeypatch) -> None:
        import job_hunter.sources.boards.jobspy as jspy_mod

        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", set())

        indeed_calls = []

        def fake_scrape(site_name, **kw) -> None:
            site = site_name[0] if isinstance(site_name, list) else site_name
            if site == "indeed":
                indeed_calls.append(1)
                raise Exception("Indeed response status code 403")
            return None

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch("job_hunter.sources.boards.jobspy.get_api_config", return_value=_BASE_CFG):
            JobSpySource().fetch(mk_params(["Product Manager", "Senior PM"], _DE))

        assert "indeed" in jspy_mod._DISABLED_SITES
        assert len(indeed_calls) == 1

    def test_non_403_does_not_disable_site(self, monkeypatch) -> None:
        import job_hunter.sources.boards.jobspy as jspy_mod

        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", set())

        def fake_scrape(site_name, **kw) -> Never:
            raise Exception("Connection timeout after 10s")

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch("job_hunter.sources.boards.jobspy.get_api_config", return_value=_BASE_CFG):
            JobSpySource().fetch(mk_params(["Product Manager"], _DE))

        assert "google" not in jspy_mod._DISABLED_SITES
        assert "indeed" not in jspy_mod._DISABLED_SITES

    def test_forbidden_string_also_disables_site(self, monkeypatch) -> None:
        import job_hunter.sources.boards.jobspy as jspy_mod

        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", set())

        def fake_scrape(site_name, **kw) -> None:
            site = site_name[0] if isinstance(site_name, list) else site_name
            if site == "indeed":
                raise Exception("403 Client Error: Forbidden for url: https://indeed.com")
            return None

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch("job_hunter.sources.boards.jobspy.get_api_config", return_value=_BASE_CFG):
            JobSpySource().fetch(mk_params(["Product Manager"], _DE))

        assert "indeed" in jspy_mod._DISABLED_SITES

    def test_all_sites_disabled_skips_remaining_titles(self, monkeypatch) -> None:
        import job_hunter.sources.boards.jobspy as jspy_mod

        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", {"google", "indeed"})

        call_count = []

        def fake_scrape(**kw) -> None:
            call_count.append(1)
            return None

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch("job_hunter.sources.boards.jobspy.get_api_config", return_value=_BASE_CFG):
            jobs = JobSpySource().fetch(mk_params(["Product Manager", "Senior PM"], _DE))

        assert jobs == []
        assert call_count == []


class TestJobSpyAutoSelection:
    def test_indeed_country_mapping_matches_jobspy_country_enum(self) -> None:
        assert _ISO_TO_INDEED == _JOBSPY_INDEED_COUNTRIES

    def test_google_and_indeed_selected_for_mapped_country(self, monkeypatch) -> None:
        import job_hunter.sources.boards.jobspy as jspy_mod

        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", set())

        calls: list[str] = []

        def fake_scrape(site_name, **kw) -> None:
            calls.append(site_name[0])
            return None

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch("job_hunter.sources.boards.jobspy.get_api_config", return_value=_BASE_CFG):
            JobSpySource().fetch(mk_params(["Engineer"], _DE))

        assert "google" in calls
        assert "indeed" in calls

    def test_only_google_for_unmapped_country(self, monkeypatch) -> None:
        import job_hunter.sources.boards.jobspy as jspy_mod

        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", set())

        calls: list[str] = []

        def fake_scrape(site_name, **kw) -> None:
            calls.append(site_name[0])
            return None

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch("job_hunter.sources.boards.jobspy.get_api_config", return_value=_BASE_CFG):
            JobSpySource().fetch(mk_params(["Engineer"], _ZZ))

        assert "google" in calls
        assert "indeed" not in calls

    def test_google_search_term_passed_to_scrape(self, monkeypatch) -> None:
        import job_hunter.sources.boards.jobspy as jspy_mod

        monkeypatch.setattr(jspy_mod, "_DISABLED_SITES", set())

        captured: list[dict] = []

        def fake_scrape(site_name, **kw) -> None:
            captured.append({"site": site_name[0], **kw})
            return None

        monkeypatch.setitem(
            __import__("sys").modules,
            "jobspy",
            SimpleNamespace(scrape_jobs=fake_scrape),
        )

        with patch("job_hunter.sources.boards.jobspy.get_api_config", return_value=_BASE_CFG):
            JobSpySource().fetch(mk_params(["Data Scientist"], _US))

        assert len(captured) >= 1
        for call in captured:
            assert call.get("google_search_term") == "Data Scientist jobs near Austin"
            assert call.get("search_term") == "Data Scientist"
