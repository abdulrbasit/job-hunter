import sys
from types import SimpleNamespace

from job_hunter.sources import ai_web_search


def test_build_queries_uses_title_and_region_only() -> None:
    config = {
        "sources": {
            "linkedin": {
                "enabled": True,
                "query_templates": ['site:linkedin.com/jobs/view "{title}" "{location}"'],
            },
            "disabled": {
                "enabled": False,
                "query_templates": ['"{title}" "{location}" "{company}"'],
            },
        }
    }

    queries = ai_web_search.build_queries(
        "Product Owner",
        {"location": "Berlin", "companies": [{"name": "ShouldNotAppear"}]},
        config,
    )

    assert queries == [("linkedin", 'site:linkedin.com/jobs/view "Product Owner" "Berlin"')]
    assert "ShouldNotAppear" not in queries[0][1]


def test_budget_enforces_prompt_and_result_caps() -> None:
    budget = ai_web_search.AIWebSearchBudget(
        max_prompts_per_run=2,
        max_prompts_per_region=1,
        max_results_per_prompt=5,
        max_results_per_region=3,
        max_total_results_per_run=4,
    )

    assert budget.can_prompt("berlin") is True
    budget.record_prompt("berlin")
    assert budget.can_prompt("berlin") is False
    assert budget.can_prompt("oman") is True

    assert budget.remaining_results("berlin") == 3
    budget.record_results("berlin", 3)
    assert budget.remaining_results("berlin") == 0
    assert budget.remaining_results("oman") == 1


def test_fetch_ai_web_search_jobs_respects_caps_and_normalizes(monkeypatch) -> None:
    config = {
        "enabled": True,
        "max_prompts_per_run": 1,
        "max_prompts_per_region": 1,
        "max_results_per_prompt": 2,
        "max_results_per_region": 2,
        "max_total_results_per_run": 2,
        "sources": {
            "linkedin": {
                "enabled": True,
                "query_templates": ['site:linkedin.com/jobs/view "{title}" "{location}"'],
            },
            "stepstone": {
                "enabled": True,
                "query_templates": ['site:stepstone.de/stellenangebote-- "{title}" "{location}"'],
            },
        },
    }
    raw = """
    [
      {
        "title": "Product Owner",
        "company": "TestCo",
        "location": "Berlin",
        "url": "https://www.linkedin.com/jobs/view/123",
        "source": "linkedin",
        "snippet": "Product backlog role",
        "confidence": 0.9
      },
      {
        "title": "Product Owner AI",
        "company": "OtherCo",
        "location": "Berlin",
        "url": "https://www.linkedin.com/jobs/view/456",
        "source": "stepstone",
        "snippet": "AI product role",
        "confidence": 0.8
      }
    ]
    """
    calls = []

    monkeypatch.setattr(ai_web_search, "ai_web_search_config", lambda: config)
    monkeypatch.setattr(ai_web_search, "_load_search_config", lambda: {})
    monkeypatch.setattr(ai_web_search, "_llm_settings", lambda: ("anthropic", "cheap-model", 500))

    def fake_complete(provider, model, user, max_tokens):
        calls.append(user)
        return raw

    monkeypatch.setattr(ai_web_search, "_complete_with_web_search", fake_complete)

    jobs = ai_web_search.fetch_ai_web_search_jobs(
        ["Product Owner"],
        {"berlin": {"location": "Berlin"}},
    )

    assert len(jobs) == 2
    assert len(calls) == 1
    assert "Filtering rules from config/job_hunter.yml" in calls[0]
    assert "Required title families: Product Owner" in calls[0]
    assert "Target location/region: Berlin" in calls[0]
    assert jobs[0]["source"] == "AI web search: linkedin"
    assert jobs[0]["query"] == 'site:linkedin.com/jobs/view "Product Owner" "Berlin"'


