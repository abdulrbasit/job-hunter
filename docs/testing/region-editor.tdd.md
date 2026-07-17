# Region editor fix — TDD evidence

## User journeys

- Existing legacy regions open with the correct City, Country, or Remote scope.
- Normal region editing shows only Type, Country, and City choices.
- City selection uses one searchable control and stores a canonical package ID.
- Guided save folds legacy exclusions into scalar filters without losing values.

## RED evidence

`uv run pytest tests/test_locations.py::test_legacy_remote_and_country_regions_infer_non_city_scopes tests/test_web_api.py::test_region_editor_keeps_only_location_choices_visible_by_default -q --tb=short`

- 2 failed: legacy remote/country scopes remained unresolved; compact editor
  markup was absent.

`uv run pytest tests/test_web_api.py::test_guided_form_round_trips_legacy_remote_country_and_city_regions -q --tb=short`

- 1 failed: guided save retained removed top-level `exclusions` and schema
  validation rejected the save.

## GREEN guarantees

| Guarantee | Test |
|---|---|
| Legacy `remote Germany` becomes `remote_country` | `test_legacy_remote_and_country_regions_infer_non_city_scopes` |
| Country names become country scopes, not empty cities | `test_legacy_remote_and_country_regions_infer_non_city_scopes` |
| Compact card hides internal metadata under Advanced | `test_region_editor_keeps_only_location_choices_visible_by_default` |
| One searchable city input replaces duplicate search/select controls | `test_region_editor_keeps_only_location_choices_visible_by_default` |
| Exact reported workspace shapes round-trip through guided save | `test_guided_form_round_trips_legacy_remote_country_and_city_regions` |
| Legacy exclusions become scalar filters during explicit guided save | `test_guided_form_round_trips_legacy_remote_country_and_city_regions` |

Live in-app browser control was unavailable during this run. Dashboard DOM/API
tests, JavaScript syntax validation, and a read-only projection of the reported
workspace provide the UI and data-mapping evidence.

## Final validation

- Reported workspace projection: all eight regions resolved to intended scopes
  and canonical city IDs; config remained untouched.
- Focused dashboard/location/config/assembly suite: 222 passed.
- Full suite: 1,474 passed; coverage: 86.57%.
- Ruff format, Ruff lint, `ty check`, and `node --check`: passed.
