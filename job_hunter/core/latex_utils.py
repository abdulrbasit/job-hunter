"""LaTeX text extraction utilities."""

from __future__ import annotations

import re


def strip_latex_comments(tex: str) -> str:
    lines = []
    for line in tex.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            continue
        lines.append(line.split("%", 1)[0].rstrip())
    return "\n".join(lines)


def compact_latex_resume(tex: str) -> str:
    """Strip LaTeX markup from a resume and return plain prose text."""
    text = strip_latex_comments(tex)
    text = re.sub(r"\\(documentclass|usepackage|geometry|hypersetup)(?:\[[^\]]*\])?\{[^}]*\}", " ", text)
    text = re.sub(r"\\(begin|end)\{[^}]*\}", "\n", text)
    text = re.sub(r"\\[a-zA-Z*]+(?:\[[^\]]*\])?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
