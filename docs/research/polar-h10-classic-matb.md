# Polar H10 acquisition for classic MATB on Windows and Linux

> Research use only. This workflow produces descriptive human-performance and
> physiology measures. It is not a medical device, diagnosis, treatment,
> readiness determination, or fitness-for-duty decision.

This runbook documents the method implemented by MATB for a live Polar H10
session synchronized with the classic OpenMATB desktop task. It covers the BLE
transport, RR decoding, host timing, signal-quality rules, HRV computations,
MATB workload metrics, immutable outputs, and native Windows/Linux operation.

## 1. Evidence-based acquisition choice

MATB uses the standard Bluetooth SIG Heart Rate Service (HRS), not a
platform-specific Polar mobile SDK and not the proprietary Polar Measurement
Data (PMD) stream.

The choice follows the available primary sources:

- Polar documents H10 heart rate in beats/minute and RR intervals in
  milliseconds, typically delivered at 1 Hz. ECG at 130 Hz and accelerometry
  are separate data products. See the official
  [Polar H10 product documentation](https://github.com/polarofficial/polar-ble-sdk/blob/master/documentation/products/PolarH10.md).
- Polar identifies its HR feature as HR/RR data received through the standard
  BLE HRS. See the official
  [Polar BLE API source](https://github.com/polarofficial/polar-ble-sdk/blob/master/sources/Android/android-communications/library/src/sdk/java/com/polar/sdk/api/PolarBleApi.kt).
- The Bluetooth SIG defines RR as the interval between consecutive ECG R waves,
  makes the field variable-length, permits multiple RR values in one
  notification, and allows its presence bit to change during a connection. See
  the normative
  [Heart Rate Service 1.0 specification](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/HRS_v1.0/out/en/index-en.html).
- Polar warns that enabling SDK mode disables computed HR and RR algorithms.
  See [Polar SDK Mode](https://github.com/polarofficial/polar-ble-sdk/blob/master/documentation/SdkModeExplained.md).

Therefore, enabling HRS notifications is sufficient for the requested HR and
RR acquisition. PMD commands are only relevant if a future protocol explicitly
adds raw ECG or accelerometer streams. MATB does not enable SDK mode.

### GATT contract

| Item | UUID | MATB behavior |
| --- | --- | --- |
| Heart Rate Service | `0x180D` | Required and verified after connection |
| Heart Rate Measurement | `0x2A37` | Notifications enabled; no proprietary start write |
| Battery Level | `0x2A19` | Read when available; absence does not invent a value |

The decoder in `matb_integration/physiology/hrs.py` follows the HRS flags for
8- or 16-bit HR, contact support/status, and optional energy expended. It then
parses **every** remaining little-endian `uint16` RR field when bit 4 is set.
Each native RR tick is retained and converted as:

```text
RR milliseconds = RR ticks × 1000 / 1024
```

This is deliberately not “one RR per notification.” The SIG permits a normal
23-byte notification to contain up to 7–9 RR values depending on the other
fields. Notifications are typically about once per second, but this interval is
chosen by the sensor and is not a client-configurable sampling clock.

## 2. Cross-platform BLE method

MATB pins [Bleak 3.0.2](https://pypi.org/project/bleak/) and uses its native OS
backend:

```text
Windows 11 -> WinRT -> HRS notification
Linux      -> BlueZ/D-Bus -> HRS notification
```

The integration's supported Windows floor is Windows 11 build 22000. The
current pinned Bleak release classifies Windows 11 and Linux as supported. The
Linux backend requires BlueZ 5.55 or later; Bleak documents that it communicates
with BlueZ over D-Bus and that each Bleak object must stay on one asyncio event
loop. See the official
[Bleak backend overview](https://bleak.readthedocs.io/en/latest/backends/) and
[Linux backend documentation](https://bleak.readthedocs.io/en/latest/backends/linux.html).

MATB's backend follows these transport rules:

1. Scan first and keep the exact returned `BLEDevice`. Bleak recommends passing
   this object to `BleakClient`; connecting from a bare address can cause an
   implicit second scan. See the
   [Bleak client documentation](https://bleak.readthedocs.io/en/latest/api/client.html).
2. Return a random, 90-second opaque device token to the browser. A raw MAC,
   Windows device identifier, or stable OS identifier never enters a URL.
3. Resolve the token server-side to the exact scanned object, connect, and
   verify `0x2A37` before accepting the device.
4. Use the Linux HRS discovery filter. Do not force the same scan filter on
   Windows, where advertisement/filter behavior differs.
5. Keep the Polar manager in the FastAPI lifespan on one event loop and run one
   backend worker. Bleak explicitly warns against creating objects across
   repeated `asyncio.run()` calls; see
   [Bleak troubleshooting](https://bleak.readthedocs.io/en/stable/troubleshooting.html).
6. On a headless Windows service, call Bleak's `uninitialize_sta()` early so
   accidental COM STA initialization cannot hang WinRT BLE work. `allow_sta()`
   is for a GUI event loop integrated with asyncio, not this backend. See the
   [Bleak WinRT utility documentation](https://bleak.readthedocs.io/en/stable/_modules/bleak/backends/winrt/util.html).

Do not start Uvicorn with `--reload` or multiple workers for a hardware
collection. Reloaders and workers create more than one process/event loop and
cannot safely share one physical H10.

## 3. Timing and loss semantics

HRS contains no sensor timestamp. The SIG also requires time-sensitive data to
be discarded when a notification cannot be sent, so a disconnect creates an
irrecoverable live-stream gap; MATB never fabricates missing beats.

For every notification, MATB captures the host monotonic receipt time. It fits
a robust median host offset to cumulative native RR intervals within that BLE
connection segment and stores both:

- the unmodified notification receipt monotonic time;
- the estimated beat monotonic and UTC times;
- the fit residual and uncertainty;
- the timestamp method label;
- clock anchors that map monotonic to UTC and expose wall-clock jumps.

Reconnect delays are 1, 2, and 4 seconds. A successful reconnect starts a new
segment only after both the BLE link and the HRS notification subscription have
succeeded. A failed subscription leaves the recorder disconnected and the client
is torn down before another attempt. Timing is never bridged across a disconnect,
and any disconnected phase fails the prespecified frequency-domain gate.

## 4. Session and preflight lifecycle

The operator route is `http://127.0.0.1:3100/classic/setup`.

1. Wet both electrode areas and fit the chest strap firmly. The H10 wakes on
   skin contact.
2. Close other Polar/fitness collectors for the controlled run so ownership of
   the stream is unambiguous.
3. Scan, select the H10, and connect.
4. Run preflight. MATB requires a successfully decoded notification containing
   at least one RR value. If the sensor exposes contact status, contact must not
   be false. A connection alone is not readiness.
5. Select the pseudonymous participant, visit, and LOW/MEDIUM/HIGH scenario.
6. Prepare the attempt. The participant/visit/scenario/attempt number and
   acquisition mode become immutable. A one-time controller lease is stored in
   browser session storage and is sent only in `X-Classic-Controller`.
   Start rechecks that the device is still connected and that the live-RR
   preflight is no more than 120 seconds old; otherwise the attempt remains
   prepared until the operator repeats preflight.
7. Start the automatic protocol:

| Phase | Nominal duration | Activity |
| --- | ---: | --- |
| Baseline | 300 s | Resting RR acquisition |
| Task | 900 s | Allowlisted classic OpenMATB scenario + RR acquisition |
| Post-task questionnaire | At most 600 s | Explicit operator-visible state; task HRV has already ended |
| Recovery | 300 s | Post-task RR acquisition |

The timed collection is 25 minutes (5-minute baseline, 15-minute MATB task,
5-minute recovery). The intervening post-task questionnaire may add up to 10
minutes, so reserve as much as 35 minutes for participant occupancy.

The OpenMATB process is launched without a shell using an exact Python
executable and allowlisted scenario path. The optional CLI contract adds
`--scenario`, `--session-id`, and `--output-dir`; legacy no-argument and `-r`
launches retain their prior behavior. A normal scheduler exit writes
`scenario_completed`; `scenario_finished` alone is not accepted because it is
also written when the window is closed early. The task physiology boundary is
fixed at 900 seconds and therefore excludes any post-task questionnaire time.
After that boundary the attempt enters `POST_TASK`. OpenMATB may collect its
configured questionnaire for at most 600 wall-clock seconds; an abandoned form
interrupts and seals the attempt with `openmatb_post_task_timeout`. Recovery
begins as soon as the form closes. The observed task-to-recovery delay and the
prespecified limit are exported; RR received during the intervening state is
retained as unassigned raw evidence and is excluded from phase HRV metrics.
The synchronized child also watches its backend parent process and exits as an
interruption if that parent disappears.

If physiology cannot be collected, the operator may record a reason-coded
performance-only exception. This does not masquerade as HRV: physiology quality
is `missing_performance_only`, while MATB task validity remains independent.
Abort and interruption paths seal the data available at that point.

## 5. RR quality and HRV computation

Raw RR values are never overwritten. Corrected values and an artifact flag are
stored in separate columns.

### Artifact processing

- Physiological hard bounds: 300–2000 ms.
- Beat classification: the adaptive RR artifact method from
  [Lipponen and Tarvainen (2019)](https://pubmed.ncbi.nlm.nih.gov/31314618/).
- Correction: length-preserving interpolation only for the analysis series.
- Quality: corrected proportion, longest artifact run, out-of-bounds proportion,
  coverage, score, and `excellent` / `good` / `acceptable` / `poor` /
  `unusable` / `insufficient_data` label. Coverage below 95% is never labelled
  excellent, even when the few received beats are individually clean.

### Time-domain output

When at least two usable intervals exist in one continuous segment, MATB
computes mean NN, SDNN, RMSSD, lnRMSSD, SDSD, CVNN, NN50, pNN50, and
minimum/mean/maximum HR for each phase. A disconnected phase is explicitly
`not_computable`; successive segments are never joined into an artificial NN
difference.

### Frequency-domain output

The corrected uneven RR tachogram is cubic-interpolated to 4 Hz (linear only
when too few points support cubic interpolation), detrended, and analyzed using
a Hann-window Welch PSD. The frequency bands and five-minute minimum gate follow
the [1996 ESC/NASPE HRV measurement standard](https://pubmed.ncbi.nlm.nih.gov/8737210/);
the spectral estimator follows
[Welch's original method](https://doi.org/10.1109/TAU.1967.1161901). Output
includes:

- VLF: 0.0033–0.04 Hz;
- LF: 0.04–0.15 Hz;
- HF: 0.15–0.40 Hz;
- VLF/LF/HF/total power in ms²;
- LFnu, HFnu, LF/HF, band peaks, and the retained PSD samples.

Frequency-domain metrics are `not_computable` rather than guessed unless all
of the following are true:

- nominal phase duration is at least 300 seconds;
- summed RR coverage is at least 95%;
- RR quality is excellent, good, or acceptable;
- no Bluetooth disconnect occurred in the phase;
- no acquisition queue overflow occurred;
- no sensor contact loss was detected.

Phase changes are descriptive only: task minus baseline and recovery minus task
for HR, RMSSD, lnRMSSD, SDNN, LF, HF, and LF/HF. No causal or clinical label is
assigned.

## 6. MATB and workload output

The six-column OpenMATB CSV contract remains:

```text
logtime,scenario_time,type,module,address,value
```

A synchronized JSONL sidecar adds session ID, ordered sequence, monotonic time,
UTC time, and explicit scenario start/finish boundaries. In event schema v2,
nanosecond values are decimal strings so JavaScript/JSON consumers do not lose
integer precision. The boundary writer flushes and fsyncs both task and event
logs; normal high-rate rows are flushed but do not incur one disk sync per row.
On POSIX, creation of each CSV/JSONL capture file is followed by a parent-
directory fsync. Windows flushes the file handles but has no equivalent
portable Python directory-fsync guarantee; the Windows durability boundary is
stated explicitly below.
The converter retains the source rows and computes the available task outcomes
without creating a single unvalidated composite score:

- system monitoring: hits, misses, false alarms, correct-rejection estimate,
  hit rate, d-prime, and response time;
- communications: signal-detection counts/rates, d-prime, and response time;
- pursuit tracking: in-target proportion, center-deviation summaries, and
  recovery time;
- resource management: per-tank and combined tolerance, deviation, and recovery;
- subjective workload: ISA probes, all six NASA-TLX subscales and their
  unweighted mean on the 0–10 response scale (reported only when all six are
  complete), and Bedford;
- SAGAT fields when present;
- total activity plus event/input/performance/state counts by module.

`task_validity` and `physiology_quality` are always reported separately.

## 7. Immutable output bundle

Each attempt receives a UUID directory under `MATB_CLASSIC_OUTPUT_DIR`. Files
are staged, flushed, published with a checksum commit marker, and cannot be
overwritten. On POSIX, MATB also fsyncs files and affected directory entries.
On native Windows, file flush/fsync, exclusive creation, immutable names, and
post-publication checksum validation are enforced, but the portable
implementation does **not** claim power-loss-atomic NTFS directory publication.
Use an approved local NTFS data root, volume encryption, a UPS where required by
the protocol, and copy verified terminal bundles to institutional storage.
Terminal metadata, artifact rows, the analysis block, and
automatic selection commit in one database transaction. Every registered
artifact has a SHA-256 digest, and downloads are verified against the database
inventory. RR notifications are independently fsynced to a hidden capture
journal so a backend restart can seal the available beats instead of losing
in-memory data.

If report publication or its database transaction fails, the attempt remains
`FINALIZING` with its intended `ABORTED` or `INTERRUPTED` disposition and reason
stored in SQLite. Startup retries the bundle before committing the terminal
row, and also repairs older terminal rows that lack artifact registration.
Synthetic fallback CSV/JSONL captures are written to private staging files,
fsynced, atomically renamed, and followed by a POSIX directory fsync.

Bundle schema `matb-classic-bundle-v2` and RR schema `polar-h10-rr-v2` encode
JSON nanosecond fields as decimal strings. CSV retains ordinary decimal text.
The RR journal is sequence- and SHA-256-chain validated. Recovery tolerates
only a torn, non-newline-terminated final append; malformed or altered records
in the middle fail closed. OpenMATB CSV recovery likewise tolerates only an
incomplete final non-newline row and records that recovery in the metrics.
Registered terminal bundles are checksum-validated again during startup and
before download.

Provenance stores hashes of the exact allowlisted scenario and an explicit
OpenMATB runtime manifest: entrypoints, `core`/`plugins` Python code,
`config.ini`, `VERSION`, `requirements.txt`, questionnaires, instructions,
sounds, images, and compiled locale catalogs. Tests and bytecode caches are
excluded. Host/OS and Bleak versions, test-mode state, and wall-time scale are
also recorded. Changing the scenario or any runtime-manifest input between
prepare and start interrupts the attempt. Selecting a different retained
classic attempt replaces the canonical block provenance and invalidates any
visit-level DEPDF fit derived from the prior block. Exported provenance
intentionally records only the model
`Polar H10`; the advertised unit suffix, MAC address, Windows device ID, and
stable identifier hash are excluded from participant artifacts.

| File | Contents |
| --- | --- |
| `report.en.md` | English human-readable MATB + HRV report |
| `report.es.md` | Spanish human-readable MATB + HRV report |
| `session.json` | Complete machine-readable session, metrics, HRV, reactivity, and contracts |
| `session-metrics.csv` | Flattened MATB, physiology, quality, and reactivity metrics |
| `rr-intervals.csv` | Every raw RR plus corrected value, artifact flag, segment, and timing provenance |
| `rr-intervals.jsonl` | The same beat-level records as canonical JSON Lines |
| `hrv-psd.csv` | Phase/frequency/power PSD samples when gates pass |
| `openmatb-session.csv` | Original six-column task log |
| `openmatb-events.jsonl` | Synchronized lifecycle/event sidecar |
| `clock-anchors.json` | Monotonic-to-UTC anchors and discontinuities |
| `manifest.json` | Schema/algorithm contracts and artifact inventory |
| `checksums.sha256` | Bundle file digests |

The debrief can download individual files or a verified ZIP. Visit summaries in
Markdown, CSV, and JSON include every retake and the selected valid attempt.
The first complete valid task attempt is selected automatically; later manual
selection requires a reason code and creates an audit row. Retakes are retained.

## 8. Native Windows 11 procedure

Use Windows 11 build 22000 or later, Python 3.12+, Node 20+, an enabled BLE
adapter, and PowerShell 7. Run the H10 workflow natively; WSL Bluetooth
passthrough is outside this supported path.

From the repository root:

```powershell
$RepoRoot = (Get-Location).Path
$RuntimeRoot = Join-Path $env:LOCALAPPDATA "MATB\classic-runtime"
$DataRoot = Join-Path $env:LOCALAPPDATA "MATB\research-data\classic"
$PythonExe = Join-Path $RuntimeRoot "venv\Scripts\python.exe"
New-Item -ItemType Directory -Force -Path $RuntimeRoot, $DataRoot | Out-Null
python -m venv (Join-Path $RuntimeRoot "venv")
& $PythonExe -m pip install -r (Join-Path $RepoRoot "requirements-dev.txt")
& $PythonExe -m pip install -r (Join-Path $RepoRoot "openmatb\requirements.txt")
Set-Location (Join-Path $RepoRoot "webui\frontend")
npm ci
```

`$env:LOCALAPPDATA` normally inherits a per-user NTFS ACL. Verify it with
`icacls $DataRoot` before collection and apply the institution's service-account
ACL if any broad group has read or write access. Python mode bits do not create
a Windows DACL: MATB relies on that inherited NTFS ACL, while using exclusive
file creation and immutable bundle names. Keep BitLocker or the institution's
equivalent volume encryption enabled for this data root.

Backend terminal:

```powershell
$RepoRoot = (Resolve-Path ".\..\..").Path  # when currently in webui\frontend
$RuntimeRoot = Join-Path $env:LOCALAPPDATA "MATB\classic-runtime"
$DataRoot = Join-Path $env:LOCALAPPDATA "MATB\research-data\classic"
$PythonExe = Join-Path $RuntimeRoot "venv\Scripts\python.exe"
$env:PYTHONPATH = $RepoRoot
$env:MATB_DB_PATH = Join-Path $DataRoot "matb.db"
$env:MATB_CLASSIC_OUTPUT_DIR = Join-Path $DataRoot "attempts"
$env:MATB_CLASSIC_SCENARIO_DIR = Join-Path $RepoRoot "scenarios"
$env:MATB_OPENMATB_DIR = Join-Path $RepoRoot "openmatb"
$env:MATB_OPENMATB_PYTHON = $PythonExe
$env:MATB_POLAR_BACKEND = "bleak"
$env:MATB_FRONTEND_ORIGINS = "http://127.0.0.1:3100"
Set-Location (Join-Path $RepoRoot "webui\backend")
& $PythonExe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Frontend terminal:

```powershell
$RepoRoot = (Get-Location).Path
Set-Location (Join-Path $RepoRoot "webui\frontend")
npm run dev -- --hostname 127.0.0.1 --port 3100
```

Open `http://127.0.0.1:3100/classic/setup`.

Windows diagnostics:

```powershell
Get-PnpDevice -Class Bluetooth
Get-Service bthserv
$env:BLEAK_LOGGING = "1"
```

If scan fails, verify Bluetooth is on, the adapter has no warning state, the
Bluetooth Support Service is running, and another application is not holding
the sensor. If a headless BLE call hangs, confirm the backend was started as
shown—one console process, no reload, and no library forcing a GUI STA after
MATB's WinRT remediation.

## 9. Native Linux procedure

Use Python 3.12+, Node 20+, BlueZ 5.55+, D-Bus, a supported BLE adapter, and a
desktop/X11 environment for the OpenMATB task window. The account running MATB
must be authorized to use the system Bluetooth adapter.

```bash
REPO_ROOT="$(pwd)"
MATB_RUNTIME_ROOT="/opt/matb-classic-runtime"
CLASSIC_DATA_ROOT="/srv/matb-research/classic"
python3 -m venv "$MATB_RUNTIME_ROOT/venv"
"$MATB_RUNTIME_ROOT/venv/bin/python" -m pip install -r "$REPO_ROOT/requirements-dev.txt"
"$MATB_RUNTIME_ROOT/venv/bin/python" -m pip install -r "$REPO_ROOT/openmatb/requirements.txt"
(cd "$REPO_ROOT/webui/frontend" && npm ci)
mkdir -p "$CLASSIC_DATA_ROOT"
chmod 0700 "$CLASSIC_DATA_ROOT"
```

MATB additionally creates attempt directories as mode `0700` and bundle files
and the SQLite database as mode `0600` on POSIX systems. Keep the enclosing data
directory private as shown so transient SQLite and capture sidecars inherit a
restricted namespace.

Replace the two absolute locations above with institution-approved writable
directories. Keep both outside the source checkout; the data root should be
encrypted and access controlled.

Backend terminal:

```bash
REPO_ROOT="$(pwd)"
MATB_RUNTIME_ROOT="/opt/matb-classic-runtime"
CLASSIC_DATA_ROOT="/srv/matb-research/classic"
export PYTHONPATH="$REPO_ROOT"
export MATB_DB_PATH="$CLASSIC_DATA_ROOT/matb.db"
export MATB_CLASSIC_OUTPUT_DIR="$CLASSIC_DATA_ROOT/attempts"
export MATB_CLASSIC_SCENARIO_DIR="$REPO_ROOT/scenarios"
export MATB_OPENMATB_DIR="$REPO_ROOT/openmatb"
export MATB_OPENMATB_PYTHON="$MATB_RUNTIME_ROOT/venv/bin/python"
export MATB_POLAR_BACKEND="bleak"
export MATB_FRONTEND_ORIGINS="http://127.0.0.1:3100"
cd "$REPO_ROOT/webui/backend"
"$MATB_RUNTIME_ROOT/venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Frontend terminal:

```bash
REPO_ROOT="$(pwd)"
cd "$REPO_ROOT/webui/frontend"
npm run dev -- --hostname 127.0.0.1 --port 3100
```

Open `http://127.0.0.1:3100/classic/setup`.

Linux diagnostics:

```bash
bluetoothctl show
rfkill list bluetooth
systemctl status bluetooth
bluetoothd --version
```

Set `BLEAK_LOGGING=1` before starting the backend for detailed D-Bus/BLE logs.
Common structured API failures distinguish powered-off, unavailable,
unsupported, access-denied, service-unavailable, token-expired, missing-HRS,
and connection failures. Correct BlueZ/D-Bus permissions through the host's
normal policy mechanism; do not run the whole research console as root.

## 10. Verification without participant data

The simulator backend exists only for automated tests and never becomes the
default. The production default is `MATB_POLAR_BACKEND=bleak`; selecting
`simulated` is rejected unless `MATB_CLASSIC_TEST_MODE=1` is also explicit.
Every test-mode attempt is visibly labeled, records its acceleration factor,
is forced to `task_validity=invalid`, and cannot become the selected visit
attempt.

The simulator emits RR frames only when an automated test calls its explicit
injection method. Merely setting simulator environment variables does not
produce a pulse stream and cannot pass a manual browser preflight. It is
therefore not a hardware-free UI collector or a substitute for an H10 dry run.

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/physiology -q
PYTHONDONTWRITEBYTECODE=1 python -m pytest webui/backend/tests/test_classic_session_models.py webui/backend/tests/test_classic_persistence.py webui/backend/tests/test_classic_runtime.py webui/backend/tests/test_classic_endpoints.py webui/backend/tests/test_classic_system.py -q
(cd openmatb && PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/test_launch_contract.py -q)
(cd webui/frontend && npm test && npm run typecheck && npm run build)
```

Before enrolling a participant, run one pseudonymous dry run at each workload
on every intended host/adapter combination (at minimum, each Windows and Linux
configuration that will collect data) and verify:

- the preflight shows a live HR and RR count;
- all three automatic phases occur in order;
- the task window exits normally;
- the debrief shows task validity and physiology quality separately;
- all 12 artifacts download and match `checksums.sha256`;
- raw RR counts and reconnect/contact/overflow fields are plausible;
- gated frequency metrics remain unavailable when a deliberately degraded dry
  run violates a gate;
- abort produces an immutable partial bundle rather than deleting the attempt.

Automated and simulated tests cannot validate RF conditions, electrode contact,
the installed Bluetooth adapter/driver, WinRT behavior, BlueZ/D-Bus policy, or
real H10 firmware. A successful physical dry run and institutional data-path
review are therefore release gates, not optional substitutes for the test
suite.

Keep the database and `MATB_CLASSIC_OUTPUT_DIR` together in the institution's
encrypted, access-controlled research-data location. Back them up as one unit.
Do not commit participant data, BLE identifiers, leases, or artifact bundles.
