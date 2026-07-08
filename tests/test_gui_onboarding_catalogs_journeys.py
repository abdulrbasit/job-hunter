"""RED journey matrix for the GUI-first onboarding/catalog rewrite (Phase 0).

Each test targets one of the six spec journeys and fails today for the
planned reason (missing module/method/field), not a typo. GREEN evidence
lands phase-by-phase as docs/testing/gui-onboarding-catalogs.tdd.md tracks.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from job_hunter.config import service

_VALID_CONFIG = {
    "mode": "agent",
    "profile": {
        "resume_tex": "profile/resume_double_column.tex",
        "story_bank": "profile/story_bank.md",
        "career_context": "profile/career_context.md",
    },
    "job_titles": ["Product Manager"],
    "regions": {"berlin": {"enabled": True, "country": "DE", "location": "Berlin"}},
    "exclusions": {},
    "scoring": {"min_fit_score": 70, "batch_size": 15},
    "llm": {"default_provider": "anthropic"},
}


def _copy_schema(root: Path) -> None:
    real_schema = (Path(__file__).parents[1] / "config" / "schemas" / "job_hunter.schema.json").read_text(
        encoding="utf-8"
    )
    schema_dir = root / "config" / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    (schema_dir / "job_hunter.schema.json").write_text(real_schema, encoding="utf-8")


def test_onboarding_bootstrap_api_not_yet_built() -> None:
    """Phase 3: DashAPI should expose get_bootstrap() for the Get Started page."""
    from job_hunter.ux.web.api import DashAPI

    assert hasattr(DashAPI, "get_bootstrap")


def test_career_stage_not_yet_accepted_by_config_schema(tmp_path: Path) -> None:
    """Phase 1: career_stage should be a valid additive config field."""
    _copy_schema(tmp_path)
    data = dict(_VALID_CONFIG)
    data["career_stage"] = "experienced"

    errors = service.validate_job_hunter_yaml(data, tmp_path)

    assert errors == []


def test_catalog_company_selection_package_not_yet_built() -> None:
    """Phase 2: job_hunter.catalog should load the bundled company catalog."""
    from job_hunter import catalog

    assert callable(catalog.load_companies)


def test_daily_hunt_typed_service_not_yet_built() -> None:
    """Phase 5: DashAPI should expose typed start_hunt()/get_hunt_status()."""
    from job_hunter.ux.web.api import DashAPI

    assert hasattr(DashAPI, "start_hunt")
    assert hasattr(DashAPI, "get_hunt_status")


def test_terminal_ux_not_yet_removed() -> None:
    """Phase 6: job_hunter.ux.terminal should be deleted once the GUI covers its journeys."""
    assert importlib.util.find_spec("job_hunter.ux.terminal") is None


def test_packaged_launch_self_test_not_yet_built() -> None:
    """Phase 7/8: a headless self-test should verify resources/catalog/workspace/config/DB for frozen builds."""
    from job_hunter import diagnostics

    assert callable(diagnostics.self_test)
