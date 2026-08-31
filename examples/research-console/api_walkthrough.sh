#!/usr/bin/env bash
# Safe, local API tour for synthetic research-console data.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
base_url="${BASE_URL:-http://127.0.0.1:8000}"
api_token="${MATB_API_TOKEN:?Set MATB_API_TOKEN to the backend bearer token}"
authorization_header="Authorization: Bearer $api_token"
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
    -H "$authorization_header" \
    -d '{"id":"SYNTH-P01","enrollment_date":"2026-08-14"}' \
    "$base_url/participants"
fi
curl --fail-with-body \
  -H "$authorization_header" \
  -F 'participant_id=SYNTH-P01' -F 'visit_ordinal=1' -F 'workload_level=LOW' \
  -F "file=@$repo_root/examples/openmatb-research/fixtures/low.csv;type=text/csv" \
  "$base_url/ingest"
analysis_response="$(curl --silent --show-error --fail-with-body -X POST \
  -H "$authorization_header" \
  "$base_url/analysis/run")"
printf '%s' "$analysis_response" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
statuses = {name: result.get("status") for name, result in payload.get("q1", {}).items()}
allowed = {"ok", "insufficient_data", "not_estimable"}
if not statuses or not set(statuses.values()) <= allowed:
    raise SystemExit("analysis response contains missing or unsupported q1 status")
print(json.dumps({"analysis_status": statuses}, sort_keys=True))
'
curl --fail-with-body "$base_url/tracker"
curl --fail-with-body "$base_url/exports/research-context"
curl --fail-with-body -H 'Content-Type: application/json' -d '{"figures":[]}' \
  -H "$authorization_header" \
  --output "$output_dir/research-bundle.zip" "$base_url/exports/research-bundle"
echo "Wrote $output_dir/research-bundle.zip"
