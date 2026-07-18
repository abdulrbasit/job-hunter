# Research

Write concise company research for one imported job.

Slug: `$ARGUMENTS`

**Preconditions:** `outputs/jobs/<slug>/` must exist. If missing, stop and print: "No job
folder for `<slug>` — run `/job-hunter one <url>` or `/job-hunter batch` first."

1. Run `job-hunter internal telemetry-mark --phase research --skill research --job <slug> --state start`, then
   `job-hunter internal agent-context score --mode full --job <slug>`.
2. Run at most three targeted web searches: product/business, role challenge, recent signal.
3. Write `outputs/jobs/<slug>/company_research.md` with:
   What they build, Relevant to this role, Recent signal, Cover-letter hook, Sources.

Keep under 250 words. Cite source links. Write “No data found” when evidence is thin.
Do not score, tailor, or mutate workflow state.
Run `job-hunter internal telemetry-mark --phase research --state end` after writing.
Telemetry marker failures are non-blocking.

Control returns to the calling workflow; caller immediately continues.
