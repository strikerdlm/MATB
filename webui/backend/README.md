# MATB Research Console — Backend (Phase 1A)

FastAPI + SQLModel (SQLite) service that ingests OpenMATB session CSVs via
`matb_integration`, tracks study completeness, and auto-fits the Suhir DEPDF
per completed visit. No metric logic is duplicated — `log_converter` and
`suhir.pipeline` are reused as a library.

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
Completeness (the 12x6x3 grid) is derived, not stored. A DepdfFit row is created
per visit once all 3 levels are ingested.

## Endpoints
- GET  /health
- POST /participants  ·  GET /participants  ·  GET /participants/{id}/visits
- POST /ingest  (multipart: file, participant_id, visit_ordinal, workload_level, overwrite)
- GET  /tracker  — the completeness grid
- GET  /block  — one block's metrics + the visit's DEPDF fit
- GET  /metrics/long  — tidy long-format metric rows (optional `participant_id`)
- GET  /fits  — DEPDF fits incl. server-computed P^h(G/G₀) curves

## Notes
- Pseudonymized participant IDs only (P01…); no PII.
- Ingestion guards against duplicate files (sha256), filled-cell overwrite, and
  CSVs with no SYSMON data.

Spec: `docs/superpowers/specs/2026-06-03-webui-phase1-data-tracker-design.md`
Plan: `docs/superpowers/plans/2026-06-03-webui-phase1a-backend.md`
