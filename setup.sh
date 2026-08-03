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
#   2. Optionally installs military aviation assets into an external OpenMATB
#      checkout when OPENMATB_DIR=/path/to/openmatb is set
#   3. When MATB_INSTALL_SUAS=1, installs the native Linux/headless sUAS console
#
# After setup, run a scenario:
#   Linux/headless:  Xvfb :100 -screen 0 1920x1080x24 &
#                    cd "$OPENMATB_DIR" && DISPLAY=:100 python main.py
#   Windows/macOS:   cd "$OPENMATB_DIR" && python main.py

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MATB_VENV="${MATB_VENV:-$SCRIPT_DIR/.venv}"
OPENMATB_DIR="${OPENMATB_DIR:-}"

echo "==> Creating venv at $MATB_VENV ..."
python3 -m venv "$MATB_VENV"

echo "==> Installing repository dependencies..."
"$MATB_VENV/bin/pip" install --quiet --upgrade pip
"$MATB_VENV/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"

if [ -n "$OPENMATB_DIR" ]; then
    echo "==> Installing military aviation assets into external OpenMATB..."
    "$MATB_VENV/bin/python" "$SCRIPT_DIR/install_to_openmatb.py" "$OPENMATB_DIR"
else
    echo "==> Skipping OpenMATB asset install."
    echo "    The broken vendored openmatb submodule was removed."
    echo "    Set OPENMATB_DIR=/path/to/openmatb and rerun install_to_openmatb.py when needed."
fi

if [ "${MATB_INSTALL_SUAS:-0}" = "1" ]; then
    echo "==> Installing native offline sUAS console..."
    MATB_VENV="$MATB_VENV" bash "$SCRIPT_DIR/scripts/install_suas.sh"
fi

echo ""
echo "Setup complete."
echo ""
echo "To run a scenario (Linux/headless):"
echo "  Xvfb :100 -screen 0 1920x1080x24 &"
echo "  cd \"\$OPENMATB_DIR\" && DISPLAY=:100 python main.py"
echo ""
echo "To run a scenario (Windows / macOS):"
echo "  cd \"\$OPENMATB_DIR\" && python main.py"
echo ""
echo "To run tests:"
echo "  cd $SCRIPT_DIR"
echo "  $MATB_VENV/bin/python -m pytest tests/ -v"
