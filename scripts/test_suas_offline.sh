#!/usr/bin/env bash
# Static/runtime audit for installations that must remain offline and non-kinetic.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMP_ROOT="$(mktemp -d)"
launcher_pid=""
cleanup() {
  if [[ "$launcher_pid" =~ ^[0-9]+$ ]]; then
    kill -TERM -- "$launcher_pid" 2>/dev/null || true
    wait "$launcher_pid" 2>/dev/null || true
  fi
  rm -rf -- "$TEMP_ROOT"
}
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
"$PYTHON_BIN" -m matb_integration.suas.cli validate "$REPO_ROOT/scenarios/suas/reference_area_search.yaml" >/dev/null
"$PYTHON_BIN" -m pytest "$REPO_ROOT/tests/suas/test_scenario_schema.py" -q

"$PYTHON_BIN" -m matb_integration.suas.cli record \
  "$REPO_ROOT/scenarios/suas/reference_area_search.yaml" \
  --block HIGH --ticks 30 --session-id offline-high \
  --output "$TEMP_ROOT/high-run" >/dev/null
"$PYTHON_BIN" -m matb_integration.suas.cli verify "$TEMP_ROOT/high-run" >/dev/null

if [[ -d "$REPO_ROOT/webui/frontend/node_modules" ]]; then
  (cd "$REPO_ROOT/webui/frontend" && NEXT_PUBLIC_API_URL=http://127.0.0.1:9 API_URL=http://127.0.0.1:9 npm run build >/dev/null)
fi

launcher_venv=""
if [[ -n "${MATB_VENV:-}" && -x "${MATB_VENV}/bin/python" ]]; then
  launcher_venv="$MATB_VENV"
elif [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  launcher_venv="$REPO_ROOT/.venv"
fi
if [[ -n "$launcher_venv" && -x "$REPO_ROOT/webui/frontend/node_modules/.bin/next" ]]; then
  launcher_data="$TEMP_ROOT/launcher-data"
  MATB_VENV="$launcher_venv" bash "$REPO_ROOT/scripts/run_suas.sh" \
    --backend-port 18080 --frontend-port 13180 --data-dir "$launcher_data" \
    >"$TEMP_ROOT/launcher.log" 2>&1 &
  launcher_pid=$!
  ready=0
  for _ in {1..60}; do
    if curl --fail --silent --max-time 1 http://127.0.0.1:18080/health >/dev/null \
      && curl --fail --silent --max-time 1 http://127.0.0.1:13180/mission/setup >/dev/null; then
      ready=1
      break
    fi
    sleep 0.2
  done
  if (( ready != 1 )); then
    echo "offline launcher health check failed" >&2
    sed -n '1,160p' "$TEMP_ROOT/launcher.log" >&2 || true
    exit 1
  fi
  kill -TERM -- "$launcher_pid" 2>/dev/null || true
  wait "$launcher_pid" 2>/dev/null || true
  launcher_pid=""
fi
echo "sUAS offline audit passed"
