# MATB — Human-Factors Research and Aviation Safety Assurance

[English](README.md) | [Español](README.es.md)

> Research and safety-assurance software only. MATB is not a clinical device,
> certified operational system, aircraft-control channel, weapon system, or a
> substitute for accountable human approval.

MATB brings several independently installable workflows into one repository:
OpenMATB-compatible study tooling, a local research console, a deterministic
small-uncrewed-aircraft-system (sUAS) simulator, an offline-first FAC ISR Safety
Management System (SMS), and a retained terminal aircraft-monitor demonstration.
Choose one workflow below; you do not need to install the others.

<a id="identity-and-safety"></a>
## 1. Identity, intended use, and safety boundary

The active Python research surface generates scenarios and provenance, converts
OpenMATB CSV logs, computes descriptive/frequentist/Bayesian results, fits a
within-participant Suhir DEPDF model, and supports an exploratory
neurocognitive screen. OpenMATB itself is external and is not vendored here.

The Research Console is a loopback FastAPI/Next.js application with local
SQLite and artifact storage. Its sUAS surface is a synthetic, non-kinetic,
supervisory simulator. It has no real aircraft, weapon, targeting, autonomous
dispatch, real-world map, external telemetry, or command-and-control (C2) path.

The `SMS/` workspace evaluates controlled evidence, read-only telemetry, safety
gates, organizational SMS records, and institutional-review artifacts. A
component passing, a build succeeding, or a verification matrix completing is
not an authorization to operate. Missing, stale, untrusted, or unaccepted hard
evidence fails closed; accountable institutional reviewers remain the decision
authority.

Use only pseudonymous research identities. Keep study data, controlled evidence,
signing material, TLS material, controller leases, and institutional decisions
out of the repository and under the owning institution's custody controls.

<a id="choose-a-workflow"></a>
## 2. Choose one workflow

| Goal | Start here | Runtime | Example | Expected output |
| --- | --- | --- | --- | --- |
| Generate OpenMATB scenarios, convert logs, or try DEPDF analysis | `matb_integration/` | Python; external OpenMATB only for participant task presentation | [OpenMATB research tour](examples/openmatb-research/README.md) | Three scenarios/manifests, synthetic JSONL metrics, and one DEPDF JSON |
| Ingest sessions, track visits, visualize data, analyze, and export | `webui/` | Python 3.12+, Node 20+, local browser | [Research Console walkthrough](examples/research-console/README.md) | Local SQLite records and `research-bundle.zip` |
| Run a deterministic, observer-safe sUAS research session | `matb_integration/suas/` and `webui/` | Python 3.12+; Node 20+ for browser service | [sUAS simulator walkthrough](examples/suas-simulator/README.md) | Replay-verifiable events, metrics, debrief, manifest, and checksums |
| Evaluate offline safety-management package contracts | `SMS/` | Node 22.x; Docker only for the offline image/bundle | [SMS capability tour](examples/sms-platform/README.md) | Deterministic JSON with a deliberately blocked safety-kernel result |
| Demonstrate the older terminal monitor | `aircraft_monitor/` | Python and a terminal | [Legacy monitor guide](examples/legacy-monitor/README.md) | Headless UAV, fighter, combined, or experiment event stream |

The [examples index](examples/README.md) compares fast offline examples with the
service, browser, Docker, and external-runtime procedures.

<a id="architecture-and-data-flow"></a>
## 3. Architecture and data movement

```text
MATB/
├── matb_integration/       Python scenario, conversion, analysis, screen, and sUAS libraries
├── scenarios/              committed OpenMATB and synthetic sUAS scenarios
├── webui/                  FastAPI backend and Next.js Research Console
├── SMS/                    Node/TypeScript safety-management monorepo
├── aircraft_monitor/       retained Rich terminal demonstrations
├── examples/               deterministic synthetic workflow tours
├── scripts/                native sUAS install/launch and documentation verification
├── tests/                  Python, integration, sUAS, and documentation suites
└── docs/                   scientific, implementation, design, and verification detail
```

The four primary flows are deliberately separate:

```text
External OpenMATB -> session CSV + scenario manifest -> metrics -> DEPDF/statistics -> research bundle
Browser -> FastAPI Research Console -> local SQLite/artifacts -> tracker/analysis/export
Synthetic YAML -> deterministic sUAS engine -> observer-safe state -> replay/debrief artifacts
Signed local evidence + read-only telemetry -> edge API/safety kernel -> console/audit -> offline verification
```

The research database is not an operational database. `SMS/packages/research/`
and the SMS operational domain have explicit separation checks. Telemetry is
read-only, and neither application exposes a vehicle-command channel.

<a id="prerequisites"></a>
## 4. Prerequisite matrix

| Dependency | Version or role | OpenMATB tools | Research Console | sUAS | `SMS/` | Legacy monitor |
| --- | --- | --- | --- | --- | --- | --- |
| Git | Clone/source control | Required | Required | Required | Required | Required |
| Python | 3.12+ is required by the sUAS installer; use the same version for repository Python workflows | Required | Required | Required | No | Required |
| Node.js | Launcher checks 20+; frontend uses npm | No | 20+ required | 20+ for browser service | **22.x required** | No |
| npm | Lockfile-based dependency/build tool | No | Required for frontend | Required for browser service | Required | No |
| External OpenMATB | Separate task runner with its own dependencies | Workflow-specific | Only to collect real task sessions | No | No | No |
| Xvfb | Virtual X display for external OpenMATB/Pyglet on headless Linux | Workflow-specific | No | No—the native UI is browser/headless | No | No in `--headless` mode |
| Chromium | Browser use; Playwright Chromium is needed only for browser E2E/a11y gates | Optional | Browser required; Playwright asset optional | Browser required for UI; optional for CLI | Optional console test asset | No |
| Docker | Linux container engine and staged base image | No | No | No | Workflow-specific for offline image/bundle | No |
| WSL2 | POSIX boundary on Windows | For `setup.sh` or Linux/Xvfb procedure | For the combined POSIX launcher only | Required on Windows for `install_suas.sh`/`run_suas.sh` | For POSIX scripts, Linux permissions, and Docker verification | Not required |

Native Windows supports the PowerShell/Python/Node examples. It does not turn
POSIX shell launchers, Linux container entrypoints, `chmod`/UID behavior, or
Xvfb into native Windows procedures. Use WSL2 for those paths. PowerShell API
walkthroughs require PowerShell 7+ because they use `Invoke-RestMethod -Form`.

Check only the tools needed for the selected workflow.

```bash
git --version
python3 --version
node --version
npm --version
```

```powershell
git --version
python --version
node --version
npm --version
$PSVersionTable.PSVersion
```

<a id="quick-start-openmatb"></a>
## 5. OpenMATB research quick start

This quick start is fully synthetic. The external OpenMATB runtime is necessary
only when presenting generated tasks to a participant.

