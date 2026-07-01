"""Tests for the LinkedIn content workflow."""

import json
from importlib import resources
from pathlib import Path
from unittest.mock import patch

import yaml

from job_hunter.linkedin import (
    _config as common,
)
from job_hunter.linkedin import (
    drafts as draft_posts,
)
from job_hunter.linkedin import (
    engagement as discover_engagement,
)
from job_hunter.linkedin import (
    ideas as generate_ideas,
)


def _config(tmp_path: Path) -> Path:
    data = {
        "linkedin": {
            "enabled": True,
            "positioning": "Technical Product Owner",
            "audience": ["hiring managers"],
            "content_pillars": ["platform product management"],
            "tone": ["concrete"],
            "forbidden_phrases": ["please refer me"],
            "confidentiality": {
                "forbidden_public_details": ["internal product names"],
            },
            "files": {
                "ideas": str(tmp_path / "ideas.md"),
                "drafts_dir": str(tmp_path / "drafts"),
                "networking": str(tmp_path / "networking.md"),
            },
            "idea_generation": {"ideas_per_run": 2},
            "draft_generation": {
                "posts_per_run": 1,
                "source_status": "raw",
                "mark_converted": True,
                "max_words_per_post": 120,
            },
            "networking_discovery": {
                "results_per_query": 1,
                "region": {"country": "DE", "search_lang": "en", "location": "Berlin"},
            },
            "networking": {
                "max_message_words": 70,
            },
        }
    }
    path = tmp_path / "config.yml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _strategy_payload() -> str:
    return json.dumps(
        {
            "people_queries": ["platform product managers"],
            "recruiter_queries": ["technical recruiter product manager"],
            "target_companies": ["HERE Technologies", "Google"],
        }
    )


def test_next_idea_id_increments() -> None:
    assert common.next_idea_id("") == "IDEA-0001"
    assert common.next_idea_id("## IDEA-0007: Existing") == "IDEA-0008"


def test_idea_parsing_ignores_fenced_examples() -> None:
    text = """# Ideas

```markdown
## IDEA-0001: Example only

Status: raw
```

## IDEA-0003: Real idea

Status: raw
"""
    assert common.next_idea_id(text) == "IDEA-0004"
    assert [block["id"] for block in common.unconverted_ideas(text, "raw")] == ["IDEA-0003"]


def test_linkedin_yaml_files_parse() -> None:
    files = [
        ".github/workflows/linkedin_content.yml",
        ".github/workflows/update_from_template.yml",
        ".github/template-workflows/update_from_template.yml",
        "config/job_hunter.yml",
    ]
    for filename in files:
        path = Path(filename)
        if path.exists():
            assert yaml.safe_load(path.read_text(encoding="utf-8")) is not None


def test_template_linkedin_not_in_config() -> None:
    config = yaml.safe_load((Path(__file__).parent.parent / "config/job_hunter.yml").read_text(encoding="utf-8"))

    assert "linkedin" not in config


def test_linkedin_internal_defaults_are_packaged_and_parse() -> None:
    with resources.files("job_hunter.linkedin").joinpath("defaults.yml").open(encoding="utf-8") as defaults:
        data = yaml.safe_load(defaults)

    assert data["state_file"] == "state.yml"
    assert data["terms"]["role_terms"]
    assert data["llm_caps"]["max_people_to_rank"] == 5


def test_disabled_linkedin_discovery_exits_without_search_or_llm(tmp_path) -> None:
    config = _config(tmp_path)
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    data["linkedin"]["enabled"] = False
    config.write_text(yaml.safe_dump(data), encoding="utf-8")

    with (
        patch("job_hunter.linkedin.engagement.search_web") as search,
        patch("job_hunter.linkedin.engagement.complete_linkedin") as llm,
    ):
        result = discover_engagement.discover(config)

    assert result == {"people": [], "recruiters": []}
    search.assert_not_called()
    llm.assert_not_called()


def test_generate_ideas_appends_public_safe_items(tmp_path) -> None:
    config = _config(tmp_path)
    payload = json.dumps(
        [
            {
                "title": "Internal platforms need product thinking",
                "source": "story_bank",
                "pillar": "platform product management",
                "angle": "Platform work needs adoption and versioning.",
                "evidence_to_use": "General platform product experience.",
                "do_not_mention": "Internal product names.",
            }
        ]
    )

    with patch("job_hunter.linkedin.ideas.complete_linkedin", return_value=payload):
        rendered = generate_ideas.generate(config)

    ideas = (tmp_path / "ideas.md").read_text(encoding="utf-8")
    assert len(rendered) == 1
    assert "IDEA-0001" in ideas
    assert "Public-safe: yes" in ideas


