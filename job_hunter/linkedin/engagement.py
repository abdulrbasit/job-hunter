"""Discover LinkedIn people and recruiters and draft non-transactional review text."""

from __future__ import annotations

import argparse
import os
from dataclasses import asdict
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

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
)
from job_hunter.linkedin._engagement_support import (
    Candidate,
    candidate_text,
    canonical_url,
    clean_excerpt,
    clean_title,
    fingerprint,
    load_state,
    person_name,
    render_people,
    save_state,
    stable_key,
    topic_from_query,
    trim_words,
    update_state,
)
from job_hunter.llm.prompts.linkedin import ENGAGEMENT_PROMPT as PROMPT
from job_hunter.llm.prompts.linkedin import ENGAGEMENT_STRATEGY_PROMPT as STRATEGY_PROMPT
from job_hunter.llm.prompts.linkedin import ENGAGEMENT_STRATEGY_SYSTEM as STRATEGY_SYSTEM
from job_hunter.llm.prompts.linkedin import ENGAGEMENT_SYSTEM as SYSTEM
from job_hunter.sources.search import search_web

logger = setup_logging(log_level=os.environ.get("LOG_LEVEL", "INFO"))


@lru_cache(maxsize=1)
def _policy() -> dict[str, Any]:
    with resources.files("job_hunter.linkedin").joinpath("defaults.yml").open(encoding="utf-8") as defaults:
        return yaml.safe_load(defaults) or {}


def _terms(policy: dict[str, Any], key: str) -> list[str]:
    values = policy.get("terms", {}).get(key, []) or []
    return [str(value).lower() for value in values if str(value).strip()]


def _setting(policy: dict[str, Any], section: str, key: str, default: int) -> int:
    return int(policy.get(section, {}).get(key, default))


def _is_login_wall(description: str, policy: dict[str, Any]) -> bool:
    lower = (description or "").lower()
    return any(phrase in lower for phrase in _terms(policy, "login_wall_phrases"))


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
    return load_state(config, _policy())


def _save_state(config: dict[str, Any], state: dict[str, Any]) -> None:
    save_state(config, _policy(), state)


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
            url = canonical_url(item.get("url", ""))
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
                    title=clean_title(item.get("title", "")),
                    description=description,
                    source=item.get("source", "search"),
                    query=query,
                    topic=topic_from_query(query),
                )
            )
    return collected


def _score_candidate(
    candidate: Candidate,
    config: dict[str, Any],
    strategy: dict[str, list[str]],
    policy: dict[str, Any],
) -> Candidate:
    text = candidate_text(candidate)
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
    candidate.fingerprint = fingerprint(candidate.url, candidate.title, candidate.description)
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
        key = stable_key(candidate.url, candidate.fingerprint)
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
    first_name = person_name(candidate.title).split()[0] or "there"
    evidence = clean_excerpt(candidate.description)[:120].rstrip(".,;:")
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
    return [trim_words(text, max_words)]


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
            "name": person_name(c.title),
            "role_or_context": c.title,
            "relationship_type": c.relationship_type,
            "evidence": clean_excerpt(c.description),
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
            canonical_url(item.get("url", "")): item.get("message_variants", [])
            for item in payload.get("people", [])
            if isinstance(item, dict)
        }
        if isinstance(payload, dict)
        else {}
    )

    for candidate in all_people:
        messages = messages_by_url.get(candidate.url) or _deterministic_messages(candidate, config)
        candidate.message_variants = [
            trim_words(str(message).strip(), int(config.get("networking", {}).get("max_message_words", 70)))
            for message in messages[:2]
            if str(message).strip()
        ] or ["no message recommended"]

    return selected


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
        f"## {today_slug()}\n\n### Recruiters\n\n{render_people(selected['recruiters'])}\n\n"
        f"### Role-Adjacent Professionals and Creators\n\n{render_people(selected['people'])}",
    )
    _save_state(config, update_state(state, selected))

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
