# Swarm release and workstation qualification

Scope: the local MATB synthetic supervisory application, including its versioned
swarm condition. This procedure does not grant clinical, flight, public-server,
or human-factors qualification. See [implementation and operator details](suas-swarm-supervision.md).

## Candidate identity and compatibility

| Item | Identity |
| --- | --- |
| Bundled scenario | `swarm_supervision`, schema 2, PRACTICE/LOW/MEDIUM/HIGH = 2/4/6/8 aircraft |
| Coordination | `fixed-slot-v1`, 60 m spacing in the bundled scenario |
| Engine | `2.0.0-swarm.1`; non-swarm scenarios retain `1.0.0` |
| Console | `mission-swarm-console`, version 1, content hash pinned in the manifest |
| Presentation | v3, `racing-quad-v1-scale80`, north-up inset pinned on |
| Debrief extension | `swarm-descriptive-v1`; mission composite unchanged |

The 80x model enlargement is a recorded visualization choice. No new database
migration is required by this extension. Existing recordings remain immutable;
new fields are omitted from legacy worlds. Rollback must preserve new recordings:
a pre-swarm executable cannot verify a swarm engine recording. Keep a matching
reader/runtime with each archived candidate. Do not reinterpret a swarm record
under an older engine identity.

## Build and start

Use the repository dependency locks and an isolated Python 3.12+ environment.
For Windows, the maintained launcher resolves the local Python/Node installation,
builds the frontend and starts loopback services. From the repository root in
PowerShell 7:

```powershell
& ./windows-launchers/scripts/Initialize-MatbUas.ps1
& ./windows-launchers/scripts/Start-MatbUasConsole.ps1
```

For Linux or WSL2, from the repository root:

```bash
MATB_VENV="$PWD/.venv-suas" bash scripts/install_suas.sh
MATB_VENV="$PWD/.venv-suas" bash scripts/run_suas.sh
```

