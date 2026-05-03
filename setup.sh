#!/usr/bin/env bash
# One-shot setup for the MATB military aviation research platform.
#
# Usage (after cloning):
#   git clone --recurse-submodules https://github.com/strikerdlm/MATB
#   cd MATB
#   bash setup.sh
#
# What this does:
#   1. Ensures the openmatb submodule is initialised
#   2. Creates a Python venv at ./openmatb/.venv with all dependencies
#   3. Installs military aviation assets (questionnaires + scenarios) into openmatb/includes/
#
# After setup, run a scenario:
#   Linux/headless:  Xvfb :100 -screen 0 1920x1080x24 &
#                    cd openmatb && DISPLAY=:100 .venv/bin/python main.py
#   Windows/macOS:   cd openmatb && python main.py

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENMATB_DIR="$SCRIPT_DIR/openmatb"

echo "==> Checking submodule..."
git -C "$SCRIPT_DIR" submodule update --init --recursive

if [ ! -f "$OPENMATB_DIR/main.py" ]; then
    echo "ERROR: openmatb/main.py not found. Submodule init may have failed."
    exit 1
fi

echo "==> Creating venv at openmatb/.venv ..."
python3 -m venv "$OPENMATB_DIR/.venv"

echo "==> Installing dependencies..."
"$OPENMATB_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$OPENMATB_DIR/.venv/bin/pip" install --quiet \
    "pyglet>=2.1.0,<3.0.0" \
    "pylsl>=1.16.1" \
    "rstr==3.1.0" \
    "rich>=13.7.0" \
    "pydantic>=2.5.0" \
    "pytest>=7.4.0"

echo "==> Installing military aviation assets into OpenMATB..."
python3 "$SCRIPT_DIR/install_to_openmatb.py" "$OPENMATB_DIR"

echo ""
echo "Setup complete."
echo ""
echo "To run a scenario (Linux/headless):"
echo "  Xvfb :100 -screen 0 1920x1080x24 &"
echo "  cd openmatb && DISPLAY=:100 .venv/bin/python main.py"
echo ""
echo "To run a scenario (Windows / macOS):"
echo "  cd openmatb && .venv/Scripts/python main.py   # Windows"
echo "  cd openmatb && .venv/bin/python main.py       # macOS"
echo ""
echo "To run tests:"
echo "  cd $SCRIPT_DIR"
echo "  $OPENMATB_DIR/.venv/bin/python -m pytest tests/ -v"
