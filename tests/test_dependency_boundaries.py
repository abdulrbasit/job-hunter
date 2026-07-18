"""Guards package layering from docs/architecture.md: tracking/ is the state API;
pipeline/ and agent_context/ must not depend on ux/ (the presentation layer, outermost).

ruff's TID251 banned-api rule enforces this at lint time too (pyproject.toml); this test
is a second, independent check that doesn't depend on ruff config staying correct.
"""

from __future__ import annotations

import ast
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "job_hunter"


def _imported_modules(py_file: Path) -> list[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
    return modules


def _assert_no_dependency(package_dir: Path, banned_prefix: str) -> None:
    for py_file in package_dir.rglob("*.py"):
        for module in _imported_modules(py_file):
            assert not module.startswith(banned_prefix), (
                f"{py_file.relative_to(_PACKAGE_ROOT.parent)} imports {module} "
                f"— {package_dir.name}/ must not depend on {banned_prefix}"
            )


def test_tracking_does_not_depend_on_ux_pipeline_cli_or_agent_context() -> None:
    for banned in ("job_hunter.ux", "job_hunter.pipeline", "job_hunter.cli", "job_hunter.agent_context"):
        _assert_no_dependency(_PACKAGE_ROOT / "tracking", banned)


def test_pipeline_does_not_depend_on_ux_or_cli() -> None:
    for banned in ("job_hunter.ux", "job_hunter.cli"):
        _assert_no_dependency(_PACKAGE_ROOT / "pipeline", banned)


def test_agent_context_does_not_depend_on_ux_or_cli() -> None:
    for banned in ("job_hunter.ux", "job_hunter.cli"):
        _assert_no_dependency(_PACKAGE_ROOT / "agent_context", banned)


def test_metrics_does_not_depend_on_ux_pipeline_or_cli() -> None:
    for banned in ("job_hunter.ux", "job_hunter.pipeline", "job_hunter.cli"):
        _assert_no_dependency(_PACKAGE_ROOT / "metrics", banned)


def test_companies_does_not_depend_on_ux_pipeline_or_cli() -> None:
    """job_hunter.companies (seed + runtime store + gating) sits below pipeline/ux/cli,
    same layer as locations/ and filters/ — consumed by them, not the reverse."""
    for banned in ("job_hunter.ux", "job_hunter.pipeline", "job_hunter.cli"):
        _assert_no_dependency(_PACKAGE_ROOT / "companies", banned)


def test_ux_does_not_depend_on_cli() -> None:
    """ux/ legitimately calls into pipeline.stages.readme (report generation, see
    pyproject.toml's TID251 exemption) and agent_context.validate_score_file (health.py's
    repository-integrity check) but must not reach into cli/, the composition root."""
    _assert_no_dependency(_PACKAGE_ROOT / "ux", "job_hunter.cli")


def test_workspace_does_not_depend_on_ux_cli_or_agent_context() -> None:
    """workspace/finalize.py's run_finalize_core is shared by cli/, ux/, and the public
    `job-hunter finalize` command — it must stay callable from ux/ (which must not depend
    on cli/), so it takes verify_errors/validate_score_file as caller-supplied parameters
    instead of importing job_hunter.ux.health or job_hunter.agent_context itself."""
    for banned in ("job_hunter.ux", "job_hunter.cli", "job_hunter.agent_context"):
        _assert_no_dependency(_PACKAGE_ROOT / "workspace", banned)


def test_filters_do_not_depend_on_config() -> None:
    """Package filter definitions and resources sit below user config loading."""
    _assert_no_dependency(_PACKAGE_ROOT / "filters", "job_hunter.config")


def test_banned_import_boundaries_stay_configured() -> None:
    """The AST checks above are one guard; ruff's TID251 banned-api list (docs/testing.md's
    'Known technical debt' section) is the other. Catch someone removing the ruff side only."""
    import tomllib

    pyproject = tomllib.loads((_PACKAGE_ROOT.parent / "pyproject.toml").read_text(encoding="utf-8"))
    banned = pyproject["tool"]["ruff"]["lint"]["flake8-tidy-imports"]["banned-api"]
    assert {"job_hunter.cli", "job_hunter.pipeline", "job_hunter.ux", "job_hunter.agent_context"} <= banned.keys()


def test_ty_strict_override_still_covers_models_and_config() -> None:
    """Widening ty strictness to another package is a real type-fixing pass (docs/testing.md);
    this only guards that the two packages already promoted to strict don't quietly regress."""
    import tomllib

    pyproject = tomllib.loads((_PACKAGE_ROOT.parent / "pyproject.toml").read_text(encoding="utf-8"))
    overrides = pyproject["tool"]["ty"]["overrides"]
    strict_override = next(
        o for o in overrides if set(o["include"]) >= {"job_hunter/models.py", "job_hunter/config/**"}
    )
    assert strict_override["rules"]["invalid-argument-type"] == "error"
