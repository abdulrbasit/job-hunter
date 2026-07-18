"""Validates every SKILL.md and reference.md under .claude/skills/ for required frontmatter and quality rules."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

SKILLS_DIR = Path(__file__).parent.parent / ".claude" / "skills"
REQUIRED_AUTHOR = "Abdul Basit (@abdulrbasit)"
ALLOWED_CATEGORIES = {"workflow", "atomic", "tool", "linkedin", "dev"}

# Patterns that indicate a hardcoded config value was embedded in skill logic.
# Skills should read thresholds from config at runtime, not bake them in.
_HARDCODED_THRESHOLD_RE = re.compile(
    r"(?<!\w)(min_fit_score|min_fit|max_tailor|max_years)\s*[=:]\s*\d+",
)

skill_files = sorted(SKILLS_DIR.glob("*/SKILL.md"))
reference_files = sorted(SKILLS_DIR.glob("*/reference.md"))
REPO_ROOT = Path(__file__).parent.parent

# Skill names that must NOT exist after the v0.0 rebuild
DELETED_SKILL_NAMES = {
    "hunt",
    "manage-skills",
    "push",
    "report-bug",
    "process-batch",
    "process-one",
    "stories",
    "one",
    "batch",
}


# ---------------------------------------------------------------------------
# SKILL.md checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skill_md", skill_files, ids=lambda p: p.parent.name)
def test_required_frontmatter_keys(skill_md: Path) -> None:
    text = skill_md.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    assert len(parts) >= 3, f"{skill_md}: no frontmatter found"
    fm = yaml.safe_load(parts[1])
    assert fm, f"{skill_md}: frontmatter is empty"
    for key in ("name", "description", "when_to_use", "author"):
        assert key in fm, f"{skill_md}: missing required frontmatter key '{key}'"


@pytest.mark.parametrize("skill_md", skill_files, ids=lambda p: p.parent.name)
def test_author_value(skill_md: Path) -> None:
    text = skill_md.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    fm = yaml.safe_load(parts[1])
    if fm.get("third-party"):
        return
    assert fm.get("author") == REQUIRED_AUTHOR, (
        f"{skill_md}: author must be '{REQUIRED_AUTHOR}', got '{fm.get('author')}'"
    )


@pytest.mark.parametrize("skill_md", skill_files, ids=lambda p: p.parent.name)
def test_no_hardcoded_thresholds(skill_md: Path) -> None:
    body = skill_md.read_text(encoding="utf-8").split("---", 2)[-1]
    match = _HARDCODED_THRESHOLD_RE.search(body)
    assert not match, (
        f"{skill_md}: hardcoded config threshold found: '{match.group()}' — "
        "read thresholds from config at runtime instead"
    )


@pytest.mark.parametrize("skill_md", skill_files, ids=lambda p: p.parent.name)
def test_category_present_and_valid(skill_md: Path) -> None:
    text = skill_md.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    fm = yaml.safe_load(parts[1])
    cat = fm.get("category")
    assert cat is not None, f"{skill_md}: missing 'category:' frontmatter field"
    assert cat in ALLOWED_CATEGORIES, f"{skill_md}: category '{cat}' must be one of {sorted(ALLOWED_CATEGORIES)}"


@pytest.mark.parametrize("skill_md", skill_files, ids=lambda p: p.parent.name)
def test_dev_category_when_to_use(skill_md: Path) -> None:
    text = skill_md.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    fm = yaml.safe_load(parts[1])
    if fm.get("category") != "dev":
        return
    when = fm.get("when_to_use", "")
    assert "Developer context only" in when, (
        f"{skill_md}: dev-category skill must start when_to_use with 'Developer context only'"
    )


@pytest.mark.parametrize("skill_md", skill_files, ids=lambda p: p.parent.name)
def test_skill_folder_name_matches_frontmatter_name(skill_md: Path) -> None:
    text = skill_md.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    fm = yaml.safe_load(parts[1])
    folder_name = skill_md.parent.name
    skill_name = fm.get("name", "")
    assert skill_name == folder_name, (
        f"{skill_md}: frontmatter name '{skill_name}' must match folder name '{folder_name}'"
    )


# ---------------------------------------------------------------------------
# reference.md checks
# ---------------------------------------------------------------------------


def test_reference_no_hardcoded_thresholds() -> None:
    for ref_md in reference_files:
        body = ref_md.read_text(encoding="utf-8")
        match = _HARDCODED_THRESHOLD_RE.search(body)
        assert not match, (
            f"{ref_md}: hardcoded config threshold found: '{match.group()}'; "
            "reference.md must not contain hardcoded config values"
        )


def test_no_stale_process_command_names() -> None:
    """Ensure stale old command names are absent (check exact old names, not substrings of new names)."""
    import re

    # Old stale patterns — must NOT appear. Use word-boundary so "process-job-url" is not flagged.
    stale_patterns = [
        re.compile(r"/process-candidates\b"),
        re.compile(r"/process-job\b(?!-url)"),  # match /process-job but NOT /process-job-url
    ]
    targets = list(SKILLS_DIR.glob("*/SKILL.md"))
    targets += list(SKILLS_DIR.glob("*/reference.md"))
    targets += [
        REPO_ROOT / "CLAUDE.md",
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / "GEMINI.md",
    ]
    stale = {}
    for path in targets:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        matches = [p.pattern for p in stale_patterns if p.search(text)]
        if matches:
            stale[str(path.relative_to(REPO_ROOT))] = matches
    assert not stale, f"stale process command references found: {stale}"


def test_deleted_skill_names_absent() -> None:
    """Deleted skills must not exist as directories under .claude/skills/."""
    existing_folders = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}
    found = DELETED_SKILL_NAMES & existing_folders
    assert not found, f"deleted skill folder(s) still exist: {sorted(found)}"


@pytest.mark.parametrize("skill_md", skill_files, ids=lambda p: p.parent.name)
def test_skill_files_do_not_embed_inline_python_scripts(skill_md: Path) -> None:
    body = skill_md.read_text(encoding="utf-8").split("---", 2)[-1]
    assert "python -c" not in body, f"{skill_md}: use job-hunter CLI helpers, not inline python -c"
    assert "```python" not in body, f"{skill_md}: move Python scripts to CLI helpers or reference.md"


@pytest.mark.parametrize("skill_md", skill_files, ids=lambda p: p.parent.name)
def test_skill_files_stay_compact(skill_md: Path) -> None:
    line_count = len(skill_md.read_text(encoding="utf-8").splitlines())
    assert line_count <= 500, f"{skill_md}: split large static detail into reference.md or CLI helpers"


def test_product_tree_does_not_embed_dev_tools_skill() -> None:
    assert not (SKILLS_DIR / "dev-tools" / "SKILL.md").exists()
    assert not (SKILLS_DIR / "dev-skills" / "SKILL.md").exists()


def test_score_skill_requires_matched_story_ids() -> None:
    text = (SKILLS_DIR / "job-hunter" / "modes" / "score.md").read_text(encoding="utf-8")
    assert "matched_story_ids" in text


def test_job_hunter_router_skill_contract() -> None:
    """Validate the canonical job-hunter router skill structure."""
    path = SKILLS_DIR / "job-hunter" / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---", 2)[1])

    assert fm["name"] == "job-hunter"
    assert fm["category"] == "workflow"

    # All required modes present in argument-hint
    for mode in ("batch", "tailor", "finalize", "help"):
        assert mode in fm["argument-hint"], f"mode '{mode}' missing from argument-hint"

    # Routes to correct router mode paths.
    for child in (
        "batch",
        "one",
        "tailor",
        "outreach",
        "interview",
        "score",
        "research",
        "stories",
    ):
        assert f".claude/skills/job-hunter/modes/{child}.md" in text, (
            f"job-hunter router must reference .claude/skills/job-hunter/modes/{child}.md"
        )

    # finalize has no mode file — all bookkeeping lives in `job-hunter finalize` itself.
    assert ".claude/skills/job-hunter/modes/finalize.md" not in text
    assert "job-hunter finalize" in text

    assert "## Command Menu" in text
    assert "job-hunter dash" in text
    assert "no terminal dashboard to run inline" in text

    # All required /job-hunter commands present in the command menu
    for command in (
        "/job-hunter dashboard",
        "/job-hunter batch",
        "/job-hunter one <url>",
        "/job-hunter finalize",
        "/job-hunter tailor <job>",
        "/job-hunter outreach <job>",
        "/job-hunter interview <job>",
    ):
        assert command in text, f"missing command in job-hunter router: {command}"

    # No raw git operations in the router
    assert "git commit" not in text
    assert "git push" not in text
