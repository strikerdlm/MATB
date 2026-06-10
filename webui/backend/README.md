# MATB Research Console — Backend (Phase 1A)

FastAPI + SQLModel (SQLite) service that ingests OpenMATB session CSVs and
optional scenario manifests via `matb_integration`, tracks study completeness,
stores per-block provenance/validation metadata, exports reproducible research
bundles, and auto-fits the Suhir DEPDF per completed visit. No metric logic is
duplicated — `log_converter` and `suhir.pipeline` are reused as a library.

## Setup
```bash
python3 -m venv ~/.venvs/matb-webui
~/.venvs/matb-webui/bin/pip install -r webui/backend/requirements.txt
```

## Run (dev)
```bash
cd webui/backend
~/.venvs/matb-webui/bin/uvicorn app.main:app --reload --port 8000
```

## Test
```bash
cd webui/backend
~/.venvs/matb-webui/bin/python -m pytest -q
```

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
