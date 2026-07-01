from __future__ import annotations

from job_hunter.sources.policy import JobPolicy


def _policy(excluded_languages: list[str]) -> JobPolicy:
    return JobPolicy({"exclusions": {"languages": excluded_languages}})


GERMAN_INDICATORS = [
    "wir suchen",
    "wir freuen uns",
    "jetzt bewerben",
    "ihre aufgaben",
    "ihr profil",
    "deine aufgaben",
    "dein profil",
    "was wir bieten",
]

ITALIAN_INDICATORS = [
    "siamo alla ricerca",
    "la tua candidatura",
    "invia candidatura",
    "le tue responsabilita",
    "cosa offriamo",
    "requisiti richiesti",
]

GERMAN_HEURISTIC_TEXT = (
    "Wir suchen eine erfahrene Person, die mit uns zusammen das Team aufbauen wird. "
    "Die Person sollte die Erfahrung und das Wissen mitbringen, das wir brauchen. "
    "Wenn du dich angesprochen fuehls, freuen wir uns auf deine Bewerbung. "
    "Deine Aufgaben sind klar definiert und du wirst eine wichtige Rolle spielen."
)

ENGLISH_BERLIN_TEXT = (
    "We are looking for a product manager to join our growing team in Berlin. "
    "You will own the roadmap and work closely with engineering and design. "
    "The ideal candidate has 3+ years of product experience in a fast-paced environment. "
    "We value strong communication skills and a data-driven approach to decision making."
)


# ---------------------------------------------------------------------------
# excluded_languages: [german] — indicators
# ---------------------------------------------------------------------------


def test_german_indicator_phrase_is_excluded() -> None:
    policy = _policy(["german"])
    assert policy.is_excluded_language("Product Manager", "Wir suchen einen erfahrenen Product Manager.")


def test_german_posting_with_multiple_indicators_is_excluded() -> None:
    policy = _policy(["german"])
    snippet = "Ihre Aufgaben: Produktmanagement. Ihr Profil: 3+ Jahre Erfahrung. Jetzt bewerben!"
    assert policy.is_excluded_language("Senior PM", snippet)


# ---------------------------------------------------------------------------
# excluded_languages: [german] — statistical heuristic (no indicators match)
# ---------------------------------------------------------------------------


def test_german_heuristic_catches_text_without_indicator_phrase() -> None:
    policy = _policy(["german"])
    assert policy.is_excluded_language("Produktmanager", GERMAN_HEURISTIC_TEXT)


# ---------------------------------------------------------------------------
# excluded_languages: [german] — English posting in Berlin must pass
# ---------------------------------------------------------------------------


def test_english_berlin_posting_passes_german_filter() -> None:
    policy = _policy(["german"])
    assert not policy.is_excluded_language("Product Manager", ENGLISH_BERLIN_TEXT)


# ---------------------------------------------------------------------------
# excluded_languages: [italian] — indicators only (no heuristic for non-German)
# ---------------------------------------------------------------------------


def test_italian_indicator_phrase_is_excluded() -> None:
    policy = _policy(["italian"])
    snippet = "Siamo alla ricerca di un product manager con esperienza."
    assert policy.is_excluded_language("Product Manager", snippet)


def test_italian_text_without_matching_indicators_passes() -> None:
    policy = _policy(["italian"])
    snippet = "Cerchiamo un prodotto manager con molta esperienza nel settore tecnologico."
    assert not policy.is_excluded_language("Product Manager", snippet)


# ---------------------------------------------------------------------------
# empty excluded_languages — all postings pass
# ---------------------------------------------------------------------------


def test_empty_excluded_languages_passes_german_text() -> None:
    policy = _policy([])
    assert not policy.is_excluded_language("Product Manager", GERMAN_HEURISTIC_TEXT)


def test_empty_excluded_languages_passes_italian_text() -> None:
    policy = _policy([])
    snippet = "Siamo alla ricerca di un product manager."
    assert not policy.is_excluded_language("Product Manager", snippet)


# ---------------------------------------------------------------------------
# multiple excluded languages
# ---------------------------------------------------------------------------


def test_german_excluded_when_multiple_languages_configured() -> None:
    policy = _policy(["german", "italian"])
    assert policy.is_excluded_language("PM", "Wir suchen einen erfahrenen Produktmanager.")


def test_italian_excluded_when_multiple_languages_configured() -> None:
    policy = _policy(["german", "italian"])
    assert policy.is_excluded_language("PM", "Siamo alla ricerca di un product manager con esperienza.")


