#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
output_dir="${1:-$repo_root/examples/output/openmatb-research}"
cd "$repo_root"
python3 examples/openmatb-research/run_example.py --output-dir "$output_dir"