def test_fetch_ai_web_search_jobs_filters_irrelevant_results(monkeypatch) -> None:
    config = {
        "enabled": True,
        "max_prompts_per_run": 1,
        "max_prompts_per_region": 1,
        "max_results_per_prompt": 6,
        "max_results_per_region": 6,
        "max_total_results_per_run": 6,
        "min_confidence": 0.7,
        "sources": {
            "greenhouse": {
                "enabled": True,
                "query_templates": ['site:greenhouse.io "{title}" "{location}"'],
            }
        },
    }
    raw = """
    [
      {
        "title": "Product Owner",
        "company": "LiveCo",
        "location": "Berlin",
        "url": "https://job-boards.greenhouse.io/liveco/jobs/123456",
        "snippet": "Open product owner role",
        "confidence": 0.9
      },
      {
        "title": "Applying to Product Owner",
        "company": "ApplyCo",
        "location": "Berlin",
        "url": "https://job-boards.greenhouse.io/applyco/jobs/234567",
        "snippet": "Application shell",
        "confidence": 0.9
      },
      {
        "title": "Product Owner",
        "company": "SearchCo",
        "location": "Berlin",
        "url": "https://job-boards.greenhouse.io/searchco",
        "snippet": "Company listing page, no individual job",
        "confidence": 0.9
      },
      {
        "title": "Product Owner",
        "company": "ClosedCo",
        "location": "Berlin",
        "url": "https://job-boards.greenhouse.io/closedco/jobs/345678",
        "snippet": "This job is no longer available",
        "confidence": 0.9
      },
      {
        "title": "Product Owner",
        "company": "WeakCo",
        "location": "Berlin",
        "url": "https://job-boards.greenhouse.io/weakco/jobs/567890",
        "snippet": "Maybe a product role",
        "confidence": 0.4
      }
    ]
    """

    monkeypatch.setattr(ai_web_search, "ai_web_search_config", lambda: config)
    monkeypatch.setattr(
        ai_web_search,
        "_load_search_config",
        lambda: {"exclusions": {"title_terms": []}},
    )
    monkeypatch.setattr(ai_web_search, "_llm_settings", lambda: ("anthropic", "cheap-model", 500))
    monkeypatch.setattr(ai_web_search, "_complete_with_web_search", lambda *args: raw)

    jobs = ai_web_search.fetch_ai_web_search_jobs(
        ["Product Owner"],
        {"berlin": {"location": "Berlin"}},
    )

    assert [job["company"] for job in jobs] == ["LiveCo"]


def test_build_rule_context_includes_compact_search_config_rules() -> None:
    context = ai_web_search.build_rule_context(
        {
            "exclusions": {
                "companies": ["N26"],
                "title_terms": ["engineer"],
                "languages": ["german"],
                "industries": ["banking"],
            }
        },
        ["Product Owner"],
        {"location": "Berlin"},
    )

    assert "Required title families: Product Owner" in context
    assert "Target location/region: Berlin" in context
    assert "Reject excluded companies: N26" in context
    assert "Reject excluded title terms: engineer" in context
    assert "Reject stale/closed indicators: no longer available" in context
    assert "Reject languages: german" in context
    assert "Reject excluded industries: banking" in context
    assert "Reject URL patterns: linkedin\\.com/jobs/search" in context


def test_provider_secret_is_cached(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(
        ai_web_search,
        "get_secret",
        lambda env_var, required=True: calls.append((env_var, required)) or "secret",
    )
    ai_web_search._SECRET_CACHE.clear()

    assert ai_web_search._provider_secret("anthropic") == "secret"
    assert ai_web_search._provider_secret("anthropic") == "secret"

    assert calls == [("ANTHROPIC_API_KEY", True)]


def test_llm_settings_come_from_job_hunter_config(monkeypatch) -> None:
    monkeypatch.setattr(
        ai_web_search,
        "get_config",
        lambda _name: {
            "llm": {
                "default_provider": "anthropic",
                "models": {"ai_web_search": "configured-search-model"},
                "max_tokens": {"ai_web_search": 777},
            }
        },
    )

    assert ai_web_search._llm_settings() == ("anthropic", "configured-search-model", 777)


def test_anthropic_web_search_client_is_reused(monkeypatch) -> None:
    instances = []

    class FakeAnthropic:
        def __init__(self, api_key) -> None:
            instances.append(api_key)
            self.messages = SimpleNamespace(create=self.create)

        def create(self, **kwargs):
            return SimpleNamespace(content=[SimpleNamespace(type="text", text='[{"title": "Product Owner"}]')])

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=FakeAnthropic))
    monkeypatch.setattr(ai_web_search, "_provider_secret", lambda provider: "cached-key")
    ai_web_search._ANTHROPIC_CLIENTS.clear()

    first = ai_web_search._complete_with_web_search("anthropic", "model", "query 1", 100)
    second = ai_web_search._complete_with_web_search("anthropic", "model", "query 2", 100)

    assert first == '[{"title": "Product Owner"}]'
    assert second == '[{"title": "Product Owner"}]'
    assert instances == ["cached-key"]
