# Search

Find extra direct job postings when normal discovery is thin.

1. Run `job-hunter agent-context llm-search-config`.
2. Stop when disabled or trigger threshold is met.
3. Search enabled regions and effective titles. Stop at `max_results_per_run`.
4. Verify each URL is a live, specific job posting. Reject exact excluded companies,
   exact excluded title terms, stale pages, listing pages, and clear location/language failures.
   Do not semantically reject industries here; Screen owns that judgment.
5. Write `outputs/candidates/<date>_llm_search_candidates.json`:

```json
{"jobs": [{"title": "", "company": "", "url": "", "location": "",
           "region": "", "snippet": "", "source": "web-search"}]}
```

6. Build the bounded queue:

```bash
job-hunter agent-context candidates \
  --source outputs/candidates/<date>_llm_search_candidates.json \
  --write-queue outputs/state/llm_search_queue.json
```

Return counts and paths only. Caller runs normal hard screen then semantic Screen.
Control returns to the calling workflow; caller immediately continues.
