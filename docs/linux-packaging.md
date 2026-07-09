# Linux packaging spike

Status: experimental, **unbuilt**. `packaging/linux/job-hunter.spec` exists
and mirrors the structurally-verified Windows spike (same `datas`/
`hiddenimports`, `console=False`), plus `packaging/linux/job-hunter.desktop`
for the AppImage's desktop metadata — but neither has actually been run; this
environment has no Linux machine. Not part of release or PyPI workflows.

Build from repository root, on Linux:

```bash
uv run --with pyinstaller pyinstaller --noconfirm --clean packaging/linux/job-hunter.spec
```

The bundle includes dashboard HTML/CSS/JS, workspace templates, schemas,
skills, the country/filter/company catalogs, pywebview, and dynamic LLM
provider modules — the same asset list as Windows. Playwright Chromium is
intentionally not bundled; company-hunt browser fallback reports the setup
action (`playwright install chromium`).

## Not yet done (needs a real Linux machine + appimagetool + signing key)

- **AppImage wrapping**: PyInstaller only produces the `onedir` bundle in
  `dist/job-hunter/`; turning that into `Job-Hunter-x86_64.AppImage` is a
  separate step with [`appimagetool`](https://github.com/AppImage/appimagetool),
  using `packaging/linux/job-hunter.desktop` and an icon (not yet created).
- **GPG-signed artifact/checksum**: `gpg --detach-sign` on the finished
  AppImage, plus a signed `sha256sum` — needs a real signing key.
- A frozen smoke test equivalent to the Windows one (`internal self-test
  --json` against the built onedir bundle) — the spec is written to support
  it, but running it requires the hardware this environment lacks.

Per this repo's rules: **do not** publish, bump the version, or trigger a
release from this spike without separate, explicit user authorization —
unsigned artifacts may exist for internal CI only.
