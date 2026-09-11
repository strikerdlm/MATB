#!/usr/bin/env bash
# Local, lifecycle-only sUAS API tour. It never sends aircraft commands.
set -euo pipefail

base_url="${BASE_URL:-http://127.0.0.1:8000}"
api_token="${MATB_API_TOKEN:?Set MATB_API_TOKEN to the backend bearer token}"
authorization_header="Authorization: Bearer $api_token"
participant_id="P01"

participant_exists() {
  curl --silent --show-error --fail-with-body "$base_url/participants" |
    python3 -c 'import json, sys; raise SystemExit(0 if any(p.get("id") == sys.argv[1] for p in json.load(sys.stdin)) else 1)' "$participant_id"
}

curl --fail-with-body "$base_url/health"
if participant_exists; then
  echo "Synthetic sUAS participant already exists; continuing."
else
  curl --fail-with-body -H 'Content-Type: application/json' \
    -H "$authorization_header" \
    -d '{"id":"P01","enrollment_date":"2026-08-14"}' "$base_url/participants"
fi
curl --fail-with-body "$base_url/simulation/scenarios"
prepared_json="$(curl --silent --show-error --fail-with-body -H 'Content-Type: application/json' \
  -H "$authorization_header" \
  -d '{"execution_purpose":"study","participant_id":"P01","visit_ordinal":1,"scenario_id":"reference_area_search","locale":"en"}' \
  "$base_url/simulation/sessions")"
read -r session_id controller_lease_value < <(
  printf '%s' "$prepared_json" | python3 -c 'import json, sys; value=json.load(sys.stdin); print(value["id"], value["controller_lease"])'
)
unset prepared_json
controller_header_name='X-Simulation-Controller'
curl --fail-with-body -H "$controller_header_name: $controller_lease_value" \
  -H "$authorization_header" \
  -H 'Content-Type: application/json' -d '{"block_id":"PRACTICE"}' \
  "$base_url/simulation/sessions/$session_id/start"
curl --fail-with-body "$base_url/simulation/sessions/$session_id/state"
curl --fail-with-body -H "$controller_header_name: $controller_lease_value" \
  -H "$authorization_header" \
  -H 'Content-Type: application/json' -d '{"disposition":"complete"}' \
  "$base_url/simulation/sessions/$session_id/finish"
curl --fail-with-body "$base_url/simulation/sessions/$session_id/debrief"
curl --fail-with-body "$base_url/simulation/sessions/$session_id/artifacts"
unset controller_lease_value
unset controller_header_name
