# macOS packaging spike

Status: experimental, **unbuilt**. `packaging/macos/job-hunter.spec` exists and
mirrors the structurally-verified Windows spike (same `datas`/`hiddenimports`,
`console=False`, wrapped in a `BUNDLE()` for a `.app`), but has not actually
been run through PyInstaller — this environment has no macOS machine. Not part
of release or PyPI workflows.

Build from repository root, on macOS:

```bash
uv run --with pyinstaller pyinstaller --noconfirm --clean packaging/macos/job-hunter.spec
```

The bundle includes dashboard HTML/CSS/JS, workspace templates, schemas,
skills, the country/filter/company catalogs, pywebview, and dynamic LLM
provider modules — the same asset list as Windows. Playwright Chromium is
intentionally not bundled; company-hunt browser fallback reports the setup
action (`playwright install chromium`).

## Not yet done (needs real macOS hardware + signing credentials)

- **Hardened-runtime signing**: `codesign --deep --force --options runtime
  --sign "<Developer ID>" "dist/Job Hunter.app"` — needs an actual Apple
  Developer ID certificate.
- **Apple notarization**: `xcrun notarytool submit` + `xcrun stapler staple`
  — needs an App Store Connect API key.
- **Signed DMG**: `hdiutil create` wrapping the notarized `.app`, then signing
  the DMG itself.
- A frozen smoke test equivalent to the Windows one (`internal self-test
  --json` against the built `.app`'s embedded Python) — the spec is written
  to support it, but running it requires the hardware this environment lacks.

Per this repo's rules: **do not** publish, bump the version, or trigger a
release from this spike without separate, explicit user authorization —
unsigned artifacts may exist for internal CI only.

## Bundling fix carried over from the Windows spike

The `datas` list here mirrored Windows/Linux exactly, so it inherited the
same bug: `catalog/companies.json` no longer exists (company data moved to
`job_hunter/companies/data/*.jsonl`; location data is a separate
`job_hunter/locations/data/` tree). Fixed identically — bundles all four
`job_hunter/catalog/*.json` files plus `job_hunter/companies/data/` and
`job_hunter/locations/data/`. Unverified on real macOS hardware (same
limitation as the rest of this doc), but the fix is mechanical and
structurally identical to the Windows build, which was rebuilt and
re-verified after this change (see docs/windows-packaging.md).

## Installer layer: pkgbuild

`packaging/macos/build_pkg.sh <version>` wraps the built `dist/Job
Hunter.app` into an unsigned `.pkg` via `pkgbuild`. Also unbuilt/untested
here — needs the same real Mac hardware called out above.
`.github/workflows/release.yml`'s `build-installers` job runs it on a
`macos-latest` runner, which will be the first real validation.

```bash
uv run --with pyinstaller pyinstaller --noconfirm --clean packaging/macos/job-hunter.spec
bash packaging/macos/build_pkg.sh 0.25
```

Unsigned, so first launch needs right-click (Control-click) the app →
**Open** → **Open**, instead of a normal double-click, until signing and
notarization (above) are done.
