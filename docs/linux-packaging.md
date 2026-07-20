# Linux packaging spike

Status: experimental, **built and smoke-tested** (in a `python:3.12-slim`
Docker container on Windows via Docker Desktop's Linux engine — not native
Linux hardware, but a real Linux userspace, not emulation). Not part of
release or PyPI workflows.

Build from repository root, on Linux (or in a Linux container):

```bash
uv run --with pyinstaller pyinstaller --noconfirm --clean packaging/linux/job-hunter.spec
```

The bundle includes dashboard HTML/CSS/JS, workspace templates, schemas,
skills, the country/filter/company catalogs, pywebview, and dynamic LLM
provider modules — the same asset list as Windows. Playwright Chromium is
intentionally not bundled; company-hunt browser fallback reports the setup
action (`playwright install chromium`).

## System packages pywebview needs on Linux

`pywebview`'s Linux backend is GTK+WebKit2GTK, which needs system packages
beyond what `pip install pywebview[gtk]` alone provides — discovered by
actually building this spike, not assumed:

```bash
apt-get install -y build-essential pkg-config libcairo2-dev \
  libgirepository1.0-dev gir1.2-gtk-3.0 gir1.2-webkit2-4.1 \
  python3-gi python3-gi-cairo gcc
pip install "pywebview[gtk]"
```

Without these, `import webview` fails at install/build time, before
PyInstaller ever runs. A `msvcrt`/`user32` ctypes-not-found warning during
the PyInstaller build is expected and harmless (Windows-only libraries
referenced by a cross-platform dependency; irrelevant on Linux).

## Verified spike result

Built inside a `python:3.12-slim` (Debian 13/trixie) container, repo mounted
read-only, GTK deps installed as above:

- Build: successful (`pyinstaller --noconfirm --clean packaging/linux/job-hunter.spec`)
- Frozen `--help`: same command list as Windows (`dash`, `doctor`, `hunt`, `tailor`, `init`, `update`, `version`, `applications` — no `dashboard`)
- Frozen `internal self-test --json`: **all 7 checks pass** — `countries_resource` (249), `filters_resource` (5 career stages, 30 languages), `catalog_resource` (19 companies), `dashboard_assets`, `workspace_and_config`, `config_save`, `db_open`
- Frozen `init` into `/tmp/linux-test-ws`: successful, same next-steps output as Windows/source
- Frozen `doctor --json` against the fresh workspace: `python_version` (3.12.13), `editable_package`, and `docker` checks all pass

Not verified: a live click-through of `dash`'s window (no display/X11 forwarding
in the container) and AppImage wrapping itself (a separate step after
PyInstaller, not exercised here).

## Not yet done (needs appimagetool + a signing key)

- **AppImage wrapping**: PyInstaller only produces the `onedir` bundle in
  `dist/job-hunter/`; turning that into `Job-Hunter-x86_64.AppImage` is a
  separate step with [`appimagetool`](https://github.com/AppImage/appimagetool),
  using `packaging/linux/job-hunter.desktop` and an icon (not yet created).
- **GPG-signed artifact/checksum**: `gpg --detach-sign` on the finished
  AppImage, plus a signed `sha256sum` — needs a real signing key.

Per this repo's rules: **do not** publish, bump the version, or trigger a
release from this spike without separate, explicit user authorization —
unsigned artifacts may exist for internal CI only.

## Bundling fix

Same `catalog/companies.json`-doesn't-exist bug as Windows/macOS (see
docs/windows-packaging.md) — fixed identically here: all four
`job_hunter/catalog/*.json` files plus `job_hunter/companies/data/` and
`job_hunter/locations/data/` are now bundled.

## Install layer: bootstrap script, not the AppImage/PyInstaller spike

Linux keeps `uv tool install` as the primary install path — the PyInstaller
spike above is not wired into a shipped installer. `packaging/linux/install.sh`
just automates the manual steps: installs `uv` if missing, runs `uv tool
install job-hunter-kit`, registers a `~/.local/share/applications/job-hunter.desktop`
launcher (reusing `packaging/linux/job-hunter.desktop`'s content), and opens
the dashboard.

```bash
curl -fsSL https://raw.githubusercontent.com/abdulrbasit/job-hunter/main/packaging/linux/install.sh | sh
```

`.github/workflows/release.yml` attaches this script to each GitHub Release
so the URL above always resolves to the version matching `main` at release
time. AppImage wrapping of the PyInstaller spike (below) remains a possible
future layer, not built now.
