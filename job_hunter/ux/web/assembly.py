"""Assembles the three dashboard source files (shell/css/js) into one HTML string.

pywebview's create_window(html=...) takes one in-memory string with no base URL,
so relative <link href="dashboard.css"> / <script src="dashboard.js"> in the shell
can't resolve at runtime. Source stays split into three files for maintainability;
this inlines them back together only at launch time.

The inlined <script> is itself an inline script block, which a strict CSP
script-src 'self' (no 'unsafe-inline') blocks same as any other inline script —
so the shell's script-src carries a __CSP_NONCE__ placeholder that this function
replaces with a real per-launch nonce, applied to both the CSP header and the
<script> tag's nonce attribute. Without this, the whole dashboard fails silently
(no JS error, no CSP violation event reaches app code either, since that inline
script is blocked too) — every click handler and data load just never runs.
"""

from __future__ import annotations

_CSS_LINK_TAG = '<link rel="stylesheet" href="dashboard.css">'
_JS_SRC_TAG = '<script src="dashboard.js"></script>'
_NONCE_PLACEHOLDER = "__CSP_NONCE__"


def build_dashboard_html(shell: str, css: str, js: str, nonce: str) -> str:
    if _CSS_LINK_TAG not in shell:
        raise ValueError(f"dashboard.html shell is missing {_CSS_LINK_TAG!r}")
    if _JS_SRC_TAG not in shell:
        raise ValueError(f"dashboard.html shell is missing {_JS_SRC_TAG!r}")
    if _NONCE_PLACEHOLDER not in shell:
        raise ValueError(f"dashboard.html shell is missing the {_NONCE_PLACEHOLDER!r} CSP placeholder")
    html = shell.replace(_NONCE_PLACEHOLDER, nonce)
    html = html.replace(_CSS_LINK_TAG, f"<style>\n{css}</style>")
    html = html.replace(_JS_SRC_TAG, f'<script nonce="{nonce}">\n{js}</script>')
    return html
