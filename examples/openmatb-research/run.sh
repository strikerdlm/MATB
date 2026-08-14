#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
output_dir="${1:-$repo_root/examples/output/openmatb-research}"
python_bin="${MATB_PYTHON:-python3}"
if ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "MATB Python executable not found: $python_bin" >&2
  exit 1
fi
cd "$repo_root"
"$python_bin" examples/openmatb-research/run_example.py --output-dir "$output_dir"
