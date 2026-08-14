#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
output_dir="${1:-$repo_root/examples/output/suas-simulator}"
scenario="$repo_root/scenarios/suas/reference_area_search.yaml"
mkdir -p "$output_dir"
cd "$repo_root"
python3 -m matb_integration.suas.cli validate "$scenario"
python3 -m matb_integration.suas.cli run "$scenario" --block PRACTICE --ticks 10
python3 -m matb_integration.suas.cli record "$scenario" --block PRACTICE --ticks 10 \
  --session-id SYNTH-SUAS-01 --output "$output_dir"
python3 -m matb_integration.suas.cli verify "$output_dir"
