# sUAS C2 Phase 6 — Linux Delivery and Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove and package the complete simulator for offline Linux use with headless browser coverage, accessibility/responsive QA, deterministic soak tests, one-command launch, and final regression evidence.

**Architecture:** Repository-owned Playwright tests drive an isolated FastAPI/Next.js test deployment and accelerated fixture protocol. Shell launch/install scripts orchestrate production processes without Docker or a display server; Python soak/offline checks exercise the authoritative engine independently of the UI.

**Tech Stack:** Bash, Python 3.12, pytest, FastAPI/Uvicorn, Node.js 20+, Next.js, Playwright Test 1.55, `@axe-core/playwright` 4.10, Chromium/headless Chrome, existing Vitest/Testing Library.

## Global Constraints

- Complete and push Phases 1–5 first.
- Read the approved design and every prior phase plan before editing.
- Runtime must work after installation with no internet, Docker, X11, Wayland, remote tile/font, telemetry, or analytics dependency.
- Wall-time acceleration is available only when both `MATB_SIMULATION_TEST_MODE=1` and `MATB_SIMULATION_WALL_TIME_SCALE` is in `[0.05, 1.0]`; production ignores the scale variable.
- Browser screenshots and traces must never contain controller leases or hidden truth.
- Reference viewports are 1280×720 and 1920×1080; keyboard-only and reduced-motion paths are required.
- The production launcher binds both services to `127.0.0.1` unless the researcher explicitly overrides documented bind variables.
- Preserve all master-plan non-kinetic, privacy, determinism, regression, and Git constraints.

---

### Task 1: Isolated headless Playwright harness and fast research fixture

**Files:**
- Modify: `webui/frontend/package.json`
- Modify: `webui/frontend/package-lock.json`
- Create: `webui/frontend/playwright.config.ts`
- Create: `webui/frontend/e2e/fixtures.ts`
- Create: `webui/frontend/e2e/mission-flow.spec.ts`
- Create: `tests/suas/fixtures/e2e_area_search.yaml`
- Modify: `webui/backend/app/db.py`
- Modify: `webui/backend/app/main.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: complete backend/frontend protocol.
- Produces: `npm run test:e2e`, isolated DB/artifact/scenario roots, full setup→practice→LOW/MEDIUM/HIGH→debrief test.

- [x] **Step 1: Install exact browser-test dependencies and scripts**

Run from `webui/frontend`:

```bash
npm install --save-dev @playwright/test@1.55.0 @axe-core/playwright@4.10.2
```

Add scripts:

```json
{
  "test:e2e": "playwright test",
  "test:e2e:update": "playwright test --update-snapshots"
}
```

- [x] **Step 2: Add environment-configurable DB/scenario roots with secure defaults**

`db.py` resolves `MATB_DB_PATH` when set, otherwise retains `webui/backend/matb_webui.db`. Reject an empty path and expand/resolve it. `main.py` resolves `MATB_SIMULATION_SCENARIO_DIR` only when set; default remains repo `scenarios/suas`. When test mode is exactly `1`, parse `MATB_SIMULATION_WALL_TIME_SCALE` as a finite decimal in `[0.05, 1.0]` and multiply both tick-loop and snapshot-loop sleeps by it; authoritative tick size, snapshot interval in simulation time, event schedule, hashes, and state results remain unchanged. Outside test mode force scale `1.0`. Ignore `webui/frontend/test-results/`, `webui/frontend/playwright-report/`, `.suas-e2e/`, and `/exports/`.

- [x] **Step 3: Create a valid short-duration fixture with every protocol gate**

`tests/suas/fixtures/e2e_area_search.yaml` uses the same geometry/types as the reference but durations PRACTICE=4 s and LOW/MEDIUM/HIGH=6 s, two aircraft per block, one contact, explicit `isa_times_s: [1]`, one SAGAT freeze in `[2,3]` s, and no scheduled conflict/lost-link event. With the Phase 5 dynamic guard, at least one 100 ms SAGAT tick remains eligible. It remains strict-schema valid and is marked only by its scenario ID `e2e_area_search`; production never points at this directory.

- [x] **Step 4: Configure Playwright's two local web servers and isolation**

`playwright.config.ts` must use one worker, Chromium, trace on first retry, screenshots only on failure, base URL `http://127.0.0.1:3100`, and two `webServer` entries. Both receive a shared `.suas-e2e/<process-id>` root for DB/artifacts and these environment variables:

