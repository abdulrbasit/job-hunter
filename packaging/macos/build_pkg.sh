#!/usr/bin/env bash
# Wraps the PyInstaller-built "dist/Job Hunter.app" (packaging/macos/job-hunter.spec)
# into an unsigned .pkg installer via pkgbuild. Unbuilt/untested in this repo's dev
# environment — no macOS hardware available (same limitation docs/macos-packaging.md
# already documents for the .app spike itself). Run this on a real Mac after building
# the .app; signing/notarization are separate follow-up steps, also documented there.
set -euo pipefail

VERSION="${1:?Usage: build_pkg.sh <version>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP="$ROOT/dist/Job Hunter.app"
OUT_DIR="$ROOT/dist-installer"

if [ ! -d "$APP" ]; then
  echo "error: $APP not found — build it first:" >&2
  echo "  uv run --with pyinstaller pyinstaller --noconfirm --clean packaging/macos/job-hunter.spec" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
pkgbuild \
  --install-location /Applications \
  --component "$APP" \
  --version "$VERSION" \
  --identifier com.jobhunterkit.jobhunter \
  "$OUT_DIR/Job-Hunter-$VERSION.pkg"

echo "Unsigned package written to $OUT_DIR/Job-Hunter-$VERSION.pkg"
echo "Unsigned — first launch needs right-click > Open. See docs/macos-packaging.md for signing/notarization."
