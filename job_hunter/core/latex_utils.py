"""LaTeX text extraction utilities."""

from __future__ import annotations

import re


def strip_latex_comments(tex: str) -> str:
    lines = []
    for line in tex.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            continue
        lines.append(re.sub(r"(?<!\\)%.*$", "", line).rstrip())
    return "\n".join(lines)


def compact_latex_resume(tex: str) -> str:
    """Strip LaTeX markup from a resume and return plain prose text."""
    document = re.search(r"\\begin\{document\}(.*?)\\end\{document\}", tex, re.DOTALL)
    if document:
        tex = document.group(1)
    text = strip_latex_comments(tex)
    text = re.sub(r"\\(documentclass|usepackage|geometry|hypersetup)(?:\[[^\]]*\])?\{[^}]*\}", " ", text)
    text = re.sub(r"\\photoR(?:\[[^\]]*\])?\{[^{}]*\}\{[^{}]*\}", " ", text)
    text = re.sub(r"\\setlength\{[^{}]*\}\{[^{}]*\}", " ", text)
    text = re.sub(r"\\(?:columnratio|[vh]space\*?)\{[^{}]*\}", " ", text)
    text = re.sub(r"\\(begin|end)\{[^}]*\}(?:\{[^{}]*\})?", "\n", text)
    text = text.replace(r"$\cdot$", "·")
    text = re.sub(r"\\[a-zA-Z*]+(?:\[[^\]]*\])?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    text = re.sub(r"\\([%&_$#])", r"\1", text)
    text = re.sub(r"\\\\(?:\[[^\]]*\])?", "\n", text)
    text = text.replace(r"\ ", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
