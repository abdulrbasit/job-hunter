import os
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Must be set before any module is imported; config/loader.py reads API key constants at module level.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("BRAVE_API_KEY", "test-brave-key")
os.environ.setdefault("RAPIDAPI_KEY", "test-rapidapi-key")

runtime_root = Path(tempfile.mkdtemp(prefix="job-hunter-test-root-"))
config_dir = runtime_root / "config"
config_dir.mkdir(parents=True)
(config_dir / "job_hunter.yml").write_text(
    textwrap.dedent(
        """
        mode: agent
        profile:
          resume_tex: profile/resume_double_column.tex
          story_bank: profile/story_bank.md
          career_context: profile/career_context.md
        job_titles:
          - Product Manager
        regions:
          primary:
            enabled: true
            primary: true
            country: DE
            search_lang: en
            location: Berlin
        exclusions:
          companies: []
          title_terms: []
          languages: []
          industries: []
        scoring:
          min_fit_score: 70
          batch_size: 15
        linkedin:
          enabled: false
        llm:
          default_provider: anthropic
          providers:
            validation: anthropic
            scoring: anthropic
            tailoring: anthropic
            cover_letter: anthropic
            jd_extraction: anthropic
            linkedin: anthropic
          models:
            validation: test-model
            scoring: test-model
            tailoring: test-model
            cover_letter: test-model
            jd_extraction: test-model
            linkedin: test-model
          max_tokens:
            validation: 256
            scoring: 256
            tailoring: 1024
            cover_letter: 1024
            jd_extraction: 512
            linkedin: 1024
        """
    ).lstrip(),
    encoding="utf-8",
)

profile_dir = runtime_root / "profile"
profile_dir.mkdir(parents=True)
for filename in ("resume_double_column.tex", "story_bank.md", "altacv.cls"):
    (profile_dir / filename).write_text("", encoding="utf-8")
(profile_dir / "career_context.md").write_text("", encoding="utf-8")

state_dir = runtime_root / "outputs" / "state"
state_dir.mkdir(parents=True)
(state_dir / "discovered_urls.yml").write_text("discovered: []\ncandidate_urls: []\n", encoding="utf-8")

os.environ.setdefault("JOB_HUNTER_ROOT", str(runtime_root))

# The project package is on sys.path via the installed package (pip install -e .)
# No manual path manipulation needed.


@pytest.fixture(autouse=True)
def _clear_llm_cache():
    yield
    from job_hunter.llm import client as _llm_client

    _llm_client.clear_cache()


@pytest.fixture
def mock_llm_client():
    """Factory fixture — call mock_llm_client(text) to get a MagicMock whose complete() returns text."""

    def _factory(text: str) -> MagicMock:
        mock = MagicMock()
        mock.complete.return_value = MagicMock(content=text)
        return mock

    return _factory


def mk_params(job_titles, regions, *, search_lang="", excluded_title_terms=None):
    """Convert legacy (job_titles, regions) args to SearchParams for the first region."""
    from job_hunter.models import SearchParams

    key, cfg = next(iter(regions.items()))
    return SearchParams(
        region_key=key,
        country=str(cfg.get("country", "")),
        location=str(cfg.get("location", "")),
        search_lang=str(cfg.get("search_lang", search_lang)),
        job_titles=list(job_titles),
        excluded_title_terms=list(excluded_title_terms) if excluded_title_terms else [],
    )
