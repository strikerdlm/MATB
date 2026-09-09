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
neurocognitive screen. The OpenMATB task runtime is tracked in `openmatb/` for
local development and task presentation; the asset installer also supports a
separate compatible checkout when a study requires one.

Scientific metrics use the additive v2 registry described in
[`docs/research/scientific-foundation-v2.md`](docs/research/scientific-foundation-v2.md).
Corrected RTLX and observed-opportunity SYSMON metrics are explicit; legacy
aliases remain reproducible but exploratory. LOW/MEDIUM/HIGH are engineering
presets pending human calibration, and software timing QC is not a substitute
for physical-onset qualification.

Strict v3 event and separate timing-observation contracts are published. The
runtime emits an ordered additive JSONL envelope that explicitly identifies
itself as pre-v3 until contract-pair promotion and reconciliation are complete;
it already records explicit SYSMON target/non-target opportunities and an
optional fail-observable LSL mirror. The adaptive-automation policy and
failure-model engine is implemented as an experimental component; it is not yet
a validated participant-facing closed-loop intervention.

Qualification tooling now lives in `matb_integration/qualification/`. It keeps
software conformance, rig-specific physical timing, human calibration,
cross-implementation characterization, and public-release eligibility as
independent fail-closed evidence classes. See
[`docs/research/qualification-workflow.md`](docs/research/qualification-workflow.md).
The candidate public core is decoupled from optional sUAS/Liftoff product trees.
Public release remains deliberately blocked by empirical qualification,
privacy/data-review, dependency-SBOM, and final licensing gates.

The Research Console is a loopback FastAPI/Next.js application with local
SQLite and artifact storage. Its current OpenMATB upload path accepts legacy CSV
plus an optional scenario manifest; derived Console metrics are labeled
`legacy_csv_derived_not_reconciled_to_authoritative_event_stream` and remain
confirmatory-ineligible until paired v3 JSONL reconciliation is implemented.
Its sUAS surface is a synthetic, non-kinetic,
supervisory simulator. Optional Colombia maps and read-only aircraft observations
provide geographic context; live traffic is limited to exploration and technical
sessions, while research uses pinned captures. MATB controls the synthetic
scenario, clock, commands and scoring. It has no real-aircraft command channel,
weapon, targeting or autonomous dispatch capability.

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
| Generate OpenMATB scenarios, convert logs, or try DEPDF analysis | `matb_integration/` and `openmatb/` | Python; tracked or compatible OpenMATB for participant task presentation | [OpenMATB research tour](examples/openmatb-research/README.md) | Three scenarios/manifests, synthetic JSONL metrics, and one DEPDF JSON |
| Ingest sessions, track visits, visualize data, analyze, and export | `webui/` | Python 3.12+, Node >=20.9, local browser | [Research Console walkthrough](examples/research-console/README.md) | Local SQLite records and `research-bundle.zip` |
| Capture Polar H10 HR/RR, ECG, ACC, and descriptive HRV locally | `matb_integration/physiology/` and `webui/` | Windows 11, Python 3.12, optional physiology dependencies | [Polar H10 Release A](docs/physiology/polar-h10-release-a.md) | Checksummed local Parquet bundle; no automatic upload |
| Run a deterministic, observer-safe sUAS research session | `matb_integration/suas/` and `webui/` | Python 3.12+; Node >=20.9 for browser service | [sUAS simulator walkthrough](examples/suas-simulator/README.md) | Replay-verifiable events, metrics, debrief, manifest, and checksums |
| Evaluate offline safety-management package contracts | `SMS/` | Node 22.x; Docker only for the offline image/bundle | [SMS capability tour](examples/sms-platform/README.md) | Deterministic JSON with a deliberately blocked safety-kernel result |
| Demonstrate the older terminal monitor | `aircraft_monitor/` | Python and a terminal | [Legacy monitor guide](examples/legacy-monitor/README.md) | Headless UAV, fighter, combined, or experiment event stream |

The [examples index](examples/README.md) compares fast offline examples with the
service, browser, Docker, and OpenMATB task-presentation procedures.

<a id="architecture-and-data-flow"></a>
## 3. Architecture and data movement

