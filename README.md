# MATB — Human-Factors Research and Aviation Safety Assurance

[English](README.md) | [Español](README.es.md)

> Research and safety-assurance software only. MATB is not a clinical device,
> certified operational system, aircraft-control channel, weapon system, or
> substitute for accountable human approval.

MATB is a repository of related, independently usable workflows for aerospace
medicine, human-factors, aviation-safety, and supervisory sUAS research. You do
not need to install every workflow.

## Start here: choose a workflow

| Your goal | Start with | What you get |
| --- | --- | --- |
| Design workload blocks, run MATB sessions, convert logs, or fit DEPDF models | `matb_integration/` and `openmatb/` | Counterbalanced scenarios, manifests, metrics, and analysis-ready JSONL |
| Track participants and visits, visualize data, run statistics, and export a study bundle | `webui/` | A local FastAPI/Next.js Research Console with SQLite-backed provenance |
| Run a deterministic, non-kinetic supervisory sUAS study | `matb_integration/suas/` and `webui/` | Browser sessions, ISA/SAGAT/TLX/Bedford data, replay verification, and sealed artifacts |
| Evaluate offline safety-management, evidence, telemetry, and research-separation contracts | `SMS/` | TypeScript packages, a local console, deterministic checks, and offline-verification tooling |
| Explore the original terminal demonstrations | `aircraft_monitor/` | Seeded UAV, fighter, combined, and MATB-inspired experiment demos |