def test_english_passes_when_multiple_languages_configured() -> None:
    policy = _policy(["german", "italian"])
    assert not policy.is_excluded_language("Product Manager", ENGLISH_BERLIN_TEXT)


def test_excluded_company_matches_suffix_and_case_variants() -> None:
    policy = JobPolicy({"exclusions": {"companies": ["Delivery Hero", "Auto1 Group"]}})

    assert policy.is_excluded_company("Delivery Hero SE")
    assert policy.is_excluded_company("AUTO1 Group")
    assert not policy.is_excluded_company("Hero Digital")


def test_wrong_location_uses_singular_location_config() -> None:
    policy = JobPolicy({"exclusions": {}})
    region_config = {"country": "DE", "location": "Berlin"}

    assert not policy.has_wrong_location({"location": "Berlin, Germany"}, region_config)
    assert policy.has_wrong_location({"location": "Munich, Germany"}, region_config)


def test_wrong_location_keeps_plural_locations_config() -> None:
    policy = JobPolicy({"exclusions": {}})
    region_config = {"country": "DE", "locations": ["Berlin", "Munich"]}

    assert not policy.has_wrong_location({"location": "Munich, Germany"}, region_config)
    assert policy.has_wrong_location({"location": "Hamburg, Germany"}, region_config)


def test_city_region_rejects_plain_remote_without_metadata() -> None:
    policy = JobPolicy({"exclusions": {}})
    region_config = {"country": "DE", "location": "Berlin"}

    assert policy.has_incompatible_location_metadata({"location": "Remote"}, region_config)


def test_city_region_accepts_remote_country_metadata() -> None:
    policy = JobPolicy({"exclusions": {}})
    region_config = {"country": "DE", "location": "Berlin"}
    job = {"location": "Remote", "location_restrictions": ["Germany"]}

    assert not policy.has_incompatible_location_metadata(job, region_config)
    assert not policy.has_wrong_location(job, region_config)


def test_country_slug_restrictions_reject_incompatible_remote_jobs() -> None:
    policy = JobPolicy({"exclusions": {}})
    region_config = {"country": "DE", "location": "Berlin"}

    assert policy.has_incompatible_location_metadata(
        {"url": "https://example.com/jobs/product-manager-remote-within-the-us", "location": "Remote"},
        region_config,
    )
    assert policy.has_incompatible_location_metadata(
        {"url": "https://example.com/jobs/product-manager-remote-uk", "location": "Remote"},
        region_config,
    )


# --- has_incompatible_location_for_global_feed ---

_MULTI_REGION_CONFIG = {
    "regions": {
        "berlin": {"enabled": True, "country": "DE", "location": "Berlin"},
        "dublin": {"enabled": True, "country": "IE", "location": "Dublin"},
    },
    "exclusions": {},
}


def test_global_feed_rejects_location_restrictions_to_non_configured_country() -> None:
    policy = JobPolicy(_MULTI_REGION_CONFIG)
    assert policy.has_incompatible_location_for_global_feed({"location_restrictions": ["Spain"]})
    assert policy.has_incompatible_location_for_global_feed({"location_restrictions": ["Greece"]})
    assert policy.has_incompatible_location_for_global_feed({"location_restrictions": ["USA"]})
    assert policy.has_incompatible_location_for_global_feed({"location_restrictions": ["United States"]})


def test_global_feed_accepts_location_restrictions_to_configured_country() -> None:
    policy = JobPolicy(_MULTI_REGION_CONFIG)
    assert not policy.has_incompatible_location_for_global_feed({"location_restrictions": ["Germany"]})
    assert not policy.has_incompatible_location_for_global_feed({"location_restrictions": ["Ireland"]})
    assert not policy.has_incompatible_location_for_global_feed({"location_restrictions": ["DE"]})


def test_global_feed_accepts_broad_location_restrictions() -> None:
    policy = JobPolicy(_MULTI_REGION_CONFIG)
    assert not policy.has_incompatible_location_for_global_feed({"location_restrictions": ["Anywhere"]})
    assert not policy.has_incompatible_location_for_global_feed({"location_restrictions": ["worldwide"]})
    assert not policy.has_incompatible_location_for_global_feed({"location_restrictions": ["Remote"]})