```text
MATB/
├── matb_integration/       Python scenario, conversion, analysis, screen, and sUAS libraries
├── openmatb/               tracked OpenMATB desktop task runtime and plugins
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
Tracked/compatible OpenMATB -> ordered pre-v3 JSONL + timing QC + legacy CSV + manifest -> future v3 pair/reconciliation
Legacy CSV upload -> provisional Console metrics -> tracker/analysis/export (not event-stream reconciled)
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
| Node.js | Frontend requires >=20.9; launcher enforces it | No | >=20.9 required | >=20.9 for browser service | **22.x required** | No |
| npm | Lockfile-based dependency/build tool | No | Required for frontend | Required for browser service | Required | No |
| OpenMATB runtime | Tracked in `openmatb/`; a separate compatible checkout is optional | Workflow-specific | Only to collect task sessions | No | No | No |
| Xvfb | Virtual X display for OpenMATB/Pyglet on headless Linux | Workflow-specific | No | No—the native UI is browser/headless | No | No in `--headless` mode |
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

The first example is fully synthetic and does not start a task window. Use the
tracked `openmatb/` runtime—or a separate compatible checkout—when presenting
generated tasks to a participant.

<h3>Prerequisites</h3>

Use Git and Python 3.12+. The tracked runtime is in `openmatb/`; a separate
compatible checkout is optional. Linux/headless presentation also needs Xvfb
and a working Pyglet display; native Windows runs the desktop runtime directly.

<h3>Install</h3>

Linux Bash or WSL2, from the clone root:

```bash
REPO_ROOT="$(pwd)"
python3 -m venv "$REPO_ROOT/.venv-openmatb"
"$REPO_ROOT/.venv-openmatb/bin/python" -m pip install -r "$REPO_ROOT/requirements-dev.txt"
"$REPO_ROOT/.venv-openmatb/bin/python" -m pip install -r "$REPO_ROOT/openmatb/requirements.txt"
```

`setup.sh` is POSIX-only and installs the narrower base `requirements.txt` for
legacy/OpenMATB asset integration. It is not a substitute for the development
dependency installation above when running the DEPDF/statistics example.

```bash
REPO_ROOT="$(pwd)"
MATB_VENV="$REPO_ROOT/.venv-openmatb" bash "$REPO_ROOT/setup.sh"
```

Native Windows PowerShell 7+:

```powershell
$RepoRoot = (Get-Location).Path
python -m venv (Join-Path $RepoRoot ".venv-openmatb")
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") -m pip install -r (Join-Path $RepoRoot "requirements-dev.txt")
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") -m pip install -r (Join-Path $RepoRoot "openmatb\requirements.txt")
```

<h3>Configure</h3>

Synthetic generation needs no configuration. Install the repository-owned
scenarios and questionnaires into the tracked runtime:

```bash
REPO_ROOT="$(pwd)"
OPENMATB_DIR="$REPO_ROOT/openmatb"
"$REPO_ROOT/.venv-openmatb/bin/python" "$REPO_ROOT/install_to_openmatb.py" "$OPENMATB_DIR"
```

```powershell
$RepoRoot = (Get-Location).Path
$OpenMatbDir = (Resolve-Path (Join-Path $RepoRoot "openmatb")).Path
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") (Join-Path $RepoRoot "install_to_openmatb.py") $OpenMatbDir
```

The installer accepts the tracked runtime directly. A separate checkout is
accepted only when it implements the required provenance, clock, bounded-log,
explicit SYSMon-opportunity, and COMM-response-window capabilities and its
pinned communications WAV inventory passes byte-level timing-profile
qualification. An `includes/` directory alone is deliberately insufficient.

<h3>Spanish localization and task-window shortcuts</h3>

The tracked OpenMATB runtime now ships with Colombian Spanish (`es_CO`) as its
default display language. The locale covers the application and scenario
generator UI, validation messages, participant instructions, questionnaire
assets, and Spanish COMM audio using ICAO radiotelephony spelling. Confirm this
setting in `openmatb/config.ini`:

```ini
[Openmatb]
language=es_CO
visual_theme=fac_modern
```

OpenMATB includes three bundled presentation conditions: `classic` preserves
the historical light interface, `cockpit` applies a generic dark glass-cockpit
theme, and the default `fac_modern` applies the light MATB-FAC presentation.
Researchers can clone, edit, validate, preview, publish, import, and export
strict profiles at **Settings → Appearance** (`/openmatb/appearance`). Only a
published profile can be selected for a controlled session. Its ID, semantic
version, schema version, canonical SHA-256, and resolved JSON are frozen in the
session artifacts and verified again before every native block launch.

For a direct launch, select a bundle with `main.py --visual-theme cockpit` or
load a strict profile using `main.py --theme-file <absolute-path>`. A visual
profile contains rendering data only; automation, workload, task activation,
response windows, and scoring remain under the scenario/runtime boundary. See
the [OpenMATB visual-profile v1 contract](docs/contracts/openmatb-visual-profile-v1.md).
The software preserves task geometry, hit areas, timing, input mappings, and
scoring, but perceptual and workload equivalence must be established
empirically before pooling results across appearances.

Start the localized task window from the runtime directory:

```bash
REPO_ROOT="$(pwd)"
cd "$REPO_ROOT/openmatb"
"$REPO_ROOT/.venv-openmatb/bin/python" main.py
```

```powershell
$RepoRoot = (Get-Location).Path
Set-Location (Join-Path $RepoRoot "openmatb")
& (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") main.py
```

Set `language=en_EN` or `language=fr_FR` to select another distributed locale.
See the [complete Spanish OpenMATB guide](openmatb/README.es.md) and the
[controlled aviation terminology](openmatb/locales/es_CO/TERMINOLOGIA.md).
Localization does not by itself establish psychometric validation for a
questionnaire in a Colombian study population; record the exact instrument,
administration, scoring method, and adaptation status in the study protocol.

The global task-window shortcuts are:

| Key | Action |
| --- | --- |
| `P` | Open the pause dialog |
| `Escape` | Open the exit-confirmation dialog |

All other response keys are scenario-specific. Scenario module identifiers,
commands, and file names remain internal OpenMATB values and are not translated.

<h4>Windows RC controller setup: Hitec Aurora 9 and RealFlight InterLink</h4>

The tracked OpenMATB runtime accepts one Windows game-controller device when it
starts. It uses that device's `X` and `Y` axes for tracking and its numbered
buttons or hat directions for discrete responses. It currently opens the first
controller returned by Windows, does not hot-swap controllers, and does not
convert extra RC axes such as `Z`, `Rx`, or `Ry` into buttons. Qualify the exact
hardware, cable, USB port, Windows build, and mapping before collecting
participant data.

Use these hardware routes in order:

1. **Existing RealFlight G2 InterLink:** connect the InterLink by USB and use
   its rear transmitter-interface port with the original or a known-compatible
   PPM trainer lead. The original G2 InterLink was designed to accept an FM/PPM
   field transmitter through this port. Do not force a 6-pin adapter into the
   Aurora's 3.5-mm Multi-I/O/trainer socket.
2. **Aurora-specific fallback:** use an [IKARUS USB interface #3031037](https://shop.ikarus.net/en/commander-und-interfaces/947-usb-interfaceset-fur-35-mm-schulerbuchse-spektrum.html)
   or another interface that explicitly accepts a 3.5-mm mono PPM trainer
   signal and appears in Windows as a standard game controller.
3. **Controller-only fallback:** use the [Spektrum InterLink DX](https://www.spektrumrc.com/product/spektrum-interlink-dx-simulator-controller-with-usb-plug/SPMRFTX1.html)
   directly as the OpenMATB controller. This does not require the Aurora.

The Spektrum WS2000 is not an Aurora interface: it receives DSM2/DSMX, whereas
the Aurora 9 uses Hitec AFHSS. The Hitec HPP-22 is a programming/firmware
interface, not a Windows game-controller interface.

Create a dedicated Aurora model memory named `OPENMATB`:

1. Select a simple airplane model with no mixing.
2. Disable dual rates, exponential, flight-condition mixing, and channel
   coupling. Set output centers to 0% and travel to approximately -100%/+100%.
3. Assign each MATB control to its own output channel. Prefer centered
   three-position controls for pairs of commands so returning the control to
   center releases the virtual button.
4. Connect the trainer/interface cable using the power sequence in the Aurora
   and USB-interface manuals. On the Aurora, open **Multi-I/O**, select
   **T.Pupil**, and select PPM output if the firmware presents a modulation
   choice.

The following nine-channel layout covers every active task except resource
management:

| Aurora channel | Negative/first position | Positive/second position |
| --- | --- | --- |
| 1 | Tracking X axis | Tracking X axis |
| 2 | Tracking Y axis | Tracking Y axis |
| 3 | `JOY_BTN_1`: SYSMon light 1 | `JOY_BTN_2`: SYSMon light 2 |
| 4 | `JOY_BTN_3`: SYSMon scale 1 | `JOY_BTN_4`: SYSMon scale 2 |
| 5 | `JOY_BTN_5`: SYSMon scale 3 | `JOY_BTN_6`: SYSMon scale 4 |
| 6 | `JOY_BTN_7`: previous radio | `JOY_BTN_8`: next radio |
| 7 | `JOY_BTN_10`: frequency down | `JOY_BTN_9`: frequency up |
| 8 | Unused | `JOY_BTN_11`: validate response |
| 9 | Spare | Spare |

Scheduling is display-only and needs no control channel. Resource management is
not included in this layout because its pump bindings remain keyboard-only.

Before starting OpenMATB, press Win+R, run `joy.cpl`, select the controller, and
open **Properties > Test**. The hardware passes only if:

- the device appears on every reconnect without a vendor driver error;
- the two tracking controls center consistently and reach their full ranges;
- every command produces one intended button or hat state and releases when
  returned to neutral;
- holding the two frequency controls keeps the corresponding state pressed;
- operating one control does not move an unrelated axis or button; and
- the same button numbering remains after a reboot and USB reconnect.

Write down the observed button numbers. The table above is the required logical
layout, not a promise that a particular adapter will assign those numbers
automatically.

If the interface already reports two suitable axes and at least 11 buttons,
use it directly. If Aurora switch channels appear only as additional axes, a
Windows translation layer is required because OpenMATB does not currently read
those axes as response keys. One reproducible bridge is [vJoy](https://github.com/jshafer817/vJoy/releases)
with [Joystick Gremlin](https://whitemagic.github.io/JoystickGremlin/quickstart.html):

1. Create `vJoy Device 1` with only `X` and `Y` enabled, 11 buttons, and no POV.
2. In a new Joystick Gremlin profile, map the two physical tracking channels to
   vJoy `X` and `Y` and add a small measured center dead zone.
3. For channels 3-7, map the negative range to the first button in the table and
   the positive range to the second. Leave a neutral interval around zero that
   presses neither button. Map channel 8 positive to button 11.
4. Configure buttons 9 and 10 as held states, not one-shot macros. Configure the
   remaining switch ranges to release their buttons when the control returns to
   neutral.
5. Activate the profile and repeat the complete `joy.cpl` test on `vJoy Device`.
   Save the profile with the study protocol and record the vJoy and Joystick
   Gremlin versions and profile checksum.

OpenMATB must enumerate `vJoy Device` first. If it instead reacts to the
physical interface, stop qualification: do not depend on an incidental Windows
device order for participant data. Use a direct-button controller or implement
controller selection in `openmatb/core/joystick.py` before proceeding.

Add the observed logical button map before the task `start` commands in the
selected scenario:

```text
# SYSMon: two lights and four scales
0:00:00;sysmon;lights-1-key;JOY_BTN_1
0:00:00;sysmon;lights-2-key;JOY_BTN_2
0:00:00;sysmon;scales-1-key;JOY_BTN_3
0:00:00;sysmon;scales-2-key;JOY_BTN_4
0:00:00;sysmon;scales-3-key;JOY_BTN_5
0:00:00;sysmon;scales-4-key;JOY_BTN_6

# Communications: radio selection, held tuning, and validation
0:00:00;communications;keys-selectradioup;JOY_BTN_7
0:00:00;communications;keys-selectradiodown;JOY_BTN_8
0:00:00;communications;keys-tunefrequencyup;JOY_BTN_9
0:00:00;communications;keys-tunefrequencydown;JOY_BTN_10
0:00:00;communications;keys-validateresponse;JOY_BTN_11
```

Run a non-participant acceptance scenario containing TRACK, SYSMon,
communications, and scheduling but no resource management. Verify all six
SYSMon responses, both radio-selection directions, both held tuning directions,
validation, and simultaneous two-axis tracking. Reject the setup if any input
is missing, duplicated, stuck, or changes numbering between runs. Preserve the
scenario, controller profile, device identity, calibration record, and input
log with the study configuration.

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

For task presentation, edit `openmatb/config.ini` and start with
`language=en_EN`, `fullscreen=False`, and
`scenario_path=military_aviation/low_workload.txt`. Then run the tracked task
window from its directory:

```bash
REPO_ROOT="$(pwd)"
cd "$REPO_ROOT/openmatb"
MATB_SOURCE_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD)" \
  "$REPO_ROOT/.venv-openmatb/bin/python" main.py
