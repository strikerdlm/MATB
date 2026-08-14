#!/usr/bin/env bash
# Safe, local API tour for synthetic research-console data.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
base_url="${BASE_URL:-http://127.0.0.1:8000}"
output_dir="${OUTPUT_DIR:-$repo_root/examples/output/research-console}"
participant_id="SYNTH-P01"
mkdir -p "$output_dir"

participant_exists() {
  curl --silent --show-error --fail-with-body "$base_url/participants" |
    python3 -c 'import json, sys; raise SystemExit(0 if any(p.get("id") == sys.argv[1] for p in json.load(sys.stdin)) else 1)' "$participant_id"
}

curl --fail-with-body "$base_url/health"
if participant_exists; then
  echo "Synthetic participant already exists; continuing."
else
  curl --fail-with-body -H 'Content-Type: application/json' \
    -d '{"id":"SYNTH-P01","enrollment_date":"2026-08-14"}' \
    "$base_url/participants"
fi
curl --fail-with-body \
  -F 'participant_id=SYNTH-P01' -F 'visit_ordinal=1' -F 'workload_level=LOW' \
  -F "file=@$repo_root/examples/openmatb-research/fixtures/low.csv;type=text/csv" \
  "$base_url/ingest"
curl --fail-with-body "$base_url/tracker"
curl --fail-with-body "$base_url/exports/research-context"
curl --fail-with-body -H 'Content-Type: application/json' -d '{"figures":[]}' \
  --output "$output_dir/research-bundle.zip" "$base_url/exports/research-bundle"
echo "Wrote $output_dir/research-bundle.zip"
