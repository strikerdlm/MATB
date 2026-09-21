# MATB Research Console — Backend

FastAPI + SQLModel (SQLite) service that ingests OpenMATB session CSVs and
optional scenario manifests via `matb_integration`, tracks study completeness,
stores per-block provenance/validation metadata, exports reproducible research
bundles, and auto-fits the Suhir DEPDF per completed visit. No metric logic is
duplicated — `log_converter` and `suhir.pipeline` are reused as a library.

## Setup
```bash
cd /path/to/MATB
python3 -m venv .venv-suas
.venv-suas/bin/pip install -r requirements-dev.txt
```

## Run (dev)
```bash
cd webui/backend
../../.venv-suas/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Test
```bash
cd webui/backend
../../.venv-suas/bin/python -m pytest -q
```

For the production-shaped offline server, use the repository launcher instead
of a development reload:

```bash
cd /path/to/MATB
MATB_VENV="$PWD/.venv-suas" bash scripts/install_suas.sh
MATB_VENV="$PWD/.venv-suas" bash scripts/run_suas.sh
```

The launcher sets `MATB_DB_PATH`, `MATB_SIMULATION_OUTPUT_DIR`,
`MATB_SIMULATION_SCENARIO_DIR`, and `MATB_FRONTEND_ORIGINS`, creates owner-only
directories, starts the API and built frontend together, and tears both down
on Ctrl-C. No Windows service, X server, or external telemetry is needed.

State-changing browser requests require an exact configured `Origin`; every
request also passes a loopback `Host` allowlist. Origin-less CLI requests must
send `Authorization: Bearer $MATB_API_TOKEN`. The combined launcher creates a
stable owner-only token at `<data-dir>/api-token` when one is not supplied.

## Data model
Participant -> Visit (timepoint 1-6) -> Block (LOW/MEDIUM/HIGH) -> metrics.
Each Block may have one BlockProvenance row with manifest filename/SHA-256,
manifest JSON, validation status, and validation issues. Completeness (the
12x6x3 grid) is derived, not stored. A DepdfFit row is created per visit once
all 3 levels are ingested.

## Endpoints
- GET  /health
- POST /participants  ·  GET /participants  ·  GET /participants/{id}/visits
- POST /ingest  (multipart: file, optional manifest, participant_id, visit_ordinal, workload_level, overwrite)
- GET  /tracker  — the completeness grid
- GET  /block  — one block's metrics, provenance/validation, and the visit's DEPDF fit
- GET  /metrics/long  — tidy long-format metric rows (optional `participant_id`)
- GET  /fits  — DEPDF fits incl. `hcf_value` and F-aware P^h(G/G₀) curves (Eq. 5.1 when a screen HCF is present, Eq. 5.16 otherwise)
- POST /analysis/run  — collect rows, fingerprint input, run the Phase 3A stats engine, cache result
- GET  /analysis/latest  — return the most recent cached artifact (404 when none)
- POST /analysis/bayes/run  — fingerprint input, spawn background NUTS sampler; returns 202 immediately; re-POST while a job is active returns the existing job (no duplicate sampling); caches done artifact by (fingerprint, bayes_version)
- GET  /analysis/bayes/status  — job lifecycle: queued|running|done|failed; artifact attached when done; 404 before any job submitted
- POST /screen  — ingest raw subtest trial payload; score server-side; store result; refresh `hcf_value`/`hcf_source` on all existing DepdfFit rows; 409 on duplicate (unless `overwrite=true`); 422 on malformed payload
- GET  /screen  — per-participant screen scores, cohort F/F₀ values, and gate status
- GET  /exports/research-context  — one JSON payload with participants, visits, tracker, metrics_long, fits, latest analysis artifacts, and block provenance
- POST /exports/research-bundle  — ZIP export with the research context, caveats, stored scenario manifests, and optional frontend ECharts figure options

### Native offline sUAS research console

The optional sUAS component also provides `/geography/catalog`, `/geography/traffic`,
`/geography/preparations`, `/geography/recordings`, and verified scene assets.
Preparation jobs support progress/cancellation; capture promotion requires a
finished technical session and its controller lease. Provider credentials remain
server-side. Research sessions reject live traffic and pin capture checksums.
These routes are absent in `MATB_COMPONENTS=core`.
See the [Colombia guide](../../docs/implementation/colombia-geography-traffic.md)
for endpoints, configuration, source attribution and offline preparation.

The native simulator is a Linux/headless-safe, non-kinetic research instrument.
It uses one process-local controller lease and a local SQLite/artifact root; no
Internet, real-world map, vehicle, weapon, or external telemetry service is
required.

- `GET /simulation/scenarios` lists valid direct `.yaml` children of the
  configured scenario directory.
- `POST /simulation/sessions` prepares a pseudonymized participant/visit and
  returns the controller lease once.  Send that value only as
  `X-Simulation-Controller` on lifecycle and command mutations.
- `POST /simulation/sessions/{id}/start|pause|resume|finish|recover` controls
  lifecycle.  A controller WebSocket disconnect pauses a running session and
  never resumes it automatically.
- `POST /simulation/sessions/{id}/commands` accepts supervisory, non-kinetic
  commands; `GET .../state` is observer-readable and redacted.
- `WS /simulation/sessions/{id}/stream` accepts an exact configured Origin,
  an optional URL-encoded `lease`, and `after_sequence`.  A lease-bearing
  stream is the sole controller; a lease-free stream is read-only.  The first
  message is a complete resynchronizing snapshot, followed by ordered bounded
  envelopes.  Pings must be exactly `{"kind":"ping"}`.
- `GET .../debrief` and `GET .../artifacts` are available only after a terminal
  finish/abort and expose relative paths plus hashes, never leases or absolute
  filesystem paths.

The stream is intentionally ordered and bounded. The first frame is a complete
snapshot marked with the requested `after_sequence`; later envelopes are
monotonic. A lease-free stream is an observer and cannot submit commands or
finish a session. A valid controller disconnect transitions RUNNING to PAUSED;
an explicit lease-bearing reconnect is required to resume. Probe payloads are
redacted, while private answers remain in the sealed artifact set.

Set `MATB_SIMULATION_OUTPUT_DIR` to an owner-only local directory for run
artifacts.  On startup, rows left RUNNING/PAUSED by a dead process are marked
INTERRUPTED.  Recovery is explicit: an in-process interruption requires the
  existing lease; a stale-process recovery requires
  `confirm_process_restart=true` and returns a new lease once.  Checkpoint
  recovery always marks `valid_with_deviation` and preserves the append-only
  audit trail.

## Notes
- Pseudonymized participant IDs only (P01…); no PII.
- Ingestion guards against duplicate files (sha256), filled-cell overwrite, and
  CSVs with no SYSMON data.
- Missing manifests are accepted but stored as `missing_manifest`; malformed or
  mismatched manifests are stored with validation issues instead of being silently
  ignored.
- Analysis results are cached per (input fingerprint, engine version) in the
  `analysis_result` table; re-running `POST /analysis/run` with unchanged data
  returns the cached artifact immediately (response includes `"cached": true`).
- Screen HCF refresh: every `POST /screen` ingest (including overwrites) recomputes
  the cohort F value and writes it to `hcf_value`/`hcf_source` on all DepdfFit rows.
  New fits pick the stored value up automatically; no re-ingest of session data is needed.
  Mapping is exploratory — not a validated predictive instrument.
- Backend endpoint tests use an ASGI transport fixture instead of Starlette's
  TestClient portal so the suite remains stable under the pinned FastAPI stack.

Spec: `docs/superpowers/specs/2026-06-03-webui-phase1-data-tracker-design.md`
Plan: `docs/superpowers/plans/2026-06-03-webui-phase1a-backend.md`

### Acquisition purpose and historical provenance

All new acquisition POST bodies require `execution_purpose`: `study` or
`practice` for `/pvt`, `/screen`, `/openmatb/sessions`, `/liftoff/sessions` and
`/physiology/polar-h10/v1/captures`; `/simulation/sessions` requires `study`, and
`/simulation/technical-sessions` requires `practice`. A fast screen or PVT declared
as study returns 422. Existing artifact readers retain tolerant historical defaults.

Record views expose `purpose_provenance_id`. Read its immutable identity and full
classification history at `GET /purpose-provenance/{id}`. Append a retrospective
local attestation with `POST /purpose-provenance/{id}/classifications`:

```json
{
  "purpose": "practice",
  "reviewer": "Named local reviewer",
  "reason": "Retained training log identifies this observation as practice",
  "supporting_references": ["training-log:retained-local-reference"]
}
```

These routes use the existing loopback Host and mutation Origin/bearer protections.
There is no public API to assign historical observations an `explicit`
classification or edit/delete history. Source purposes, scores, raw observations,
and collection timestamps remain unchanged by classification. New declarations
and acquisition rows persist in one transaction; UUID provenance survives archived
assessment replacement even if SQLite reuses a numeric row ID. Migration labels
unsupported historical prospective intent `unknown`, including historical practice
rows, and records legacy fast-mode inference as a system retrospective event at
migration time. A classification is evidence for subsequent plan-based selection,
not automatic scientific eligibility or approval.

## Versioned swarm sessions

`swarm_supervision` uses schema v2 and engine `2.0.0-swarm.1`. The existing command
route accepts `SWARM_TASK`, `SWARM_WAYPOINT` and `SWARM_MEMBERSHIP` through the same
controller lease, Origin, optimistic state version and idempotency checks as
individual commands. Group updates validate all affected members before commit;
individual flight commands require explicit detachment. JOIN requires held
members and a subsequent new group task. RETURN can be held/resumed and still
terminates in recovery.

Public state adds `swarms`; checkpoints and sealed replay retain membership,
formation, bounded trails and fault-response state. Swarm research requires an
explicit presentation v3 configuration. Exposure records must match the configured
version and pin `racing-quad-v1-scale80` with the north-up inset enabled. Old
scenario hashes/world shapes and old presentation readers remain supported.
`metrics.swarm` contains descriptive group summaries, with null for unavailable
observations; the mission composite is unchanged. The coverage observation is
mission-wide and is not proof that the affected group recovered its own task.

[Payloads and operator behavior](../../docs/implementation/suas-swarm-supervision.md)
· [Deployment and release verification](../../docs/implementation/suas-swarm-release.md).
