"""Deterministic student posting signals and bounded search terms."""

from __future__ import annotations

import re
from dataclasses import dataclass

from job_hunter.models import PostingType

STUDENT_POSTING_TYPES = tuple(item.value for item in PostingType)

_POSTING_PATTERNS: tuple[tuple[PostingType, tuple[str, ...]], ...] = (
    (PostingType.THESIS, (r"\b(?:abschluss|bachelor|master|diplom)arbeit\b", r"\bthesis\b", r"\bcapstone\b")),
    (PostingType.WORKING_STUDENT, (r"\bwerkstudent(?:in|en)?\b", r"\bworking[\s-]+student\b")),
    (
        PostingType.INTERNSHIP,
        (r"\bpflicht[\s-]*praktikum\b", r"\bpraktik(?:um|ant|antin)\b", r"\bintern(?:ship)?\b", r"\bco[\s-]*op\b"),
    ),
    (
        PostingType.GRADUATE_PROGRAM,
        (r"\bgraduate[\s-]+(?:program(?:me)?|scheme)\b", r"\bnew[\s-]+grad(?:uate)?\b", r"\babsolventenprogramm\b"),
    ),
    (PostingType.TRAINEE, (r"\btrainee[\s-]*programm\b", r"\btrainee\b")),
)

_NO_EXPERIENCE_PATTERNS = (
    r"\bno (?:prior |professional )?experience (?:is )?required\b",
    r"\bexperience (?:is )?not required\b",
    r"\bno experience necessary\b",
    r"\bkeine berufserfahrung (?:ist )?erforderlich\b",
    r"\bberufserfahrung nicht erforderlich\b",
    r"\bberufseinsteiger(?:innen)? willkommen\b",
    r"\bquereinsteiger(?:innen)? willkommen\b",
)


@dataclass(frozen=True)
class PostingSignals:
    posting_type: PostingType | None
    no_experience_required: bool


def detect_posting_signals(title: str, description: str) -> PostingSignals:
    text = f"{title}\n{description}"
    posting_type = next(
        (kind for kind, patterns in _POSTING_PATTERNS if any(re.search(pattern, text, re.I) for pattern in patterns)),
        None,
    )
    no_experience = any(re.search(pattern, text, re.I) for pattern in _NO_EXPERIENCE_PATTERNS)
    return PostingSignals(posting_type, no_experience)


def student_query_terms(job_titles: list[str], groups: set[str]) -> list[str]:
    """Return a small package-owned query expansion; user titles remain unchanged."""
    modifiers: list[str] = []
    if "student" in groups:
        modifiers.extend(("internship", "Werkstudent", "thesis", "Praktikum"))
    if groups & {"student", "entry"}:
        modifiers.extend(("graduate program", "trainee", "new grad"))
    terms = [f"{title} {modifier}" for title in job_titles for modifier in modifiers]
    return list(dict.fromkeys(terms))[:20]


def evidence_scoring_guidance(*, is_student: bool) -> str:
    expert_rule = (
        "For Expert roles, distinguish advanced individual-contributor evidence from "
        "people-management evidence; do not require management history unless the posting does."
    )
    if not is_student:
        return expert_rule
    return (
        "For student roles, prioritize verified education, coursework, academic and personal "
        "projects, internships, and transferable skills. Do not penalize missing professional "
        "tenure when the posting says no experience is required. " + expert_rule
    )
