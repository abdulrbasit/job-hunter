from __future__ import annotations

from job_hunter.sources.policy import JobPolicy


def _language_policy(*codes: str) -> JobPolicy:
    return JobPolicy({"filters": {"hunt_languages": list(codes)}})


def test_language_allowlist_rejects_detected_unlisted_language() -> None:
    policy = _language_policy("en")

    excluded, code, uncertain = policy.language_screen("PM", "Wir suchen einen erfahrenen Produktmanager.")

    assert excluded
    assert code == "de"
    assert not uncertain


def test_language_allowlist_accepts_listed_language() -> None:
    policy = _language_policy("en", "de")

    excluded, code, uncertain = policy.language_screen("PM", "Wir suchen einen erfahrenen Produktmanager.")

    assert not excluded
    assert code == "de"
    assert not uncertain


def test_language_screen_fails_open_on_low_confidence_short_title() -> None:
    policy = _language_policy("en")

    excluded, code, uncertain = policy.language_screen("Manager", "")

    assert not excluded
    assert code is None
    assert uncertain


def _experience_policy(*level_ids: str) -> JobPolicy:
    return JobPolicy({"filters": {"experience_levels": list(level_ids)}})


def test_experience_screen_excludes_no_overlap_range() -> None:
    policy = _experience_policy("entry", "junior")  # 0-1, 0-2 -> user range 0-2

    excluded, detail, ambiguous = policy.experience_screen(
        "Principal Engineer", "We require 10+ years of experience leading platform architecture."
    )

    assert excluded
    assert not ambiguous
    assert detail is not None
    assert detail.detected_min == 10
    assert detail.detected_max is None
    assert detail.user_min == 0
    assert detail.user_max == 2


def test_experience_screen_accepts_overlapping_range() -> None:
    policy = _experience_policy("mid", "senior")  # 3-6, 5-9 -> user range 3-9

    excluded, detail, ambiguous = policy.experience_screen("Senior Engineer", "5+ years of experience required.")

    assert not excluded
    assert not ambiguous
    assert detail is not None
    assert detail.detected_min == 5


def test_experience_screen_fails_open_on_ambiguous_text() -> None:
    policy = _experience_policy("entry", "junior")

    excluded, detail, ambiguous = policy.experience_screen(
        "Software Engineer", "Join our growing team and make an impact."
    )

    assert not excluded
    assert ambiguous
    assert detail is None


def test_experience_screen_noop_when_no_levels_selected() -> None:
    policy = _experience_policy()

    excluded, detail, ambiguous = policy.experience_screen("Principal Engineer", "10+ years of experience required.")

    assert not excluded
    assert not ambiguous
    assert detail is None


def test_format_experience_reason_detail_renders_open_and_closed_ranges() -> None:
    from job_hunter.sources.policy import ExperienceScreenDetail, format_experience_reason_detail

    detail = ExperienceScreenDetail(detected_level_id=None, detected_min=8, detected_max=None, user_min=0, user_max=3)
    assert format_experience_reason_detail(detail) == "requires 8+y, your range 0-3y"


def test_excluded_company_matches_suffix_and_case_variants() -> None:
    policy = JobPolicy({"filters": {"excluded_companies": ["Delivery Hero", "Auto1", "Spam Co"]}})

    assert policy.is_excluded_company("Delivery Hero SE")
    assert policy.is_excluded_company("AUTO1 Group")
    assert policy.is_excluded_company("Spam Co")
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


def test_explicit_country_overrides_broad_remote_restriction() -> None:
    policy = JobPolicy(_MULTI_REGION_CONFIG)

    assert policy.has_incompatible_location_for_global_feed(
        {"location_restrictions": ["Anywhere in the World", "United States"]}
    )
    assert policy.has_incompatible_location_for_global_feed({"location_restrictions": ["Worldwide", "Spain"]})
    assert not policy.has_incompatible_location_for_global_feed({"location_restrictions": ["Worldwide", "Germany"]})


def test_explicit_country_overrides_broad_remote_for_region() -> None:
    policy = JobPolicy(_MULTI_REGION_CONFIG)
    berlin = _MULTI_REGION_CONFIG["regions"]["berlin"]

    assert policy.has_incompatible_location_metadata(
        {"location": "Remote", "location_restrictions": ["Anywhere", "United States"]},
        berlin,
    )
    assert not policy.has_incompatible_location_metadata(
        {"location": "Remote", "location_restrictions": ["Anywhere", "Germany"]},
        berlin,
    )


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


# --- is_location_restricted ---


def test_is_location_restricted_false_with_no_configured_regions() -> None:
    policy = JobPolicy({"regions": {}, "exclusions": {}})
    assert not policy.is_location_restricted("PM (Remote/Egypt)", "must be based in Egypt")


def test_is_location_restricted_true_for_restriction_phrase_naming_non_allowed_country() -> None:
    policy = JobPolicy(_MULTI_REGION_CONFIG)  # berlin=DE, dublin=IE
    assert policy.is_location_restricted("Product Manager", "Applicants from Spain only will be considered.")


def test_is_location_restricted_false_when_restriction_names_allowed_country() -> None:
    policy = JobPolicy(_MULTI_REGION_CONFIG)  # berlin=DE, dublin=IE
    assert not policy.is_location_restricted("Product Manager", "Must be based in Germany.")


def test_is_location_restricted_true_for_bare_country_name_in_title() -> None:
    policy = JobPolicy(_MULTI_REGION_CONFIG)  # berlin=DE, dublin=IE
    assert policy.is_location_restricted("PM - Colombia", "")


def test_is_location_restricted_true_for_us_shorthand_phrase() -> None:
    policy = JobPolicy(_MULTI_REGION_CONFIG)  # berlin=DE, dublin=IE — no US region
    assert policy.is_location_restricted("Product Manager (US Remote)", "")


def test_is_location_restricted_false_for_us_shorthand_when_us_is_allowed() -> None:
    policy = JobPolicy({"regions": {"nyc": {"enabled": True, "country": "US"}}, "exclusions": {}})
    assert not policy.is_location_restricted("Product Manager (US Remote)", "")


def test_is_location_restricted_false_with_no_restriction_language() -> None:
    policy = JobPolicy(_MULTI_REGION_CONFIG)
    assert not policy.is_location_restricted("Product Manager", "Join our growing team and own the roadmap.")
