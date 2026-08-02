#!/usr/bin/env bash
# Install the native, offline-capable sUAS console without global packages.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/suas_processes.sh
source "$SCRIPT_DIR/lib/suas_processes.sh"

require_command python3
require_command node
require_command npm

python_version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
python_major="${python_version%%.*}"
python_minor="${python_version#*.}"
if (( python_major < 3 || (python_major == 3 && python_minor < 12) )); then
  echo "Python 3.12 or newer is required (found $python_version)" >&2
  exit 1
fi
node_major="$(node --version | sed 's/^v//' | cut -d. -f1)"
if [[ ! "$node_major" =~ ^[0-9]+$ ]] || (( node_major < 20 )); then
  echo "Node.js 20 or newer is required" >&2
  exit 1
fi

VENV="${MATB_VENV:-$REPO_ROOT/.venv}"
if [[ -z "$VENV" ]]; then
  echo "MATB_VENV must not be empty" >&2
  exit 1
fi
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r "$REPO_ROOT/requirements-dev.txt"

pushd "$REPO_ROOT/webui/frontend" >/dev/null
npm ci
npm run build
popd >/dev/null

"$VENV/bin/python" -m pytest "$REPO_ROOT/tests/suas" -q
pushd "$REPO_ROOT/webui/backend" >/dev/null
"$VENV/bin/python" -m pytest -q
popd >/dev/null

cat <<EOF

sUAS console installed for offline Linux use.
Launch with:
  bash "$REPO_ROOT/scripts/run_suas.sh"
EOF