<h3>Prerequisites</h3>

Use Git and Python 3.12+. For participant presentation, provide a separate
OpenMATB checkout. Linux/headless presentation also needs Xvfb and a working
Pyglet display; native Windows runs the external desktop runtime directly.

<h3>Install</h3>

Linux Bash or WSL2, from the clone root:

```bash
REPO_ROOT="$(pwd)"
python3 -m venv "$REPO_ROOT/.venv-openmatb"
"$REPO_ROOT/.venv-openmatb/bin/python" -m pip install -r "$REPO_ROOT/requirements.txt"
```

`setup.sh` is an equivalent POSIX-only repository setup entry point:

```bash
REPO_ROOT="$(pwd)"
MATB_VENV="$REPO_ROOT/.venv-openmatb" bash "$REPO_ROOT/setup.sh"
```

Native Windows PowerShell 7+:

```powershell
$RepoRoot = (Get-Location).Path
python -m venv (Join-Path $RepoRoot ".venv-openmatb")
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") -m pip install -r (Join-Path $RepoRoot "requirements.txt")
```

<h3>Configure</h3>

Synthetic generation needs no configuration. To install assets into an
external checkout derived from the clone location:

```bash
REPO_ROOT="$(pwd)"
OPENMATB_DIR="$REPO_ROOT/../openmatb"
"$REPO_ROOT/.venv-openmatb/bin/python" "$REPO_ROOT/install_to_openmatb.py" "$OPENMATB_DIR"
```

```powershell
$RepoRoot = (Get-Location).Path
$OpenMatbDir = (Resolve-Path (Join-Path $RepoRoot "..\openmatb")).Path
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") (Join-Path $RepoRoot "install_to_openmatb.py") $OpenMatbDir
```

The external checkout must contain `includes/`. Configure its own environment
and scenario selector according to that runtime. Do not point the installer at
this repository.

<h3>Run</h3>

Generate the committed protocol shape without starting OpenMATB:

```bash
REPO_ROOT="$(pwd)"
"$REPO_ROOT/.venv-openmatb/bin/python" -m matb_integration.scenario_builder \
  --output-dir "$REPO_ROOT/examples/output/generated-scenarios" --block-duration 900 --seed 42
```

```powershell
$RepoRoot = (Get-Location).Path
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") -m matb_integration.scenario_builder `
  --output-dir (Join-Path $RepoRoot "examples\output\generated-scenarios") --block-duration 900 --seed 42