```

```powershell
$RepoRoot = (Get-Location).Path
$env:MATB_SOURCE_COMMIT = (git -C $RepoRoot rev-parse HEAD).Trim()
Push-Location (Join-Path $RepoRoot "openmatb")
try {
  & (Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe") main.py
} finally {
  Pop-Location
}
```

`MATB_SOURCE_COMMIT` must resolve to the frozen, full lowercase Git object ID
(40 hexadecimal characters for SHA-1 repositories or 64 for SHA-256). Missing,
sentinel, abbreviated, or arbitrary values remain explicitly provisional and
cannot upgrade runtime provenance to `complete`.

Set `MATB_SOURCE_DIRTY=false` only after independently confirming that the exact
source tree and study assets are clean; use `true` whenever they differ from the
commit. Leave it unset (or use `unknown` in tooling that accepts it) when the
state was not checked. An unset value intentionally records
`provisional_unverified_source_tree` rather than guessing that the tree was clean.

For a separate compatible checkout, run its `main.py` from that checkout using
the selected environment. Use `DISPLAY` and Xvfb only on a Linux/headless host;
native Windows does not use Xvfb.

<h3>Try the synthetic example</h3>

```bash
REPO_ROOT="$(pwd)"
MATB_PYTHON="$REPO_ROOT/.venv-openmatb/bin/python" \
  bash "$REPO_ROOT/examples/openmatb-research/run.sh" "$REPO_ROOT/examples/output/openmatb-research"
```

```powershell
$RepoRoot = (Get-Location).Path
$env:MATB_PYTHON = Join-Path $RepoRoot ".venv-openmatb\Scripts\python.exe"
& (Join-Path $RepoRoot "examples\openmatb-research\run.ps1") -OutputDir (Join-Path $RepoRoot "examples\output\openmatb-research")
```

<h3>Expected result</h3>

The tour writes three `scenarios/*.txt` files with adjacent manifests,
`metrics.jsonl`, and `suhir.json`, then prints `External OpenMATB was not
started.` That message refers only to the synthetic tour: it does not launch
the tracked or a separate task runtime. The fixture contains only `SYNTH-P01`;
it is not participant data.

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

Stop OpenMATB or Xvfb with Ctrl-C. Delete only the selected synthetic output,
never a task runtime or session store.

```bash
REPO_ROOT="$(pwd)"
rm -rf -- "$REPO_ROOT/examples/output/openmatb-research" "$REPO_ROOT/examples/output/generated-scenarios"
```

```powershell
$RepoRoot = (Get-Location).Path
Remove-Item -Recurse -Force (Join-Path $RepoRoot "examples\output\openmatb-research"), (Join-Path $RepoRoot "examples\output\generated-scenarios") -ErrorAction SilentlyContinue
```

<h3>Troubleshooting</h3>

An `includes/ not found` error means the selected tracked or compatible
checkout is wrong. `ModuleNotFoundError` usually means the selected venv is
inactive or its OpenMATB requirements were not installed. On Linux,
display/flicker/Pyglet failures belong to the OpenMATB/X11 boundary: validate
`DISPLAY`, use Xvfb on headless hosts, and begin windowed. See the
[complete OpenMATB example](examples/openmatb-research/README.md).

<a id="quick-start-research-console"></a>
## 6. Research Console quick start

<h3>Prerequisites</h3>

Use Python 3.12+, Node >=20.9, npm, and a browser. Initial dependency installation
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

Run exactly one Uvicorn worker for each Research Console database. The backend
holds a durable database-instance lease and rejects a second live process so
Bayesian jobs and SQLite writes cannot split across competing process-local
executors. Scale by assigning separate databases/data roots, not `--workers`.

<h3>Try the synthetic example</h3>

With the service running:

```bash
REPO_ROOT="$(pwd)"
export MATB_API_TOKEN="$(<"$REPO_ROOT/examples/output/research-console-service/api-token")"
BASE_URL=http://127.0.0.1:8000 OUTPUT_DIR="$REPO_ROOT/examples/output/research-console-tour" \
  bash "$REPO_ROOT/examples/research-console/api_walkthrough.sh"
```

```powershell
$RepoRoot = (Get-Location).Path
$env:MATB_API_TOKEN = Read-Host "MATB API token"
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

The browser is admitted only from configured exact origins. State-changing
CLI requests have no browser `Origin`, so they must send the owner-only bearer
token from `MATB_API_TOKEN`; the combined launcher creates it at
`<data-dir>/api-token`. Host validation also blocks loopback DNS rebinding.

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

The CLI needs Python 3.12+. The browser service adds Node >=20.9, npm, and a
browser. `install_suas.sh` and `run_suas.sh` are Linux/WSL2 contracts; native
Windows PowerShell may run the CLI and may call a service hosted in WSL2.

For native one-click use, see the
[MATB UAS Windows launchers](windows-launchers/README.md). They provide setup,
the interactive console, PRACTICE/LOW/MEDIUM/HIGH technical runs, replay
verification, diagnostics, results access, and identity-checked shutdown of
tracked processes.

| Windows shortcut | Purpose |
| --- | --- |
| `00 - Preparar MATB UAS.cmd` | Check prerequisites, install missing dependencies, build the UI, and run focused checks |
| `01 - Abrir consola UAS.cmd` | Start the supervised local services and open the interactive console |
| `02 - Diagnosticar MATB UAS.cmd` | Run read-only environment, port, process, health, and latest-run diagnostics |
| `10 - Simular PRACTICE.cmd` | Run and verify the complete PRACTICE technical profile |
| `11 - Simular LOW.cmd` | Run and verify the complete LOW technical profile |
| `12 - Simular MEDIUM.cmd` | Run and verify the complete MEDIUM technical profile |
| `13 - Simular HIGH.cmd` | Run and verify the complete HIGH technical profile |
| `90 - Verificar ultima simulacion.cmd` | Re-run replay and checksum verification for the latest technical run |
| `91 - Abrir resultados MATB UAS.cmd` | Open the latest sealed technical results and available service logs |
| `99 - Detener MATB UAS.cmd` | Stop only the identity-checked processes tracked by the launcher |

Run `00` once before first use, use `01` for the interactive console, and keep
its supervisor window open. The `10`–`13` shortcuts create technical
simulations, not valid participant sessions. Full requirements and recovery
guidance are in the linked launcher guide.

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
MATB_VENV="$REPO_ROOT/.venv-suas" \
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

### Colombia geography and observed traffic

Open **`http://localhost:3100/colombia`** after starting the Research Console.
The national explorer offers imagery, relief, roads, rivers, settlements,
boundaries, airports and live aircraft observations. Six installed local scenes
cover Villavicencio, Popayán (Cauca), Cúcuta (Norte de Santander), Rionegro
(Antioquia), Minca (Sierra Nevada de Santa Marta), and El Cocuy–Güicán.

Each local scene covers a 12 × 8 km mission with a 2 km margin. Choose
**Technical test** on its card to use the Three.js/TypeScript overview, follow
and drone cameras. The national map and live traffic require internet; prepared
scenes and captured traffic support offline missions. Traffic coverage is
partial and provider outages are displayed explicitly. Research sessions accept
recorded traffic with pinned checksums, preserving deterministic scoring.

[Setup, optional map preparation and capture workflow](docs/implementation/colombia-geography-traffic.md)
· [Verification and screenshots](docs/implementation/colombia-geography-verification.md).
Scene datasets retain their source terms; see [third-party notices](THIRD_PARTY_NOTICES.md).

<a id="quick-start-sms"></a>
## 8. FAC ISR SMS quick start

<h3>Prerequisites</h3>

Use Node.js 22.23.2 and npm. Docker with Linux-container support is needed only
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
npm run verify:ci -- --platform linux --local
```

```powershell
$RepoRoot = (Get-Location).Path
Set-Location (Join-Path $RepoRoot "SMS")
npm test
npm run typecheck
npm run verify:no-c2
npm run verify:data-separation
```

The Linux-local CI command uses controlled TEST-ONLY platform fixtures and makes
no production-candidate claim. Production CI additionally requires the exact
official-runtime native bundle, Linux OCI candidate/image, and native platform
smoke evidence. Native Windows verification runs on Windows Server 2022 without
WSL or Docker. See the [0.2.0-rc.1 operator guide](SMS/docs/operator-guide.md)
for standalone, tactical, Linux, Windows, OCI, bootstrap, keys, backup,
upgrade, rollback, diagnostics, and limitation procedures.

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
"$REPO_ROOT/.venv-legacy/bin/python" -m aircraft_monitor --help
"$REPO_ROOT/.venv-legacy/bin/python" -m pytest \
  "$REPO_ROOT/tests/test_dashboard_behavior.py" \
  "$REPO_ROOT/tests/test_research_protocol.py" -q
```

```powershell
$RepoRoot = (Get-Location).Path
$Python = Join-Path $RepoRoot ".venv-legacy\Scripts\python.exe"
& $Python -m aircraft_monitor --help
& $Python -m pytest `
  (Join-Path $RepoRoot "tests\test_dashboard_behavior.py") `
  (Join-Path $RepoRoot "tests\test_research_protocol.py") -q
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
| `matb_integration/scenario_builder.py` | Generate LOW/MEDIUM/HIGH counterbalanced scenarios | Study designer | Protocol, duration, seed → OpenMATB text scenarios | Python | [OpenMATB tour](examples/openmatb-research/README.md) | `pytest tests/test_scenario_builder.py tests/test_scenario_manifest.py tests/test_log_converter.py tests/suhir tests/analysis_stats tests/screen -q` | Generated tasks require the tracked or a compatible OpenMATB runtime for presentation |
| `matb_integration/scenario_manifest.py` | Hash scenarios and validate session provenance | Data steward | Scenario/tags/expected probes → adjacent manifest and validation issues | Python | OpenMATB tour | Same suite | Hash integrity does not establish protocol validity or consent |
| `matb_integration/log_converter.py` | Convert legacy OpenMATB CSV into versioned metric derivatives | Research analyst | CSV + pseudonym/workload → provisional JSONL metrics | Python | OpenMATB tour | Same suite | CSV derivatives are explicitly not authoritative-event-stream reconciled and remain confirmatory-ineligible |
| `matb_integration/questionnaires/` | EN/ES NASA-TLX, Bedford, ISA, and SAGAT assets | Study designer | Controlled text/YAML → configured questionnaire/probe content | OpenMATB or sUAS loader | OpenMATB and sUAS tours | Questionnaire/SAGAT tests | Scales must be administered under an approved protocol |
| `matb_integration/analysis/` | Descriptive outputs plus frequentist MixedLM/rmcorr/rmANOVA/FDR and Bayesian PyMC sensitivity engines | Statistician | `/metrics/long` and `/fits` JSON arrays → versioned artifacts | Python; PyMC sampling is optional/slow | [OpenMATB analysis commands](examples/openmatb-research/README.md) | Analysis tests | Small/incomplete datasets may be not estimable; Bayesian diagnostics govern interpretation |
| `matb_integration/suhir/` | Fit Suhir DEPDF parameters and mission-outcome research summaries | Human-factors researcher | Three workload records → G0/P0/tau0 and curves | Python/SciPy | OpenMATB tour | Suhir tests; [DEPDF guide](matb_integration/suhir/README.md) | Within-participant comparative model; three levels exactly identify parameters; not certified |
| `matb_integration/screen/` | Score reaction/2-back/tracking tasks and map exploratory HCF/F/F0 | Researcher | Raw trials/cohort → scores and exploratory mapping | Python through backend | Research Console `/screen` | Screen/backend tests | Not a diagnostic, selection, or validated predictive instrument |

### Research Console

| Module | Purpose | User | Inputs → outputs | Runtime | Example | Verification | Limitation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `webui/backend/` tracker and ingestion | Pseudonymous participant/visit grid, CSV/manifest checks, fits | Data steward | Legacy CSV + optional manifest → provisional SQLite block/provenance rows | FastAPI, Python 3.12+, one worker, port 8000 | [Console walkthrough](examples/research-console/README.md) | `cd webui/backend && python -m pytest -q` | Paired authoritative JSONL reconciliation remains a named release gate; duplicate/fill guards are not consent |
| `webui/backend/` analysis and export | Cache frequentist/Bayesian results and build reproducible bundles | Analyst | Stored metrics/fits/figures → analysis records and ZIP | FastAPI/background PyMC | Console walkthrough | Backend analysis/export tests | Export remains research data under owner custody |
| `webui/frontend/` tracker, ingestion, and visualization | Browser grid, upload, descriptive charts | Research staff | Backend JSON → interactive local UI/PNG | Next.js, Node >=20.9, port 3100 | Console walkthrough | `npm test`, `npm run typecheck`, `npm run build` | Descriptive plots are not inferential conclusions |
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
| `verify:ci` / `verify:technical-release` / `verify:operational` | Build/test both native targets, verify exact signed cross-platform candidate evidence, and independently check institutional readiness | CI, release custodian, institutional reviewer | Exact commit + three artifacts + fresh evidence + external public key → separate technical/operational results | Node 22.23.2; Ubuntu 24.04 and Windows Server 2022 | [Operator guide](SMS/docs/operator-guide.md) | named npm scripts | `technicalReady=true` never implies `operationalReady=true`; this RC remains operationally blocked |
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
npm run release:evidence
npm run verify:ci -- --platform linux --local
npm run verify:technical-release
npm run verify:operational -- --require-ready
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

### Capabilities and research potential

The module catalog above supports current research on workload dose-response,
situation awareness, repeated-visit learning or fatigue, DEPDF parameter drift,
supervisory sUAS decisions, evidence freshness, human-performance constraints,
and research/operations data separation. It combines seeded scenarios,
provenance manifests, pseudonymous longitudinal tracking, frequentist and
Bayesian analysis, deterministic replay, debrief artifacts, and fail-closed SMS
assurance without creating an aircraft-control path.

Promising extensions include synchronized LSL/physiology streams (HRV, ECG,
EEG, eye tracking), BIDS-like longitudinal derivatives, controlled automation
reliability and trust studies, protocol-specific aviation/space stressor packs,
multimodal workload models, participant-specific classifiers with uncertainty,
and publication-oriented Markdown/Quarto reports. These are research
opportunities, not claims that every extension is implemented or validated.

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
| `MATB_PYTHON` | Example wrappers | Exact Python executable selected for OpenMATB or sUAS CLI tours |
| `MATB_VENV` | Cross-platform launchers | Python environment root (`bin/python` on POSIX, `Scripts/python.exe` on Windows) |
| `MATB_DATA_ROOT` | sUAS launchers | Relocatable root for mutable databases, logs, process state, and sealed runs |
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
| Installer rejects Python or Node | Use Python 3.12+ for sUAS/repository Python, Node >=20.9 for the Research Console launcher, and Node 22.x for `SMS/`; recreate only that workflow's venv/install. |
| Python module is missing | Confirm the selected venv's Python is running (`python -c "import sys; print(sys.executable)"`) and install the matching requirements; do not install globally to mask it. |
| OpenMATB cannot find a scenario | Run `install_to_openmatb.py` against `openmatb/` or a compatible checkout containing `includes/`, then verify `includes/scenarios/military_aviation/`. |
| OpenMATB flickers or Pyglet/display fails | This is the desktop/X11 boundary. Start windowed, validate Pyglet in the selected venv, and on headless Linux validate Xvfb and `DISPLAY`. sUAS needs neither X11 nor Pyglet. |
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
[OpenMATB frontend control](docs/implementation/openmatb-frontend-control.md),
[sUAS verification](docs/implementation/suas-c2-v1-verification.md),
[SMS verification matrix](SMS/docs/release/verification-matrix.md),
[known limitations](SMS/docs/release/known-limitations.md), and
[state-aviation acceptance checklist](SMS/docs/release/state-aviation-acceptance-checklist.md).

<a id="repository-map"></a>
## 14. Repository map

| Path | Maintained role |
| --- | --- |
| `matb_integration/` | Research protocol bridge, metrics, statistics, DEPDF, screen, and deterministic sUAS libraries |
| `openmatb/` | Tracked OpenMATB desktop task runtime, plugins, scenarios, and replay support |
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
| OpenMATB | Tracked desktop task-presentation runtime; a compatible separate checkout is also supported |
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
intentionally unavailable task runtime, browser asset, Docker input, or
controlled evidence; do not weaken a check to make it green.

<a id="license"></a>
## 18. License

Repository-authored MATB components are provided under the [MIT License](LICENSE).
The embedded and modified [`openmatb/`](openmatb) runtime remains under
[CeCILL v2.1](openmatb/LICENSE). See the [component license map](LICENSES/component-map.json)
and [third-party notices](THIRD_PARTY_NOTICES.md) for the path-level boundary;
the most specific notice applies. These licenses do not certify fitness for
clinical, flight, defense, safety-critical, or operational use and do not
replace applicable law, institutional governance, ethics review, independent
licensing review, or human acceptance.
