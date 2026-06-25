from __future__ import annotations

from copy import deepcopy
from typing import Any

SECRET_ENV_VARS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "brave": "BRAVE_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "exa": "EXA_API_KEY",
    "firecrawl": "FIRECRAWL_API_KEY",
    "rapidapi": "RAPIDAPI_KEY",
    "jooble": "JOOBLE_API_KEY",
    "adzuna_app_id": "ADZUNA_APP_ID",
    "adzuna_api_key": "ADZUNA_API_KEY",
    "reed": "REED_API_KEY",
}

PROVIDER_SECRET_ENV_VARS: dict[str, str] = {
    "anthropic": SECRET_ENV_VARS["anthropic"],
    "openai": SECRET_ENV_VARS["openai"],
    "google": SECRET_ENV_VARS["google"],
}

LLM_ROLE_DEFAULTS: dict[str, Any] = {
    "default_provider": "anthropic",
    "providers": {
        "validation": "anthropic",
        "scoring": "anthropic",
        "tailoring": "anthropic",
        "cover_letter": "anthropic",
        "research": "anthropic",
        "linkedin": "anthropic",
        "jd_extraction": "anthropic",
    },
    "models": {
        "validation": "claude-haiku-4-5-20251001",
        "scoring": "claude-haiku-4-5-20251001",
        "tailoring": "claude-sonnet-4-6",
        "cover_letter": "claude-sonnet-4-6",
        "research": "claude-haiku-4-5-20251001",
        "linkedin": "claude-sonnet-4-6",
        "jd_extraction": "claude-haiku-4-5-20251001",
    },
    "max_tokens": {
        "validation": 200,
        "scoring": 1000,
        "tailoring": 4000,
        "cover_letter": 800,
        "research": 800,
        "linkedin": 6000,
        "jd_extraction": 1500,
    },
    "max_workers": 5,
    "rate_limits": {},
    "ollama": {"base_url": "http://localhost:11434"},
}

JOB_BOARD_SOURCE_NAMES: tuple[str, ...] = (
    "careerjet",
    "workingnomads",
    "jobspy",
    "remotive",
    "the_muse",
    "jobicy",
    "remoteok",
    "weworkremotely",
    "jooble",
    "himalayas",
    "adzuna",
    "reed",
    "mycareersfuture",
    "jobstreet",
    "jobbank",
    "gulftalent",
    "arbeitsagentur",
    "arbeitnow",
    "jsearch",
)

ATS_DISCOVERY_SOURCES: tuple[str, ...] = (
    "greenhouse",
    "lever",
    "ashby",
    "smartrecruiters",
    "workable",
    "personio",
    "recruitee",
    "hibob",
    "teamtailor",
    "breezy",
    "workday",
    "bamboohr",
)

STALE_INDICATORS: tuple[str, ...] = (
    "no longer available",
    "this job has expired",
    "position has been filled",
    "not accepting applications",
    "applications are closed",
    "job is closed",
    "posting has closed",
)

EXCLUDED_LISTING_URL_PATTERNS: tuple[str, ...] = (
    r"linkedin\.com/jobs/search",
    r"linkedin\.com/jobs/[^/?#]+-jobs",
    r"linkedin\.com/jobs/collections",
    r"linkedin\.com/jobs/remote-",
    r"linkedin\.com/jobs/[a-z]+-stellen",
    r"linkedin\.com/jobs/[a-z]+-stellenangebote",
)

LANGUAGE_INDICATORS: dict[str, tuple[str, ...]] = {
    "german": (
        "wir suchen",
        "wir freuen uns",
        "jetzt bewerben",
        "ihre aufgaben",
        "ihr profil",
        "deine aufgaben",
        "dein profil",
        "was wir bieten",
        "was du mitbringst",
        "das bieten wir",
        "stellenangebot",
        "berufserfahrung",
        "deutschkenntnisse",
    ),
    "italian": (
        "siamo alla ricerca",
        "la tua candidatura",
        "invia candidatura",
        "le tue responsabilita",
        "cosa offriamo",
        "requisiti richiesti",
    ),
    "spanish": (
        "buscamos",
        "envia tu solicitud",
        "tus responsabilidades",
        "tu perfil",
        "que ofrecemos",
    ),
    "french": (
        "nous recherchons",
        "votre candidature",
        "vos missions",
        "votre profil",
        "ce que nous offrons",
    ),
    "dutch": (
        "wij zoeken",
        "jouw profiel",
        "je verantwoordelijkheden",
        "solliciteer nu",
        "wat wij bieden",
    ),
}

