"""Discover LinkedIn people and recruiters and draft non-transactional review text."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml

from job_hunter.config.loader import setup_logging
from job_hunter.linkedin._config import (
    append_section,
    complete_linkedin,
    configured_path,
    extract_json,
    format_yaml_list,
    linkedin_enabled,
    load_linkedin_config,
    read_text,
    repo_path,
    today_slug,
    write_text,
)
from job_hunter.sources.search_providers import search_web

logger = setup_logging(log_level=os.environ.get("LOG_LEVEL", "INFO"))

SYSTEM = """You write concise LinkedIn networking drafts from pre-ranked candidates.
Return JSON only. Do not include markdown fences."""

PROMPT = """Write human-reviewed LinkedIn message drafts for these already-ranked candidates.
The user manually decides whether to connect, follow, or message.

POSITIONING:
{positioning}

FORBIDDEN PHRASES:
{forbidden_phrases}

MESSAGE RULES:
- No job ask, referral ask, generic flattery, or "pick your brain"
- If evidence is weak, return "no message recommended"
- Recruiter notes should be short, role-aware, and not needy
- Role-adjacent notes should cite one specific reason and one shared professional context
- Max {max_message_words} words per message

PEOPLE:
{people}

Return a JSON object with key "people".
Each person: url, message_variants (list of up to 2 strings)."""

STRATEGY_SYSTEM = """You design low-cost LinkedIn search strategies from a user's
professional profile and job-search configuration. Return JSON only."""

STRATEGY_PROMPT = """Create a compact LinkedIn search strategy for this user.
Do not assume the user is a PM or PO unless their positioning or target job
titles say so.

POSITIONING:
{positioning}

AUDIENCE:
{audience}

CONTENT PILLARS:
{pillars}

TARGET JOB TITLES FROM JOB HUNTER CONFIG:
{job_titles}

TARGET REGIONS FROM JOB HUNTER CONFIG:
{regions}

TARGET COMPANIES FROM JOB HUNTER CONFIG:
{companies}

Return a JSON object with:
- people_queries: up to {people_query_count} role-relevant people/creator searches
- recruiter_queries: up to {recruiter_query_count} SHORT (2-4 words) recruiter/talent searches; use industry terms and seniority, not full job titles
- target_companies: up to {target_company_count} company names from the provided company list only

