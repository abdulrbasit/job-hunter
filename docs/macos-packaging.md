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
