"""Tests for job_hunter/tools/compile_profile.py and job_hunter/core/latex_utils.py."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from job_hunter.core.latex_utils import compact_latex_resume, strip_latex_comments
from job_hunter.tools.compile_profile import (
    _collapse_blanks,
    compile_all,
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


def test_strip_latex_comments_preserves_escaped_percent() -> None:
    result = strip_latex_comments("\\item{Contributed 15\\% to engineering} % note")
    assert "15\\% to engineering" in result
    assert "note" not in result


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


def test_compact_latex_resume_keeps_only_document_content() -> None:
    tex = textwrap.dedent("""\
        \\definecolor{PrimaryColor}{HTML}{1B2A4E}
        \\renewcommand{\\cvevent}[4]{layout internals}
        \\begin{document}
        \\name{Abdul Basit}
        \\item{Contributed 15\\% to Software Engineering}
        \\item{AI \\& Speech}
        \\end{document}
    """)
    result = compact_latex_resume(tex)
    assert "PrimaryColor" not in result
    assert "layout internals" not in result
    assert "Abdul Basit" in result
    assert "15% to Software Engineering" in result
    assert "AI & Speech" in result


def test_compact_latex_resume_drops_layout_only_commands() -> None:
    tex = textwrap.dedent("""\
        \\begin{document}
        \\photoR{2.8cm}{profile}
        \\columnratio{0.70}
        \\setlength{\\columnsep}{0.8cm}
        \\cvsection{Experience}
        \\item{Built products}
        \\end{document}
    """)
    result = compact_latex_resume(tex)
    assert "2.8cm" not in result
    assert "profile" not in result
    assert "0.70" not in result
    assert "0.8cm" not in result
    assert "Experience" in result
    assert "Built products" in result


def test_compact_latex_resume_cleans_math_separator_and_blank_lines() -> None:
    tex = "\\begin{document}\nGitHub $\\cdot$ PyPI\\\\[6pt]\n\\divider\n\n\nText\n\\end{document}"
    result = compact_latex_resume(tex)
    assert "$" not in result
    assert "GitHub · PyPI" in result
    assert "[6pt]" not in result
    assert "\n\n\n" not in result


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


STORY_BANK_NO_SEPARATOR = textwrap.dedent("""\
    # My Story Bank

    Some intro notes with no --- separator below them.

    # Senior Engineer — Acme (2020–2023)

    ## Draft — raw notes

    Draft content here.

    ## Final — refined STAR stories

    ### ENG-01: Led migration

    Result: 40% latency reduction.
""")


def test_compile_story_bank_without_separator_keeps_final_content(tmp_dir: Path) -> None:
    """Regression: a file with no `---` preamble separator must not compile to empty."""
    src = tmp_dir / "story_bank.md"
    src.write_text(STORY_BANK_NO_SEPARATOR, encoding="utf-8")
    dst = compile_story_bank(src, tmp_dir)
    text = dst.read_text(encoding="utf-8")
    assert "ENG-01" in text
    assert "40% latency reduction" in text
    assert "Draft content" not in text


def test_compile_story_bank_strips_html_comments(tmp_dir: Path) -> None:
    src = tmp_dir / "story_bank.md"
    src.write_text(
        STORY_BANK.replace(
            "## Final — refined STAR stories",
            "## Final — refined STAR stories\n\n<!-- Only stories promoted here are used. -->",
        ),
        encoding="utf-8",
    )
    dst = compile_story_bank(src, tmp_dir)
    text = dst.read_text(encoding="utf-8")
    assert "<!--" not in text


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


# ---------------------------------------------------------------------------
# compile_all
# ---------------------------------------------------------------------------


def test_compile_all_warns_when_a_source_compiles_to_empty(tmp_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_dir / "config").mkdir()
    (tmp_dir / "config" / "job_hunter.yml").write_text(
        "profile:\n  career_context: profile/career_context.md\n  story_bank: profile/story_bank.md\n",
        encoding="utf-8",
    )
    (tmp_dir / "profile").mkdir()
    (tmp_dir / "profile" / "career_context.md").write_text(
        "# Career Context\n\nSome real content.\n" * 3, encoding="utf-8"
    )
    # Nothing has been promoted to Final yet, so every line after the preamble is Draft content.
    (tmp_dir / "profile" / "story_bank.md").write_text(
        "# Story Bank\n\nSome notes about how this file works.\n\n---\n\n"
        "## Draft — raw notes\n\nNothing finalized yet, still drafting this story.\n",
        encoding="utf-8",
    )

    with caplog.at_level("WARNING"):
        compile_all(tmp_dir)

    assert any("story_bank.md compiled to empty" in record.message for record in caplog.records)