At module load, resolve the repository root from `import.meta.url`, set `const e2eRoot = path.join(repoRoot, ".suas-e2e", String(process.pid))`, and create that exact directory with `fs.mkdirSync(e2eRoot, { recursive: true })`. Pass absolute paths derived from `e2eRoot`; do not use shell interpolation or a shared developer database.

```text
MATB_DB_PATH=<root>/matb-e2e.db
MATB_SIMULATION_OUTPUT_DIR=<root>/exports
MATB_SIMULATION_SCENARIO_DIR=<repo>/tests/suas/fixtures
MATB_SIMULATION_TEST_MODE=1
MATB_SIMULATION_WALL_TIME_SCALE=0.1
MATB_BACKEND_PORT=8000
```

Backend command: `python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000` from `webui/backend`. Frontend command: `npm run dev` from `webui/frontend`. Reuse existing servers only when `PW_REUSE_SERVER=1`; CI/default isolation must fail on occupied ports instead of connecting to an unknown service.

- [x] **Step 5: Write the failing full mission-flow browser test**

```ts
test("researcher completes the full native sUAS protocol", async ({ page, request }, testInfo) => {
  const participantNumber = ((process.pid % 9_999) + 1) * 60 + testInfo.retry * 6;
  const participant = `P${String(participantNumber).padStart(2, "0")}`;
  // Every generated suffix is divisible by 6, selecting LOW/MEDIUM/HIGH.
  await request.post("http://127.0.0.1:8000/participants", {
    data: { id: participant, enrollment_date: "2026-08-01" },
  });
  await page.goto("/mission/setup");
  await selectSetup(page, participant, "e2e_area_search", "en");
  await page.getByRole("checkbox", { name: /research instrument/i }).check();
  await page.getByRole("button", { name: /prepare session/i }).click();
  await expect(page).toHaveURL(/\/mission\?session=sim-/);
  await completeBlock(page, "PRACTICE");
  await completeBlock(page, "LOW");
  await completeBlock(page, "MEDIUM");
  await completeBlock(page, "HIGH");
  await expect(page).toHaveURL(/\/mission\/debrief/);
  await expect(page.getByText(/deterministic replay verified/i)).toBeVisible();
  await expect(page.getByText(/descriptive feedback only/i)).toBeVisible();
});
```

`completeBlock()` starts the expected next block, assigns active aircraft to valid sectors, responds to ISA 1–10, verifies map/fleet/contact/alert DOM is absent during SAGAT, selects one available answer for every SAGAT probe, completes all six TLX values and Bedford, and waits for READY_FOR_BLOCK/FINISHED. It must not bypass UI through debug endpoints.

- [x] **Step 6: Run E2E once to confirm failure, then finish fixtures/config until it passes**

Run: `cd webui/frontend && npm run test:e2e -- e2e/mission-flow.spec.ts`

Expected before completion: FAIL at the first uncovered integration mismatch. Fix only fixture/config/real product defects; do not weaken assertions or add test-only mission endpoints. Expected after completion: PASS.

- [x] **Step 7: Run unit/type/build plus E2E regression**

```bash
cd webui/frontend
npm test -- --run
npm run typecheck
npm run build
npm run test:e2e -- e2e/mission-flow.spec.ts
```

Expected: PASS.

- [x] **Step 8: Commit and push Task 1**

```bash
git add webui/frontend/package.json webui/frontend/package-lock.json webui/frontend/playwright.config.ts webui/frontend/e2e/fixtures.ts webui/frontend/e2e/mission-flow.spec.ts tests/suas/fixtures/e2e_area_search.yaml webui/backend/app/db.py webui/backend/app/main.py .gitignore
git diff --cached --check
git commit -m "test(suas): cover the complete browser mission flow"
git push origin HEAD
```

