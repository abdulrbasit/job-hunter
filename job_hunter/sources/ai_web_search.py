"""AI-assisted web search for title-and-region job discovery."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse

import requests

from job_hunter.config.defaults import (
    EXCLUDED_LISTING_URL_PATTERNS,
    LANGUAGE_INDICATORS,
    PROVIDER_SECRET_ENV_VARS,
    STALE_INDICATORS,
)
from job_hunter.core.config import get_config, get_secret, load_api_config
from job_hunter.core.utils import title_matches

logger = logging.getLogger(__name__)

ROLE = "ai_web_search"
GOOGLE_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_GOOGLE_API_TIMEOUT = 30  # seconds: HTTP timeout for the Google Generative Language API
_SECRET_CACHE: dict[tuple[str, str, bool], str] = {}
_OPENAI_CLIENTS: dict[str, Any] = {}
_ANTHROPIC_CLIENTS: dict[str, Any] = {}
_CLIENT_LOCK = threading.Lock()

SYSTEM_PROMPT = """You find public job postings. Return only valid JSON.
Rules:
- Search only for the exact query provided by the user.
- Return individual job-posting URLs only; not search pages, saved-job pages, company profile pages, or generic career pages.
- Do not invent companies, titles, locations, dates, or URLs.
- Return only current, open postings. Reject expired, closed, archived, filled, or not-accepting-applications postings.
- Do not return titles that start with "Applying to".
- The response must be a JSON array of objects with:
  title, company, location, url, source, snippet, confidence.
