"""Guards the package layering from ARCHITECTURE.md §1: tracking/ is the state API;
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


def test_ux_does_not_depend_on_cli() -> None:
    """ux/ legitimately calls into pipeline.stages.readme (report generation, see
    pyproject.toml's TID251 exemption) and agent_context.validate_score_file (health.py's
    repository-integrity check) but must not reach into cli/, the composition root."""
    _assert_no_dependency(_PACKAGE_ROOT / "ux", "job_hunter.cli")
