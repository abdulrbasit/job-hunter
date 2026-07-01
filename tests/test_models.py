from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from job_hunter.models import JobPosting


def _sample_posting() -> JobPosting:
    from job_hunter.models import JobPosting

    return JobPosting(
        title="Software Engineer",
        company="Acme Corp",
        url="https://acme.com/jobs/1",
        location="Berlin",
        snippet="Work on cool stuff",
        source="Greenhouse API",
        posted="2024-01-01",
        region="de",
        query="Software Engineer Berlin",
        extraction_method="ats_api",
        source_url="https://acme.com",
    )


def test_round_trip() -> None:
    jp = _sample_posting()
    from job_hunter.models import JobPosting

    assert JobPosting.model_validate(jp.model_dump()) == jp


def test_extra_keys_dropped() -> None:
    jp = _sample_posting()
    from job_hunter.models import JobPosting

    d = jp.model_dump()
    d["unknown_field"] = "should be dropped"
    result = JobPosting.model_validate(d)
    assert result == jp


def test_hunt_output_snapshot_path_is_optional_legacy_field() -> None:
    from pathlib import Path

    from job_hunter.models import HuntOutput

    default = HuntOutput()
    assert default.snapshot_path is None

    with_path = HuntOutput(snapshot_path=Path("outputs/state/hunt_scrape_2026-01-01.json"))
    assert with_path.snapshot_path == Path("outputs/state/hunt_scrape_2026-01-01.json")


def test_models_module_has_no_dependency_on_config_cli_ux_or_sources() -> None:
    """Domain models are the lowest layer (ARCHITECTURE.md §1) — importing config/cli/ux/sources
    into models.py would make a data contract depend on the code that produces or renders it."""
    import ast
    from pathlib import Path

    banned_prefixes = ("job_hunter.config", "job_hunter.cli", "job_hunter.ux", "job_hunter.sources")
    source = Path(__file__).resolve().parents[1].joinpath("job_hunter", "models.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    offenders = [name for name in imported if name.startswith(banned_prefixes)]
    assert offenders == [], f"models.py must not import: {offenders}"
