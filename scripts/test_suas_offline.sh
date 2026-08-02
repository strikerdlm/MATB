#!/usr/bin/env bash
# Static/runtime audit for installations that must remain offline and non-kinetic.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMP_ROOT="$(mktemp -d)"
cleanup() { rm -rf -- "$TEMP_ROOT"; }
trap cleanup EXIT INT TERM

source_paths=(
  "$REPO_ROOT/matb_integration/suas"
  "$REPO_ROOT/webui/backend/app/simulation_runtime.py"
  "$REPO_ROOT/webui/backend/app/simulation_schemas.py"
  "$REPO_ROOT/webui/backend/app/routers/simulation.py"
  "$REPO_ROOT/webui/frontend/src/lib/simulation"
  "$REPO_ROOT/webui/frontend/src/components/mission"
)
if rg -n --glob '*.py' --glob '*.ts' --glob '*.tsx' --glob '!*.test.ts' --glob '!*.test.tsx' 'https?://' "${source_paths[@]}" | rg -v 'localhost|127\.0\.0\.1' ; then
  echo "offline audit found a non-local network dependency" >&2
  exit 1
fi
if rg -n -i --glob '*.py' --glob '*.ts' --glob '*.tsx' --glob '!*.test.ts' --glob '!*.test.tsx' 'WEAPON|ENGAGE|FIRE|STRIKE|TARGET_ASSIGN|DAMAGE' "${source_paths[@]}" ; then
  echo "offline audit found a kinetic command identifier" >&2
  exit 1
fi

PYTHON_BIN="${MATB_PYTHON:-python3}"
"$PYTHON_BIN" -m pytest "$REPO_ROOT/tests/suas/test_scenario_schema.py" -q
if [[ -d "$REPO_ROOT/webui/frontend/node_modules" ]]; then
  (cd "$REPO_ROOT/webui/frontend" && npm run build >/dev/null)
fi
echo "sUAS offline audit passed"