Keep queries short and searchable. Do not include LinkedIn site: operators."""


@dataclass
class Candidate:
    kind: str
    url: str
    title: str
    description: str
    source: str
    query: str = ""
    topic: str = ""
    relationship_type: str = ""
    score: int = 0
    reason: str = ""
    fingerprint: str = ""
    suggested_action: str = "review manually"
    message_variants: list[str] | None = None


@lru_cache(maxsize=1)
def _policy() -> dict[str, Any]:
    with resources.files("job_hunter.linkedin").joinpath("defaults.yml").open(encoding="utf-8") as defaults:
        return yaml.safe_load(defaults) or {}


def _terms(policy: dict[str, Any], key: str) -> list[str]:
    values = policy.get("terms", {}).get(key, []) or []
    return [str(value).lower() for value in values if str(value).strip()]


def _setting(policy: dict[str, Any], section: str, key: str, default: int) -> int:
    return int(policy.get(section, {}).get(key, default))


def _state_path(config: dict[str, Any], policy: dict[str, Any]) -> Path:
    value = Path(policy.get("state_file", "state.yml"))
    if value.is_absolute():
        return value
    config_dir = config.get("__config_dir")
    return Path(config_dir) / value if config_dir else repo_path(value)


def _canonical_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def _stable_key(url: str, text: str = "") -> str:
    canonical = _canonical_url(url)
    if canonical:
        return canonical
    return hashlib.sha1(text.lower().encode("utf-8")).hexdigest()  # noqa: S324


def _fingerprint(*parts: str) -> str:
    text = " ".join(part for part in parts if part).lower()
    text = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha1(text.encode("utf-8")).hexdigest()  # noqa: S324


def _topic_from_query(query: str) -> str:
    match = re.search(r'"([^"]+)"', query or "")
    return match.group(1) if match else "this topic"


def _clean_title(title: str) -> str:
    title = re.sub(r"\s+-\s+LinkedIn\s*$", "", title or "", flags=re.IGNORECASE)
    title = re.sub(r"\s+\|\s+LinkedIn\s*$", "", title, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", title).strip() or "LinkedIn result"


def _person_name(title: str) -> str:
    cleaned = _clean_title(title)
    for separator in (" - ", " | ", " @ "):
        if separator in cleaned:
            return cleaned.split(separator, 1)[0].strip()
    return cleaned


def _trim_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(".,;:") + "."


def _clean_excerpt(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _is_login_wall(description: str, policy: dict[str, Any]) -> bool:
    lower = (description or "").lower()
    return any(phrase in lower for phrase in _terms(policy, "login_wall_phrases"))


def _text(candidate: Candidate) -> str:
    return f"{candidate.title} {candidate.description} {candidate.query} {candidate.topic}".lower()


def _relationship_type(title: str, description: str, policy: dict[str, Any]) -> str:
    lower = f"{title} {description}".lower()
    if any(term in lower for term in _terms(policy, "recruiter_terms")):
        return "recruiter_intro"
    if any(term in lower for term in _terms(policy, "senior_terms")):
        return "senior_professional"
    if any(term in lower for term in _terms(policy, "role_terms")):
        return "role_adjacent_professional"
    return "creator"


def _load_state(config: dict[str, Any]) -> dict[str, Any]:
    state_path = _state_path(config, _policy())
    data = yaml.safe_load(read_text(state_path, "{}")) or {}
    return {
        "seen_people": list(data.get("seen_people", [])),
        "skipped_urls": list(data.get("skipped_urls", [])),
        "message_fingerprints": list(data.get("message_fingerprints", [])),
    }


def _save_state(config: dict[str, Any], state: dict[str, Any]) -> None:
    state_path = _state_path(config, _policy())
    normalized = {key: sorted(set(value)) for key, value in state.items()}
    write_text(state_path, yaml.safe_dump(normalized, sort_keys=False, allow_unicode=False))


def _search_context(policy: dict[str, Any]) -> dict[str, list[str]]:
    data = yaml.safe_load(read_text(repo_path("config/job_hunter.yml"), "{}")) or {}
    regions: list[str] = []
    companies: list[str] = []
    titles = list(data.get("job_titles", []) or [])
    for region_name, region in (data.get("regions", {}) or {}).items():
        if not region.get("enabled", False):
            continue
        location = str(region.get("location") or region_name).strip()
        if location:
            regions.append(location)
        for title in region.get("job_titles", []) or []:
            if title not in titles:
                titles.append(title)
    for company in (data.get("linkedin", {}) or {}).get("target_companies", []) or []:
        name = str(company).strip()
        if name and name not in companies:
            companies.append(name)
    return {
        "job_titles": titles[: _setting(policy, "strategy", "search_context_title_limit", 12)],
        "regions": regions[: _setting(policy, "strategy", "search_context_region_limit", 12)],
        "companies": companies[: _setting(policy, "strategy", "search_context_company_limit", 40)],
    }


def _fallback_strategy(
    config: dict[str, Any],
    context: dict[str, list[str]],
    policy: dict[str, Any],
) -> dict[str, list[str]]:
    strategy_policy = policy.get("strategy", {}) or {}
    pillars = list(config.get("content_pillars", []) or [])
    audience = list(config.get("audience", []) or [])
    titles = context.get("job_titles", [])
    people = list(dict.fromkeys(audience + titles + pillars))[: _setting(policy, "strategy", "people_query_count", 5)]
    templates = strategy_policy.get("fallback_recruiter_query_templates", []) or []
    recruiter_queries = [
        str(template).format(title=title) for title in titles for template in templates if str(template).strip()
    ]
    return {
        "people_queries": people or ["people in this field"],
        "recruiter_queries": recruiter_queries[: _setting(policy, "strategy", "recruiter_query_count", 5)]
        or ["technical recruiter"],
        "target_companies": context.get("companies", [])[: _setting(policy, "strategy", "target_company_count", 8)],
    }


def _search_strategy(config: dict[str, Any]) -> dict[str, list[str]]:
    policy = _policy()
    context = _search_context(policy)
    fallback = _fallback_strategy(config, context, policy)
    company_context_limit = _setting(policy, "strategy", "search_context_company_limit", 40)
    prompt = STRATEGY_PROMPT.format(
        positioning=config.get("positioning", ""),
        audience=format_yaml_list(config.get("audience", [])),
        pillars=format_yaml_list(config.get("content_pillars", [])),
        job_titles=format_yaml_list(context.get("job_titles", [])),
        regions=format_yaml_list(context.get("regions", [])),
        companies=format_yaml_list(context.get("companies", [])[:company_context_limit]),
        people_query_count=_setting(policy, "strategy", "people_query_count", 5),
        recruiter_query_count=_setting(policy, "strategy", "recruiter_query_count", 5),
        target_company_count=_setting(policy, "strategy", "target_company_count", 8),
    )
    try:
        payload = extract_json(complete_linkedin(STRATEGY_SYSTEM, prompt))
    except Exception as exc:
        logger.warning("[linkedin] Search strategy generation failed; using config-derived fallback: %s", exc)
        return fallback
    if not isinstance(payload, dict):
        return fallback
    strategy = {}
    for key in ("people_queries", "recruiter_queries", "target_companies"):
        values = payload.get(key)
        strategy[key] = (
            [str(value).strip() for value in values if str(value).strip()] if isinstance(values, list) else []
        )
    for key, values in fallback.items():
        if not strategy.get(key):
            strategy[key] = values
    allowed_companies = set(context.get("companies", []))
    strategy["target_companies"] = [
        company for company in strategy["target_companies"] if company in allowed_companies
    ][: _setting(policy, "strategy", "target_company_count", 8)] or fallback["target_companies"]
    strategy["target_regions"] = context.get("regions", [])
    return strategy


def _queries(
    config: dict[str, Any],
    strategy: dict[str, list[str]],
    policy: dict[str, Any],
) -> list[tuple[str, str]]:
    people_domain = "linkedin.com/in"
    queries: list[tuple[str, str]] = []
    people_region_limit = _setting(policy, "strategy", "people_region_query_limit", 5)
    for topic in strategy.get("people_queries", []):
        for region in strategy.get("target_regions", [])[:people_region_limit] or [""]:
            region_suffix = f' "{region}"' if region else ""
            queries.append(("person", f"site:{people_domain} {topic}{region_suffix}"))
    for query in strategy.get("recruiter_queries", []):
        region_limit = _setting(policy, "strategy", "recruiter_region_query_limit", 12)
        company_limit = _setting(policy, "strategy", "recruiter_company_query_limit", 4)
        for region in strategy.get("target_regions", [])[:region_limit] or [""]:
            queries.append(("person", f'site:{people_domain} {query} "{region}"'))
        for company in strategy.get("target_companies", [])[:company_limit]:
            queries.append(("person", f'site:{people_domain} {query} "{company}"'))
    return queries


def _collect_public_results(
    config: dict[str, Any],
    strategy: dict[str, list[str]],
    policy: dict[str, Any],
) -> list[Candidate]:
    discovery = config.get("networking_discovery", {}) or {}
    region = discovery.get("region", {})
    results_per_query = int(discovery.get("results_per_query", 5))
    collected: list[Candidate] = []
    seen = set()

    for _kind, query in _queries(config, strategy, policy):
        for item in search_web(query, region, count=results_per_query):
            url = _canonical_url(item.get("url", ""))
            if not url or url in seen:
                continue
            if "/in/" not in url:
                continue
            description = item.get("description", "")
            if _is_login_wall(description, policy):
                continue
            seen.add(url)
            collected.append(
                Candidate(
                    kind="person",
                    url=url,
                    title=_clean_title(item.get("title", "")),
                    description=description,
                    source=item.get("source", "search"),
                    query=query,
                    topic=_topic_from_query(query),
                )
            )
    return collected


def _score_candidate(
    candidate: Candidate,
    config: dict[str, Any],
    strategy: dict[str, list[str]],
    policy: dict[str, Any],
) -> Candidate:
    text = _text(candidate)
    target_companies = [str(c).lower() for c in strategy.get("target_companies", [])]
    score = 0
    reasons: list[str] = []

    if len(candidate.description.split()) >= _setting(policy, "scoring", "enough_evidence_words", 18):
        score += _setting(policy, "scoring", "enough_evidence_points", 15)
        reasons.append("has enough evidence")
    if any(term in text for term in _terms(policy, "theme_terms")):
        score += _setting(policy, "scoring", "theme_match_points", 20)
        reasons.append("matches configured themes")
    if any(term in text for term in _terms(policy, "role_terms")):
        score += _setting(policy, "scoring", "role_match_points", 15)
        reasons.append("matches configured professional audience")
    if any(company and company in text for company in target_companies):
        score += _setting(policy, "scoring", "target_company_points", 15)
        reasons.append("matches target company")

    candidate.relationship_type = _relationship_type(candidate.title, candidate.description, policy)
    if candidate.relationship_type == "recruiter_intro":
        score += _setting(policy, "scoring", "recruiter_role_points", 30)
        reasons.append("recruiter or talent role")
        if any(term in text for term in _terms(policy, "recruiter_context_terms")):
            score += _setting(policy, "scoring", "recruiter_context_points", 15)
            reasons.append("recruiter context matches configured role")
    elif candidate.relationship_type in {"role_adjacent_professional", "senior_professional"}:
        score += _setting(policy, "scoring", "senior_professional_points", 10)
    else:
        score += _setting(policy, "scoring", "creator_points", 5)

    candidate.score = max(score, 0)
    candidate.reason = "; ".join(reasons) or "matches configured search"
    candidate.fingerprint = _fingerprint(candidate.url, candidate.title, candidate.description)
    return candidate


def _dedupe_and_select(
    candidates: list[Candidate],
    config: dict[str, Any],
    state: dict[str, Any],
    strategy: dict[str, list[str]],
    policy: dict[str, Any],
) -> dict[str, list[Candidate]]:
    quality = policy.get("quality", {}) or {}
    caps = policy.get("llm_caps", {}) or {}
    seen_people = set(state.get("seen_people", []))
    skipped = set(state.get("skipped_urls", []))
    by_key: dict[str, Candidate] = {}

    for candidate in candidates:
        candidate = _score_candidate(candidate, config, strategy, policy)
        key = _stable_key(candidate.url, candidate.fingerprint)
        if key in skipped:
            continue
        if key in seen_people or candidate.fingerprint in seen_people:
            continue
        existing = by_key.get(key)
        if existing is None or candidate.score > existing.score:
            by_key[key] = candidate

    people = []
    recruiters = []
    for candidate in by_key.values():
        if candidate.relationship_type == "recruiter_intro":
            if candidate.score >= int(quality.get("min_recruiter_score", 45)):
                recruiters.append(candidate)
        elif candidate.score >= int(quality.get("min_person_score", 35)):
            people.append(candidate)

    return {
        "people": sorted(people, key=lambda c: c.score, reverse=True)[: int(caps.get("max_people_to_rank", 5))],
        "recruiters": sorted(recruiters, key=lambda c: c.score, reverse=True)[
            : int(caps.get("max_recruiters_to_message", 5))
        ],
    }


def _deterministic_messages(candidate: Candidate, config: dict[str, Any]) -> list[str]:
    max_words = int(config.get("networking", {}).get("max_message_words", 70))
    first_name = _person_name(candidate.title).split()[0] or "there"
    evidence = _clean_excerpt(candidate.description)[:120].rstrip(".,;:")
    positioning = str(config.get("positioning", "I work in a related field.")).rstrip(".")
    if len(evidence.split()) < 6:
        return ["no message recommended"]
    if candidate.relationship_type == "recruiter_intro":
        text = (
            f"Hi {first_name}, I noticed your work around {evidence}. My background is "
            f"{positioning}. I would be glad to stay connected for relevant conversations."
        )
    else:
        text = (
            f"Hi {first_name}, your work around {evidence} connects with my current focus: "
            f"{positioning}. I would be glad to connect and follow your perspective."
        )
    return [_trim_words(text, max_words)]


def _generate_suggestions(
    selected: dict[str, list[Candidate]],
    config: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, list[Candidate]]:
    all_people = selected["recruiters"] + selected["people"]
    if not all_people:
        return selected

    people_payload = [
        {
            "url": c.url,
            "name": _person_name(c.title),
            "role_or_context": c.title,
            "relationship_type": c.relationship_type,
            "evidence": _clean_excerpt(c.description),
            "score": c.score,
        }
        for c in all_people
    ]
    prompt = PROMPT.format(
        positioning=config.get("positioning", ""),
        forbidden_phrases=format_yaml_list(config.get("forbidden_phrases", [])),
        max_message_words=int(config.get("networking", {}).get("max_message_words", 70)),
        people=yaml.safe_dump(people_payload, sort_keys=False, allow_unicode=False),
    )
    try:
        payload = extract_json(complete_linkedin(SYSTEM, prompt))
    except Exception as exc:
        logger.warning("[linkedin] Discovery generation failed; using deterministic drafts: %s", exc)
        payload = {}

    messages_by_url = (
        {
            _canonical_url(item.get("url", "")): item.get("message_variants", [])
            for item in payload.get("people", [])
            if isinstance(item, dict)
        }
        if isinstance(payload, dict)
        else {}
    )

    for candidate in all_people:
        messages = messages_by_url.get(candidate.url) or _deterministic_messages(candidate, config)
        candidate.message_variants = [
            _trim_words(str(message).strip(), int(config.get("networking", {}).get("max_message_words", 70)))
            for message in messages[:2]
            if str(message).strip()
        ] or ["no message recommended"]

    return selected


def _render_people(items: list[Candidate]) -> str:
    if not items:
        return "_No people suggestions returned._"
    sections = []
    for item in items:
        messages = item.message_variants or []
        messages_text = "\n".join(f"  - {msg}" for msg in messages)
        sections.append(
            f"""### {_person_name(item.title)}

