#!/usr/bin/env bash
# One-shot setup for the MATB military aviation research platform.
#
# Usage (after cloning):
#   git clone https://github.com/strikerdlm/MATB
#   cd MATB
#   bash setup.sh
#
# What this does:
#   1. Creates a Python venv at ./.venv with repository dependencies
#   2. Installs military aviation assets into the tracked, qualified OpenMATB
#      runtime (or an explicitly selected runtime that passes capability checks)
#   3. When MATB_INSTALL_SUAS=1, installs the native Linux/headless sUAS console
#
# After setup, run a scenario:
#   Linux/headless:  Xvfb :100 -screen 0 1920x1080x24 &
#                    cd "$OPENMATB_DIR" && DISPLAY=:100 python main.py
#   Windows/macOS:   cd "$OPENMATB_DIR" && python main.py

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MATB_VENV="${MATB_VENV:-$SCRIPT_DIR/.venv}"
OPENMATB_DIR="${OPENMATB_DIR:-$SCRIPT_DIR/openmatb}"

echo "==> Creating venv at $MATB_VENV ..."
python3 -m venv "$MATB_VENV"

echo "==> Installing repository dependencies..."
"$MATB_VENV/bin/pip" install --quiet --upgrade pip
"$MATB_VENV/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"

echo "==> Verifying OpenMATB capabilities and installing military aviation assets..."
"$MATB_VENV/bin/python" "$SCRIPT_DIR/install_to_openmatb.py" "$OPENMATB_DIR"

if [ "${MATB_INSTALL_SUAS:-0}" = "1" ]; then
    echo "==> Installing native offline sUAS console..."
    MATB_VENV="$MATB_VENV" bash "$SCRIPT_DIR/scripts/install_suas.sh"
fi

echo ""
echo "Setup complete."
echo ""
echo "To run a scenario (Linux/headless):"
echo "  Xvfb :100 -screen 0 1920x1080x24 &"
echo "  cd \"$OPENMATB_DIR\" && DISPLAY=:100 python main.py"
echo ""
echo "To run a scenario (Windows / macOS):"
echo "  cd \"$OPENMATB_DIR\" && python main.py"
echo ""
echo "To run tests:"
echo "  cd $SCRIPT_DIR"
echo "  $MATB_VENV/bin/python -m pytest tests/ -v"
