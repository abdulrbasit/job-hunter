from __future__ import annotations

ATS_DISCOVERY_API_TIMEOUT = 8
CAREER_PAGE_SNIPPET_CHARS = 400
JOB_BOARD_SNIPPET_CHARS = 1000
LLM_REPAIR_INPUT_CHARS = 2000
DEFAULT_BATCH_SIZE = 15
MIN_FULL_JD_SNIPPET_CHARS = 300
VALIDATION_SNIPPET_CHARS = 2000

# Per-region/per-source result target signal (SearchParams.max_results), not a page count.
# Paged adapters derive their own page count from this via source_config.pages_for_max_results.
DEFAULT_STANDARD_MAX_RESULTS = 50
DEFAULT_BACKFILL_MAX_RESULTS = 150
MAX_SAFE_PAGES_PER_SOURCE = 5