If you are new to the repository, read the relevant quick start below and use
synthetic or pseudonymous data first. The detailed specialist guides are linked
in [References and deeper guides](#references-and-deeper-guides).

## Safety, privacy, and research boundaries

- The OpenMATB and MATB workflows are research instruments. NASA-TLX, ISA,
  Bedford, SAGAT, signal-detection scores, neurocognitive scores, statistics,
  and DEPDF outputs are not clinical findings, fitness determinations,
  airworthiness findings, or operational authorizations.
- The native sUAS simulator is synthetic and non-kinetic. It has no real
  aircraft, weapons, targeting, real-world map, external telemetry, autonomous
  dispatch, or command-and-control path.
- The `SMS/` workspace is an offline safety-assurance and evidence system. A
  passing test, build, evidence matrix, or safety gate is not institutional
  operational approval. Its current release status remains non-operational
  until qualified human reviewers close the required acceptance scopes.
- Keep participant linkage keys, consent, health information, controlled
  evidence, signing material, TLS keys, controller leases, and institutional
  decisions outside the repository and under the owning institution's custody.
- Use pseudonymous participant and session identifiers such as `P01` or
  `SYNTH-P01`. Never put a controller lease in a URL, log, screenshot, or
  research export.

## Architecture and data flow

```text
OpenMATB task session
        │ CSV + scenario manifest
        ▼
matb_integration.log_converter ──► JSONL metrics ──► Suhir DEPDF/statistics
                                                        │
                                                        ▼
                                               Research Console/export bundle

Synthetic YAML ──► deterministic sUAS engine ──► observer-safe state
                                                   │
                                                   ▼
                                            replay/debrief artifacts

Signed local evidence + read-only telemetry ──► SMS edge API/safety kernel
                                                   │
                                                   ▼
                                             console/audit/offline checks
```

```text
MATB/
├── matb_integration/       Scenario, conversion, analysis, screen, and sUAS libraries
├── openmatb/               Tracked OpenMATB task runtime and plugins
├── scenarios/              Military-aviation and synthetic sUAS scenarios
├── webui/                  FastAPI backend and Next.js Research Console
├── SMS/                    Node/TypeScript safety-management monorepo
├── aircraft_monitor/       Retained Rich terminal demonstrations
├── scripts/                Install, launch, and offline-test helpers
├── tests/                  Python, integration, sUAS, and application tests
└── docs/                   Scientific, implementation, design, and verification detail
```

The research database and the SMS operational domain are separate concerns.
The SMS research package has explicit data-boundary checks, and the native
sUAS/telemetry surfaces are deliberately read-only with respect to real
aircraft.

## Prerequisites

Install only the dependencies for the workflow you plan to use.

| Dependency | Used by | Version or note |
| --- | --- | --- |
| Git | All workflows | Required to clone the repository |
| Python | MATB, OpenMATB, Research Console, sUAS, legacy monitor | Python 3.12+ is the supported baseline |
| Node.js and npm | Research Console frontend, sUAS launcher, SMS | Node 20+ for `webui/` and sUAS; Node 22.x for `SMS/` |
| Xvfb | OpenMATB on headless Linux | Required only when running the Pyglet desktop task runner without a display |
| Browser | Research Console and sUAS UI | Any supported local browser; Chromium/Playwright is additionally needed for browser gates |
| Docker | SMS offline image/bundle workflows | Linux containers and institution-controlled inputs are required |

Clone the repository:

```bash
git clone https://github.com/strikerdlm/MATB.git
cd MATB
```

On Windows, the Python and Node examples can run natively. The POSIX launchers,
Linux container entrypoints, Unix permission checks, and Xvfb procedures require
Linux, macOS, or WSL2.

## Quick start: MATB/OpenMATB research workflow

This is the main workflow for a human-factors study. It produces scenarios and
synthetic analysis without requiring a participant. The tracked `openmatb/`
directory is available for local development; `install_to_openmatb.py` can also
copy this repository's scenarios and questionnaires into a separate compatible
OpenMATB checkout.

### 1. Create the Python environment

```bash
python3 -m venv .venv-matb
.venv-matb/bin/python -m pip install --upgrade pip
.venv-matb/bin/python -m pip install -r requirements-dev.txt
.venv-matb/bin/python -m pip install -r openmatb/requirements.txt
```

`requirements-dev.txt` includes the Python analysis and backend dependencies.
The OpenMATB requirements add its task-runtime-specific packages.

### 2. Install the committed scenarios and questionnaires

```bash
.venv-matb/bin/python install_to_openmatb.py "$PWD/openmatb"
```

This copies the repository-owned military-aviation scenarios and questionnaire
assets into `openmatb/includes/`. To use an external checkout instead, replace
`"$PWD/openmatb"` with its path; it must contain an `includes/` directory.

### 3. Generate a new workload set when needed

The generator creates LOW, MEDIUM, and HIGH blocks plus adjacent deterministic
manifest files. Use a dedicated output directory so you do not overwrite the
committed scenarios:

```bash
mkdir -p exports
.venv-matb/bin/python -m matb_integration.scenario_builder \
  --output-dir exports/military-aviation \
  --block-duration 900 \
  --seed 42
```

The generated filenames are `low_workload.txt`, `medium_workload.txt`, and
`high_workload.txt`. The manifests record the seed, duration, workload level,
scenario hash, expected probes, and questionnaire configuration.

### 4. Configure and run one OpenMATB block

Edit [`openmatb/config.ini`](openmatb/config.ini) and start with:

```ini
language=en_EN
fullscreen=False
scenario_path=military_aviation/low_workload.txt
display_session_number=True
```

Run on a desktop:

```bash
cd openmatb
../.venv-matb/bin/python main.py
```

Run on headless Linux with Xvfb:

```bash
Xvfb :100 -screen 0 1920x1080x24 &
cd openmatb
DISPLAY=:100 ../.venv-matb/bin/python main.py
```

OpenMATB writes a timestamped CSV below `openmatb/sessions/`. Change
`scenario_path` to `military_aviation/medium_workload.txt` or
`military_aviation/high_workload.txt` for the other conditions. Start windowed
first; fullscreen can be re-enabled after the target machine is stable.

### 5. Convert a session CSV into metrics

```bash
cd ..
.venv-matb/bin/python -m matb_integration.log_converter \
  openmatb/sessions/<session>.csv \
  --participant P01 \
  --level LOW \
  --block low_workload \
  --output exports/P01_low.jsonl
```

The converter records SYSMON and COMM signal-detection metrics, reaction times,
NASA-TLX, Bedford, ISA, and SAGAT information when present. It writes one
structured JSONL record and uses a log-linear correction for d-prime.

### 6. Fit the Suhir DEPDF when a visit has three workload levels

```bash
.venv-matb/bin/python -m matb_integration.suhir.cli fit \
  --participant P01 \
  --low LOW.csv \
  --medium MEDIUM.csv \
  --high HIGH.csv \
  --source raw_tlx \
  --out exports/P01_suhir.json
```

The fit estimates `G0`, `P0`, and `tau0` from the three graded workload
records. Read the [DEPDF guide](matb_integration/suhir/README.md) before
citing the model: it is comparative and within-participant, and three levels
exactly identify the parameters rather than providing goodness-of-fit degrees
of freedom.

### 7. Run the standalone statistics CLI when needed

The CLI accepts JSON arrays returned by the Research Console's
`/metrics/long` and `/fits` endpoints:

```bash
.venv-matb/bin/python -m matb_integration.analysis.stats.cli run \
  --metrics-json metrics.json \
  --fits-json fits.json \
  --output exports/frequentist.json

.venv-matb/bin/python -m matb_integration.analysis.stats.cli bayes \
  --metrics-json metrics.json \
  --fits-json fits.json \
  --output exports/bayesian.json \
  --seed 20260604 \
  --draws 1000 \
  --tune 1000 \
  --chains 4
```

The frequentist engine provides MixedLM workload effects, visit trajectories,
repeated-measures correlation, DEPDF parameter drift, multiplicity handling,
effect sizes, confidence intervals, and provenance. The Bayesian command is a
separate sensitivity artifact; R-hat, effective sample size, and divergences
must be checked before interpretation.

## Quick start: MATB Research Console

The Research Console manages pseudonymous participants, six-visit study
tracking, CSV/manifest ingestion, descriptive visualization, statistics,
neurocognitive screening, and reproducible exports.

### 1. Install the backend and frontend

```bash
python3 -m venv .venv-webui
.venv-webui/bin/python -m pip install --upgrade pip
.venv-webui/bin/python -m pip install -r requirements-dev.txt

cd webui/frontend
npm ci
cd ../..
mkdir -p exports/research-console
```

### 2. Start the backend

In terminal 1:

```bash
cd webui/backend
MATB_DB_PATH="$PWD/../../exports/research-console/matb.db" \
MATB_FRONTEND_ORIGINS="http://127.0.0.1:3100" \
../../.venv-webui/bin/python -m uvicorn app.main:app \
  --reload --host 127.0.0.1 --port 8000
```

Check that it is running:

```bash
curl --fail http://127.0.0.1:8000/health
```

### 3. Start the frontend

In terminal 2:

```bash
cd webui/frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev
```

Open <http://127.0.0.1:3100/>.

### 4. Follow the first-use sequence

1. Open `Participants` and create a pseudonymous participant such as `P01`.
2. Open `Upload` and ingest the LOW, MEDIUM, and HIGH CSV files for the same
   participant and visit. Attach each adjacent scenario manifest when available.
3. Open `Tracker` and confirm the visit cell is complete.
4. Open `Visualization` for trajectories, workload-level comparisons, DEPDF
   curves, and group summaries.
5. Open `Analysis` to run the frequentist artifact and, when appropriate, the
   asynchronous Bayesian sensitivity analysis.
6. Open `Screen` to administer the four-subtest exploratory baseline battery:
   Simple RT, Choice RT, 2-back, and pursuit tracking. Participant-facing text
   is in Colombian Spanish (`es-CO`).
7. Use the Research Bundle action to export participants, visits, tidy metrics,
   fits, analysis artifacts, provenance, caveats, manifests, and figure options.

Important backend endpoints include:

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Service health |
| `POST /participants` and `GET /participants` | Participant setup |
| `POST /ingest` | CSV and optional manifest ingestion |
| `GET /tracker`, `GET /block` | Completeness and block detail |
| `GET /metrics/long`, `GET /fits` | Analysis inputs and DEPDF curves |
| `POST /analysis/run`, `POST /analysis/bayes/run` | Frequentist and Bayesian analysis |
| `POST /screen`, `GET /screen` | Screen scoring and cohort HCF summary |
| `GET /exports/research-context`, `POST /exports/research-bundle` | Reproducible exports |

Read the [backend guide](webui/backend/README.md) and [frontend guide](webui/frontend/README.md)
for the complete API and screen contracts.

## Quick start: native synthetic sUAS simulator

This is a browser-based, Linux/headless-first research simulator. It is
deterministic, non-kinetic, and designed for supervisory workload, situation
awareness, communication, recovery, and replay studies.

### 1. Install the offline-capable launcher

Python 3.12+, Node 20+, and npm are required for the supported launcher:

```bash
MATB_VENV="$PWD/.venv-suas" bash scripts/install_suas.sh
```

The installer builds the frontend and runs the native sUAS/backend gates. The
first install may need network access; the installed runtime is designed to run
without Docker, X11, a GPU, or Internet access.

### 2. Launch the console

```bash
MATB_VENV="$PWD/.venv-suas" bash scripts/run_suas.sh
```

Open <http://127.0.0.1:3100/mission/setup>. The backend health endpoint is
<http://127.0.0.1:8000/health>. The launcher keeps the default binds on
loopback and writes owner-only data below `var/suas/`. Use `--data-dir`,
`--backend-port`, and `--frontend-port` for a dedicated local run.

### 3. Use the browser protocol

1. Select a validated YAML scenario and a session language (`en` or `es-CO`).
2. Enter a pseudonymous participant and visit code.
3. Prepare and start the practice or research block.
4. Use the supervisory controls to manage the synthetic fleet, contacts,
   alerts, links, energy, separation, and required actions.
5. Complete ISA/SAGAT probes and post-block NASA-TLX/Bedford gates.
6. Finish the block, review the debrief, and download the sealed artifact set.
7. If the controller disconnects, reconnect explicitly; a running session is
   paused and never resumes automatically.

### 4. Run a small deterministic CLI check

```bash
.venv-suas/bin/python -m matb_integration.suas.cli validate \
  scenarios/suas/reference_area_search.yaml

.venv-suas/bin/python -m matb_integration.suas.cli record \
  scenarios/suas/reference_area_search.yaml \
  --block PRACTICE \
  --ticks 10 \
  --session-id SYNTH-SUAS-01 \
  --output exports/suas-demo

.venv-suas/bin/python -m matb_integration.suas.cli verify exports/suas-demo
```

The recorded directory contains a manifest, ordered events, checkpoints,
metrics, debrief data, replay verification, and `checksums.sha256`. A matching
replay verifies internal determinism; it does not validate real-world flight
behavior.

The native API exposes scenario validation, session lifecycle, non-kinetic
commands, redacted observer state, ordered WebSocket resynchronization,
controller leases, explicit recovery, debrief, and artifact download. Never
send the lease to an observer or place it in a URL.

## Quick start: FAC ISR SMS workspace

`SMS/` is a separate Node/TypeScript workspace for offline safety-management and
evidence assurance. Its research domain is deliberately separate from its
operational domain, and its runtime has no command-and-control path.

### 1. Install and build the workspace

Use Node 22.x:

```bash
cd SMS
npm ci
npm run build
```

### 2. Run the technical verification gates

```bash
npm test
npm run typecheck
npm run lint
npm run verify:no-c2
npm run verify:data-separation
```

The workspace also provides `build:offline`, `verify:offline`, evidence
verification, SBOM/release-manifest commands, verification-matrix generation,
and controlled acceptance-packet tooling. Do not run
`acceptance:record` with invented data: it is a separate institutional
decision-intake action for authorized human custodians.

### 3. Explore the console and packages

The console can be started for local UI development with:

```bash
npm run dev --workspace @fac-isr/console
```

The workspace includes:

- `apps/edge-api/`: local Fastify API for missions, gates, post-flight,
  package intake, audit, telemetry replay, safe mode, and data boundaries.
- `apps/console/`: bilingual React review console for evidence, risk,
  telemetry, checklists, research, and debrief views.
- `packages/evidence/`: canonical JSON, hashes, source registers, manifests,
  and downgrade/tamper checks.
- `packages/safety-kernel/`: deterministic applicability, freshness,
  dependencies, risk, lifecycle, gates, and audit decisions.
- `packages/energy/`, `packages/fleet/`, and `packages/geo/`: energy/reserve,
  configuration/qualification, and coordinate/route/airspace/terrain logic.
- `packages/human-performance/`: bounded duty, fatigue, workload, alert-load,
  and CRM evaluations; it is not medical diagnosis or fitness certification.
- `packages/research/`: protocol, ethics/consent, MATB and sensor adapters,
  instruments, replay, aggregation, and deidentified research export.
- `packages/sms/` and `packages/telemetry/`: SMS records and read-only telemetry
  canonicalization/replay.

For controlled offline deployment, TLS, package custody, evidence freshness,
and institutional acceptance, use the [SMS acceptance checklist](SMS/docs/release/state-aviation-acceptance-checklist.md),
[verification matrix](SMS/docs/release/verification-matrix.md), and [known limitations](SMS/docs/release/known-limitations.md).

## Quick start: legacy aircraft-monitor demonstrations

The `aircraft_monitor/` package is retained as a deterministic terminal demo,
not the active research surface:

```bash
python3 -m venv .venv-legacy
.venv-legacy/bin/python -m pip install -r requirements.txt

.venv-legacy/bin/python -m aircraft_monitor
.venv-legacy/bin/python -m aircraft_monitor.demo_uav
.venv-legacy/bin/python -m aircraft_monitor.demo_fighter
.venv-legacy/bin/python -m aircraft_monitor experiment \
  --headless --research-modality uas --seed 42
```

Generated research output defaults to `./exports/`; use a dedicated output
directory and pseudonymous IDs for any experiment run.

## Capabilities

### MATB and OpenMATB research

- Four-task OpenMATB workflow: system monitoring, tracking, communications, and
  resource management.
- LOW/MEDIUM/HIGH workload blocks with seeded event generation and
  counterbalancing support.
- Deterministic scenario manifests with SHA-256 provenance, expected probes,
  questionnaire metadata, and validation helpers.
- English and Spanish questionnaire assets for NASA-TLX, ISA, Bedford, and
  SAGAT, with validation limitations documented in the scale guides.
- Structured performance metrics: d-prime, hits, misses, false alarms,
  correct rejections, response time, TLX, Bedford, ISA, and SAGAT accuracy.
- Optional LSL-compatible OpenMATB plugin support for future synchronized
  physiology workflows; a complete physiology study still needs a validated
  acquisition and synchronization protocol.

### Modelling and statistics

- Suhir DEPDF human-nonfailure and mission-outcome calculations, Weibull
  degradation, FOAT calibration, MWL normalization, HCF inputs, and reporting.
- Frequentist Q1–Q4 analysis: workload effects, visit trajectories,
  repeated-measures correlation, DEPDF parameter drift, multiplicity controls,
  effect sizes, confidence intervals, and complete-case sensitivity.
- Bayesian PyMC sensitivity re-fits with posterior intervals, R-hat, effective
  sample size, divergence counts, seeds, and sampler provenance.
- Explicit statuses for `ok`, `insufficient_data`, and `not_estimable` rather
  than silently turning missing data into conclusions.

### Research Console

- Pseudonymous participant and six-visit tracking with a derived completeness
  grid.
- CSV ingestion with duplicate-file, filled-cell, missing-SYSMON, overwrite,
  and scenario-manifest validation guards.
- Descriptive trajectories, workload-level charts, DEPDF curves, group views,
  PNG export, and publication-oriented ECharts option JSON.
- Automatic DEPDF fitting once all three workload levels of a visit are present.
- Browser-administered Simple RT, Choice RT, 2-back, and pursuit-tracking
  baseline screen; raw-trial-first server scoring and exploratory cohort HCF
  mapping.
- Research-context JSON and reproducible ZIP bundle exports containing metrics,
  fits, analysis artifacts, manifests, caveats, and provenance.

### Native synthetic sUAS simulator

- Deterministic synthetic fleet, routes, sectors, contacts, alerts, sensors,
  links, energy, separation, workload profiles, and supervisory commands.
- Practice/LOW/MEDIUM/HIGH blocks with ISA, SAGAT, NASA-TLX, and Bedford gates.
- Pseudonymous participant/visit setup, controller lease isolation, observer
  mode, redacted private probe truth, disconnect-to-pause behavior, and explicit
  recovery.
- Append-only event recording, checkpoints, sealed debriefs, relative artifact
  paths, SHA-256 checksums, and deterministic replay verification.
- Linux/headless operation without X11, Docker, a GPU, external telemetry, or
  real aircraft integration.

### FAC ISR SMS assurance workspace

- Evidence/source registers, canonical JSON, hashes, manifests, signatures,
  freshness checks, and downgrade/tamper detection.
- Deterministic safety kernel with pass/blocked/unknown results and fail-closed
  hard-evidence behavior.
- Mission planning/review, safety gates, checklists, post-flight records,
  audit ledger, safe mode, and signed local package intake.
- Read-only telemetry replay, retention provenance, fleet/configuration/
  maintenance/crew qualification checks, energy/reserve evaluation, and offline
  geospatial package logic.
- Human-performance policies, controlled research protocols, consent,
  MATB/HRV/sensor adapters, instruments, replay, aggregation, and deidentified
  non-dispatchable exports.
- No-C2 and research/operational data-separation verification scripts.

## Research potential

### Questions supported by the current platform

1. **Workload dose-response:** Do increasing event rates and concurrent task
   demands change detection, response time, NASA-TLX, ISA, Bedford, or tracking
   performance?
2. **Situation awareness:** How do freeze-probe perception, comprehension, and
   projection scores change under workload, link loss, contact uncertainty, or
   supervisory conflict?
3. **Learning and fatigue:** Do performance, workload, SA, or DEPDF parameters
   change over repeated visits or prolonged blocks?
4. **Human-nonfailure and mission outcome:** How do comparative workload and
   failure-event records alter fitted DEPDF parameters and mission-outcome
   estimates?
5. **Supervisory sUAS operations:** How do fleet size, alerts, separation
   events, energy constraints, link loss, and required contact reports affect
   operator decisions and debrief metrics?
6. **Human-centered safety assurance:** How should evidence freshness, safety
   gates, read-only telemetry, fatigue/workload controls, and research-data
   separation be presented and reviewed by accountable human roles?

### Research extensions on the roadmap

These are research opportunities, not claims that every capability is already
implemented or validated:

- LSL marker and physiology-stream synchronization for HRV, ECG, EEG, eye
  tracking, and other time-aligned signals.
- BIDS-like derivatives and portable longitudinal data packages.
- Controlled automation reliability, adaptive handoffs, transparency cues, and
  trust-in-automation manipulations.
- Fighter, RPA, transport/ISR, MUM-T, rotorcraft, and space-robotics stressor
  packs with protocol-specific validation.
- Eye-tracking/pupillometry integration and multimodal workload models.
- Participant-specific online workload classifiers with uncertainty and
  explicit gates against operational decision use.
- Publication-oriented Markdown/Quarto report generation with provenance,
  missingness, effect sizes, and analysis caveats.

The evidence review and capability roadmap in [`docs/research/military-aviation-platform/2026-06-10_current_state_and_capability_roadmap.md`](docs/research/military-aviation-platform/2026-06-10_current_state_and_capability_roadmap.md)
describe the scientific rationale and remaining limitations.

## Verification and operations

Run only the suites relevant to the workflow you changed. Use a dedicated
environment and dedicated output directory for every study or demo.

```bash
# Documentation contract
pytest tests/test_readme_documentation.py -q

# MATB bridge, DEPDF, statistics, screen, and integration tests
.venv-matb/bin/python -m pytest tests/test_scenario_builder.py \
  tests/test_scenario_manifest.py tests/test_log_converter.py \
  tests/analysis_stats tests/suhir tests/screen -q

# Native sUAS tests
.venv-suas/bin/python -m pytest tests/suas -q

# Research Console backend
cd webui/backend
../../.venv-webui/bin/python -m pytest -q

# Research Console frontend
cd ../frontend
npm test -- --run
npm run typecheck
npm run build

# SMS workspace
cd ../../SMS
npm test
npm run typecheck
npm run verify:no-c2
npm run verify:data-separation
```

Browser E2E/accessibility checks additionally need the approved Chromium or
Playwright browser asset. SMS offline-image verification additionally needs
Docker, pinned build inputs, and controlled evidence/packages.

Default local service boundaries:

| Service | Default | Boundary |
| --- | --- | --- |
| Research/sUAS FastAPI | `127.0.0.1:8000` | Loopback; health at `/health` |
| Research/sUAS Next.js | `127.0.0.1:3100` | Local browser UI |
| SMS development console | Vite default port | Development/review UI only |
| SMS edge deployment | Controlled HTTPS deployment | Requires institution-managed TLS, packages, and custody |

Keep loopback defaults. A non-loopback bind requires explicit browser origins,
authentication, privacy, network, and threat controls beyond these launchers.

## Troubleshooting

| Symptom | Safe response |
| --- | --- |
| A Python module is missing | Confirm the selected interpreter with `python -c "import sys; print(sys.executable)"`; install the requirements for that workflow rather than installing globally. |
| OpenMATB cannot find a scenario | Run `install_to_openmatb.py` against the intended checkout and verify `includes/scenarios/military_aviation/`. |
| OpenMATB flickers or Pyglet fails | Start windowed, verify the OpenMATB virtual environment, and on headless Linux verify Xvfb and `DISPLAY`. The native sUAS UI does not need X11. |
| The Research Console cannot connect | Confirm backend `/health`, frontend `NEXT_PUBLIC_API_URL`, `MATB_FRONTEND_ORIGINS`, and that ports 8000/3100 are not occupied. |
| An ingestion request returns 409 | The file hash or participant/visit/workload cell already exists. Use a fresh dedicated database or the documented overwrite flow after checking provenance. |
| sUAS recording refuses the output directory | The output must be absent or empty. Choose a new dedicated directory; do not delete a study artifact to make a demo run. |
| The sUAS controller disconnects | Reconnect explicitly with the controller lease. A valid disconnect pauses the session and never resumes it automatically. |
| SMS verification reports missing, expired, or altered evidence | Stop, preserve the diagnostic, and obtain current authorized evidence through custody procedures. Never bypass freshness, authority, signature, or hash checks. |
| Tests pass but SMS readiness remains blocked | This is expected until the scoped institutional reviews and human acceptance decisions are current. Technical verification is not operational authorization. |

## Repository map

| Path | Role |
| --- | --- |
| `matb_integration/` | Scenario generation, conversion, questionnaires, DEPDF, statistics, screen, and deterministic sUAS libraries |
| `openmatb/` | Tracked OpenMATB task runtime, plugins, scenarios, and replay support |
| `scenarios/military_aviation/` | Committed OpenMATB-compatible study scenarios |
| `scenarios/suas/` | Synthetic sUAS YAML scenarios |
| `webui/backend/` | Research/sUAS FastAPI service, persistence, analysis, and exports |
| `webui/frontend/` | Research tracker/analysis and sUAS browser console |
| `SMS/apps/` | SMS edge API and bilingual review console |
| `SMS/packages/` | Evidence, safety-kernel, energy, fleet, geo, human-performance, research, SMS, and telemetry domains |
| `SMS/tools/` | Evidence acquisition, map packaging, offline build, release, and acceptance tools |
| `aircraft_monitor/` | Retained synthetic terminal demonstrations |
| `tests/` | Python, integration, sUAS, application, and documentation tests |
| `docs/` and `SMS/docs/` | Scientific evidence, implementation, verification, release, and governance detail |

## References and deeper guides

- [OpenMATB runtime guide](openmatb/README.md)
- [Research Console overview](webui/README.md), [backend API](webui/backend/README.md), and [frontend screens](webui/frontend/README.md)
- [Suhir DEPDF guide](matb_integration/suhir/README.md)
- [Spanish scale validation](docs/research/scales/scale_validation_es.md) and [SAGAT validation](docs/research/scales/sagat_validation.md)
- [Current capability roadmap](docs/research/military-aviation-platform/2026-06-10_current_state_and_capability_roadmap.md)
- [sUAS verification report](docs/implementation/suas-c2-v1-verification.md)
- [SMS research data dictionary](SMS/docs/provenance/research-data-dictionary.md)
- [SMS verification matrix](SMS/docs/release/verification-matrix.md), [known limitations](SMS/docs/release/known-limitations.md), and [acceptance checklist](SMS/docs/release/state-aviation-acceptance-checklist.md)
- [Changelog](CHANGELOG.md)

## Glossary

| Term | Meaning in this repository |
| --- | --- |
| MATB | Multi-Attribute Task Battery human-factors paradigm |
| OpenMATB | Open-source desktop task runtime used to present the four MATB tasks |
| DEPDF | Double-exponential probability distribution function used for comparative human-nonfailure modelling |
| HCF / F/F0 | Exploratory human-capacity-factor mapping from the baseline research screen |
| SAGAT | Situation Awareness Global Assessment Technique freeze-probe method |
| sUAS | Small uncrewed aircraft system; here, a synthetic supervisory simulator |
| SMS | Safety Management System; here, the `SMS/` assurance workspace |
| Non-dispatchable | Research data or result that cannot enter an operational-release decision |

## License

MATB is provided under the [MIT License](LICENSE). The license does not certify
fitness for clinical, flight, defense, safety-critical, or operational use and
does not replace applicable law, institutional governance, ethics review, or
human acceptance.
