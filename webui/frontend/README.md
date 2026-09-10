# MATB Research Console — Frontend

Next.js + TypeScript tracker UI for the MATB longitudinal study, styled to match
the HRV "Mission Control" console. Talks to the Phase 1A FastAPI backend.

The `/mission/setup` and `/mission` routes are the native synthetic sUAS
operations console. They render the fleet, tactical map, alerts/contacts,
controller lifecycle, protocol overlays, observer mode, and sealed debrief
flow. The UI is browser-only and works on a headless Linux server because no
desktop or X11 APIs are used; the shipped Playwright gate runs Chromium in
headless mode.

## Setup

```bash
cd webui/frontend
npm ci
```

## Run (dev — backend must be running on :8000)

```bash
# backend (from repo root):
cd webui/backend && ~/.venvs/matb-webui/bin/uvicorn app.main:app --port 8000

# frontend:
cd webui/frontend && npm run dev   # http://localhost:3100
```

Override the API base with `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

## Test

```bash
npm test          # vitest unit tests (lib/: api client + tracker aggregation)
npm run typecheck # tsc --noEmit
npm run build     # production build
```

From the repository root, the offline launcher builds this frontend and starts
it with the backend:

```bash
MATB_VENV="$PWD/.venv-suas" bash scripts/install_suas.sh
MATB_VENV="$PWD/.venv-suas" bash scripts/run_suas.sh
```

For the browser hardening gate (Linux/Chromium, no GUI):

```bash
cd webui/frontend
MATB_VENV=/path/to/MATB/.venv-suas \
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/opt/google/chrome/chrome \
npm run test:e2e
```

The browser suite starts the production frontend, so run `npm run build` after
source changes before invoking it. `MATB_VENV` is resolved as
`bin/python` on Linux and `Scripts/python.exe` on Windows; `MATB_PYTHON` may
instead name a Python command or an absolute executable path.

The suite covers the complete four-block protocol and replay/debrief path,
axe serious/critical checks, keyboard operation, reduced motion, observer
read-only behavior, controller disconnect/reconnect, and 1280×720 and
1920×1080 responsive screenshot baselines.

## Screens

- **Colombia** (`/colombia`) — national geographic layers, live observed aircraft,
  six installed local scenes, and preparation of additional offline areas.
  Mission scenes use Three.js/TypeScript; the national explorer uses MapLibre.
  [Setup and capture/replay guide](../../docs/implementation/colombia-geography-traffic.md).

- **Workspace** (`/`) — explicit participant/researcher navigation choice, remembered per tab. Participant catalog is `/start`; preparation requires an explicit practice/study choice.
- **Tracker** (`/tracker`) — the participant × active-visit × 3 completeness grid; click a filled cell for that
  block's metrics (SYSMON d′, hit-rate, RT; COMM d′; NASA-TLX; Bedford; ISA) plus
  the visit's DEPDF fit (G₀/P₀/τ₀) once all three levels are ingested.
- **Participants** (`/participants`) — list + add (auto-generates the active protocol visits; ASTRA uses T0, DM8, and DM15).
- **OpenMATB** (`/openmatb/setup`) — readiness, detected displays, assigned visit and published configuration. The controller preserves session purpose, reports block attempts, and links its completion receipt to the session's evidence. Unfinished participant ratings are restored only for the same session/block in the current tab.
- **Scientific evidence** (`/evidence`) — searchable capture list; `capture`, `session`, `purpose`, `q` and `offset` remain in the URL. Registration, source eligibility and measurement qualification are distinct.
- **Upload** (`/upload`) — tag + ingest an OpenMATB CSV, with guard feedback
  (duplicate / filled-cell / validation). Optionally attach the adjacent
  `*.txt.manifest.json` scenario manifest so the backend can store provenance and
  validate workload/visit tags, expected probes, and questionnaire completion.
- **Visualization** (`/visualization`) — Trajectories / Levels / DEPDF / Group tabs
  with PNG export on every chart (descriptive only; inferential stats are Phase 3).
- **Analysis** (`/analysis`) — run the frequentist statistics engine via a
  single button; displays a confirmatory family table (p, p-FDR, survives) for
  the 6-test BH-FDR family; Q1 (MixedLM workload effects) and Q2 (visit
  trajectory) cards with `ok` / `insufficient_data` / `not_estimable` status
  badges and pairwise contrast tables; Q3 repeated-measures correlation table;
  Q4 DEPDF parameter drift cards; rmANOVA complete-case sensitivity lines; and a
  provenance footer (input fingerprint, engine version, library versions, caveats).
  **Bayesian section (Phase 3B):** dedicated run button that posts to
  `POST /analysis/bayes/run` and polls `GET /analysis/bayes/status` every 2 s
  (polling resumes automatically when mounting over an active job); posterior
  summary tables showing mean, 95% ETI, R̂, and ESS per parameter for Q2 and Q4
  re-fits; red "not converged" badge when max R̂ > 1.01 or divergences detected;
  sampler settings and pinned priors provenance footnote.
  The Research Bundle button exports a ZIP from `POST /exports/research-bundle`
  containing backend research context, caveats, scenario-manifest provenance, and
  the current publication-grade ECharts option JSON for the Q1-Q4 figures.
- **PVT** (`/pvt`; legacy `/screen` redirects here) — 10-minute Psychomotor Vigilance Test, preceded by the Karolinska Sleepiness Scale. Picker
  lists unscreened participants; selecting one launches a fullscreen 4-subtest
  battery in es-CO Spanish (~10–12 min): Simple RT, Choice RT (2-choice arrows),
  2-back letters (d′ via Hautus helper), pursuit tracking (90 s sum-of-sines).
  After completion the backend scores the raw trials, computes validity and the
  cohort-z F/F₀ composite, and returns a per-participant summary with an
  explicitly "exploratory" F/F₀ column. Append `?fast=1` for a reduced-trial
  dev/e2e run that exercises the same scoring logic. All participant-facing text
  is in `src/components/screen/strings_es.ts`.

## Geography verification and assets

`npm ci` installs the pinned Three.js, MapLibre and projection dependencies.
`predev` and `prebuild` copy MapLibre's ESM worker, shared module and license to
`public/maplibre/`; this generated directory is not committed. The six pinned
offline scenes and geographic reference catalog are committed with checksums
and source attribution. See [geographic data terms](../../LICENSES/GEOGRAPHY-DATA.md).

After `npm run build`, run the regional and traffic acceptance suite from this
directory (PowerShell shown):

```powershell
$env:MATB_E2E_TRAFFIC_FIXTURE='1'
$env:MATB_E2E_REGION_CHECK='1'
$env:PW_TEST_MATCH='**/{geography,geography-assets,presentation}.spec.ts'
npm run test:e2e
```

Set `MATB_PYTHON` to the MATB interpreter if needed. The explicit traffic fixture
is isolated from production. Set `MATB_E2E_ONLINE_CHECK=1` to additionally verify
public tile services; ordinary acceptance tests use local assets and controlled
traffic responses. Release verification is recorded in the
[Colombia report](../../docs/implementation/colombia-geography-verification.md).

## Design system

Mirrors `HRV/frontend`: TailwindCSS + shadcn/ui (Radix + CVA), HSL CSS-variable
theme tokens, dark-mode, lucide-react icons, zustand state. Pure logic lives in
`src/lib/{api,tracker}.ts` (unit-tested); React components are thin.

Spec: `docs/superpowers/specs/2026-06-03-webui-phase1b-frontend-design.md`
Plan: `docs/superpowers/plans/2026-06-03-webui-phase1b-frontend.md`