```

For external Linux/OpenMATB use, run its `main.py` inside its own environment.
Use `DISPLAY` and Xvfb only on a Linux/headless host. Native Windows does not
use Xvfb.

<h3>Try the synthetic example</h3>

```bash
REPO_ROOT="$(pwd)"
bash "$REPO_ROOT/examples/openmatb-research/run.sh" "$REPO_ROOT/examples/output/openmatb-research"
```

```powershell
$RepoRoot = (Get-Location).Path
& (Join-Path $RepoRoot "examples\openmatb-research\run.ps1") -OutputDir (Join-Path $RepoRoot "examples\output\openmatb-research")
```

<h3>Expected result</h3>

The tour writes three `scenarios/*.txt` files with adjacent manifests,
`metrics.jsonl`, and `suhir.json`, then prints `External OpenMATB was not
started.` The fixture contains only `SYNTH-P01`; it is not participant data.

<h3>Verify</h3>

```bash
REPO_ROOT="$(pwd)"
"$REPO_ROOT/.venv-openmatb/bin/python" -m pytest \
  "$REPO_ROOT/tests/test_scenario_builder.py" \
  "$REPO_ROOT/tests/test_scenario_manifest.py" \
  "$REPO_ROOT/tests/test_log_converter.py" \
  "$REPO_ROOT/tests/analysis_stats" "$REPO_ROOT/tests/suhir" "$REPO_ROOT/tests/screen" -q
```

```powershell
$RepoRoot = (Get-Location).Path
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") -m pytest `
  (Join-Path $RepoRoot "tests\test_scenario_builder.py") `
  (Join-Path $RepoRoot "tests\test_scenario_manifest.py") `
  (Join-Path $RepoRoot "tests\test_log_converter.py") `
  (Join-Path $RepoRoot "tests\analysis_stats") (Join-Path $RepoRoot "tests\suhir") (Join-Path $RepoRoot "tests\screen") -q
```

<h3>Stop and clean up</h3>

Stop external OpenMATB or Xvfb with Ctrl-C. Delete only the selected synthetic
output, never an external runtime or session store.

```bash
REPO_ROOT="$(pwd)"
rm -rf -- "$REPO_ROOT/examples/output/openmatb-research" "$REPO_ROOT/examples/output/generated-scenarios"
```

```powershell
$RepoRoot = (Get-Location).Path
Remove-Item -Recurse -Force (Join-Path $RepoRoot "examples\output\openmatb-research"), (Join-Path $RepoRoot "examples\output\generated-scenarios") -ErrorAction SilentlyContinue
```

<h3>Troubleshooting</h3>

An `includes/ not found` error means the selected external checkout is wrong.
`ModuleNotFoundError` usually means the repository or external-runtime venv is
inactive. On Linux, display/flicker/Pyglet failures belong to the external
OpenMATB/X11 boundary: validate `DISPLAY`, use Xvfb on headless hosts, and begin
windowed. See the [complete OpenMATB example](examples/openmatb-research/README.md).

<a id="quick-start-research-console"></a>
## 6. Research Console quick start

<h3>Prerequisites</h3>

Use Python 3.12+, Node 20+, npm, and a browser. Initial dependency installation
needs network access or prepared Python/npm caches; the installed service is
local and offline-capable.

<h3>Install</h3>

Linux or WSL2 combined launcher:

```bash
REPO_ROOT="$(pwd)"
MATB_VENV="$REPO_ROOT/.venv-console" bash "$REPO_ROOT/scripts/install_suas.sh"
```

Native Windows PowerShell 7+ development installation:

```powershell
$RepoRoot = (Get-Location).Path
python -m venv (Join-Path $RepoRoot ".venv-console")
& (Join-Path $RepoRoot ".venv-console\Scripts\python.exe") -m pip install -r (Join-Path $RepoRoot "requirements-dev.txt")
Set-Location (Join-Path $RepoRoot "webui\frontend")
npm ci
Set-Location $RepoRoot
```

<h3>Configure</h3>

Choose a dedicated data root. The POSIX launcher sets `MATB_DB_PATH`,
`MATB_SIMULATION_OUTPUT_DIR`, `MATB_SIMULATION_SCENARIO_DIR`, and
`MATB_FRONTEND_ORIGINS`. For native development:

```bash
REPO_ROOT="$(pwd)"
export MATB_DB_PATH="$REPO_ROOT/examples/output/research-console-service/matb.db"
export MATB_FRONTEND_ORIGINS="http://127.0.0.1:3100"
```

```powershell
$RepoRoot = (Get-Location).Path
$DataRoot = Join-Path $RepoRoot "examples\output\research-console-service"
New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
$env:MATB_DB_PATH = Join-Path $DataRoot "matb.db"
$env:MATB_FRONTEND_ORIGINS = "http://127.0.0.1:3100"
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
```

<h3>Run</h3>

Linux/WSL2 starts both built services and applies owner-only POSIX permissions:

```bash
REPO_ROOT="$(pwd)"
MATB_VENV="$REPO_ROOT/.venv-console" bash "$REPO_ROOT/scripts/run_suas.sh" \
  --data-dir "$REPO_ROOT/examples/output/research-console-service"
```

Native Windows uses two PowerShell terminals. Backend:

```powershell
$RepoRoot = (Get-Location).Path
Set-Location (Join-Path $RepoRoot "webui\backend")
& (Join-Path $RepoRoot ".venv-console\Scripts\python.exe") -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
$RepoRoot = (Get-Location).Path
Set-Location (Join-Path $RepoRoot "webui\frontend")
npm run dev -- --hostname 127.0.0.1 --port 3100
```

Open `http://127.0.0.1:3100/`.

<h3>Try the synthetic example</h3>

With the service running:

```bash
REPO_ROOT="$(pwd)"
BASE_URL=http://127.0.0.1:8000 OUTPUT_DIR="$REPO_ROOT/examples/output/research-console-tour" \
  bash "$REPO_ROOT/examples/research-console/api_walkthrough.sh"
```

```powershell
$RepoRoot = (Get-Location).Path
& (Join-Path $RepoRoot "examples\research-console\api_walkthrough.ps1") `
  -BaseUrl http://127.0.0.1:8000 -OutputDir (Join-Path $RepoRoot "examples\output\research-console-tour")
```

<h3>Expected result</h3>

Health succeeds; synthetic participant `SYNTH-P01` has one LOW visit block;
tracker/context JSON is printed; and `research-bundle.zip` is written. Missing
manifest status is deliberate and must not be interpreted as a complete study.

<h3>Verify</h3>

```bash
curl --fail http://127.0.0.1:8000/health
```

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Backend and frontend suites are listed under operations below.

<h3>Stop and clean up</h3>

Press Ctrl-C in the combined launcher or both native-development terminals.
After services stop, remove only the dedicated example directories:

```bash
REPO_ROOT="$(pwd)"
rm -rf -- "$REPO_ROOT/examples/output/research-console-service" "$REPO_ROOT/examples/output/research-console-tour"
```

```powershell
$RepoRoot = (Get-Location).Path
Remove-Item -Recurse -Force (Join-Path $RepoRoot "examples\output\research-console-service"), (Join-Path $RepoRoot "examples\output\research-console-tour") -ErrorAction SilentlyContinue
```

<h3>Troubleshooting</h3>

A 409 on rerun means the CSV hash or visit/workload cell already exists; use a
fresh dedicated database. If 8000 or 3100 is occupied, stop the other process
or pass different launcher ports and align `NEXT_PUBLIC_API_URL`. PowerShell
execution-policy or quoting failures can be avoided by using PowerShell 7 and
the call operator `&` with `Join-Path`. See the [Research Console guide](examples/research-console/README.md).

<a id="quick-start-suas"></a>
## 7. Synthetic sUAS quick start

<h3>Prerequisites</h3>

The CLI needs Python 3.12+. The browser service adds Node 20+, npm, and a
browser. `install_suas.sh` and `run_suas.sh` are Linux/WSL2 contracts; native
Windows PowerShell may run the CLI and may call a service hosted in WSL2.

<h3>Install</h3>

Linux/WSL2 service installation:

```bash
REPO_ROOT="$(pwd)"
MATB_VENV="$REPO_ROOT/.venv-suas" bash "$REPO_ROOT/scripts/install_suas.sh"
```

Native Windows CLI-only installation:

```powershell
$RepoRoot = (Get-Location).Path
python -m venv (Join-Path $RepoRoot ".venv-suas")
& (Join-Path $RepoRoot ".venv-suas\Scripts\python.exe") -m pip install -r (Join-Path $RepoRoot "requirements-dev.txt")
```

<h3>Configure</h3>

The service defaults to validated scenarios in `scenarios/suas/`, loopback
ports 8000/3100, and a dedicated output root. A non-loopback bind is refused
unless `MATB_FRONTEND_ORIGINS` is explicitly set. Do not expose the development
service to an untrusted network.

```bash
REPO_ROOT="$(pwd)"
export MATB_SIMULATION_SCENARIO_DIR="$REPO_ROOT/scenarios/suas"
```

```powershell
$RepoRoot = (Get-Location).Path
$env:MATB_SIMULATION_SCENARIO_DIR = Join-Path $RepoRoot "scenarios\suas"
```

<h3>Run</h3>

Linux/WSL2 browser service:

```bash
REPO_ROOT="$(pwd)"
MATB_VENV="$REPO_ROOT/.venv-suas" bash "$REPO_ROOT/scripts/run_suas.sh" \
  --data-dir "$REPO_ROOT/examples/output/suas-service"
```

On native Windows, start that command inside WSL2, then open the loopback URL
from Windows or use the PowerShell walkthrough. The POSIX launcher owns service
startup, shutdown, process groups, and Unix permissions.

<h3>Try the synthetic example</h3>

Fast CLI-only Linux/WSL2 tour:

```bash
REPO_ROOT="$(pwd)"
bash "$REPO_ROOT/examples/suas-simulator/cli_demo.sh" "$REPO_ROOT/examples/output/suas-simulator"
```

Native Windows equivalent, using the same committed scenario:

```powershell
$RepoRoot = (Get-Location).Path
$Python = Join-Path $RepoRoot ".venv-suas\Scripts\python.exe"
$Scenario = Join-Path $RepoRoot "scenarios\suas\reference_area_search.yaml"
$Output = Join-Path $RepoRoot "examples\output\suas-simulator"
& $Python -m matb_integration.suas.cli validate $Scenario
& $Python -m matb_integration.suas.cli record $Scenario --block PRACTICE --ticks 10 --session-id SYNTH-SUAS-01 --output $Output
& $Python -m matb_integration.suas.cli verify $Output
```

The service API tour is available in Bash and PowerShell; it uses a lease only
in the `X-Simulation-Controller` header and never submits an aircraft command.

<h3>Expected result</h3>

The CLI output directory contains `events.jsonl`, `manifest.json`,
`metrics.json`, `debrief.json`, `replay-verification.json`, and
`checksums.sha256`. The service exposes observer-safe state and sealed terminal
artifact metadata. A controller disconnect pauses; it never auto-resumes.

<h3>Verify</h3>

```bash
REPO_ROOT="$(pwd)"
"$REPO_ROOT/.venv-suas/bin/python" -m matb_integration.suas.cli verify "$REPO_ROOT/examples/output/suas-simulator"
```

```powershell
$RepoRoot = (Get-Location).Path
& (Join-Path $RepoRoot ".venv-suas\Scripts\python.exe") -m matb_integration.suas.cli verify (Join-Path $RepoRoot "examples\output\suas-simulator")
```

<h3>Stop and clean up</h3>

Press Ctrl-C in the launcher. After it exits, remove only the chosen demo roots:

```bash
REPO_ROOT="$(pwd)"
rm -rf -- "$REPO_ROOT/examples/output/suas-service" "$REPO_ROOT/examples/output/suas-simulator"
```

```powershell
$RepoRoot = (Get-Location).Path
Remove-Item -Recurse -Force (Join-Path $RepoRoot "examples\output\suas-simulator") -ErrorAction SilentlyContinue
```

<h3>Troubleshooting</h3>

Recording refuses a nonempty output directory; select a fresh directory.
Missing frontend build or venv errors mean `install_suas.sh` was not completed.
WSL2 users should keep the clone and data in a WSL filesystem for predictable
permissions and verify Windows-to-WSL loopback forwarding. See the
[sUAS walkthrough](examples/suas-simulator/README.md).

<a id="quick-start-sms"></a>
## 8. FAC ISR SMS quick start

<h3>Prerequisites</h3>

Use Node.js 22.x and npm. Docker with Linux-container support is needed only
for `build:offline` and container verification, not for the package tour.

<h3>Install</h3>

```bash
REPO_ROOT="$(pwd)"
cd "$REPO_ROOT/SMS"
npm ci
```

```powershell
$RepoRoot = (Get-Location).Path
Set-Location (Join-Path $RepoRoot "SMS")
npm ci
```

`npm ci` may need the network on a development workstation; an isolated host
must have the locked dependency cache staged beforehand.

<h3>Configure</h3>

The package tour requires no credentials, signing material, telemetry, or
service configuration. For the Docker deployment, institutions supply
`SMS_DATA_DIR`, read-only `SMS_PACKAGE_DIR`, and `SMS_TLS_DIR` through approved
custody. `SMS_EDGE_PORT` changes only the loopback host port. Do not create
demonstration keys or place controlled material in the repository.

<h3>Run</h3>

```bash
REPO_ROOT="$(pwd)"
bash "$REPO_ROOT/examples/sms-platform/run.sh"
```

```powershell
$RepoRoot = (Get-Location).Path
& (Join-Path $RepoRoot "examples\sms-platform\run.ps1")
```

The runners install locked dependencies, compile all nine packages, and print
the deterministic package tour.

<h3>Try the synthetic example</h3>

After the first build, repeat the network-free executable directly:

```bash
REPO_ROOT="$(pwd)"
cd "$REPO_ROOT/SMS"
node ../examples/sms-platform/package-tour.mjs
```

```powershell
$RepoRoot = (Get-Location).Path
Set-Location (Join-Path $RepoRoot "SMS")
node ..\examples\sms-platform\package-tour.mjs
```

<h3>Expected result</h3>

One JSON document contains the nine package keys. The synthetic hard
requirement deliberately leaves `safetyKernel.status` blocked, and
`research.nonDispatchable` remains true. No service, decision, release, or
operational readiness is created.

<h3>Verify</h3>

```bash
REPO_ROOT="$(pwd)"
cd "$REPO_ROOT/SMS"
npm test
npm run typecheck
npm run verify:no-c2
npm run verify:data-separation
```

```powershell
$RepoRoot = (Get-Location).Path
Set-Location (Join-Path $RepoRoot "SMS")
npm test
npm run typecheck
npm run verify:no-c2
npm run verify:data-separation
```

Run Docker/offline verification only on Linux, WSL2, or a Linux-container
runtime with all pinned inputs staged. An offline *runtime* does not imply an
unstaged build can access missing dependencies or images.

<h3>Stop and clean up</h3>

The package tour starts no service. If you started a development server, use
Ctrl-C. Generated `SMS/node_modules/` and `SMS/packages/*/dist/` are local
products; inspect `git status` and remove only those known generated paths when
you intentionally want a clean install. Never delete controlled data or a
shared Docker volume as part of example cleanup.

<h3>Troubleshooting</h3>

An engine warning means Node is not 22.x. Docker-daemon or missing-base-image
errors belong to the staged build boundary. Evidence verification can fail on
hash mismatch, tamper, missing source artifacts, or expiry; restore approved
evidence or obtain a current authorized release—never bypass freshness,
signature, or hash checks. Readiness remaining false after tests pass is an
expected separation of technical verification from institutional acceptance.
See the [SMS guide](examples/sms-platform/README.md).

<a id="quick-start-legacy-monitor"></a>
## 9. Legacy monitor quick start

<h3>Prerequisites</h3>

Use Python 3.12+ and a terminal. The published launchers force headless mode,
seed 42, and the minimum supported 0.05-second event delay.

<h3>Install</h3>

```bash
REPO_ROOT="$(pwd)"
python3 -m venv "$REPO_ROOT/.venv-legacy"
"$REPO_ROOT/.venv-legacy/bin/python" -m pip install -r "$REPO_ROOT/requirements.txt"
```

```powershell
$RepoRoot = (Get-Location).Path
python -m venv (Join-Path $RepoRoot ".venv-legacy")
& (Join-Path $RepoRoot ".venv-legacy\Scripts\python.exe") -m pip install -r (Join-Path $RepoRoot "requirements.txt")
```

<h3>Configure</h3>

No network or external service is required. For manual experiment runs, use
pseudonymous IDs and a dedicated output directory. The example launchers
already use `SYNTH-P01` and `SYNTH-S01`.

<h3>Run</h3>

With the selected venv active, choose one mode:

```bash
REPO_ROOT="$(pwd)"
PATH="$REPO_ROOT/.venv-legacy/bin:$PATH" bash "$REPO_ROOT/examples/legacy-monitor/run.sh" combined
```

```powershell
$RepoRoot = (Get-Location).Path
$env:PATH = "$(Join-Path $RepoRoot '.venv-legacy\Scripts');$env:PATH"
& (Join-Path $RepoRoot "examples\legacy-monitor\run.ps1") -Mode combined
```

Available modes are `uav`, `fighter`, `combined`, and `experiment`.

<h3>Try the synthetic example</h3>

```bash
REPO_ROOT="$(pwd)"
PATH="$REPO_ROOT/.venv-legacy/bin:$PATH" bash "$REPO_ROOT/examples/legacy-monitor/run.sh" experiment "$REPO_ROOT/examples/output/legacy-monitor"
```

```powershell
$RepoRoot = (Get-Location).Path
$env:PATH = "$(Join-Path $RepoRoot '.venv-legacy\Scripts');$env:PATH"
& (Join-Path $RepoRoot "examples\legacy-monitor\run.ps1") -Mode experiment -OutputDir (Join-Path $RepoRoot "examples\output\legacy-monitor")
```

<h3>Expected result</h3>

The terminal ends with `Simulation complete!`. Experiment mode writes JSONL
events and summary output only under the caller-selected directory. Other modes
do not receive a research-output directory.

<h3>Verify</h3>

```bash
REPO_ROOT="$(pwd)"
"$REPO_ROOT/.venv-legacy/bin/python" -m pytest "$REPO_ROOT/tests" -q
```

```powershell
$RepoRoot = (Get-Location).Path
& (Join-Path $RepoRoot ".venv-legacy\Scripts\python.exe") -m pytest (Join-Path $RepoRoot "tests") -q
```

<h3>Stop and clean up</h3>

Ctrl-C returns normally. Remove only the dedicated experiment directory:

```bash
REPO_ROOT="$(pwd)"
rm -rf -- "$REPO_ROOT/examples/output/legacy-monitor"
```

```powershell
$RepoRoot = (Get-Location).Path
Remove-Item -Recurse -Force (Join-Path $RepoRoot "examples\output\legacy-monitor") -ErrorAction SilentlyContinue
```

<h3>Troubleshooting</h3>

If the launcher resolves the wrong Python, activate the selected venv or put
its `bin`/`Scripts` directory first on `PATH`. Use `--headless` on noninteractive
terminals. See the [legacy guide](examples/legacy-monitor/README.md).

<a id="module-catalog"></a>
## 10. Module catalog

Each table points to the smallest runnable example. Detailed scientific,
endpoint, release, and evidence explanations stay in their specialist guides.

### Python/OpenMATB research modules

| Module | Purpose | User | Inputs → outputs | Runtime | Example | Verification | Limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `matb_integration/scenario_builder.py` | Generate LOW/MEDIUM/HIGH counterbalanced scenarios | Study designer | Protocol, duration, seed → OpenMATB text scenarios | Python | [OpenMATB tour](examples/openmatb-research/README.md) | `pytest tests/matb_integration -q` | Generated tasks require external OpenMATB for presentation |
| `matb_integration/scenario_manifest.py` | Hash scenarios and validate session provenance | Data steward | Scenario/tags/expected probes → adjacent manifest and validation issues | Python | OpenMATB tour | Same suite | Hash integrity does not establish protocol validity or consent |
| `matb_integration/log_converter.py` | Convert OpenMATB CSV into canonical metrics | Research analyst | CSV + pseudonym/workload → JSONL metrics | Python | OpenMATB tour | Same suite | Input quality and missing tasks constrain inference |
| `matb_integration/questionnaires/` | EN/ES NASA-TLX, Bedford, ISA, and SAGAT assets | Study designer | Controlled text/YAML → configured questionnaire/probe content | External OpenMATB or sUAS loader | OpenMATB and sUAS tours | Questionnaire/SAGAT tests | Scales must be administered under an approved protocol |
| `matb_integration/analysis/` | Descriptive outputs plus frequentist MixedLM/rmcorr/rmANOVA/FDR and Bayesian PyMC sensitivity engines | Statistician | `/metrics/long` and `/fits` JSON arrays → versioned artifacts | Python; PyMC sampling is optional/slow | [OpenMATB analysis commands](examples/openmatb-research/README.md) | Analysis tests | Small/incomplete datasets may be not estimable; Bayesian diagnostics govern interpretation |
| `matb_integration/suhir/` | Fit Suhir DEPDF parameters and mission-outcome research summaries | Human-factors researcher | Three workload records → G0/P0/tau0 and curves | Python/SciPy | OpenMATB tour | Suhir tests; [DEPDF guide](matb_integration/suhir/README.md) | Within-participant comparative model; three levels exactly identify parameters; not certified |
| `matb_integration/screen/` | Score reaction/2-back/tracking tasks and map exploratory HCF/F/F0 | Researcher | Raw trials/cohort → scores and exploratory mapping | Python through backend | Research Console `/screen` | Screen/backend tests | Not a diagnostic, selection, or validated predictive instrument |

### Research Console

| Module | Purpose | User | Inputs → outputs | Runtime | Example | Verification | Limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `webui/backend/` tracker and ingestion | Pseudonymous participant/visit grid, CSV/manifest checks, fits | Data steward | CSV + optional manifest → SQLite block/provenance rows | FastAPI, Python 3.12+, port 8000 | [Console walkthrough](examples/research-console/README.md) | `cd webui/backend && python -m pytest -q` | Duplicate/fill guards are data-quality controls, not consent |
| `webui/backend/` analysis and export | Cache frequentist/Bayesian results and build reproducible bundles | Analyst | Stored metrics/fits/figures → analysis records and ZIP | FastAPI/background PyMC | Console walkthrough | Backend analysis/export tests | Export remains research data under owner custody |
| `webui/frontend/` tracker, ingestion, and visualization | Browser grid, upload, descriptive charts | Research staff | Backend JSON → interactive local UI/PNG | Next.js, Node 20+, port 3100 | Console walkthrough | `npm test`, `npm run typecheck`, `npm run build` | Descriptive plots are not inferential conclusions |
| `webui/frontend/` screen, analysis, and export | Administer baseline screen, review analyses, request bundle | Research staff | Raw trials/backend artifacts → UI summaries/export request | Browser/Next.js | Console walkthrough | Screen is exploratory; browser is not a clinical device |

Endpoint and screen contracts are maintained in the [backend guide](webui/backend/README.md)
and [frontend guide](webui/frontend/README.md).

### Synthetic sUAS simulator

| Module | Purpose | User | Inputs → outputs | Runtime | Example | Verification | Limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `matb_integration/suas/scenarios/` | Validate YAML schemas, manifests, and workload profiles | Scenario author | Synthetic YAML → immutable scenario definition | Python 3.12+ | [sUAS CLI tour](examples/suas-simulator/README.md) | `python -m matb_integration.suas.cli validate ...` | Synthetic coordinates and conditions only |
| `matb_integration/suas/engine/` | Deterministic clock, route, energy, link, sensor, separation, and reducer logic | Simulator developer | Scenario + supervisory commands → world state/events | Python, no service required | sUAS CLI tour | `pytest tests/suas -q` | No real vehicle adapter or autonomous dispatch |
| `matb_integration/suas/` session/lifecycle | Prepare, start, pause, resume, finish, interrupt, and explicitly recover sessions | Research operator | Pseudonym + visit + scenario → audited lifecycle | Python/FastAPI | sUAS API tour | Backend and sUAS tests | Recovery is marked as deviation; interruption never auto-resumes |
| `webui/backend/app/routers/simulation.py` controller lease | Enforce one mutation controller | Operator | One-time lease header → authorized lifecycle mutation | Loopback FastAPI | sUAS API tour | Lease is sensitive; never log it or place it in a URL |
| `webui/backend/app/websocket/simulation.py` observer stream | Ordered resync plus redacted, lease-free observer state | Observer/researcher | Sequence cursor → snapshot/envelopes | WebSocket | Browser tour | Observer cannot mutate; hidden truth/probes stay private |
| `matb_integration/suas/recording/` replay | Append events/checkpoints and deterministically replay them | Auditor/researcher | Events + manifest → replay verification | Python CLI | sUAS CLI tour | Verification proves internal consistency, not real-world validity |
| `matb_integration/suas/metrics/` debrief | Compute terminal research metrics and debrief | Researcher | Sealed terminal state/events → metrics/debrief JSON | Python | sUAS CLI tour | Debrief is a research artifact, not an operational judgment |
| `matb_integration/suas/recording/artifacts.py` | Seal manifest, checksums, public metadata, and private artifacts | Data custodian | Session records → relative-path hashed artifact set | Python/local filesystem | sUAS CLI tour | Keep artifact root owner-only; hashes do not deidentify content |

### FAC ISR SMS applications

| Module | Purpose | User | Inputs → outputs | Runtime | Example | Verification | Limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SMS/apps/edge-api/` | Local Fastify package intake, gates, missions, postflight, audit, safe mode, and data boundaries | Safety reviewer/deployment custodian | Verified local packages + read-only telemetry → SQLite/audit/API results | Node 22.x; hardened Linux container for offline deployment | [SMS tour](examples/sms-platform/README.md) | Workspace tests and `/healthz` | Non-C2, internet-disabled runtime; no dispatch authority |
| `SMS/apps/console/` | Accessible React console for evidence, risk, telemetry, checklists, and research boundaries | Human reviewer | Edge API results → review views | Node/Vite; ports 5173 dev or 4173 controlled preview | SMS guide | unit, a11y, Playwright E2E | Displaying a pass does not record human acceptance |

