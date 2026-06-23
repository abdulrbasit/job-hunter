# Search

Search for more job postings. After completing, control returns to the calling workflow; caller must immediately continue the next step.

## Approach

Run 5 web searches per title per region using ATS-specific site queries. Do not use configured company lists or career URLs; query by title and location only.

### Query Templates

For each job title and region, run:

```
site:boards.greenhouse.io "<title>" "<location>"
site:jobs.lever.co OR site:ashbyhq.com "<title>" "<location>"
site:jobs.smartrecruiters.com OR site:workdayjobs.com "<title>" "<location>"
site:apply.workable.com "<title>" "<location>"
"<title>" "<location>" job apply -site:linkedin.com -site:glassdoor.com
```

## Deduplication

Before adding any URL, check:
- `outputs/state/discovered_urls.yml` for persistent URL dedup.
- `exclusions.companies` in `config/job_hunter.yml`.
- `exclusions.title_terms` in `config/job_hunter.yml`.
- Code-owned listing URL patterns, which remove search/category pages such as LinkedIn collection URLs.
- Code-owned stale indicators, which remove expired or closed postings.

Skip listing/search/category page URLs. Only add direct job posting URLs.

## Limits

Read `search.llm_search.max_results_per_run` from `config/job_hunter.yml`. Stop when that limit is reached across all queries.

## Output

Append new job URLs to the candidate queue for the calling workflow to process. Do not score or tailor; this skill only finds URLs.
