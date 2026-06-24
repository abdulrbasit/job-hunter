# Add / Remove Region

Single responsibility: safely add or remove one region from `config/job_hunter.yml`.

## Token Rules

- Read only the target region block and global anchors needed for the edit.
- Print the changed region key, not the full config.

## Steps — Add

1. Parse `$ARGUMENTS`. If the first word is `add`, the region name follows (e.g., `add amsterdam`).
   If arguments are empty, ask: "Add or remove? And what region name?"

2. Read `config/job_hunter.yml` to confirm the region key does not already exist.

3. Determine region metadata via web search:
   - Country code (ISO 3166-1 alpha-2)
   - Primary language (use `search_lang: en` unless the market is non-English)

4. Build the new region block following the exact structure of an existing region in the file
   (allowed keys: `enabled`, `primary`, `country`, `search_lang`, `location`, `description`).
   Set `primary: false`.

5. Append the new region block to `config/job_hunter.yml`.

6. Print: `Region '<name>' added. Run job-hunter hunt --region <name> to test.`

## Steps — Remove

1. Parse `$ARGUMENTS`. If the first word is `remove`, the region key follows.

2. Read `config/job_hunter.yml`. Confirm the region key exists.

3. Ask: "Remove region '<name>'? Reply yes to confirm."

4. On confirmation, delete the region's YAML block from the file. Leave all other regions untouched.

5. Print: `Region '<name>' removed.`

## Source activation by country code

New job board sources activate automatically when a region's `country` key matches their guard.

| Country | Sources activated |
|---|---|
| `SG` | MyCareersFuture, JobStreet |
| `MY`, `ID`, `PH`, `VN` | JobStreet |
| `CA` | Job Bank Canada |
| `AE`, `SA`, `QA`, `KW`, `BH`, `OM` | GulfTalent |
| Any | Careerjet (when affid configured), Working Nomads (remote-only) |

## Rules

- Never edit global config keys.
- Never touch other existing regions.
- Only operate on the single region named in `$ARGUMENTS`.
