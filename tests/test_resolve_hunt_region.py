from job_hunter.pipeline import resolve_hunt_region as resolver

SCHEDULES = [
    "0 4 * * 1-5",
    "0 5 * * 1,3,5",
    "0 6 * * 1,3,5",
]


def _config(regions):
    return {"regions": regions}


def test_scheduled_primary_slot_uses_primary_region() -> None:
    config = _config(
        {
            "berlin": {"enabled": True, "primary": True, "country": "DE"},
            "oman": {"enabled": True, "country": "OM"},
        }
    )

    status, outputs = resolver.resolve_hunt_region(config, "schedule", SCHEDULES[0], "all", SCHEDULES)

    assert status == 0
    assert outputs["should_run"] == "true"
    assert outputs["region"] == "berlin"
    assert outputs["arg"] == "--region berlin"


def test_scheduled_secondary_slots_follow_config_order() -> None:
    config = _config(
        {
            "berlin": {"enabled": True, "primary": True, "country": "DE"},
            "malaysia": {"enabled": True, "country": "MY"},
            "indonesia": {"enabled": True, "country": "ID"},
        }
    )

    _, first_secondary = resolver.resolve_hunt_region(config, "schedule", SCHEDULES[1], "all", SCHEDULES)
    _, second_secondary = resolver.resolve_hunt_region(config, "schedule", SCHEDULES[2], "all", SCHEDULES)

    assert first_secondary["region"] == "malaysia"
    assert second_secondary["region"] == "indonesia"


def test_scheduled_empty_template_config_skips_cleanly() -> None:
    config = _config(
        {
            "primary": {"enabled": False, "primary": True, "country": "DE"},
        }
    )

    status, outputs = resolver.resolve_hunt_region(config, "schedule", SCHEDULES[0], "all", SCHEDULES)

    assert status == 0
    assert outputs["should_run"] == "false"
    assert "No enabled region" in outputs["reason"]


def test_manual_all_preserves_all_region_behavior() -> None:
    config = _config(
        {
            "berlin": {"enabled": True, "country": "DE"},
        }
    )

    status, outputs = resolver.resolve_hunt_region(config, "workflow_dispatch", "", "all", SCHEDULES)

    assert status == 0
    assert outputs == {
        "should_run": "true",
        "region": "",
        "arg": "",
        "label": "all",
    }


def test_manual_unknown_region_errors_with_enabled_regions() -> None:
    config = _config(
        {
            "berlin": {"enabled": True, "country": "DE"},
            "disabled": {"enabled": False, "country": "DE"},
        }
    )

    status, outputs = resolver.resolve_hunt_region(config, "workflow_dispatch", "", "missing", SCHEDULES)

    assert status == 1
    assert "missing" in outputs["error"]
    enabled_list = outputs["error"].split("Enabled regions: ", 1)[1]
    assert enabled_list == "berlin"


def test_enabled_regions_do_not_require_company_lists() -> None:
    config = _config(
        {
            "berlin": {"enabled": True, "primary": True, "country": "DE"},
            "disabled": {"enabled": False, "country": "DE"},
        }
    )

    assert [name for name, _region in resolver.enabled_regions(config)] == ["berlin"]


def test_schedules_are_read_from_github_workflow(monkeypatch, tmp_path) -> None:
    workflow = tmp_path / ".github" / "workflows" / "find-jobs.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        'on:\n  schedule:\n    - cron: "0 4 * * *"\n    - cron: "30 5 * * *"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert resolver._schedules_from_workflow() == ["0 4 * * *", "30 5 * * *"]