### FAC ISR SMS packages

| Module | Purpose | User | Inputs → outputs | Runtime | Example | Verification | Limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SMS/packages/evidence/` | Canonical JSON, SHA-256, source records, claims, manifests, downgrade rejection | Evidence custodian | Controlled local sources → verifiable claims/manifests | Node 22.x | SMS package tour | workspace tests | Trust, authority, scope, and freshness remain external controls |
| `SMS/packages/energy/` | Unit-labelled mission-energy and reserve evaluation | Performance analyst | Evidence-backed aircraft/segment facts → deterministic energy result | Node 22.x | SMS package tour | workspace/property tests | Component result is not authorization |
| `SMS/packages/fleet/` | Configuration, capability, maintenance release, and crew qualification facts | Fleet reviewer | Accepted evidence + fleet state → capability evaluation | Node 22.x | SMS package tour | workspace tests | Missing qualification/release evidence fails closed |
| `SMS/packages/geo/` | Coordinates, routes, terrain, visibility, weather, airspace, offline packages, flight-plan drafts | Geo reviewer | Controlled geo package → deterministic geo facts/draft | Node 22.x | SMS package tour | workspace tests | No transmitter or official geospatial authority |
| `SMS/packages/human-performance/` | Duty, qualification, fatigue, workload, alert-load, CRM boundaries | Human-factors reviewer | Explicit policy + status → bounded assessment | Node 22.x | SMS package tour | privacy/contracts tests | Not a medical diagnosis or fitness decision |
| `SMS/packages/research/` | Protocol, ethics/consent, instruments, MATB/sensors, replay, aggregation, deidentified export | Research steward | Pseudonymous consented events → non-dispatchable research export | Node 22.x | SMS package tour | boundary/export tests | Strictly separated from operational release |
| `SMS/packages/safety-kernel/` | Deterministic applicability, freshness, dependencies, risk, lifecycle, gates, audit | Accountable reviewer | Evidence-backed facts → pass/blocked/unknown decisions | Node 22.x | SMS package tour | golden/property/integration tests | Unknown hard evidence fails closed; never grants acceptance |
| `SMS/packages/sms/` | Hazards, SPIs, audits, CAPA, ERP, management of change | Safety organization | Organizational records → controlled SMS evaluations | Node 22.x | SMS package tour | workspace tests | Incomplete accountable evidence remains blocked |
| `SMS/packages/telemetry/` | Canonicalize and replay delayed/dropout telemetry with retention provenance | Observer/analyst | Read-only events → canonical/replayed stream | Node 22.x | SMS package tour | contract/replay tests | Deliberately has no command path |

### FAC ISR SMS tools, release, and acceptance

| Module/workflow | Purpose | User | Inputs → outputs | Runtime | Example | Verification | Limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `SMS/tools/map-packager/` | Inspect/build manifests and controlled sign/verify of offline geo packages | Geo/release custodian | Directory + metadata + controlled signing/verification input → package manifest | Node 22.x | SMS guide CLI inventory | tool tests and `verify` | Signing requires externally controlled material and authority |
| `SMS/tools/research/` | Record acquisition queries, acquire/copy/extract sources, verify hashes/offline/no-C2 | Evidence researcher | Registered source artifacts → provenance/query records | Node 22.x | SMS guide CLI inventory | tool tests; `verify:evidence-offline` | Search leads are not evidence until acquired and verified |
| `build:offline` / `verify:offline` | Build/test Linux image and assemble/verify a disconnected transfer bundle | Deployment custodian | Locked dependencies, pinned image, local evidence → OCI archive/bundle | Linux containers/Docker | [SMS offline guide](examples/sms-platform/README.md) | `npm run verify:offline` | Build inputs must be staged; offline describes runtime/transfer boundary |
| `release:manifest` / `release:sign` / `release:verify` | Generate SBOM, scan/test report, canonical manifest, controlled signature, integrity result | Release custodian | Versioned artifacts + external signing input → release evidence | Node 22.x | SMS guide | `npm run release:verify` | Signature/integrity is not operational acceptance |
| `verify:no-c2` / `verify:data-separation` | Inspect absence of command paths and research/operations separation | Security/research reviewer | Built source/workspaces → verification result | Node 22.x | SMS guide | named npm scripts | Scope is repository software, not every deployment control |
| `verify:matrix` / `verify:acceptance` | Execute evidence matrix and validate controlled acceptance state | Independent reviewer | Release/evidence records + exact UTC → report/readiness state | Node 22.x | SMS guide | named npm scripts | Matrix can pass while readiness remains false |
| `acceptance:packets` | Generate deterministic unsigned reviewer packets | Review coordinator | Empty output directory + exact `--as-of` UTC + optional approved scope → packets | Node 22.x | SMS guide | `npm run verify:acceptance` | Packets are not decisions and remain unsigned |
| `acceptance:record` | Intake a human-supplied, controlled institutional decision | Authorized records custodian | Current packet + real authorized decision → controlled record | Node 22.x; explicit separate action | No synthetic decision example | dry run then institutional process | Never fabricate reviewer, outcome, timestamp, evidence, or signature |

The user-invoked SMS build and verification inventory from `SMS/package.json`
is below. Parameterized release and packet commands still require the arguments
and custody described in the [SMS guide](examples/sms-platform/README.md).

```bash
cd SMS
npm run build
npm run build:packages
npm run build:tools
npm run build:apps
npm run build:research
npm test
npm run typecheck
npm run lint
npm run build:offline
npm run verify:offline
npm run verify:evidence-offline
npm run verify:no-c2
npm run verify:data-separation
npm run release:manifest
npm run release:sign
npm run release:verify
npm run verify:matrix
npm run acceptance:packets
npm run verify:acceptance
npm run verify:all
```

The remaining manifest scripts are automatic npm lifecycle hooks: `pretest`
builds before `test`; `preverify:evidence-offline` builds the research tool;
`preverify:no-c2` builds the edge API; and `preverify:data-separation` builds
the research package and edge API. The `acceptance:record` script (invoked only
as `npm run acceptance:record` by an authorized custodian) is inventory, not a
routine instruction: it is a separate, potentially mutating decision-intake
action that requires a current packet and genuine institution-controlled human
input. Do not invoke it merely because it is documented.

### Legacy aircraft monitor

| Module/mode | Purpose | User | Inputs → outputs | Runtime | Example | Verification | Limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `aircraft_monitor/` `uav` | Deterministic UAV terminal demonstration | Developer/educator | Seeded model → terminal event stream | Python/Rich | [Legacy guide](examples/legacy-monitor/README.md) | Python tests | Legacy synthetic demonstration, not live monitoring |
| `aircraft_monitor/` `fighter` | Deterministic fighter terminal demonstration | Developer/educator | Seeded model → terminal event stream | Python/Rich | Legacy guide | Python tests | Contains simulated combat vocabulary but no weapon/control path |
| `aircraft_monitor/` `combined` | Joint terminal demonstration | Developer/educator | Both seeded models → combined stream | Python/Rich | Legacy guide | Python tests | Not the active research collection surface |
| `aircraft_monitor/` `experiment` | MATB-inspired human-factors protocol | Research developer | Pseudonym, session, modality, seed → JSONL/summary | Python/Rich | Legacy guide | Research tests | Use synthetic or approved pseudonyms; not OpenMATB |

<a id="operations-and-maintenance"></a>
## 11. Operations and maintenance

### Verification suites

Run only the suites for the workflow you changed, then the documentation gate:

```bash
python -m pytest tests/test_scenario_builder.py tests/test_scenario_manifest.py \
  tests/test_log_converter.py tests/analysis_stats tests/suhir tests/screen -q