def test_global_feed_rejects_location_field_named_non_configured_country() -> None:
    policy = JobPolicy(_MULTI_REGION_CONFIG)
    assert policy.has_incompatible_location_for_global_feed({"location": "Barcelona, Spain"})
    assert policy.has_incompatible_location_for_global_feed({"location": "Athens, Greece"})
    assert policy.has_incompatible_location_for_global_feed({"location": "New York, United States"})


def test_global_feed_accepts_remote_or_empty_location() -> None:
    policy = JobPolicy(_MULTI_REGION_CONFIG)
    assert not policy.has_incompatible_location_for_global_feed({"location": "Remote"})
    assert not policy.has_incompatible_location_for_global_feed({"location": ""})
    assert not policy.has_incompatible_location_for_global_feed({})


def test_global_feed_passes_when_no_regions_configured() -> None:
    policy = JobPolicy({"regions": {}, "exclusions": {}})
    assert not policy.has_incompatible_location_for_global_feed({"location_restrictions": ["Spain"]})


def test_global_feed_accepts_europe_and_emea_restrictions_when_region_is_in_europe() -> None:
    """Adapters (RemoteOK/Himalayas/etc) now defer this decision to policy — broad
    continental restrictions must not be dropped early for an EU-configured region."""
    policy = JobPolicy(_MULTI_REGION_CONFIG)  # berlin=DE, dublin=IE — both in Europe
    assert not policy.has_incompatible_location_for_global_feed({"location_restrictions": ["Europe"]})
    assert not policy.has_incompatible_location_for_global_feed({"location_restrictions": ["EMEA"]})


def test_global_feed_rejects_europe_restriction_when_no_configured_region_is_in_europe() -> None:
    non_eu_config = {
        "regions": {"sg": {"enabled": True, "country": "SG", "location": "Singapore"}},
        "exclusions": {},
    }
    policy = JobPolicy(non_eu_config)
    assert policy.has_incompatible_location_for_global_feed({"location_restrictions": ["Europe"]})


def test_wrong_region_job_is_still_rejected_after_adapter_stops_pre_filtering() -> None:
    """Adapters (RemoteOK/Himalayas/The Muse/JobSpy) no longer drop wrong-region jobs
    themselves — this is the downstream safety net that must still catch them."""
    policy = JobPolicy(_MULTI_REGION_CONFIG)
    berlin_region_config = _MULTI_REGION_CONFIG["regions"]["berlin"]

    # A job onsite in a non-configured country, exactly as RemoteOK/JobSpy would emit it now.
    wrong_region_job = {"location": "Bangalore, India", "location_restrictions": ["India"]}
    assert policy.has_incompatible_location_metadata(wrong_region_job, berlin_region_config)


_GULF_REGION_CONFIG = {
    "regions": {
        "ae": {"enabled": True, "country": "AE", "location": "Dubai"},
        "bh": {"enabled": True, "country": "BH", "location": "Manama"},
    },
    "exclusions": {},
}


def test_global_feed_accepts_gulf_and_mena_broad_restrictions_for_gulf_region() -> None:
    """GulfTalent/Bayt yield: a remote job restricted to "GCC"/"Middle East"/"MENA"
    must not be dropped for AE/BH-configured regions — these were previously only
    matched against Europe country codes."""
    policy = JobPolicy(_GULF_REGION_CONFIG)
    assert not policy.has_incompatible_location_for_global_feed({"location_restrictions": ["GCC"]})
    assert not policy.has_incompatible_location_for_global_feed({"location_restrictions": ["Middle East"]})
    assert not policy.has_incompatible_location_for_global_feed({"location_restrictions": ["MENA"]})
    assert not policy.has_incompatible_location_for_global_feed({"location_restrictions": ["EMEA"]})


def test_global_feed_rejects_gulf_restrictions_when_no_configured_region_is_in_gulf() -> None:
    policy = JobPolicy(_MULTI_REGION_CONFIG)  # berlin=DE, dublin=IE — no Gulf region
    assert policy.has_incompatible_location_for_global_feed({"location_restrictions": ["GCC"]})
    assert policy.has_incompatible_location_for_global_feed({"location_restrictions": ["Middle East"]})


def test_emea_still_accepted_for_europe_only_region() -> None:
    """EMEA must keep matching pure-Europe regions too, not just Gulf ones."""
    policy = JobPolicy(_MULTI_REGION_CONFIG)  # berlin=DE, dublin=IE
    assert not policy.has_incompatible_location_for_global_feed({"location_restrictions": ["EMEA"]})