- Role/context: {item.title}
- Link: {item.url}
- Score: {item.score}
- Why relevant: {item.reason}
- Evidence: {_clean_excerpt(item.description)[:300]}
- Relationship type: {item.relationship_type}
- Suggested action: {item.suggested_action}
- Ask readiness: cold
- Message variants:
{messages_text}
"""
        )
    return "\n\n".join(sections)


def _update_state(state: dict[str, Any], selected: dict[str, list[Candidate]]) -> dict[str, Any]:
    for candidate in selected["people"] + selected["recruiters"]:
        state.setdefault("seen_people", []).append(_stable_key(candidate.url, candidate.fingerprint))
        state.setdefault("seen_people", []).append(candidate.fingerprint)
        for message in candidate.message_variants or []:
            state.setdefault("message_fingerprints", []).append(_fingerprint(message))
    return state


def discover(config_path: Path | None = None) -> dict:
    config = load_linkedin_config(config_path)
    if not linkedin_enabled(config):
        logger.info("[linkedin] LinkedIn workflow disabled.")
        return {"people": [], "recruiters": []}

    policy = _policy()
    state = _load_state(config)
    strategy = _search_strategy(config)
    candidates = _collect_public_results(config, strategy, policy)
    if not candidates:
        logger.warning("[linkedin] No LinkedIn candidates found.")
        return {"people": [], "recruiters": []}

    selected = _dedupe_and_select(candidates, config, state, strategy, policy)
    selected = _generate_suggestions(selected, config, policy)

    append_section(
        configured_path(config, "networking"),
        f"## {today_slug()}\n\n### Recruiters\n\n{_render_people(selected['recruiters'])}\n\n"
        f"### Role-Adjacent Professionals and Creators\n\n{_render_people(selected['people'])}",
    )
    _save_state(config, _update_state(state, selected))

    logger.info(
        "[linkedin] Added %s recruiters and %s people.",
        len(selected["recruiters"]),
        len(selected["people"]),
    )
    return {
        "people": [asdict(item) for item in selected["people"]],
        "recruiters": [asdict(item) for item in selected["recruiters"]],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover LinkedIn networking suggestions.")
    parser.add_argument("--config", type=Path, help="Optional standalone LinkedIn YAML config path")
    args = parser.parse_args()
    discover(args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