"""

_SOURCE_URL_PATTERNS = {
    # host pattern, path pattern — both must match for the URL to be accepted
    "greenhouse": (r"greenhouse\.io$", r"/jobs/\d+"),
    "lever": (r"^jobs\.lever\.co$", r"^/[^/]+/[0-9a-f-]{36}"),
    "ashby": (r"^jobs\.ashbyhq\.com$", r"^/[^/]+/[0-9a-f-]{36}"),
}

_DEFAULT_SOURCE_CONFIGS = {
    "greenhouse": {
        "enabled": True,
        "query_templates": ['site:greenhouse.io "{title}" "{location}"'],
    },
    "lever": {
        "enabled": True,
        "query_templates": ['site:jobs.lever.co "{title}" "{location}"'],
    },
    "ashby": {
        "enabled": True,
        "query_templates": ['site:jobs.ashbyhq.com "{title}" "{location}"'],
    },
    "smartrecruiters": {
        "enabled": True,
        "query_templates": ['site:jobs.smartrecruiters.com "{title}" "{location}"'],
    },
    "workable": {
        "enabled": True,
        "query_templates": ['site:apply.workable.com "{title}" "{location}"'],
    },
    "personio": {
        "enabled": True,
        "query_templates": ['(site:jobs.personio.de OR site:jobs.personio.com) "{title}" "{location}"'],
    },
    "recruitee": {
        "enabled": True,
        "query_templates": ['site:recruitee.com "{title}" "{location}"'],
    },
    "hibob": {
        "enabled": True,
        "query_templates": ['site:careers.hibob.com/jobs "{title}" "{location}"'],
    },
    "generic_web": {
        "enabled": True,
        "query_templates": [
            '"{title}" "{location}" job apply '
            "-site:glassdoor.com -site:indeed.com -site:linkedin.com "
            "-site:monster.com -site:xing.com -site:stepstone.de"
        ],
    },
}


@dataclass
class AIWebSearchBudget:
    max_prompts_per_run: int
    max_prompts_per_region: int
    max_results_per_prompt: int
    max_results_per_region: int
    max_total_results_per_run: int
    prompts_used: int = 0
    results_used: int = 0
    prompts_by_region: dict[str, int] | None = None
    results_by_region: dict[str, int] | None = None

    def __post_init__(self) -> None:
        self.prompts_by_region = {}
        self.results_by_region = {}

    def can_prompt(self, region_name: str) -> bool:
        if self.prompts_used >= self.max_prompts_per_run:
            return False
        return self.prompts_by_region.get(region_name, 0) < self.max_prompts_per_region

    def record_prompt(self, region_name: str) -> None:
        self.prompts_used += 1
        self.prompts_by_region[region_name] = self.prompts_by_region.get(region_name, 0) + 1

    def remaining_results(self, region_name: str) -> int:
        run_remaining = self.max_total_results_per_run - self.results_used
        region_remaining = self.max_results_per_region - self.results_by_region.get(region_name, 0)
        return max(0, min(run_remaining, region_remaining, self.max_results_per_prompt))

    def record_results(self, region_name: str, count: int) -> None:
        self.results_used += count
        self.results_by_region[region_name] = self.results_by_region.get(region_name, 0) + count


def ai_web_search_config() -> dict[str, Any]:
    api_cfg = load_api_config().get("http", {}).get("search_providers", {}).get("ai_web_search", {}) or {}
    search_cfg = ((_load_search_config().get("search", {}) or {}).get("llm_search", {}) or {}).copy()
    merged = {**api_cfg, **search_cfg}
    if "max_results_per_run" in search_cfg:
        merged["max_total_results_per_run"] = search_cfg["max_results_per_run"]
    merged["enabled"] = bool(search_cfg.get("enabled", False))
    return merged


def enabled() -> bool:
    return bool(ai_web_search_config().get("enabled", False))


def _int_cfg(config: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(config.get(key, default))
    except (TypeError, ValueError):
        return default


def make_budget(config: dict[str, Any] | None = None) -> AIWebSearchBudget:
    config = config or ai_web_search_config()
    return AIWebSearchBudget(
        max_prompts_per_run=_int_cfg(config, "max_prompts_per_run", 30),
        max_prompts_per_region=_int_cfg(config, "max_prompts_per_region", 10),
        max_results_per_prompt=_int_cfg(config, "max_results_per_prompt", 8),
        max_results_per_region=_int_cfg(config, "max_results_per_region", 30),
        max_total_results_per_run=_int_cfg(config, "max_total_results_per_run", 60),
    )


def _source_configs(config: dict[str, Any]) -> dict[str, Any]:
    return config.get("sources") or _DEFAULT_SOURCE_CONFIGS


def _load_search_config() -> dict[str, Any]:
    return get_config("job_hunter")


def _compact_list(values: Any, limit: int = 20) -> str:
    if not values:
        return "none"
    items = [str(value).strip() for value in values if str(value).strip()]
    if not items:
        return "none"
    shown = items[:limit]
    suffix = f"; +{len(items) - limit} more" if len(items) > limit else ""
    return "; ".join(shown) + suffix


def build_rule_context(search_config: dict[str, Any], title_filters: list[str], region_config: dict[str, Any]) -> str:
    exclusions = search_config.get("exclusions", {}) or {}
    location = region_config.get("location") or region_config.get("name") or ""
    lines = [
        "Filtering rules from config/job_hunter.yml:",
        f"- Required title families: {_compact_list(title_filters)}",
        f"- Target location/region: {location or 'any'}; allow remote only when the posting says remote.",
    ]
    excluded_companies = exclusions.get("companies", [])
    if excluded_companies:
        lines.append(f"- Reject excluded companies: {_compact_list(excluded_companies)}")
    excluded_title_terms = exclusions.get("title_terms", [])
    if excluded_title_terms:
        lines.append(f"- Reject excluded title terms: {_compact_list(excluded_title_terms)}")
    lines.append(f"- Reject stale/closed indicators: {_compact_list(STALE_INDICATORS)}")
    excluded_languages = exclusions.get("languages", [])
    if excluded_languages:
        lines.append(f"- Reject languages: {_compact_list(excluded_languages)}")
    for language in excluded_languages or []:
        indicators = LANGUAGE_INDICATORS.get(str(language).lower(), ())
        if indicators:
            lines.append(f"- Reject {language} indicators: {_compact_list(indicators)}")
    excluded_industries = exclusions.get("industries", [])
    if excluded_industries:
        lines.append(f"- Reject excluded industries: {_compact_list(excluded_industries)}")
    lines.append(f"- Reject URL patterns: {_compact_list(EXCLUDED_LISTING_URL_PATTERNS)}")
    lines.append("Return [] if the search result does not clearly satisfy these rules.")
    return "\n".join(lines)


def build_queries(title: str, region_config: dict[str, Any], config: dict[str, Any]) -> list[tuple[str, str]]:
    location = region_config.get("location") or region_config.get("name") or ""
    queries: list[tuple[str, str]] = []

    for source, source_cfg in _source_configs(config).items():
        if not source_cfg.get("enabled", True):
            continue
        for template in source_cfg.get("query_templates", []):
            query = template.format(title=title, location=location).strip()
            if query:
                queries.append((source, query))

    return queries


def _llm_settings() -> tuple[str, str, int]:
    cfg = get_config("job_hunter")
    llm = cfg.get("llm", {})
    provider = llm.get("providers", {}).get(ROLE) or llm.get("default_provider", "")
    models = llm.get("models", {})
    if ROLE not in models:
        raise RuntimeError("Missing llm.models.ai_web_search")
    model = models[ROLE]
    max_tokens = int(llm.get("max_tokens", {}).get(ROLE, 1200))
    if not provider:
        raise RuntimeError("Missing llm.default_provider or llm.providers.ai_web_search")
    return provider, model, max_tokens


def _provider_secret(provider: str) -> str:
    env_var = PROVIDER_SECRET_ENV_VARS.get(provider, "")
    required = bool(env_var)
    if not env_var:
        raise RuntimeError(f"AI web search does not support provider {provider!r}")
    key = (provider, env_var, required)
    with _CLIENT_LOCK:
        if key in _SECRET_CACHE:
            return _SECRET_CACHE[key]
        secret = get_secret(env_var, required=required)
        _SECRET_CACHE[key] = secret
        return secret


def _openai_client(api_key: str) -> Any:
    with _CLIENT_LOCK:
        if api_key in _OPENAI_CLIENTS:
            return _OPENAI_CLIENTS[api_key]

        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        _OPENAI_CLIENTS[api_key] = client
        return client


def _anthropic_client(api_key: str) -> Any:
    with _CLIENT_LOCK:
        if api_key in _ANTHROPIC_CLIENTS:
            return _ANTHROPIC_CLIENTS[api_key]

        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        _ANTHROPIC_CLIENTS[api_key] = client
        return client


def _complete_with_web_search(provider: str, model: str, user: str, max_tokens: int) -> str:
    if provider == "google":
        api_key = _provider_secret("google")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY is not configured")
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
            },
        }
        resp = requests.post(
            GOOGLE_ENDPOINT.format(model=quote(model, safe="")),
            params={"key": api_key},
            json=payload,
            timeout=_GOOGLE_API_TIMEOUT,
        )
        resp.raise_for_status()
        parts = resp.json()["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts).strip()

    if provider == "openai":
        client = _openai_client(_provider_secret("openai"))
        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            tools=[{"type": "web_search_preview"}],
            max_output_tokens=max_tokens,
        )
        return getattr(resp, "output_text", "").strip()

    if provider == "anthropic":
        client = _anthropic_client(_provider_secret("anthropic"))
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user}],
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}],
        )
        return "\n".join(
            getattr(block, "text", "") for block in resp.content if getattr(block, "type", "") == "text"
        ).strip()

    raise RuntimeError(f"AI web search does not support provider {provider!r}")


def _parse_json_array(text: str) -> list[dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if isinstance(data, dict):
        data = data.get("jobs", [])
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _passes_source_url_shape(url: str, source: str) -> bool:
    patterns = _SOURCE_URL_PATTERNS.get(source)
    if not patterns:
        return True
    host_pattern, path_pattern = patterns
    parsed = urlparse(url)
    return (
        re.search(host_pattern, parsed.netloc, re.IGNORECASE) is not None
        and re.search(path_pattern, parsed.path, re.IGNORECASE) is not None
    )


def _confidence(item: dict[str, Any]) -> float:
    try:
        return float(item.get("confidence", 0))
    except (TypeError, ValueError):
        return 0


def _region_location_ok(job_location: str, region_config: dict[str, Any]) -> bool:
    """Return False only when the job has an explicit location that clearly belongs to a different region."""
    if not job_location:
        return True
    loc_lower = job_location.lower()
    if "remote" in loc_lower:
        return True
    region_loc = (region_config.get("location") or "").lower()
    region_term = region_loc.replace("remote ", "").replace(" remote", "").strip()
    if not region_term:
        return True
    return region_term in loc_lower


def _looks_stale(item: dict[str, Any], search_config: dict[str, Any]) -> bool:
    combined = " ".join(str(item.get(key) or "").lower() for key in ("title", "snippet", "description"))
    return any(str(marker).lower() in combined for marker in STALE_INDICATORS)


def _normalize(
    item: dict[str, Any],
    source: str,
    query: str,
    title_filters: list[str],
    config: dict[str, Any],
    search_config: dict[str, Any],
    region_config: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    url = str(item.get("url") or "").strip()
    title = str(item.get("title") or "").strip()
    if not url or not title:
        return None
    if title.lower().startswith("applying to "):
        return None
    excluded_title_terms = (search_config.get("exclusions", {}) or {}).get("title_terms", []) or []
    if title_filters and not title_matches(title, title_filters, excluded_title_terms):
        return None
    if _looks_stale(item, search_config):
        return None
    if not _passes_source_url_shape(url, source):
        return None
    job_location = str(item.get("location") or "").strip()
    if region_config and not _region_location_ok(job_location, region_config):
        return None

    min_confidence = float(config.get("min_confidence", 0.7))
    if min_confidence > 0 and _confidence(item) < min_confidence:
        return None

    return {
        "title": title,
        "company": str(item.get("company") or "").strip(),
        "location": str(item.get("location") or "").strip(),
        "url": url,
        "posted": "",
        "snippet": str(item.get("snippet") or "").strip(),
        "source": f"AI web search: {source}",
        "query": query,
        "region": str(region_config.get("name") or "") if region_config else "",
    }


def fetch_ai_web_search_jobs(
    title_filters: list[str],
    regions: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    config = ai_web_search_config()
    if not config.get("enabled", False):
        return []
    if not title_filters or not regions:
        return []

    provider, model, max_tokens = _llm_settings()
    budget = make_budget(config)
    search_config = _load_search_config()
    prompt_delay = float(config.get("prompt_delay_seconds", 5))
    jobs: list[dict[str, str]] = []
    first_prompt = True

    for region_name, region_config in regions.items():
        for title in title_filters:
            for source, query in build_queries(title, region_config, config):
                remaining = budget.remaining_results(region_name)
                if remaining <= 0:
                    logger.info("[ai-web-search] result cap reached for region=%s", region_name)
                    break
                if not budget.can_prompt(region_name):
                    logger.info("[ai-web-search] prompt cap reached for region=%s", region_name)
                    break

                if not first_prompt and prompt_delay > 0:
                    time.sleep(prompt_delay)
                first_prompt = False

                region_context = dict(region_config)
                region_context.setdefault("name", region_name)
                user = (
                    f"Query: {query}\n"
                    f"{build_rule_context(search_config, title_filters, region_context)}\n"
                    f"Return up to {remaining} current job postings as JSON."
                )
                try:
                    budget.record_prompt(region_name)
                    raw = _complete_with_web_search(provider, model, user, max_tokens)
                    normalized = [
                        job
                        for item in _parse_json_array(raw)
                        if (
                            job := _normalize(
                                item,
                                source,
                                query,
                                title_filters,
                                config,
                                search_config,
                                region_context,
                            )
                        )
                    ][:remaining]
                except Exception as exc:
                    logger.warning("[ai-web-search] %s failed for %r: %s", provider, query, exc)
                    continue

                budget.record_results(region_name, len(normalized))
                jobs.extend(normalized)

                if budget.results_used >= budget.max_total_results_per_run:
                    logger.info("[ai-web-search] run result cap reached")
                    return jobs

    logger.info(
        "[ai-web-search] complete: prompts=%s results=%s",
        budget.prompts_used,
        len(jobs),
    )
    return jobs
