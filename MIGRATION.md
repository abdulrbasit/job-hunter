# CLI migration

Normal user commands are now `init`, `doctor`, `hunt`, `brief`, `tailor`, `dashboard`, `applications`, `update`, and `version`.

- `config check` is part of `doctor`.
- `update-info` is printed by `version`.
- `update-skills` becomes `update --skills-only`.
- `update-workflows` becomes `update --workflows-only`.
- Skill and automation commands move under `job-hunter internal`.
- LLM provider SDKs require `job-hunter-kit[llm]`.

Bundled skills already use new internal paths.