python -m pytest tests/suas -q
cd webui/backend && python -m pytest -q
cd ../../webui/frontend && npm test && npm run typecheck && npm run build
cd ../../SMS && npm test && npm run typecheck && npm run lint
cd .. && python -m pytest tests/documentation/test_documentation.py -q
python scripts/verify_documentation.py
```

Browser E2E/a11y suites additionally require installed Chromium/Playwright
assets. The SMS offline build additionally requires Docker, the pinned base
image, locked dependencies, and institution-controlled inputs.

### Ports and process boundaries

| Service | Default | Boundary |
| --- | --- | --- |
| Research/sUAS FastAPI | `127.0.0.1:8000` | Loopback; health at `/health` |
| Research/sUAS Next.js | `127.0.0.1:3100` | Loopback; tracker `/`, sUAS `/mission/setup` |
| SMS edge deployment | `127.0.0.1:8443` host default | HTTPS in controlled container deployment |
| SMS Vite console | 5173 dev / 4173 controlled preview | Development/reviewer UI only |

Keep loopback defaults. A non-loopback research/sUAS bind requires explicit
`MATB_FRONTEND_ORIGINS`; it also requires the institution's network,
authentication, privacy, and threat controls beyond this development launcher.

### Configuration

| Variable | Scope | Meaning |
| --- | --- | --- |
| `MATB_VENV` | POSIX install/launcher | Repository-local Python environment path |
| `MATB_DB_PATH` | Research/sUAS backend | Dedicated SQLite path |
| `MATB_SIMULATION_OUTPUT_DIR` | sUAS | Owner-only sealed artifact root |
| `MATB_SIMULATION_SCENARIO_DIR` | sUAS | Validated YAML scenario directory |
| `MATB_FRONTEND_ORIGINS` | Research/sUAS | Explicit allowed browser origins |
| `NEXT_PUBLIC_API_URL` | Research frontend | Browser-visible FastAPI base URL |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE` | Browser tests | Approved Chromium executable |
| `SMS_DATA_DIR`, `SMS_PACKAGE_DIR`, `SMS_TLS_DIR` | SMS container | Controlled writable data, read-only packages, and TLS custody roots |
| `SMS_EDGE_PORT` | SMS container | Loopback host port override |
| `SMS_EVIDENCE_VERIFY_AS_OF` | SMS evidence verification | Exact authorized UTC verification instant |
| `SMS_RESEARCH_DATABASE_URL`, `SMS_RESEARCH_DATA_DIR` | SMS separation | Separate research store locations |

