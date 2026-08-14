#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
output_dir="${1:-$repo_root/examples/output/suas-simulator}"
scenario="$repo_root/scenarios/suas/reference_area_search.yaml"
if [[ -n "${MATB_PYTHON:-}" ]]; then
  python_bin="$MATB_PYTHON"
elif [[ -n "${MATB_VENV:-}" ]]; then
  python_bin="$MATB_VENV/bin/python"
else
  python_bin="python3"
fi
if ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "MATB Python executable not found: $python_bin" >&2
  exit 1
fi
mkdir -p "$output_dir"
cd "$repo_root"
"$python_bin" -m matb_integration.suas.cli validate "$scenario"
"$python_bin" -m matb_integration.suas.cli run "$scenario" --block PRACTICE --ticks 10
"$python_bin" -m matb_integration.suas.cli record "$scenario" --block PRACTICE --ticks 10 \
  --session-id SYNTH-SUAS-01 --output "$output_dir"
"$python_bin" -m matb_integration.suas.cli verify "$output_dir"
