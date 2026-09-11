# Research Console walkthrough

[Español](README.es.md)

This is a local, synthetic tour of the FastAPI research console. It uses only
`SYNTH-P01` and the committed LOW fixture; it is not a participant record or an
operational deployment. For endpoint and screen detail, see the
[backend guide](../../webui/backend/README.md) and
[frontend guide](../../webui/frontend/README.md).

## Prerequisites and native development

Use Python 3.12 and Node.js 20.9 or later. From the repository root, create a
venv and install the backend dependencies, then install the frontend Node
dependencies:

```bash
python3 -m venv .venv-suas
.venv-suas/bin/python -m pip install -r requirements-dev.txt
cd webui/frontend
npm install
```

Run the API in one terminal and the browser UI in another. The default API port
is 8000 and the frontend port is 3100.

Use one Uvicorn worker per database. The API acquires a durable instance lease;
starting a second live backend against the same SQLite file fails closed instead
of splitting Bayesian work and writes across process-local executors.

```bash
cd webui/backend
../../.venv-suas/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd webui/frontend
npm run dev -- --hostname 127.0.0.1 --port 3100
```

On Windows, use **PowerShell 7+** (not Windows PowerShell 5.1) to create and
activate a Python 3.12 venv, run the same backend module from `webui/backend`,
and run `npm install` then `npm run dev` in `webui/frontend`. The API
walkthrough also requires PowerShell 7+ because it uses `Invoke-RestMethod
-Form`. Open `http://127.0.0.1:3100`; it calls the loopback API at
`http://127.0.0.1:8000` unless `NEXT_PUBLIC_API_URL` is set.

The API stores SQLite data at `MATB_DB_PATH` when it is set; otherwise its
development default applies. Uploaded blocks and export requests become
database rows and a downloaded ZIP, respectively. Keep each study database and
export directory owner-controlled.

## Offline launcher

On Linux or WSL2, the launcher creates the Python environment, builds the
frontend, and starts both services. Its initial `pip` and `npm` dependency
installation requires network access or a prepared local package cache/mirror.
After dependencies and frontend build artifacts are installed, the launched
service is local and offline-capable; it is not an Internet-facing service.

```bash
MATB_VENV="$PWD/.venv-suas" bash scripts/install_suas.sh
MATB_VENV="$PWD/.venv-suas" bash scripts/run_suas.sh \
  --data-dir "$PWD/examples/output/research-console-service"
```

The launcher uses ports 8000 and 3100 on loopback by default. Press `Ctrl-C`
in its terminal for orderly shutdown. If you choose a non-loopback bind, set
an explicit `MATB_FRONTEND_ORIGINS` value first; do not expose the default
development service unintentionally.

## API tour

Start either local service first, then run one of these from the repository
root. `BASE_URL` and `OUTPUT_DIR` override the loopback address and ZIP output
directory. Load the owner-only token created by the launcher for CLI mutations.

```bash
export MATB_API_TOKEN="$(<examples/output/research-console-service/api-token)"
BASE_URL=http://127.0.0.1:8000 OUTPUT_DIR=/tmp/matb-console \
  bash examples/research-console/api_walkthrough.sh
```

```powershell
$env:MATB_API_TOKEN = Read-Host "MATB API token"
.\examples\research-console\api_walkthrough.ps1 -BaseUrl http://127.0.0.1:8000 -OutputDir C:\Temp\matb-console
```

The tour checks health, creates `SYNTH-P01` only when absent, uploads
`fixtures/low.csv` as visit 1/LOW, safely requests `POST /analysis/run`, prints
and validates the returned per-metric `analysis_status` values, reads the
tracker and research context, and writes `research-bundle.zip`. It accepts only
the engine's `ok`, `insufficient_data`, or `not_estimable` statuses; the
single-row fixture is expected to remain insufficient for many fits. Re-running against the same database can return
409: participant creation is detected, but duplicate CSV SHA-256 and an
already-filled visit/workload cell are intentionally rejected. Clean the
example data directory (or use a fresh `MATB_DB_PATH`) before repeating a
complete ingest.

The upload deliberately omits a scenario manifest. That is accepted and shown
as `missing_manifest`; a malformed or mismatched manifest is retained with
validation issues rather than silently accepted. Do not interpret the one-row
tour as a completed visit or analysis dataset.

This upload surface currently ingests legacy CSV, not the runtime's authoritative
v3 event/timing stream. Every derived record and long-format metric carries
`legacy_csv_derived_not_reconciled_to_authoritative_event_stream`; confirmatory
eligibility stays false even when the optional scenario manifest is valid. Paired
JSONL ingestion and event-ID reconciliation is an explicit public-release gate.

## Browser tour and cleanup

With the frontend on port 3100, visit:

- `http://127.0.0.1:3100/` for the tracker;
- `/upload` for CSV and optional manifest ingestion;
- `/visualization` for descriptive charts;
- `/analysis` for frequentist and Bayesian analysis plus research-bundle export;
- `/screen` for the baseline screen; and
- `/participants` for pseudonymized study identities.

Use `GET /health` (or the first walkthrough request) to check the API. Stop
native development with `Ctrl-C` in each terminal. To reset this example, stop
the services and delete only the selected example data directory or its
dedicated SQLite file—never a shared study database.

New acquisition requests must explicitly include `execution_purpose` (`study` or
`practice`). Fast screen/PVT requests require `practice`. Record views return a
`purpose_provenance_id`; the protected local purpose API retains immutable
classification history, including unknown historical intent. See the
[backend contract](../../webui/backend/README.md#acquisition-purpose-and-historical-provenance).
