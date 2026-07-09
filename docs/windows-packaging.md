# Windows packaging spike

Status: experimental. PyInstaller `onedir`, console enabled. Not part of release or PyPI workflows.

Build from repository root:

```powershell
uv run --with pyinstaller pyinstaller --noconfirm --clean packaging/windows/job-hunter.spec
```

The bundle includes dashboard HTML, workspace templates, schemas, skills, pywebview, and dynamic LLM provider modules. Playwright Chromium is intentionally not bundled. Company-hunt browser fallback reports the setup action:

```text
playwright install chromium
```

The dashboard uses the installed Microsoft Edge WebView2 Evergreen Runtime through pywebview. Current supported Windows releases normally include it; machines without it must install WebView2 Evergreen.

This spike does not add an installer, signing, a release workflow, or a version change. Build output belongs in temporary `build/` and `dist/` directories and must be deleted after validation.

## Measured spike result

Measured on Windows 11 with Python 3.12.10 and PyInstaller 6.21.0.

First pass found a real bug: frozen `init`/`doctor` raised an unhandled exception setting up
telemetry hooks (a permissions edge case not hit under `uv run` in the dev venv). Fixed in
`job_hunter/workspace/operations.py::install_telemetry` by catching `(OSError, ValueError)`
and returning a non-blocking warning instead. The full matrix below was then re-run against
a **rebuilt** exe to confirm the fix, not just re-read from the first pass:

- Build: successful, ~91s (`uv run --with pyinstaller pyinstaller --noconfirm --clean packaging/windows/job-hunter.spec`)
- `onedir` size: ~259 MB (`dist/job-hunter/`)
- Frozen `--help`: successful, 458 ms
- Frozen `init` (fresh workspace via `job-hunter.exe init <path>`): successful, no telemetry exception — the fix holds
- Frozen `doctor`: all checks pass except `playwright_chromium`, which fails with the expected actionable `playwright install chromium` fix message — proves the "missing browser gives actionable setup, not crash" requirement, not just that the check exists
- Frozen `hunt --region primary --scrape-only` (real network calls, no mocking): completed in 18s, fetched from 8 live job-board sources, wrote 36 rows to a real `outputs/state/jobs.db` — proves DB open/write and the scraping pipeline both work unmodified inside the frozen bundle
- Frozen `dash`: launched and stayed up cleanly (no Python traceback in stderr; only a benign, pre-existing WebView2 teardown log line unrelated to packaging)
- One new gap found during the live `hunt` run: the `jobspy` source's native dependency (`tls-client-64.dll`) is not bundled, so that one source fails with a clear, caught warning and the run continues — no crash, but `jobspy` results are unavailable in a frozen build until that DLL is added to `datas`/`binaries` in the spec
- Config save (via the dashboard Settings UI) was not independently click-tested — no way to drive the native WebView2 window from this environment. Indirect evidence is strong: `config_schema` doctor check passed (proves the bundled JSON schema file and `jsonschema` import both resolve correctly in the frozen build), and the dashboard's Python API (`job_hunter.ux.web.api`, `job_hunter.config.service`) is the same code the `doctor`/`hunt` checks above already exercised successfully — no packaging-specific reason config save would behave differently.

Verdict: **GO for continued spike investment, still NO-GO for release.** The previously-found
blocker is fixed and verified. Remaining before a release decision: bundle or gracefully
degrade the `jobspy` native dependency, and get one real click-through of Settings save in
the frozen dashboard. Nuitka comparison is still not justified — no measured PyInstaller
blocker requires it.

## Re-verified after the GUI-first rewrite (dashboard split, catalogs, diagnostics)

Rebuilt from the updated spec (now also bundling `dashboard.css`/`dashboard.js`,
`config/countries.json`, `config/filters.json`, and `catalog/companies.json` —
none of which existed at the time of the first spike) and re-ran the frozen exe:

- Build: successful (`uv run --with pyinstaller pyinstaller --noconfirm --clean packaging/windows/job-hunter.spec`)
- Frozen `--help`: the removed `dashboard` command is gone from the command list; `dash`, `doctor`, `hunt`, `tailor`, `init`, `update`, `version`, `applications` all present
- Frozen `internal self-test --json` (the new Phase 7 headless smoke test): **all 7 checks pass** — `countries_resource` (249 countries), `filters_resource` (5 career stages, 30 languages), `catalog_resource` (19 companies), `dashboard_assets` (html/css/js all present and non-empty), `workspace_and_config`, `config_save`, `db_open`. This is the strongest evidence yet that the new package resources actually resolve correctly via `importlib.resources` inside a frozen bundle, not just in the dev `.venv`.
- Frozen `init` into a fresh temp directory: successful, same next-steps output as source
- Frozen `doctor --json` against the freshly-initialized workspace: `python_version`, `editable_package`, `docker`, and the config/profile file-presence checks all pass

Not re-verified this pass (same limitation as before): a live click-through of
`dash`'s window (no display automation available in this environment) and a
real `hunt` network run. The `internal self-test` result is a meaningfully
stronger proxy than before for "will the packaged data actually load," since
it's the first frozen-build check that specifically exercises the new
catalog/reference-data resources end-to-end.
