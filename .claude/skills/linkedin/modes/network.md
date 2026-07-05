# LinkedIn Network

Single responsibility: find relevant public contacts and draft connection requests.

Run `job-hunter internal telemetry-mark --phase linkedin_network --skill linkedin_network --state start`.
Telemetry failure is non-blocking and must not be printed.

## Token Rules

- Start with `job-hunter internal agent-context outreach-context` → `writing_rules.outreach`.
- Then `job-hunter internal agent-context linkedin-weekly`.
- Prioritize companies with active tailored jobs from the compact context.
- Search at most five companies and print only the output path.

## Steps

1. Pick target companies from active weekly jobs, then `profile/career_context.md` targets if needed.
2. Search public LinkedIn profile pages for PM/product leaders and recruiting contacts.
3. Deduplicate against `outputs/linkedin/networking.md`.
4. Append up to 10 contacts and request drafts.
5. Do not commit here; `/job-hunter finalize` handles reviewed `outputs/linkedin/` drafts.

## Rules

- Apply every rule in `writing_rules.outreach` exactly — universal (code-owned), wins over any
  conflicting `career_context.md` preference.

## Output

Run `job-hunter internal telemetry-mark --phase linkedin_network --state end` before printing.

```
Networking queue updated -> outputs/linkedin/networking.md
Contacts added: N
```
