from __future__ import annotations

from pathlib import Path

import pytest

from job_hunter.config.resume_style import apply_resume_style, detect_template, read_resume_style

ROOT = Path(__file__).resolve().parents[1]
ALTACV_TEX = (ROOT / "job_hunter" / "templates" / "workspace" / "profile" / "resume_double_column.tex").read_text(
    encoding="utf-8"
)
ARTICLE_TEX = (ROOT / "job_hunter" / "templates" / "workspace" / "profile" / "resume_single_column.tex").read_text(
    encoding="utf-8"
)


def test_detect_template_identifies_altacv_and_article() -> None:
    assert detect_template(ALTACV_TEX) == "altacv"
    assert detect_template(ARTICLE_TEX) == "article"
    assert detect_template("no documentclass here") is None


def test_read_resume_style_reports_current_altacv_values() -> None:
    style = read_resume_style(ALTACV_TEX)

    assert style["ok"] is True
    assert style["template"] == "altacv"
    assert style["font_size"] == "10pt"
    assert style["paper"] == "a4"
    assert style["heading_color"] == "1B2A4E"
    assert style["accent_color"] == "7A8DA8"
    assert style["column_ratio"] == "0.70"
    assert style["font"] is None  # all font lines commented out in the shipped template


def test_read_resume_style_reports_current_article_values() -> None:
    style = read_resume_style(ARTICLE_TEX)

    assert style["ok"] is True
    assert style["template"] == "article"
    assert style["font_size"] == "10pt"
    assert style["paper"] == "a4"
    assert style["heading_color"] == "1B2A4E"
    assert style["accent_color"] == "7A8DA8"
    assert style["column_ratios"] == []
    assert style["font"] == "noto-sans"  # the one uncommented line in the shipped template


def test_apply_resume_style_changes_only_the_requested_altacv_fields() -> None:
    new_text = apply_resume_style(ALTACV_TEX, {"heading_color": "#1A237E", "font_size": "9pt"})

    style = read_resume_style(new_text)
    assert style["heading_color"] == "1A237E"
    assert style["font_size"] == "9pt"
    assert style["accent_color"] == "7A8DA8"  # untouched
    assert style["paper"] == "a4"  # untouched
    assert new_text.count("\\definecolor{PrimaryColor}{HTML}{1A237E}") == 1
    assert new_text.count("\\definecolor{SecondaryColor}{HTML}{1A237E}") == 1


def test_apply_resume_style_switches_altacv_font_by_comment_toggling() -> None:
    new_text = apply_resume_style(ALTACV_TEX, {"font": "lato"})

    assert "\\usepackage[sfdefault]{lato}" in new_text
    assert "% \\usepackage[sfdefault]{lato}" not in new_text
    style = read_resume_style(new_text)
    assert style["font"] == "lato"

    switched = apply_resume_style(new_text, {"font": "roboto"})
    assert "% \\usepackage[sfdefault]{lato}" in switched
    assert read_resume_style(switched)["font"] == "roboto"


def test_apply_resume_style_switches_article_font() -> None:
    new_text = apply_resume_style(ARTICLE_TEX, {"font": "charter"})

    assert read_resume_style(new_text)["font"] == "charter"
    assert "% \\usepackage[sfdefault]{noto-sans}" in new_text


def test_apply_resume_style_sets_altacv_paper_and_column_ratio() -> None:
    new_text = apply_resume_style(ALTACV_TEX, {"paper": "letter", "column_ratio": "0.65"})

    style = read_resume_style(new_text)
    assert style["paper"] == "letter"
    assert style["column_ratio"] == "0.65"
    assert "\\documentclass[10pt,letterpaper,ragged2e,withhyper]{altacv}" in new_text


def test_apply_resume_style_sets_article_paper_and_size_together() -> None:
    new_text = apply_resume_style(ARTICLE_TEX, {"paper": "letter", "font_size": "12pt"})

    assert "\\documentclass[letterpaper,12pt]{article}" in new_text
    style = read_resume_style(new_text)
    assert style["paper"] == "letter"
    assert style["font_size"] == "12pt"


def test_apply_resume_style_rejects_invalid_hex() -> None:
    with pytest.raises(ValueError, match="Invalid hex color"):
        apply_resume_style(ALTACV_TEX, {"heading_color": "not-a-hex"})


def test_apply_resume_style_rejects_unknown_font() -> None:
    with pytest.raises(ValueError, match="Unknown font"):
        apply_resume_style(ALTACV_TEX, {"font": "comic-sans"})


def test_apply_resume_style_rejects_unsupported_font_size() -> None:
    with pytest.raises(ValueError, match="Unsupported font size"):
        apply_resume_style(ARTICLE_TEX, {"font_size": "9pt"})  # not in ARTICLE_FONT_SIZES


def test_apply_resume_style_rejects_unrecognized_template() -> None:
    with pytest.raises(ValueError, match="Unrecognized resume template"):
        apply_resume_style("no documentclass here", {"font_size": "10pt"})


def test_apply_resume_style_never_touches_body_content() -> None:
    new_text = apply_resume_style(ALTACV_TEX, {"heading_color": "#000000"})

    # Everything after the preamble (post \begin{document}) must be byte-identical.
    original_body = ALTACV_TEX.split("\\begin{document}", 1)[1]
    new_body = new_text.split("\\begin{document}", 1)[1]
    assert original_body == new_body