Signing/TLS/key identifiers and inputs are release-custodian concerns. Never
put their values in source, examples, shell history, logs, or support tickets.

### Generated data and constrained cleanup

Expected generated paths include selected `examples/output/...` directories,
Python venvs, SQLite databases, sUAS logs/artifacts, research bundle ZIPs,
`webui/frontend/.next/`, Node `node_modules/`, TypeScript `dist/` trees, and SMS
offline/release outputs. Before deleting anything, stop writers, resolve the
exact path, confirm it is a dedicated example/build path, and preserve study,
controlled evidence, release, or acceptance records according to policy.

Offline-capable means the installed runtime can operate without Internet. It
does not mean the first dependency install, a Docker build without a staged
base image, or verification without registered evidence can succeed offline.

<a id="troubleshooting"></a>
## 12. Troubleshooting by symptom

| Symptom | Check and safe response |
| --- | --- |
| Installer rejects Python or Node | Use Python 3.12+ for sUAS/repository Python, Node 20+ for the Research Console launcher, and Node 22.x for `SMS/`; recreate only that workflow's venv/install. |
| Python module is missing | Confirm the selected venv's Python is running (`python -c "import sys; print(sys.executable)"`) and install the matching requirements; do not install globally to mask it. |
| External OpenMATB cannot be found | It is not vendored. Point `install_to_openmatb.py` at a separate checkout containing `includes/`. |
| OpenMATB flickers or Pyglet/display fails | This is the external desktop/X11 boundary. Start windowed, validate Pyglet in its venv, and on headless Linux validate Xvfb and `DISPLAY`. sUAS needs neither X11 nor Pyglet. |
| PowerShell script is blocked or a path with spaces fails | Use PowerShell 7+, invoke scripts with `&`, build paths with `Join-Path`, and use an institution-approved execution policy; do not disable security controls globally. |
| WSL2 cannot reach a service or changes permissions | Run POSIX launchers and data roots in the WSL filesystem, confirm the service binds loopback/selected port, and verify Windows-to-WSL loopback behavior. Do not replace `chmod`/UID controls with broad permissions. |
| Port 8000 or 3100 is occupied | Stop the known process or pass unique `--backend-port`/`--frontend-port`; update `NEXT_PUBLIC_API_URL` and allowed origins consistently. |
| Browser/E2E test cannot find Chromium | Install the repository-supported Playwright browser asset or set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to an approved local binary. Unit/API/CLI tests do not require it. |
| Docker is unavailable | Use the Node package tour and non-container suites, or provision an approved Linux-container runtime. Do not call an unbuilt/unverified directory an offline bundle. |
| Evidence is expired, missing, or reports tamper/hash mismatch | Stop the workflow, preserve the diagnostic, and obtain current authorized evidence through custody procedures. Never weaken freshness, signature, source-authority, or hash checks. |
| Tests pass but readiness remains blocked | Expected: automation verifies technical contracts; `operationalReady=false` remains until every scoped institutional review is current and an authorized human decision is recorded. |

