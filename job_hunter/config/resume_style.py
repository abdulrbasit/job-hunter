"""Deterministic resume preamble styling — the code behind the dashboard's Settings ->
Resume Style form. Only edits \\documentclass/\\definecolor/font \\usepackage/\\columnratio
lines already present in the file; never adds new LaTeX commands or packages. Mirrors what
the old `/setup style` skill used to do by hand.
"""

from __future__ import annotations

import re

ALTACV = "altacv"
ARTICLE = "article"

COLOR_PRESETS: dict[str, dict[str, str]] = {
    "dark_navy": {"label": "Dark Navy (default)", "heading": "1B2A4E", "accent": "7A8DA8"},
    "classic_black": {"label": "Classic Black", "heading": "000000", "accent": "555555"},
    "midnight_blue": {"label": "Midnight Blue", "heading": "1A237E", "accent": "5C6BC0"},
    "slate": {"label": "Slate", "heading": "37474F", "accent": "78909C"},
    "forest": {"label": "Forest", "heading": "1B5E20", "accent": "66BB6A"},
    "burgundy": {"label": "Burgundy", "heading": "4A0010", "accent": "B03050"},
    "warm_charcoal": {"label": "Warm Charcoal", "heading": "2C2C2C", "accent": "9E7B5A"},
}

# Font id -> exact usepackage line (uncommented form). Order matters for display only.
ALTACV_FONTS: dict[str, str] = {
    "roboto": r"\usepackage[sfdefault]{roboto}",
    "lato": r"\usepackage[sfdefault]{lato}",
    "sourcesanspro": r"\usepackage[sfdefault]{sourcesanspro}",
    "noto-sans": r"\usepackage[sfdefault]{noto-sans}",
    "firasans": r"\usepackage[sfdefault]{FiraSans}",
    "cormorantgaramond": r"\usepackage{CormorantGaramond}",
    "charter": r"\usepackage{charter}",
    "lmodern": r"\usepackage{lmodern}",
}
ARTICLE_FONTS: dict[str, str] = {
    "firasans": r"\usepackage[sfdefault]{FiraSans}",
    "roboto": r"\usepackage[sfdefault]{roboto}",
    "noto-sans": r"\usepackage[sfdefault]{noto-sans}",
    "sourcesanspro": r"\usepackage[default]{sourcesanspro}",
    "cormorantgaramond": r"\usepackage{CormorantGaramond}",
    "charter": r"\usepackage{charter}",
}

ALTACV_FONT_SIZES = ("8pt", "9pt", "10pt", "10.5pt", "11pt")
ARTICLE_FONT_SIZES = ("10pt", "11pt", "12pt")
COLUMN_RATIOS = ("0.65", "0.68", "0.70", "0.72", "0.75")
_HEX_RE = re.compile(r"^[0-9A-Fa-f]{6}$")


def detect_template(text: str) -> str | None:
    if re.search(r"\\documentclass(\[[^\]]*\])?\{altacv\}", text):
        return ALTACV
    if re.search(r"\\documentclass(\[[^\]]*\])?\{article\}", text):
        return ARTICLE
    return None


def _active_font(text: str, fonts: dict[str, str]) -> str | None:
    for font_id, line in fonts.items():
        if re.search(rf"^{re.escape(line)}\s*$", text, re.MULTILINE):
            return font_id
    return None


def _documentclass_options(text: str, class_name: str) -> tuple[list[str], int, int] | None:
    match = re.search(rf"\\documentclass\[([^\]]*)\]\{{{class_name}\}}", text)
    if not match:
        return None
    return match.group(1).split(","), match.start(1), match.end(1)


def read_resume_style(text: str) -> dict:
    """Read the current styling fields from a resume .tex file's content."""
    template = detect_template(text)
    if template is None:
        return {"ok": False, "error": "Unrecognized resume template (expected AltaCV or article)."}

    fonts = ALTACV_FONTS if template == ALTACV else ARTICLE_FONTS
    opts = _documentclass_options(text, template)
    option_list = opts[0] if opts else []
    font_size = next((o for o in option_list if o.endswith("pt")), None)
    paper = "letter" if "letterpaper" in option_list else "a4"
    heading = re.search(r"\\definecolor\{PrimaryColor\}\{HTML\}\{([0-9A-Fa-f]{6})\}", text)
    accent = re.search(r"\\definecolor\{AccentColor\}\{HTML\}\{([0-9A-Fa-f]{6})\}", text)
    ratio = re.search(r"\\columnratio\{([0-9.]+)\}", text) if template == ALTACV else None

    return {
        "ok": True,
        "template": template,
        "font": _active_font(text, fonts),
        "fonts": sorted(fonts),
        "font_size": font_size,
        "font_sizes": list(ALTACV_FONT_SIZES if template == ALTACV else ARTICLE_FONT_SIZES),
        "paper": paper,
        "heading_color": heading.group(1).upper() if heading else None,
        "accent_color": accent.group(1).upper() if accent else None,
        "column_ratio": ratio.group(1) if ratio else None,
        "column_ratios": list(COLUMN_RATIOS) if template == ALTACV else [],
        "presets": COLOR_PRESETS,
    }


