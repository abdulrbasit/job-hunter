#!/usr/bin/env bash
# One-line bootstrap install for job-hunter-kit on Linux: installs uv if missing,
# installs job-hunter-kit as a uv tool, registers a .desktop launcher, and opens
# the dashboard. Linux keeps `uv tool install` as the primary install path (Layer 2
# native installers are Windows/macOS-only) — this script just removes the remaining
# manual steps.
#
#   curl -fsSL https://raw.githubusercontent.com/abdulrbasit/job-hunter/main/packaging/linux/install.sh | sh
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "Installing job-hunter-kit..."
uv tool install job-hunter-kit
uv tool update-shell

BIN="$(command -v job-hunter || echo "$HOME/.local/bin/job-hunter")"
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
cat > "$APPS_DIR/job-hunter.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Job Hunter
Comment=Autonomous job search assistant
Exec=$BIN dash
Icon=job-hunter
Terminal=false
Categories=Office;Utility;
EOF

echo "Installed. Opening the dashboard..."
nohup "$BIN" dash >/dev/null 2>&1 &
disown
echo "Job Hunter is starting. Next time, launch it from your applications menu or run: job-hunter dash"