### Task 2: Accessibility, keyboard, responsive, observer, and reconnect browser QA

**Files:**
- Create: `webui/frontend/e2e/accessibility.spec.ts`
- Create: `webui/frontend/e2e/reconnect-observer.spec.ts`
- Create: `webui/frontend/e2e/responsive.spec.ts`
- Create: `webui/frontend/e2e/screenshots/mission-1280x720-linux.png`
- Create: `webui/frontend/e2e/screenshots/mission-1920x1080-linux.png`
- Modify: `webui/frontend/src/components/mission/MissionConsole.tsx`
- Modify: `webui/frontend/src/components/mission/map/MissionMap.tsx`
- Modify: `webui/frontend/src/app/globals.css`

**Interfaces:**
- Consumes: Playwright harness and mission UI.
- Produces: automated WCAG-oriented scan, keyboard workflow, controller disconnect pause, observer mode, and stable reference screenshots.

- [x] **Step 1: Write failing axe and keyboard-only tests**

```ts
test("live mission has no serious axe violations and works by keyboard", async ({ page }) => {
  await openRunningMission(page);
  const results = await new AxeBuilder({ page }).include(".simulation-console").analyze();
  expect(results.violations.filter(v => ["serious", "critical"].includes(v.impact ?? "")))
    .toEqual([]);
  await page.keyboard.press("Tab");
  await focusByKeyboard(page, /UAS-01/);
  await page.keyboard.press("Enter");
  await focusByKeyboard(page, /hold/i);
  await page.keyboard.press("Enter");
  await expect(page.getByText(/command accepted/i)).toBeVisible();
});

test("reduced motion disables sweep and position transitions", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openRunningMission(page);
  await expect(page.locator(".signal-sweep")).toHaveCSS("animation-name", "none");
  await expect(page.locator("[data-aircraft-id='UAS-01']"))
    .toHaveCSS("transition-duration", "0s");
});
```

- [x] **Step 2: Write failing observer and controller-disconnect tests**

Open a controller page and a second context without its session-storage lease. Assert the second is labeled observer and has no enabled command controls. Close the controller page, assert backend/session observer stream reports PAUSED, reconnect with the saved lease, assert the UI remains paused, then explicitly resume.

- [x] **Step 3: Write responsive/reference screenshot tests**

At 1280×720 assert no document-level horizontal overflow, map bounding box at least 640×420, right detail opens as a keyboard-focusable drawer, and all critical controls remain reachable. At 1920×1080 assert three-column layout. Mask only the wall-clock string, never mission content, then compare full-page screenshots at a fixed seeded tick with max pixel-difference ratio 0.01.

- [x] **Step 4: Run tests to expose real accessibility/layout defects, then repair product code**

Run:

```bash
cd webui/frontend
npm run test:e2e -- e2e/accessibility.spec.ts e2e/reconnect-observer.spec.ts e2e/responsive.spec.ts
```

Repair missing names/roles/focus, status text/shape, contrast, overflow, drawer behavior, and reduced-motion CSS in product components. Do not suppress axe rules without a documented false-positive assertion tied to an element.

- [x] **Step 5: Generate and inspect reference screenshots once**

Run: `cd webui/frontend && npm run test:e2e:update -- e2e/responsive.spec.ts`

Inspect both images with the local image viewer before staging. Confirm no lease, filesystem path, hidden truth, browser error overlay, clipped control, or real-world map appears.

- [x] **Step 6: Run all browser tests twice for flake detection**

```bash
cd webui/frontend
npm run test:e2e
npm run test:e2e
```

Expected: both runs PASS without retry-only success.

- [x] **Step 7: Commit and push Task 2**

```bash
git add webui/frontend/e2e/accessibility.spec.ts webui/frontend/e2e/reconnect-observer.spec.ts webui/frontend/e2e/responsive.spec.ts webui/frontend/e2e/screenshots webui/frontend/src/components/mission/MissionConsole.tsx webui/frontend/src/components/mission/map/MissionMap.tsx webui/frontend/src/app/globals.css
git diff --cached --check
git commit -m "test(suas): harden accessible mission operations"
git push origin HEAD
```

### Task 3: Offline Linux installer and one-command launcher

**Files:**
- Create: `scripts/install_suas.sh`
- Create: `scripts/run_suas.sh`
- Create: `scripts/lib/suas_processes.sh`
- Create: `tests/scripts/test_suas_scripts.sh`
- Modify: `setup.sh`
- Modify: `README.md`
- Modify: `webui/README.md`

**Interfaces:**
- Consumes: root/backend requirements and built frontend.
- Produces: repeatable installation, localhost production launch, clean shutdown, health/error diagnostics, shell regression tests.

- [x] **Step 1: Write failing shell contract tests**

```bash
#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_tmp="$(mktemp -d)"
trap 'rm -rf -- "$test_tmp"' EXIT
error_file="$test_tmp/error.txt"

bash -n "$repo_root/scripts/install_suas.sh"
bash -n "$repo_root/scripts/run_suas.sh"

help_text="$(bash "$repo_root/scripts/run_suas.sh" --help)"
[[ "$help_text" == *"--backend-port"* ]]
[[ "$help_text" == *"--frontend-port"* ]]
[[ "$help_text" == *"127.0.0.1"* ]]

if bash "$repo_root/scripts/run_suas.sh" --backend-port not-a-port 2>"$error_file"; then
  echo "invalid port unexpectedly succeeded" >&2
  exit 1
fi
grep -q "port must be an integer" "$error_file"
```

Before cleanup, validate that `test_tmp` is nonempty and is a direct child of `${TMPDIR:-/tmp}`; the trap removes only that exact directory.

- [x] **Step 2: Run shell tests and confirm scripts are missing**

Run: `bash tests/scripts/test_suas_scripts.sh`

Expected: FAIL because scripts do not exist.

- [x] **Step 3: Implement focused process helpers and installer**

`scripts/lib/suas_processes.sh` provides `require_command`, `validate_port`, `wait_http`, `terminate_pid`, and `port_in_use` without evaluating strings. `install_suas.sh`:

1. resolves repository root from its own file;
2. requires Python ≥3.12 and Node ≥20;
3. creates `.venv` unless `MATB_VENV` is explicitly set;
4. installs `requirements-dev.txt` into that venv;
5. runs `npm ci` and `npm run build` in frontend;
6. runs root/backend/frontend smoke tests;
7. prints the offline launcher command.

Installation may require network for dependencies; the completed runtime must not. Never install globally or use `sudo`.

- [x] **Step 4: Implement safe production launcher**

`run_suas.sh` accepts `--backend-port`, `--frontend-port`, `--backend-bind`, `--frontend-bind`, `--data-dir`, and `--help`; defaults binds to `127.0.0.1`, ports 8000/3100, data to repo `var/suas`. It sets `umask 077` before creating data so DB, private questionnaire records, checkpoints, logs, and exports are owner-only by default. It verifies venv/frontend build/scenario, rejects occupied/invalid ports, creates only the explicit data/log directories, and exports `MATB_DB_PATH=<data>/db/matb-webui.db`, `MATB_SIMULATION_OUTPUT_DIR=<data>/exports`, and exact localhost/127.0.0.1 frontend origins for the selected port through `MATB_FRONTEND_ORIGINS` to Uvicorn. It starts Uvicorn and `webui/frontend/node_modules/.bin/next start --hostname <bind> --port <port>` as separate process groups, passing `MATB_BACKEND_PORT=<backend-port>` to Next's runtime-config route. It waits for both health URLs, prints PIDs/URLs/logs, and blocks until SIGINT/SIGTERM. One idempotent trap terminates both children, waits, and reports nonzero child exits. Non-loopback bind overrides require an explicit documented `MATB_FRONTEND_ORIGINS`; the launcher never guesses a public origin. Never use `eval`, unresolved globs, `kill -9`, or a broad recursive delete.

Update `setup.sh` to mention/delegate `bash scripts/install_suas.sh` when `MATB_INSTALL_SUAS=1`; preserve its current default behavior.

- [x] **Step 5: Extend shell tests with stubbed processes and cleanup assertions**

Put stub `python3`, `node_modules/.bin/next`, and health helper commands first in test-owned locations. Assert exact argv, default bind addresses, data-root containment, created file mode no broader than `0600`, directory mode no broader than `0700`, both PIDs terminated on TERM, no process after exit, and refusal to use `/`, the resolved home directory, or repository root as `--data-dir`.

- [x] **Step 6: Run shell/unit/build checks and document operation**

```bash
bash tests/scripts/test_suas_scripts.sh
bash -n setup.sh scripts/install_suas.sh scripts/run_suas.sh scripts/lib/suas_processes.sh
cd webui/frontend && npm run build
```

Document installation versus offline runtime, SSH port-forward development access, local-browser deployment, logs/data paths, bind override risk, shutdown, and recovery.

- [x] **Step 7: Commit and push Task 3**

```bash
git add scripts/install_suas.sh scripts/run_suas.sh scripts/lib/suas_processes.sh tests/scripts/test_suas_scripts.sh setup.sh README.md webui/README.md
git diff --cached --check
git commit -m "feat(suas): add offline Linux launcher"
git push origin HEAD
```

### Task 4: Deterministic soak, failure-cycle, performance, and offline checks

**Files:**
- Create: `tests/suas/test_soak.py`
- Create: `tests/suas/test_performance.py`
- Create: `scripts/test_suas_offline.sh`
- Create: `pytest.ini`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: complete engine, recorder, replay, backend, launcher.
- Produces: `slow`/`performance` test markers, seeded all-profile soak, reconnect/failure cycles, offline static/runtime audit.

- [x] **Step 1: Write deterministic all-profile soak tests**

```python
@pytest.mark.slow
@pytest.mark.parametrize("seed", [1, 42, 20260801])
@pytest.mark.parametrize("profile", ["PRACTICE", "LOW", "MEDIUM", "HIGH"])
def test_complete_block_records_and_replays(seed, profile, tmp_path) -> None:
    run = run_accelerated_block(seed=seed, profile=profile, output=tmp_path / profile)
    first = ReplayVerifier().verify(run)
    second = ReplayVerifier().verify(run)
    assert first.status is ReplayStatus.MATCH
    assert second == first
    assert verify_checksum_file(run / "checksums.sha256") == ()

@pytest.mark.slow
def test_all_six_latin_orders_complete_without_state_leak(tmp_path) -> None:
    hashes = [run_complete_protocol(f"P{i:02d}", tmp_path / str(i)) for i in range(1, 7)]
    assert len(hashes) == 6
    assert all(len(value) == 64 for value in hashes)
```

- [x] **Step 2: Write real-time budget and repeated pause/recovery tests**

`test_performance.py` advances an 8-aircraft HIGH engine for 6,000 ticks without sleeping, asserts every step remains deterministic, and records median/p95 wall duration. Mark `performance`; assert p95 under 100 ms (one real-time tick budget) on the development host, with actual values in failure output. Add 25 pause/resume, controller reconnect, checkpoint interruption/recovery cycles and assert no task/file descriptor leak and matching replay.

- [x] **Step 3: Implement offline audit script**

`scripts/test_suas_offline.sh` runs:

1. a scoped source scan over `matb_integration/suas`, `webui/backend/app/simulation*`, `webui/backend/app/routers/simulation.py`, and `webui/frontend/src/**/simulation|mission/**` rejecting `http://`/`https://` except documented localhost API constants;
2. a scoped non-kinetic command scan rejecting command/type identifiers containing `WEAPON`, `ENGAGE`, `FIRE`, `STRIKE`, `TARGET_ASSIGN`, or `DAMAGE`;
3. strict scenario validation;
4. a recorded HIGH CLI run and verification inside `mktemp -d`;
5. frontend production build with proxy environment variables pointing to an unreachable local port;
6. launcher health check when the built artifacts and venv exist.

The script traps cleanup for its exact temporary directory and PIDs; it never deletes repository/user data.

- [x] **Step 4: Register markers and run targeted soak/offline checks**

```ini
# pytest.ini
[pytest]
markers =
    slow: complete accelerated simulation protocols
    performance: wall-clock budget checks for the deterministic engine
```

Run:

```bash
python3 -m pytest tests/suas -m slow -q
python3 -m pytest tests/suas -m performance -q
bash scripts/test_suas_offline.sh
```

Expected: PASS with reported p50/p95 below the 100 ms tick budget.

- [x] **Step 5: Commit and push Task 4**

```bash
git add tests/suas/test_soak.py tests/suas/test_performance.py scripts/test_suas_offline.sh pytest.ini .gitignore
git diff --cached --check
git commit -m "test(suas): add deterministic offline soak gates"
git push origin HEAD
```

### Task 5: Final documentation, complete regression matrix, and release-readiness commit

**Files:**
- Modify: `README.md`
- Modify: `webui/README.md`
- Modify: `webui/backend/README.md`
- Modify: `webui/frontend/README.md`
- Modify: `CHANGELOG.md`
- Create: `docs/implementation/suas-c2-v1-verification.md`

**Interfaces:**
- Consumes: all implemented features/tests.
- Produces: accurate runbook, capability boundaries, verification evidence, and final V1 readiness record.

- [x] **Step 1: Audit documentation against live commands and routes**

Run every documented command with `--help` or a test fixture. Search for stale claims that the frontend is pending, that OpenMATB is required for native sUAS, that Windows is required, or that V1 includes manual flight/real maps/weapons. Correct exact ports, environment variables, paths, route names, protocol durations, scale ranges, artifact schema, and recovery behavior.

- [x] **Step 2: Write the verification report template with actual-command fields**

`docs/implementation/suas-c2-v1-verification.md` must contain date/commit/platform versions, commands, pass/fail counts, headless viewports, p50/p95 tick timing, replay hashes for one block each, E2E duration, offline audit result, screenshot paths, known research limitations, and a requirement-by-requirement table for all ten Design §17 acceptance criteria. Populate it only from actual final runs; do not claim unrun evidence.

- [x] **Step 3: Run the complete regression matrix from clean processes**

```bash
python3 -m pytest tests/suas -q
python3 -m pytest tests -q
cd webui/backend && python3 -m pytest -q
cd webui/frontend && npm test -- --run
cd webui/frontend && npm run typecheck
cd webui/frontend && npm run build
cd webui/frontend && npm run test:e2e
python3 -m pytest tests/suas -m slow -q
python3 -m pytest tests/suas -m performance -q
bash tests/scripts/test_suas_scripts.sh
bash scripts/test_suas_offline.sh
```

Record exact outputs in the verification report. If any command fails, stop, fix through a focused implementation commit with its own test/push, then rerun the entire matrix.

- [x] **Step 4: Perform final repository and artifact safety checks**

```bash
git status --short
git diff --check
rg -n "controller_lease|correct_answer|contact.*truth" webui/frontend/e2e/screenshots webui/frontend/test-results 2>/dev/null || true
```

Confirm the status contains only known pre-existing unrelated files plus the intended documentation changes, no processes remain, no test DB/artifacts are staged, checksum verification passes, and reference screenshots contain no sensitive values.

- [x] **Step 5: Update all docs and CHANGELOG with evidence-backed status**

Document V1 as a research simulator, not certified/operational software. List implemented non-kinetic functions and explicit deferrals. Add installation, launch, setup, live console, disconnect recovery, debrief/export, test, and troubleshooting sections. Include the exact verification commit only after it exists; if documenting within that commit, use `verification_commit: this commit` rather than a guessed SHA.

- [x] **Step 6: Commit and push the final Phase 6 gate**

```bash
git add README.md webui/README.md webui/backend/README.md webui/frontend/README.md CHANGELOG.md docs/implementation/suas-c2-v1-verification.md
git diff --cached --check
git commit -m "docs(suas): document V1 implementation evidence"
git push origin HEAD
```

- [x] **Step 7: Report completion without starting deferred work**

Report the remote branch, final commit, exact test matrix results, artifact/run instructions, remaining pre-existing dirty files, and explicit V1 deferrals. Do not begin PX4/ArduPilot, real maps, multi-operator, physiology, adaptive automation, or any kinetic feature without a new approved specification.