For either platform, use the launcher's `DataRoot` / `--data-dir` option to select
a dedicated persistent data directory; see [Windows launcher details](../../windows-launchers/README.md)
and [Console setup](../../README.md#quick-start-research-console). Deployment uses
`npm run build` followed by `next start` through the launcher. `npm run dev` is a
development workflow. Do not rebuild an output directory while a running Next
service uses it; use a separate `MATB_NEXT_DIST_DIR` or stop the owned service first.

Before an update, finish or explicitly interrupt active sessions and stop both
owned services. Back up the complete SQLite directory (including any WAL/SHM
files) and the associated recording/artifact directory while services are stopped.
Keep the prior source revision and dependency locks with the backup. Restart only
a consistent code/build pair. The Windows stop script verifies tracked processes;
do not kill unrelated listeners to free ports. Never overwrite data to repair a
failed upgrade. To roll back, stop the updated services and restore the previous
code/build plus its matching backup into a separate data directory for inspection.
Retain recordings made with the updated candidate and their matching replay runtime.

## Automated gates

Install development dependencies as described in the root README. Set
`PYTHONDONTWRITEBYTECODE=1` to avoid changing tracked legacy bytecode. From the root:

```bash
python -m matb_integration.suas.cli validate scenarios/suas/swarm_supervision.yaml
python -m pytest tests/suas -q -p no:cacheprovider
python -m pytest tests/documentation/test_documentation.py -q -p no:cacheprovider
python scripts/verify_documentation.py
```

From `webui/backend`, using the same Python with its pinned dependencies:

```bash
python -m pytest tests/test_simulation_runtime.py tests/test_simulation_endpoints.py tests/test_simulation_failures.py -q -p no:cacheprovider
```

From `webui/frontend`:

```bash
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e:swarm
```

The dedicated Playwright configuration starts fresh services on 8186/3186 with
synthetic databases/exports under `.test-tmp`. `MATB_PYTHON` selects the backend
interpreter. `MATB_SWARM_API_PORT` and `MATB_SWARM_UI_PORT` override occupied ports.
Existing services are never reused. `.github/workflows/matb-ci.yml` includes this
functional gate for its Windows/Linux matrix and retains test artifacts.
A locally edited workflow has not run in hosted CI until the candidate is pushed.

## Hardware performance gate

Functional headless success is separate from workstation performance. Run on the
intended operator machine, with the intended browser, screen size and graphics
driver. The benchmark uses eight drones, an installed terrain scene, trails and
the inset, a two-second warmup followed by a ten-second sample at 1920x1080/DPR 1.
It records renderer identity, browser version, draw calls, triangles, memory,
median/p95 submission intervals and CPU submission time. It includes long stalls;
it does not measure GPU completion or physical screen onset.

PowerShell example after building:

```powershell
$env:MATB_PYTHON = (Resolve-Path ../../.venv-suas/Scripts/python.exe).Path
$env:MATB_SWARM_GPU = '1'
$env:MATB_SWARM_REQUIRE_PERFORMANCE = '1'
npm run test:e2e:swarm
```

Run the example from `webui/frontend`. `MATB_SWARM_GPU=1` requests ANGLE D3D11 on
Windows; omit it for Linux/default browser graphics. The strict gate rejects
software renderer identities, requires at least 120 samples and p95 intervals
below 33.3 ms. A failed gate blocks the 3D workstation claim. Do not remove the
threshold or label CPU timing as screen latency. Match reduced-motion and
interpolation settings to the frozen study condition. Qualify physical onset
separately when the study requires it.

Artifacts are written to `.next/swarm-acceptance`, including `swarm-metrics.json`,
screenshots and a synthetic debrief. For manual checks, open a technical mission
with `?metrics=1`, then use `window.__matbResetPresentationMetrics()` after warmup
and `window.__matbPresentationMetrics()` after the sample. These diagnostics are
available only on the explicit metrics URL. Pauses, hidden tabs and camera/scene
changes should not be mixed into one continuous-motion comparison.

## Operator acceptance and failure behavior

1. Open `/mission/test`, select the swarm scenario, HIGH, a prepared local scene,
   the v3 swarm option and 3D. Confirm that readiness finishes and eight members appear.
2. Issue a line/wedge transit and cooperative search. Verify acceptance, visible
   routes, group counts and the inset. Invalid group commands reject atomically.
3. Hold/resume the group; detach a held member, exercise individual control, hold
   it and the group, rejoin and issue a new group task. Resume alone after JOIN is
   rejected because old routes must not silently become a new coordinated task.
4. Switch overview/chase/free orbit, change observed group independently of command
   group and navigate with the keyboard. Resize and check at the intended zoom.
5. Observe a configured loss event. The unavailable member leaves coordination;
   survivors retain their routes until an explicit reassignment. The remaining
   member count is not a percentage of the original group size.
6. Verify SAGAT conceals the scene, inset and group controls. Verify an observer
   cannot submit group commands. A WebGL failure reports unavailable presentation;
   reload and requalify before resuming a research session.
7. Finish and open the sealed debrief. Require replay `match`, seek backward and
   forward and confirm recorded view controls stay locked. Inspect group metrics
   and download the public bundle. Missing metric observations remain null.

The fault-response measure is the elapsed simulation time until the next accepted
group task command after the pending fault. Membership edits are not counted as
group task commands. Formation error is a sampled mean residual from fixed slots,
not collision risk. First new coverage after an observed fault is mission-wide:
other groups can contribute, and it is not evidence of complete task recovery.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Scene missing or hash mismatch | Prepare/reinstall the matching offline scene; never substitute a different hash in a frozen condition. |
| `explicit v3` rejection | Set presentation version 3 in the study authoring workflow and freeze a new condition. |
| Group command rejected | Read the member/reason; resolve link, energy, geometry or ownership constraints before retrying with a new command ID/current state. |
| JOIN or RESUME rejected | Hold the member/group, JOIN, then issue a new SEARCH or formation waypoint. |
| Renderer unavailable or context lost | Pause/reload/requalify; retain failure exposure and any protocol deviation. |
| Performance gate fails | Confirm actual GPU identity, graphics acceleration, driver, viewport and background load; retain the failed measurement and rerun after an actual change. |
| Locked `.next` output | Stop only the owned app or use a separate build directory consistently for build and start. |
| FastAPI/Starlette import or constant error | Install the repository-pinned backend versions in the selected Python environment; avoid mixing user-site packages. |
| Ports already in use | Select unused test ports; do not terminate an unrelated app. |

The strict local graphics gate passed on Intel Iris Xe at 1920x1080. Release status and measured results are recorded in the [implementation guide](suas-swarm-supervision.md#release-hardening-2026-09-21).
No source commit, deployment or hosted-CI result is implied by a local test run.
