"""Tests for job_hunter/ux/web/assembly.py — inlines the shell/css/js trio for pywebview."""

from __future__ import annotations

from pathlib import Path

import pytest

from job_hunter.ux.web.assembly import build_dashboard_html

_WEB_DIR = Path(__file__).parents[1] / "job_hunter" / "ux" / "web"


def test_build_dashboard_html_inlines_css_and_js() -> None:
    shell = (
        '<head><link rel="stylesheet" href="dashboard.css">'
        "<meta http-equiv=\"Content-Security-Policy\" content=\"script-src 'self' 'nonce-__CSP_NONCE__'\">"
        '</head><body><script src="dashboard.js"></script></body>'
    )
    css = "body { color: red; }"
    js = "console.log('hi');"

    html = build_dashboard_html(shell, css, js, "test-nonce")

    assert '<link rel="stylesheet" href="dashboard.css">' not in html
    assert '<script src="dashboard.js"></script>' not in html
    assert "<style>" in html and css in html
    assert js in html
    assert '<script nonce="test-nonce">' in html
    assert "'nonce-test-nonce'" in html
    assert "__CSP_NONCE__" not in html


def test_build_dashboard_html_requires_css_link_tag() -> None:
    with pytest.raises(ValueError, match="dashboard.css"):
        build_dashboard_html("<head></head><body></body>", "css", "js", "test-nonce")


def test_build_dashboard_html_requires_js_src_tag() -> None:
    shell = '<head><link rel="stylesheet" href="dashboard.css"></head><body></body>'
    with pytest.raises(ValueError, match="dashboard.js"):
        build_dashboard_html(shell, "css", "js", "test-nonce")


def test_build_dashboard_html_requires_csp_nonce_placeholder() -> None:
    shell = '<head><link rel="stylesheet" href="dashboard.css"></head><body><script src="dashboard.js"></script></body>'
    with pytest.raises(ValueError, match="__CSP_NONCE__"):
        build_dashboard_html(shell, "css", "js", "test-nonce")


def test_real_dashboard_files_assemble_without_error() -> None:
    shell = (_WEB_DIR / "dashboard.html").read_text(encoding="utf-8")
    css = (_WEB_DIR / "dashboard.css").read_text(encoding="utf-8")
    js = (_WEB_DIR / "dashboard.js").read_text(encoding="utf-8")

    html = build_dashboard_html(shell, css, js, "test-nonce")

    assert "<style>" in html
    assert css in html
    assert js in html
    assert 'href="dashboard.css"' not in html
    assert 'src="dashboard.js"' not in html


def test_assembled_dashboard_js_script_tag_carries_matching_nonce() -> None:
    """Regression guard for the bug where script-src 'self' (no 'unsafe-inline') silently
    blocked the inlined dashboard.js entirely — no JS error, no CSP violation reaching app
    code either, since the CSP-violation listener is itself inline JS. Every click handler
    and data load just never ran. The <script> tag's nonce must match the CSP header's."""
    shell = (_WEB_DIR / "dashboard.html").read_text(encoding="utf-8")
    css = (_WEB_DIR / "dashboard.css").read_text(encoding="utf-8")
    js = (_WEB_DIR / "dashboard.js").read_text(encoding="utf-8")

    html = build_dashboard_html(shell, css, js, "test-nonce-123")

    assert '<script nonce="test-nonce-123">' in html
    assert "'nonce-test-nonce-123'" in html
    assert "__CSP_NONCE__" not in html


def test_assembled_dashboard_has_no_cdn_script_tags() -> None:
    shell = (_WEB_DIR / "dashboard.html").read_text(encoding="utf-8")
    css = (_WEB_DIR / "dashboard.css").read_text(encoding="utf-8")
    js = (_WEB_DIR / "dashboard.js").read_text(encoding="utf-8")

    html = build_dashboard_html(shell, css, js, "test-nonce")

    assert "http://" not in html
    assert "cdn." not in html.lower()


def test_onboarding_checklist_labels_are_escaped_before_innerhtml() -> None:
    """item.label/action_hint reach innerHTML; action_hint embeds user-configured file
    paths (resume_tex/career_context/story_bank), so both must be esc()'d."""
    js = (_WEB_DIR / "dashboard.js").read_text(encoding="utf-8")

    assert "${esc(item.label)}" in js
    assert "${esc(item.action_hint)}" in js


def test_dashboard_shell_declares_csp_with_no_remote_sources() -> None:
    """default-src/script-src/img-src are all local-only; connect-src is 'none'.

    script-src has no 'unsafe-inline' — all former inline onclick=/oninput=/onchange=
    handlers were converted to addEventListener wiring in dashboard.js. style-src still
    allows 'unsafe-inline' for inline style="..." attributes (not part of this gap).
    """
    shell = (_WEB_DIR / "dashboard.html").read_text(encoding="utf-8")

    assert "Content-Security-Policy" in shell
    assert "default-src 'self'" in shell
    assert "script-src 'self'" in shell
    assert "script-src 'self' 'unsafe-inline'" not in shell
    assert "connect-src 'none'" in shell
    # frame-src must allow blob: — the PDF artifact preview loads a blob: object URL into
    # an <iframe>, which default-src 'self' alone does not cover for framing.
    assert "frame-src 'self' blob:" in shell


def test_dashboard_html_has_no_inline_event_handler_attributes() -> None:
    """Regression guard for the CSP script-src tightening above — no onclick=/oninput=/
    onchange= strings should ever reappear in the static shell or the generated JS."""
    shell = (_WEB_DIR / "dashboard.html").read_text(encoding="utf-8")
    js = (_WEB_DIR / "dashboard.js").read_text(encoding="utf-8")

    for attr in ('onclick="', 'oninput="', 'onchange="'):
        assert attr not in shell
        assert attr not in js