SCORING_PROMPT_CONTEXT: dict[str, Any] = {
    "resume_mode": "compact_text",
    "resume_max_chars": 4500,
    "job_description_max_chars": 5000,
    "max_matched_keywords": 10,
    "max_gaps": 5,
}

TAILORING_DEFAULTS: dict[str, Any] = {
    "stories": {"max_chars_for_tailoring": 16000},
    "keyword_strategy": {"aggressiveness": "natural", "avoid_keywords": []},
    "rules": {
        "forbidden_modifications": [],
        "allowed_modifications": ["summary", "bullets", "skills", "active_projects"],
        "preserve_latex": True,
        "summary": {"max_lines": 4, "no_em_dashes": True, "proof_point_preferences": []},
        "bullets": {"max_per_role": 5},
        "projects": {
            "max_projects": 4,
            "min_bullets_per_project": 3,
            "max_bullets_per_project": 5,
            "max_total_resume_pages": 2,
        },
    },
}

COVER_LETTER_DEFAULTS: dict[str, Any] = {
    "tone": ["formal", "confident", "substantive"],
    "header": {
        "include_date": True,
        "date_format": "%B %d, %Y",
        "salutation": "Dear Hiring Manager,",
    },
    "closing": {"format": "Best regards\nCandidate Name"},
    "content": {"target_words": 220, "max_words": 280, "paragraphs": 4},
    "forbidden": {"style": [], "phrases": []},
    "stories": {"max_chars_for_cover": 6000},
    "structure": {
        "paragraph_1": {
            "name": "Opening",
            "max_sentences": 3,
            "purpose": "Connect the role, company, and candidate positioning.",
        },
        "paragraph_2": {
            "name": "Evidence",
            "max_sentences": 4,
            "purpose": "Use verified story-bank proof relevant to the job.",
        },
        "paragraph_3": {
            "name": "Fit",
            "max_sentences": 4,
            "purpose": "Explain how the candidate would help with the role's priorities.",
        },
        "paragraph_4": {
            "name": "Close",
            "max_sentences": 2,
            "purpose": "End with concise interest and availability for next steps.",
        },
    },
}

LINKEDIN_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "positioning": "",
    "audience": [],
    "content_pillars": [],
    "target_companies": [],
    "tone": [],
    "forbidden_phrases": [],
    "confidentiality": {"forbidden_public_details": []},
    "files": {
        "ideas": "outputs/linkedin/ideas.md",
        "drafts_dir": "outputs/linkedin/drafts",
        "networking": "outputs/linkedin/networking.md",
    },
    "idea_generation": {"ideas_per_run": 3},
    "draft_generation": {
        "posts_per_run": 1,
        "source_status": "raw",
        "mark_converted": True,
        "max_words_per_post": 150,
    },
    "networking_discovery": {
        "results_per_query": 5,
        "region": {"country": "", "search_lang": "en", "location": ""},
    },
    "networking": {"max_message_words": 70},
}

HTTP_DEFAULTS: dict[str, Any] = {
    "url_verification": {"enabled": True, "timeout_seconds": 5, "max_workers": 5},
    "ats_discovery": {"enabled": True, "timeout_seconds": 10, "sources": list(ATS_DISCOVERY_SOURCES)},
    "ats_scraper": {"timeout_seconds": 10},
    "playwright": {"timeout_seconds": 10},
    "lightpanda": {"timeout_seconds": 8},
    "firecrawl": {"timeout_seconds": 20},
    "jd_fetcher": {"timeout_seconds": 10},
    "jd_enrichment": {"timeout_seconds": 10, "max_workers": 5, "skip_url_patterns": []},
    "url_liveness": {"timeout_seconds": 10, "max_consecutive_failures": 3},
    "search_providers": {
        "timeout_seconds": 10,
        "max_consecutive_failures": 3,
        "order": ["searxng", "brave"],
        "ats_discovery_order": ["searxng", "brave", "exa"],
        "searxng_base_url": "",
        "ats_discovery": {"enabled": True, "sources": list(ATS_DISCOVERY_SOURCES)},
    },
    "job_boards": {
        "timeout_seconds": 10,
        "max_consecutive_failures": 3,
        **{name: {"enabled": True} for name in JOB_BOARD_SOURCE_NAMES},
        "careerjet": {"enabled": True, "affid": ""},
        "jobspy": {"enabled": True, "hours_old": 72},
    },
    "api_budgets": {
        "enabled": True,
        "state_path": "outputs/state/api_usage.json",
        "monthly_limits": {},
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged
