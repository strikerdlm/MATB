# Native sUAS C2 v1 — implementation and verification report

Date: 2026-08-02  
Branch: `feat/suas-c2-v1`  
Latest implementation commit before this report: `fde04d1`

## Outcome

The repository now contains a native synthetic small-UAS operations simulator
that runs on Linux without a desktop session. The FastAPI runtime, Next.js
operator UI, ordered controller/observer stream, protocol gates, replay
verification, and offline launcher are all implemented. Windows is not needed;
the supported deployment contract is POSIX shell on Linux (or WSL2/macOS for
development).

This is a non-kinetic research instrument. It cannot command an aircraft,
weapon, target, real-world map, or external telemetry source.

## Implemented surface

- Deterministic synthetic fleet, terrain, sectors, contacts, alerts, energy,
  link state, supervisory commands, checkpoints, and scenario provenance.
- Session lifecycle: prepare, start, pause, resume, finish, abort, explicit
  recovery, and fail-closed controller disconnect pause.
- Controller lease isolation; lease-free observer streams; strict Origin and
  exact ping validation; bounded queues; ordered envelopes; reconnect snapshots
  with `after_sequence`; stale controller handoff protection.
- Redacted ISA/SAGAT protocol probes, post-block NASA-TLX/Bedford scoring,
  append-only records, relative artifact paths, SHA-256 checksums, sealed
  debrief, and deterministic replay.
- Browser UI for setup, live fleet/map operations, alerts/contacts,
  lifecycle controls, observer mode, protocol overlays, and debrief.
- Linux/offline scripts: `scripts/install_suas.sh`, `scripts/run_suas.sh`,
  `scripts/test_suas_offline.sh`, and shell contract tests.
- Accessibility and responsive hardening: axe serious/critical scan,
  keyboard operation, reduced-motion behavior, 1280×720 and 1920×1080
  screenshot baselines, observer reconnect coverage.

## Verification matrix

All commands below were run from this checkout with the repository venv at
`/tmp/matb-backend-venv` where shown.

| Gate | Command | Result |
|---|---|---|
| Native sUAS library/protocol/replay suite | `PYTHONPATH=. /tmp/matb-backend-venv/bin/pytest tests/suas -q` | **161 passed** in 84.48 s |
| Native slow + performance gates | `PYTHONPATH=. /tmp/matb-backend-venv/bin/pytest tests/suas -q -m 'slow or performance'` | **14 passed**, 147 deselected, 14.19 s |
| FastAPI backend | `cd webui/backend && /tmp/matb-backend-venv/bin/pytest -q` | **83 passed**, 8 warnings, 18.70 s |
| Frontend unit/components | `cd webui/frontend && npm test -- --run` | **72 passed** across 17 files |
| Type safety | `cd webui/frontend && npm run typecheck` | passed |
| Production bundle | `cd webui/frontend && npm run build` | passed; 13 routes generated |
| Shell contract | `bash tests/scripts/test_suas_scripts.sh` | passed |
| Offline audit | `bash scripts/test_suas_offline.sh` | passed; 6 Python checks |
| Browser suite, run 1 | `MATB_VENV=... PLAYWRIGHT_CHROMIUM_EXECUTABLE=/opt/google/chrome/chrome npm run test:e2e` | **6 passed** in 1.2 min |
| Browser suite, run 2 | same command | **6 passed** in 1.4 min |

The browser suite covers the four-block rendered mission, all protocol gates,
finish/debrief, replay sealing, axe/keyboard/reduced motion, observer
read-only behavior, controller disconnect/reconnect, and both responsive
viewports. The checked-in baselines are
`e2e/screenshots/mission-1280x720-linux.png` and
`e2e/screenshots/mission-1920x1080-linux.png`.

## Sealed replay evidence

The successful browser mission artifact was generated from the deterministic
`e2e_area_search` fixture:

- Scenario SHA-256: `fb4fb8ff871728c1dc272f22eb319c60afa577f62d8ec1d51bac593b4d2f58ea`
- Records read: 89
- Ticks replayed: 220
- Replay status: `match`
- Expected/actual event hash:
  `48733194fb8d8403bb64a428f07f5e932d77316bade8d7309673743030014b93`
- Expected/actual state hash:
  `deac9d5deb3f358632fc49e7071360ce061c96e0862f65295ac3072f98071d69`
- Debrief status: `sealed`, validity `valid`,
  `deterministic_replay_verified: true`

The run produced separate `manifest.json`, `events.jsonl`,
`replay-verification.json`, `debrief.json`, `metrics.json`,
`questionnaires.json`, checkpoints, and `checksums.sha256` files. Private
probe truth is not sent to the browser.

## Linux/offline launch

```bash
MATB_VENV="$PWD/.venv-suas" bash scripts/install_suas.sh
MATB_VENV="$PWD/.venv-suas" bash scripts/run_suas.sh
```

The launcher starts the built UI on `127.0.0.1:3100` and the API on
`127.0.0.1:8000`, creates owner-only DB/artifact/log directories, validates
ports and data roots, and cleans up both child processes on exit. Non-loopback
binds require an explicit `MATB_FRONTEND_ORIGINS` value.

## Repository-wide note

The broader legacy `tests/` run completed 395 passed and 9 skipped, but three
existing Bayesian analysis tests currently fail with `not_estimable`/missing
coefficient assertions under the installed analysis dependency set. Those
failures are outside the native sUAS scope; this implementation did not modify
`matb_integration.analysis` and the dedicated native, backend, frontend,
browser, shell, and offline gates above are green.

## Known limitations

- The runtime is process-local and intended for one active session per backend
  process; deploy behind an appropriate process supervisor if hosting multiple
  isolated study workers.
- The browser lease is kept in per-tab `sessionStorage`; a new controller tab
  must receive the saved lease through an explicit recovery handoff and never
  through a URL or log.
- Scenario physics and contacts are synthetic and deterministic. They are
  suitable for human-factors instrumentation and software verification, not
  flight certification or operational decision support.