<a id="security-privacy-and-governance"></a>
## 13. Security, privacy, research, and governance

- No-C2 and non-kinetic are architectural boundaries: telemetry is read-only,
  simulations are synthetic, and no package may become an aircraft/weapon
  command, targeting, autonomous-flight, or dispatch path.
- Use pseudonymous participant/session identifiers. Store linkage keys, consent,
  health information, raw identity, and exports only in institution-controlled
  locations with least privilege, retention, and deletion rules.
- NASA-TLX, Bedford, ISA, SAGAT, screen mappings, statistical models, and DEPDF
  results are research instruments. They are not clinical findings, individual
  fitness decisions, airworthiness findings, or operational authorizations.
- Controlled evidence must retain source authority, exact scope, provenance,
  SHA-256/integrity data, version, and freshness. Time-dependent verification
  uses an explicit exact UTC instant; never substitute local ambiguous time.
- Release signatures, SBOMs, manifests, no-C2/data-separation checks, technical
  tests, and matrices are necessary evidence, not acceptance. A qualified human
  institution must review applicable regulation/translation, operational risk,
  emergency response, cybersecurity/deployment, official geo data,
  human-factors, research separation, training, and safety-promotion scopes.
- Generate reviewer packets unsigned. Run decision intake only with a current
  packet and authentic, authorized, controlled human decision. Never fabricate
  identities, approvals, timestamps, evidence, outcomes, or signatures.

