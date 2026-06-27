"""Tests for job_hunter/tools/compile_profile.py and job_hunter/core/latex_utils.py."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from job_hunter.core.latex_utils import compact_latex_resume, strip_latex_comments
from job_hunter.tools.compile_profile import (
    _collapse_blanks,
    compile_career_context,
    compile_resume,
    compile_story_bank,
)

# ---------------------------------------------------------------------------
# latex_utils
# ---------------------------------------------------------------------------


def test_strip_latex_comments_removes_full_comment_lines() -> None:
    tex = "\\textbf{Hello}\n% this is a comment\n\\item{World}"
    result = strip_latex_comments(tex)
    assert "comment" not in result
    assert "Hello" in result
    assert "World" in result


def test_strip_latex_comments_strips_inline_comments() -> None:
    result = strip_latex_comments("\\item{Foo} % inline comment")
    assert "comment" not in result
    assert "Foo" in result


def test_compact_latex_resume_strips_commands() -> None:
    tex = textwrap.dedent("""\
        \\documentclass[10pt]{altacv}
        \\begin{document}
        \\cvsection{Experience}
        \\cventry{Engineer}{Acme}{2020--2023}{}{}
        \\item{Built a pipeline that reduced latency by 40\\%}
        \\end{document}
    """)
    result = compact_latex_resume(tex)
    assert "documentclass" not in result
    assert "Experience" in result
    assert "Acme" in result
    assert "pipeline" in result


def test_compact_latex_resume_collapses_whitespace() -> None:
    tex = "\\begin{document}\n\n\n\n\\item{foo}\n\\end{document}"
    result = compact_latex_resume(tex)
    assert "\n\n\n" not in result


# ---------------------------------------------------------------------------
# compile_career_context
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_dir(tmp_path: Path) -> Path:
    return tmp_path


def test_compile_career_context_drops_empty_bullets(tmp_dir: Path) -> None:
    src = tmp_dir / "career_context.md"
    src.write_text(
        textwrap.dedent("""\
            # Career Context

            ## About Me

            - Current role: Senior Engineer at Acme
            - Education:
            - Strongest proof points: Shipped X

            ## Targeting

            - Target role shapes:
            - Dealbreakers that need judgment, not exact keyword filtering: No relocation
        """),
        encoding="utf-8",
    )
    dst = compile_career_context(src, tmp_dir)
    text = dst.read_text(encoding="utf-8")

    # Empty bullets dropped
    assert "- Education:" not in text
    assert "- Target role shapes:" not in text
    # Populated bullets kept
    assert "Senior Engineer at Acme" in text
    assert "No relocation" in text
    # Header dropped
    assert "# Career Context\n" not in text


def test_compile_career_context_strips_html_comments(tmp_dir: Path) -> None:
    src = tmp_dir / "career_context.md"
    src.write_text("## About Me\n\n<!-- hidden note -->\n\n- Current role: Engineer\n", encoding="utf-8")
    dst = compile_career_context(src, tmp_dir)
    assert "hidden note" not in dst.read_text(encoding="utf-8")


def test_compile_career_context_collapses_blank_lines(tmp_dir: Path) -> None:
    src = tmp_dir / "career_context.md"
    src.write_text("## A\n\n\n\n\n## B\n", encoding="utf-8")
    dst = compile_career_context(src, tmp_dir)
    assert "\n\n\n" not in dst.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# compile_story_bank
# ---------------------------------------------------------------------------


STORY_BANK = textwrap.dedent("""\
    # Story Bank

    **How IDs work:** stable forever

    ---

    # Senior Engineer — Acme (2020–2023)

    ## Draft — raw notes

    This is a draft note that should be dropped.

    ### DRAFT-01: Some draft story

    Draft content here.

    ## Final — refined STAR stories

    ### ENG-01: Led migration

    **Rating: 5/5**
    - **Tags:** leadership, migration

    Situation: legacy monolith.
    Task: migrate to microservices.
    Action: led team of 5.
    Result: 40% latency reduction.
""")


def test_compile_story_bank_drops_preamble(tmp_dir: Path) -> None:
    src = tmp_dir / "story_bank.md"
    src.write_text(STORY_BANK, encoding="utf-8")
    dst = compile_story_bank(src, tmp_dir)
    text = dst.read_text(encoding="utf-8")
    assert "How IDs work" not in text


def test_compile_story_bank_drops_draft_section(tmp_dir: Path) -> None:
    src = tmp_dir / "story_bank.md"
    src.write_text(STORY_BANK, encoding="utf-8")
    dst = compile_story_bank(src, tmp_dir)
    text = dst.read_text(encoding="utf-8")
    assert "draft note" not in text
    assert "DRAFT-01" not in text
    assert "Draft content" not in text


def test_compile_story_bank_keeps_final_story_text(tmp_dir: Path) -> None:
    src = tmp_dir / "story_bank.md"
    src.write_text(STORY_BANK, encoding="utf-8")
    dst = compile_story_bank(src, tmp_dir)
    text = dst.read_text(encoding="utf-8")
    assert "ENG-01" in text
    assert "led team of 5" in text
    assert "40% latency reduction" in text


def test_compile_story_bank_drops_rating_and_tags(tmp_dir: Path) -> None:
    src = tmp_dir / "story_bank.md"
    src.write_text(STORY_BANK, encoding="utf-8")
    dst = compile_story_bank(src, tmp_dir)
    text = dst.read_text(encoding="utf-8")
    assert "**Rating" not in text
    assert "**Tags" not in text


# ---------------------------------------------------------------------------
# compile_resume
# ---------------------------------------------------------------------------


def test_compile_resume_produces_plain_text(tmp_dir: Path) -> None:
    src = tmp_dir / "resume.tex"
    src.write_text(
        textwrap.dedent("""\
            \\documentclass[10pt]{altacv}
            \\begin{document}
            \\cvsection{Experience}
            \\cventry{Engineer}{Acme Corp}{2020--2023}{}{}
            \\item{Built pipeline}
            \\end{document}
        """),
        encoding="utf-8",
    )
    dst = compile_resume(src, tmp_dir)
    text = dst.read_text(encoding="utf-8")
    assert dst.suffix == ".txt"
    assert "documentclass" not in text
    assert "Acme Corp" in text
    assert "pipeline" in text


# ---------------------------------------------------------------------------
# _collapse_blanks
# ---------------------------------------------------------------------------


def test_collapse_blanks() -> None:
    assert "\n\n\n" not in _collapse_blanks("a\n\n\n\nb")
    assert _collapse_blanks("a\n\n\n\nb") == "a\n\nb"
