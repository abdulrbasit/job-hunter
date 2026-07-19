"""Deterministic profile file compiler.

Strips markdown noise, empty template lines, draft stories, and LaTeX markup from
profile files. Writes minified copies to outputs/state/compiled/ for use during
pipeline runs. Called automatically — never by the user directly.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_COMPILED_DIR = Path("outputs/state/compiled")


def _compiled_dir(root: Path) -> Path:
    d = root / _COMPILED_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# career_context.md
# ---------------------------------------------------------------------------

_EMPTY_BULLET_RE = re.compile(r"^- [^:]+:\s*$")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def compile_career_context(src: Path, out_dir: Path) -> Path:
    """Strip noise from career_context.md → career_context.min.md."""
    text = src.read_text(encoding="utf-8")

    # Strip HTML comments
    text = _HTML_COMMENT_RE.sub("", text)

    lines_out: list[str] = []
    for line in text.splitlines():
        # Drop top-level file header (redundant in context)
        if line.strip() == "# Career Context":
            continue
        # Drop empty template bullets: "- Key:" with nothing after colon
        if _EMPTY_BULLET_RE.match(line):
            continue
        lines_out.append(line.rstrip())

    text = _collapse_blanks("\n".join(lines_out))
    dst = out_dir / "career_context.min.md"
    dst.write_text(text.strip() + "\n", encoding="utf-8")
    return dst


# ---------------------------------------------------------------------------
# story_bank.md
# ---------------------------------------------------------------------------


def compile_story_bank(src: Path, out_dir: Path) -> Path:
    """Strip Draft sections and story metadata from story_bank.md → story_bank.min.md."""
    text = src.read_text(encoding="utf-8")
    text = _HTML_COMMENT_RE.sub("", text)
    lines = text.splitlines()

    # Preamble ends at the first `---` separator (standard story_bank.md layout).
    # If a user's file has no such separator, there is no preamble to strip —
    # treating the whole file as preamble would silently drop every story.
    has_separator = any(line.strip() == "---" for line in lines)

    out: list[str] = []
    in_preamble = has_separator
    in_draft = False

    for line in lines:
        if in_preamble and line.strip() == "---":
            in_preamble = False
            continue

        if in_preamble:
            continue

        # Track Draft / Final sections
        if line.startswith("## "):
            in_draft = "draft" in line.lower()
            if in_draft:
                continue
            out.append(line)
            continue

        if in_draft:
            continue

        # Inside Final: strip rating + tags metadata lines
        stripped = line.strip()
        if stripped.startswith("**Rating") or stripped.startswith("- **Tags"):
            continue

        out.append(line.rstrip())

    text = _collapse_blanks("\n".join(out))
    dst = out_dir / "story_bank.min.md"
    dst.write_text(text.strip() + "\n", encoding="utf-8")
    return dst


# ---------------------------------------------------------------------------
# resume.tex
# ---------------------------------------------------------------------------


def compile_resume(src: Path, out_dir: Path) -> Path:
    """Extract plain text from resume .tex → resume.compact.txt."""
    from job_hunter.core.latex_utils import compact_latex_resume

    tex = src.read_text(encoding="utf-8")
    compact = compact_latex_resume(tex)
    dst = out_dir / "resume.compact.txt"
    dst.write_text(compact + "\n", encoding="utf-8")
    return dst


# ---------------------------------------------------------------------------
# compile_all
# ---------------------------------------------------------------------------


def compile_all(root: Path) -> None:
    """Compile all configured profile files. Called at pipeline/skill start.

    Never raises. A missing config/profile file is a silent no-op (fine for a fresh
    workspace — see the config_path.exists() check below). Any other failure (malformed
    YAML, a bad-encoding profile file, a bug in the LaTeX compactor) is caught and logged
    as one compact warning line, and the pipeline falls back to raw profile files —
    matching the "compile-profile is silent on failure" contract documented in SKILL.md.
    """
    try:
        _compile_all_unsafe(root)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[compile_profile] failed, continuing with raw profile files: %s", exc)


def _compile_all_unsafe(root: Path) -> None:
    import yaml

    config_path = root / "config" / "job_hunter.yml"
    if not config_path.exists():
        logger.debug("[compile_profile] config not found, skipping")
        return

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    profile = config.get("profile", {}) or {}

    out_dir = _compiled_dir(root)

    def _resolve(key: str, default: str) -> Path | None:
        from job_hunter.config.resumes import SPEC_KEYS, base_resume_spec

        if key in SPEC_KEYS and isinstance(profile.get("resumes"), dict):
            val = base_resume_spec(profile).get(key) or default
        else:
            val = profile.get(key) or default
        p = Path(val)
        full = p if p.is_absolute() else root / p
        return full if full.exists() else None

    results: list[tuple[str, int, int]] = []

    career_src = _resolve("career_context", "profile/career_context.md")
    if career_src:
        dst = compile_career_context(career_src, out_dir)
        results.append((career_src.name, career_src.stat().st_size, dst.stat().st_size))

    story_src = _resolve("story_bank", "profile/story_bank.md")
    if story_src:
        dst = compile_story_bank(story_src, out_dir)
        results.append((story_src.name, story_src.stat().st_size, dst.stat().st_size))

    resume_src = _resolve("resume_tex", "profile/resume.tex")
    if resume_src:
        dst = compile_resume(resume_src, out_dir)
        results.append((resume_src.name, resume_src.stat().st_size, dst.stat().st_size))

    for name, before, after in results:
        pct = round((1 - after / before) * 100) if before else 0
        if before > 50 and after <= 2:
            logger.warning(
                "[compile_profile] %s compiled to empty (%d → %d chars) — "
                "check its structure against the template; pipeline will run with no content from it",
                name,
                before,
                after,
            )
        else:
            logger.info("[compile_profile] %-30s %6d → %6d chars  (%d%% saved)", name, before, after, pct)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _collapse_blanks(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)