def test_generate_ideas_prompt_does_not_assume_pm_or_po(tmp_path) -> None:
    config = _config(tmp_path)
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    data["linkedin"]["positioning"] = "Cloud infrastructure engineer focused on reliability."
    data["linkedin"]["content_pillars"] = ["incident response", "distributed systems"]
    config.write_text(yaml.safe_dump(data), encoding="utf-8")
    captured = {}

    def fake_complete(_system, prompt):
        captured["prompt"] = prompt
        return json.dumps([])

    with patch("job_hunter.linkedin.ideas.complete_linkedin", side_effect=fake_complete):
        generate_ideas.generate(config)

    assert "Do not assume the user is a PM or PO" in captured["prompt"]
    assert "Cloud infrastructure engineer" in captured["prompt"]


def test_draft_posts_creates_draft_and_marks_idea_converted(tmp_path) -> None:
    config = _config(tmp_path)
    (tmp_path / "ideas.md").write_text(
        """# Ideas

## IDEA-0001: Platform APIs need product lifecycle thinking

Status: raw
Source: manual
Pillar: platform product management
Confidentiality: public-safe
Public-safe: yes

Angle:
Versioning and adoption matter.
""",
        encoding="utf-8",
    )
    payload = json.dumps(
        [
            {
                "idea_id": "IDEA-0001",
                "title": "Platform APIs need product lifecycle thinking",
                "pillar": "platform product management",
                "post_text": "A platform API is still a product surface.",
                "confidentiality_notes": "Generalized.",
                "review_checklist": "Check no private names are included.",
            }
        ]
    )

    with patch("job_hunter.linkedin.drafts.complete_linkedin", return_value=payload):
        created = draft_posts.draft(config)

    assert len(created) == 1
    assert created[0].exists()
    ideas = (tmp_path / "ideas.md").read_text(encoding="utf-8")
    assert "Converted to draft: yes" in ideas
    assert "Draft:" in ideas


def test_discover_networking_writes_networking_queue(tmp_path) -> None:
    config = _config(tmp_path)
    search_result = [
        {
            "url": "https://www.linkedin.com/in/example",
            "title": "Example Product Leader",
            "description": "Posts about platform product management.",
            "source": "SearXNG",
        },
    ]
    payload = json.dumps(
        {
            "people": [
                {
                    "url": "https://www.linkedin.com/in/example",
                    "message_variants": ["I noticed your posts on platform product work."],
                }
            ],
        }
    )

    with (
        patch("job_hunter.linkedin.engagement.search_web", return_value=search_result),
        patch(
            "job_hunter.linkedin.engagement.complete_linkedin",
            side_effect=[_strategy_payload(), payload],
        ),
    ):
        result = discover_engagement.discover(config)

    assert len(result["people"]) == 1
    assert "Example Product Leader" in (tmp_path / "networking.md").read_text(encoding="utf-8")
    assert (tmp_path / "state.yml").exists()


def test_discover_networking_falls_back_on_malformed_json(tmp_path) -> None:
    config = _config(tmp_path)
    search_result = [
        {
            "url": "https://www.linkedin.com/in/example",
            "title": "Example Product Leader - Senior Product Manager - LinkedIn",
            "description": "Posts about platform product management.",
            "source": "SearXNG",
            "query": "site:linkedin.com/in platform product management",
        },
    ]

    with (
        patch("job_hunter.linkedin.engagement.search_web", return_value=search_result),
        patch(
            "job_hunter.linkedin.engagement.complete_linkedin",
            side_effect=[_strategy_payload(), '{"people": [{"name": "broken"}]'],
        ),
    ):
        result = discover_engagement.discover(config)

    assert len(result["people"]) == 1
    person = result["people"][0]
    assert person["suggested_action"] == "review manually"
    assert person["relationship_type"] in {
        "role_adjacent_professional",
        "senior_professional",
        "creator",
    }
    assert person["message_variants"]
    assert "Example Product Leader" in (tmp_path / "networking.md").read_text(encoding="utf-8")


def test_search_strategy_uses_existing_job_hunter_context(tmp_path) -> None:
    config = _config(tmp_path)
    captured = {}

    def fake_complete(_system, prompt):
        captured["prompt"] = prompt
        return _strategy_payload()

    fake_context = {
        "job_titles": ["Product Manager", "Technical Product Manager"],
        "regions": ["Berlin Remote"],
        "companies": [],
    }
    with patch("job_hunter.linkedin.engagement._search_context", return_value=fake_context):
        with patch(
            "job_hunter.linkedin.engagement.complete_linkedin",
            side_effect=fake_complete,
        ):
            strategy = discover_engagement._search_strategy(
                yaml.safe_load(config.read_text(encoding="utf-8"))["linkedin"]
            )

    assert "TARGET JOB TITLES FROM JOB HUNTER CONFIG" in captured["prompt"]
    assert "Product Manager" in captured["prompt"]
    assert strategy["people_queries"]