def _set_color(text: str, role: str, hexval: str) -> str:
    return re.sub(rf"(\\definecolor\{{{role}\}}\{{HTML\}}\{{)[0-9A-Fa-f]{{6}}(\}})", rf"\g<1>{hexval}\g<2>", text)


def _validated_hex(raw: str) -> str:
    hexval = raw.lstrip("#").upper()
    if not _HEX_RE.match(hexval):
        raise ValueError(f"Invalid hex color: {raw}")
    return hexval


def _apply_colors(text: str, template: str, choices: dict) -> str:
    if choices.get("heading_color"):
        hexval = _validated_hex(choices["heading_color"])
        roles = (
            ("PrimaryColor", "SecondaryColor", "ThirdColor", "EmphasisColor")
            if template == ALTACV
            else ("PrimaryColor",)
        )
        for role in roles:
            text = _set_color(text, role, hexval)
    if choices.get("accent_color"):
        text = _set_color(text, "AccentColor", _validated_hex(choices["accent_color"]))
    return text


def _apply_font(text: str, fonts: dict[str, str], font_id: str) -> str:
    if font_id not in fonts:
        raise ValueError(f"Unknown font for this template: {font_id}")
    active = _active_font(text, fonts)
    if active and active != font_id:
        active_line = fonts[active]
        text = re.sub(
            rf"^{re.escape(active_line)}\s*$", lambda _m, ln=active_line: f"% {ln}", text, count=1, flags=re.MULTILINE
        )
    target_line = fonts[font_id]
    return re.sub(
        rf"^%?\s*{re.escape(target_line)}\s*$", lambda _m, ln=target_line: ln, text, count=1, flags=re.MULTILINE
    )


def _apply_documentclass_options(text: str, template: str, size_choice: str | None, paper_choice: str | None) -> str:
    valid_sizes = ALTACV_FONT_SIZES if template == ALTACV else ARTICLE_FONT_SIZES
    if size_choice and size_choice not in valid_sizes:
        raise ValueError(f"Unsupported font size for this template: {size_choice}")
    if paper_choice not in (None, "a4", "letter"):
        raise ValueError(f"Unsupported paper format: {paper_choice}")
    located = _documentclass_options(text, template)
    if not located:
        return text
    option_list, start, end = located
    new_options = list(option_list)
    if size_choice:
        new_options = [size_choice if o.endswith("pt") else o for o in new_options]
    if paper_choice:
        paper_token = "letterpaper" if paper_choice == "letter" else ("a4paper" if template == ALTACV else "a4")
        new_options = [paper_token if o in ("a4paper", "letterpaper", "a4", "letter") else o for o in new_options]
    return text[:start] + ",".join(new_options) + text[end:]


def _apply_column_ratio(text: str, ratio: str) -> str:
    if ratio not in COLUMN_RATIOS:
        raise ValueError(f"Unsupported column ratio: {ratio}")
    return re.sub(r"(\\columnratio\{)[0-9.]+(\})", rf"\g<1>{ratio}\g<2>", text, count=1)


def apply_resume_style(text: str, choices: dict) -> str:
    """Apply only the fields present (truthy) in `choices`. Returns the new file content.
    Raises ValueError for an unrecognized template or an out-of-menu choice."""
    template = detect_template(text)
    if template is None:
        raise ValueError("Unrecognized resume template (expected AltaCV or article).")

    text = _apply_colors(text, template, choices)

    if choices.get("font"):
        fonts = ALTACV_FONTS if template == ALTACV else ARTICLE_FONTS
        text = _apply_font(text, fonts, choices["font"])

    size_choice = choices.get("font_size")
    paper_choice = choices.get("paper")
    if size_choice or paper_choice:
        text = _apply_documentclass_options(text, template, size_choice, paper_choice)

    if choices.get("column_ratio") and template == ALTACV:
        text = _apply_column_ratio(text, choices["column_ratio"])

    return text
