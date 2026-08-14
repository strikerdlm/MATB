# Synthetic sUAS simulator walkthrough

[Español](README.es.md)

This is a deterministic, non-kinetic research simulator. It has no real
aircraft, maps, telemetry, weapons, or external service connection. The native
API validates pseudonymous sUAS identities as `P` plus digits, so this tour
uses synthetic `P01`; the separate research-console tour uses `SYNTH-P01`.
See the [backend guide](../../webui/backend/README.md) and
[frontend guide](../../webui/frontend/README.md) for complete API and UI
contracts.

## Linux and WSL2 installation

Use Python 3.12 and Node.js 20 or later. The POSIX launcher belongs on Linux
or WSL2; on Windows, run it inside WSL2. **PowerShell 7+** (not Windows
PowerShell 5.1) may call the loopback API after WSL2 hosts the service and is
the supported shell for the published walkthroughs. It does not replace the
launcher.

```bash
MATB_VENV="$PWD/.venv-suas" bash scripts/install_suas.sh
MATB_VENV="$PWD/.venv-suas" bash scripts/run_suas.sh \
  --data-dir "$PWD/examples/output/suas-service"
```

Initial `pip` and `npm` dependency installation requires network access or a
prepared local package cache/mirror. Once dependencies and frontend build
artifacts are installed, the launcher starts an offline-capable local service:
FastAPI on `127.0.0.1:8000` and the browser console on `127.0.0.1:3100`. It
places the SQLite database, sealed artifacts, and logs below the owner-only
data directory, without external telemetry. Press `Ctrl-C` for coordinated
teardown. For a non-loopback bind, explicitly set `MATB_FRONTEND_ORIGINS`;
loopback defaults are intentional.

For native development, create the same Python 3.12 venv from
`requirements-dev.txt`, run `python -m uvicorn app.main:app --host 127.0.0.1
--port 8000` from `webui/backend`, then `npm install` and `npm run dev` from
`webui/frontend`. The mission UI is at `/mission/setup` and `/mission`.

## CLI-only deterministic run

No service or browser is needed for the CLI demo:

```bash
bash examples/suas-simulator/cli_demo.sh /tmp/matb-suas-cli
```

It validates `scenarios/suas/reference_area_search.yaml`, advances PRACTICE for
10 ticks, records `SYNTH-SUAS-01`, and verifies exactly the directory supplied
as its first argument. The recorder emits `events.jsonl`, `manifest.json`,
`metrics.json`, `debrief.json`, `replay-verification.json`, and
`checksums.sha256` directly in that output directory—there is no guessed or
searched nested session folder. Choose an empty directory: recording refuses a
nonempty output directory. Delete only that chosen demo directory to reset it.

## Lifecycle-only API tour

With the WSL2/Linux launcher running, run either client against loopback:

```bash
BASE_URL=http://127.0.0.1:8000 bash examples/suas-simulator/api_walkthrough.sh
```

```powershell
.\examples\suas-simulator\api_walkthrough.ps1 -BaseUrl http://127.0.0.1:8000
```

The clients check health, ensure synthetic `P01`, list scenarios, prepare
`reference_area_search`, start only PRACTICE, read public state as an observer,
finish as complete, then fetch public debrief and artifact metadata. The
one-time controller lease stays only in a local process variable and the
`X-Simulation-Controller` request header; it is never printed or put in a URL.
No aircraft-control command is submitted.

One controller owns lifecycle mutations. Lease-free API and browser observers
see only redacted public state. A controller disconnect pauses a running
session; it never resumes automatically. Explicit checkpoint recovery preserves
the append-only audit trail and marks recovered runs with a deviation. Terminal
artifacts are sealed; public artifact metadata has relative paths and hashes,
while private event/probe material remains unavailable. Verify a CLI artifact
with `python3 -m matb_integration.suas.cli verify OUTPUT_DIRECTORY`.

Use `GET /health` to check the service and `Ctrl-C` to stop the launcher. Keep
the data directory owner-only and remove only a dedicated demo directory after
the service stops.
