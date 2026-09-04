#!/usr/bin/env bash
# Launch the built native sUAS console on localhost without Docker or X11.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/suas_processes.sh
source "$SCRIPT_DIR/lib/suas_processes.sh"

backend_port=8000
frontend_port=3100
backend_bind=127.0.0.1
frontend_bind=127.0.0.1
data_dir="${MATB_DATA_ROOT:-$REPO_ROOT/var/suas}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Start the offline sUAS operator console (defaults are loopback-only):
  --backend-port PORT     FastAPI port (default: 8000)
  --frontend-port PORT    Next.js port (default: 3100)
  --backend-bind ADDRESS  FastAPI bind (default: 127.0.0.1)
  --frontend-bind ADDRESS Next.js bind (default: 127.0.0.1)
  --data-dir DIRECTORY    owner-only DB, artifacts, and logs (default: $data_dir)
  --help                  show this message
EOF
}

while (($#)); do
  case "$1" in
    --backend-port) [[ $# -ge 2 ]] || { echo "--backend-port requires a value" >&2; exit 2; }; backend_port="$2"; shift 2 ;;
    --frontend-port) [[ $# -ge 2 ]] || { echo "--frontend-port requires a value" >&2; exit 2; }; frontend_port="$2"; shift 2 ;;
    --backend-bind) [[ $# -ge 2 ]] || { echo "--backend-bind requires a value" >&2; exit 2; }; backend_bind="$2"; shift 2 ;;
    --frontend-bind) [[ $# -ge 2 ]] || { echo "--frontend-bind requires a value" >&2; exit 2; }; frontend_bind="$2"; shift 2 ;;
    --data-dir) [[ $# -ge 2 ]] || { echo "--data-dir requires a value" >&2; exit 2; }; data_dir="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

validate_port "$backend_port"
validate_port "$frontend_port"
if [[ "$backend_port" == "$frontend_port" && "$backend_bind" == "$frontend_bind" ]]; then
  echo "backend and frontend cannot share the same bind/port" >&2
  exit 2
fi

data_dir="$(realpath -m "$data_dir")"
repo_real="$(realpath "$REPO_ROOT")"
home_real="$(realpath "${HOME:?}")"
if [[ "$data_dir" == "/" || "$data_dir" == "$repo_real" || "$data_dir" == "$home_real" ]]; then
  echo "refusing unsafe data directory: $data_dir" >&2
  exit 2
fi

if [[ ( "$backend_bind" != "127.0.0.1" && "$backend_bind" != "localhost" ) || ( "$frontend_bind" != "127.0.0.1" && "$frontend_bind" != "localhost" ) ]]; then
  if [[ -z "${MATB_FRONTEND_ORIGINS:-}" ]]; then
    echo "non-loopback binds require an explicit MATB_FRONTEND_ORIGINS" >&2
    exit 2
  fi
  if [[ -z "${MATB_ALLOWED_HOSTS:-}" ]]; then
    echo "non-loopback binds require an explicit MATB_ALLOWED_HOSTS" >&2
    exit 2
  fi
  frontend_origins="$MATB_FRONTEND_ORIGINS"
else
  frontend_origins="http://localhost:$frontend_port,http://127.0.0.1:$frontend_port"
  MATB_ALLOWED_HOSTS="localhost,127.0.0.1"
fi

VENV="${MATB_VENV:-$REPO_ROOT/.venv}"
python_bin="${MATB_PYTHON:-$VENV/bin/python}"
next_bin="$REPO_ROOT/webui/frontend/node_modules/.bin/next"
if [[ "$python_bin" == */* ]]; then
  [[ -x "$python_bin" ]] || { echo "MATB Python executable not found: $python_bin" >&2; exit 1; }
else
  command -v "$python_bin" >/dev/null 2>&1 || { echo "MATB Python command not found: $python_bin" >&2; exit 1; }
fi
[[ -x "$next_bin" ]] || { echo "missing built frontend: $next_bin (run install_suas.sh)" >&2; exit 1; }
[[ -d "$REPO_ROOT/scenarios/suas" ]] || { echo "missing native scenarios directory" >&2; exit 1; }
if port_in_use "$backend_bind" "$backend_port"; then echo "backend port is already in use" >&2; exit 1; fi
if port_in_use "$frontend_bind" "$frontend_port"; then echo "frontend port is already in use" >&2; exit 1; fi

umask 077
mkdir -p "$data_dir/db" "$data_dir/exports" "$data_dir/logs"
chmod 700 "$data_dir" "$data_dir/db" "$data_dir/exports" "$data_dir/logs"
api_token_file="$data_dir/api-token"
if [[ -z "${MATB_API_TOKEN:-}" ]]; then
  if [[ -f "$api_token_file" ]]; then
    MATB_API_TOKEN="$(<"$api_token_file")"
  else
    MATB_API_TOKEN="$($python_bin -c 'import secrets; print(secrets.token_urlsafe(32))')"
    printf '%s\n' "$MATB_API_TOKEN" >"$api_token_file"
    chmod 600 "$api_token_file"
  fi
fi
if [[ ${#MATB_API_TOKEN} -lt 32 || "$MATB_API_TOKEN" =~ [[:space:]] ]]; then
  echo "MATB_API_TOKEN must contain at least 32 non-whitespace characters" >&2
  exit 2
fi

backend_pid=""
frontend_pid=""
cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM
  terminate_pid "$frontend_pid" || true
  terminate_pid "$backend_pid" || true
  wait "$frontend_pid" 2>/dev/null || true
  wait "$backend_pid" 2>/dev/null || true
  if (( exit_code != 0 )); then
    echo "sUAS console stopped with exit code $exit_code; inspect $data_dir/logs" >&2
  fi
  exit "$exit_code"
}
trap cleanup EXIT INT TERM

export MATB_DB_PATH="$data_dir/db/matb-webui.db"
export MATB_SIMULATION_OUTPUT_DIR="$data_dir/exports"
export MATB_FRONTEND_ORIGINS="$frontend_origins"
export MATB_ALLOWED_HOSTS
export MATB_SIMULATION_SCENARIO_DIR="$REPO_ROOT/scenarios/suas"
export MATB_BACKEND_PORT="$backend_port"
export MATB_API_TOKEN
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

pushd "$REPO_ROOT/webui/backend" >/dev/null
setsid "$python_bin" -m uvicorn app.main:app --host "$backend_bind" --port "$backend_port" >"$data_dir/logs/backend.log" 2>&1 &
backend_pid=$!
popd >/dev/null
pushd "$REPO_ROOT/webui/frontend" >/dev/null
setsid "$next_bin" start --hostname "$frontend_bind" --port "$frontend_port" >"$data_dir/logs/frontend.log" 2>&1 &
frontend_pid=$!
popd >/dev/null

wait_http "http://$backend_bind:$backend_port/health"
wait_http "http://$frontend_bind:$frontend_port/mission/setup"
cat <<EOF
sUAS console is running (offline, research-only).
  Frontend: http://localhost:$frontend_port/mission/setup
  Backend:  http://$backend_bind:$backend_port/health
  Data:     $data_dir
  CLI token file: $api_token_file (owner-only)
Press Ctrl-C to stop both services.
EOF

while true; do
  if ! kill -0 "$backend_pid" 2>/dev/null || ! kill -0 "$frontend_pid" 2>/dev/null; then
    echo "a sUAS console process exited; inspect $data_dir/logs" >&2
    exit 1
  fi
  sleep 1
done