def test_discovery_defaults_can_follow_non_pm_profiles(tmp_path) -> None:
    config = _config(tmp_path)
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    data["linkedin"]["positioning"] = "Cloud infrastructure engineer focused on reliability."
    config.write_text(yaml.safe_dump(data), encoding="utf-8")
    search_result = [
        {
            "url": "https://www.linkedin.com/in/sre",
            "title": "Example Site Reliability Engineer",
            "description": "Writes about incident response and distributed systems operations for reliable infrastructure teams.",
            "source": "SearXNG",
        }
    ]

    with (
        patch("job_hunter.linkedin.engagement.search_web", return_value=search_result),
        patch(
            "job_hunter.linkedin.engagement.complete_linkedin",
            side_effect=[_strategy_payload(), '{"people": []}'],
        ),
    ):
        result = discover_engagement.discover(config)

    assert len(result["people"]) == 1
    assert result["people"][0]["relationship_type"] == "role_adjacent_professional"


def test_discovery_dedupes_seen_people(tmp_path) -> None:
    config = _config(tmp_path)
    state = {
        "seen_people": ["https://www.linkedin.com/in/seen"],
        "skipped_urls": [],
        "message_fingerprints": [],
    }
    (tmp_path / "state.yml").write_text(yaml.safe_dump(state), encoding="utf-8")
    search_result = [
        {
            "url": "https://www.linkedin.com/in/seen",
            "title": "Seen Product Manager",
            "description": "AI product management and platform work.",
            "source": "SearXNG",
        },
    ]

    with (
        patch("job_hunter.linkedin.engagement.search_web", return_value=search_result),
        patch(
            "job_hunter.linkedin.engagement.complete_linkedin",
            return_value=_strategy_payload(),
        ) as llm,
    ):
        result = discover_engagement.discover(config)

    assert result == {"people": [], "recruiters": []}
    llm.assert_called_once()


def test_recruiters_are_prioritized_with_specific_messages(tmp_path) -> None:
    config = _config(tmp_path)
    search_result = [
        {
            "url": "https://www.linkedin.com/in/recruiter",
            "title": "Example Recruiter - Technical Recruiter at ExampleCo",
            "description": "Hiring product managers and AI platform product people in Berlin.",
            "source": "SearXNG",
        }
    ]
    payload = json.dumps(
        {
            "people": [
                {
                    "url": "https://www.linkedin.com/in/recruiter",
                    "message_variants": [
                        "Hi Example, I noticed you hire AI platform product people in Berlin. I work across AI, speech, platform, and automotive software and would be glad to stay connected."
                    ],
                }
            ],
        }
    )

    with (
        patch("job_hunter.linkedin.engagement.search_web", return_value=search_result),
        patch(
            "job_hunter.linkedin.engagement.complete_linkedin",
            side_effect=[_strategy_payload(), payload],
        ),
    ):
        result = discover_engagement.discover(config)

    assert len(result["recruiters"]) == 1
    assert result["recruiters"][0]["relationship_type"] == "recruiter_intro"
    assert "AI platform product people" in (tmp_path / "networking.md").read_text(encoding="utf-8")


def test_llm_caps_limit_generation_candidates(tmp_path) -> None:
    config = _config(tmp_path)
    search_result = [
        {
            "url": f"https://www.linkedin.com/in/person-{idx}",
            "title": f"Person {idx} - Senior Product Manager",
            "description": "AI product management and platform product work with enough detail to score well.",
            "source": "SearXNG",
        }
        for idx in range(7)
    ]
    captured = {}

    def fake_complete(_system, prompt):
        captured.setdefault("prompts", []).append(prompt)
        if "Create a compact LinkedIn search strategy" in prompt:
            return _strategy_payload()
        return json.dumps({"people": []})

    with (
        patch("job_hunter.linkedin.engagement.search_web", return_value=search_result),
        patch(
            "job_hunter.linkedin.engagement.complete_linkedin",
            side_effect=fake_complete,
        ),
    ):
        discover_engagement.discover(config)

    assert captured["prompts"][-1].count("linkedin.com/in/person-") == 5


def test_login_wall_results_are_filtered(tmp_path) -> None:
    config = _config(tmp_path)
    search_result = [
        {
            "url": "https://www.linkedin.com/in/login-wall-profile",
            "title": "Some Person - LinkedIn",
            "description": "Agree & Join LinkedIn\nBy clicking Continue to join...",
            "source": "SearXNG",
            "query": "site:linkedin.com/in platform product management",
        },
    ]
    with (
        patch("job_hunter.linkedin.engagement.search_web", return_value=search_result),
        patch(
            "job_hunter.linkedin.engagement.complete_linkedin",
            side_effect=[_strategy_payload(), "{}"],
        ),
    ):
        result = discover_engagement.discover(config)
    assert len(result["people"]) == 0
    assert len(result["recruiters"]) == 0