For advanced detail, use the [research evidence review](docs/research/military-aviation-platform/research_evidence_review.md),
[scale validation](docs/research/scales/sagat_validation.md),
[sUAS verification](docs/implementation/suas-c2-v1-verification.md),
[SMS verification matrix](SMS/docs/release/verification-matrix.md),
[known limitations](SMS/docs/release/known-limitations.md), and
[state-aviation acceptance checklist](SMS/docs/release/state-aviation-acceptance-checklist.md).

<a id="repository-map"></a>
## 14. Repository map

| Path | Maintained role |
| --- | --- |
| `matb_integration/` | Research protocol bridge, metrics, statistics, DEPDF, screen, and deterministic sUAS libraries |
| `scenarios/military_aviation/` | OpenMATB-compatible study scenarios |
| `scenarios/suas/` | Synthetic sUAS YAML scenarios |
| `webui/backend/` | Research/sUAS FastAPI service, persistence, analysis, and exports |
| `webui/frontend/` | Research tracker/analysis and sUAS browser console |
| `SMS/apps/`, `SMS/packages/`, `SMS/tools/` | Offline SMS applications, contracts, and release/evidence tools |
| `SMS/docs/` | Controlled provenance, regulatory research, release evidence, and acceptance guidance |
| `aircraft_monitor/` | Retained synthetic terminal demonstration |
| `examples/` | Safe, deterministic, pseudonymous walkthroughs |
| `tests/` | Python integration, simulator, application, and documentation checks |
| `docs/` | Scientific reviews and design/implementation records |

<a id="glossary"></a>
## 15. Glossary

| Term | Meaning here |
| --- | --- |
| C2 | Command and control; intentionally absent from MATB operational boundaries |
| DEPDF | Double-exponential probability distribution function used for comparative human-nonfailure modeling |
| HCF / F/F0 | Exploratory human-capacity-factor mapping from the research screen |
| Manifest | Canonical metadata and hashes binding content to provenance |
| MATB | Multi-Attribute Task Battery human-factors paradigm |
| Non-dispatchable | Research data/result that cannot enter an operational-release decision |
| OpenMATB | External task-presentation runtime; not part of this repository |
| Operational readiness | Institution-controlled state that automation alone cannot grant |
| Pseudonym | Study identifier that omits direct identity; still potentially linkable research data |
| SMS | Safety Management System; here, the `SMS/` assurance workspace |
| sUAS | Small uncrewed aircraft system; here, a synthetic supervisory research simulator |

<a id="references"></a>
## 16. References and deeper guides

- [Examples and workflow chooser](examples/README.md)
- [Research Console overview](webui/README.md), [backend API](webui/backend/README.md), and [frontend screens](webui/frontend/README.md)
- [Suhir DEPDF guide](matb_integration/suhir/README.md)
- [Research evidence review](docs/research/military-aviation-platform/research_evidence_review.md) and [scale validation](docs/research/scales/sagat_validation.md)
- [Synthetic sUAS design](docs/superpowers/specs/2026-08-01-suas-c2-research-simulator-design.md) and [verification](docs/implementation/suas-c2-v1-verification.md)
- [SMS capability evidence register](SMS/docs/provenance/capability-evidence-register.jsonl), [verification matrix](SMS/docs/release/verification-matrix.md), and [known limitations](SMS/docs/release/known-limitations.md)

<a id="contributing"></a>
## 17. Contributing

Keep changes scoped to one workflow, preserve Linux/native-Windows/WSL2
boundaries, and add tests before behavior changes. Examples must be
deterministic, synthetic, pseudonymous, offline-safe after dependencies are
installed, and constrained to caller-selected output directories. Never commit
generated study data, credentials, private keys, controller leases, controlled
signatures, or fabricated acceptance decisions.

Before submitting documentation changes, run:

```bash
python -m pytest tests/documentation/test_documentation.py -q
python scripts/verify_documentation.py
```

Then run the relevant Python, frontend, or SMS suites listed above. Explain any
intentionally unavailable external runtime, browser asset, Docker input, or
controlled evidence; do not weaken a check to make it green.

<a id="license"></a>
## 18. License

MATB is provided under the [MIT License](LICENSE). The license does not certify
fitness for clinical, flight, defense, safety-critical, or operational use and
does not replace applicable law, institutional governance, ethics review, or
human acceptance.
