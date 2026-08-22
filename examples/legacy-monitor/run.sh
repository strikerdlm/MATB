#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
mode="${1:-combined}"
output_dir="${2:-$repo_root/examples/output/legacy-monitor}"

case "$mode" in
  uav|fighter|combined|experiment) ;;
  *)
    echo "Usage: $0 [uav|fighter|combined|experiment] [output-dir]" >&2
    exit 2
    ;;
esac

cd "$repo_root"
command=(python3 -m aircraft_monitor "$mode" --headless --event-delay 0.05 --seed 42)
if [[ "$mode" == "experiment" ]]; then
  command+=(--participant-id SYNTH-P01 --session-id SYNTH-S01 --research-output-dir "$output_dir")
fi
"${command[@]}"
