# 🛩️ MATB — Military Aviation Research Platform

A Python research platform for **multi-attribute task battery (MATB)** human-factors studies in military aviation. It builds OpenMATB-compatible counterbalanced scenarios, converts session logs into analysis-ready metrics, and applies a probabilistic mission-outcome model. It also includes a native, Linux/headless-safe sUAS command-and-control research simulator with a browser UI and sealed replay artifacts.

> **Author:** Dr. Diego Malpica, MD — Aerospace Medicine, Colombian Aerospace Force (FAC).
> Research targets: *Aerospace Medicine and Human Performance*, *Human Factors*, *Frontiers in Neuroergonomics*.

---

## What this is (and what it is not)

This repository has evolved from a terminal aircraft-monitoring demo into an OpenMATB-compatible research platform. The active research surface is the `matb_integration` bridge plus the research console, **not** the original Rich dashboard (which is retained as a legacy/secondary tool — see [Legacy dashboard](#legacy-aircraft-monitoring-dashboard)). The OpenMATB task runner is no longer vendored here; use a separate working OpenMATB checkout/install when collecting operator-in-the-loop sessions.

It is a **research instrument**, not a clinical or certified safety tool. Statistical and modelling outputs use comparative, evidence-based framing (effect sizes, confidence/credible intervals).

---

## Architecture

```
MATB/
├── matb_integration/         # Python bridge layer (no OpenMATB install needed to use it)
│   ├── scenario_builder.py   #   ResearchProtocol → OpenMATB .txt; Latin-square counterbalancing
│   ├── scenario_manifest.py  #   Deterministic scenario provenance + CSV validation helpers
│   ├── log_converter.py      #   OpenMATB CSV → structured JSONL metrics (d′, TLX, Bedford, ISA, SAGAT)
│   ├── suhir/                #   Suhir (2018) DEPDF probabilistic mission-outcome model  [PR #5]
│   ├── questionnaires/       #   EN/ES NASA-TLX, ISA, Bedford, SAGAT assets
│   └── analysis/             #   descriptive analysis helpers
├── webui/                    # MATB Research Console (FastAPI backend + Next.js UI)  [PR #6]
│   ├── backend/              #   ingestion + tracker + provenance + exports + auto DEPDF fit
│   └── frontend/             #   tracker, upload, visualization, analysis, screen UI
├── scenarios/military_aviation/   # Pre-baked LOW / MEDIUM / HIGH scenarios
├── aircraft_monitor/         # Legacy Rich terminal dashboard (secondary)
├── tests/                    # Bridge + protocol + SAGAT + analysis tests
├── setup.sh                  # One-shot clone-to-running install
└── docs/                     # Research evidence review, specs, plans
```

| Component | Role | Status |
|---|---|---|
| External OpenMATB runtime | Operator-in-the-loop MATB task runner | Not vendored; broken `openmatb @ 2d9e20a` submodule removed after the GitHub source resolved 404 |
| `matb_integration/scenario_builder.py` | Generate counterbalanced LOW/MED/HIGH scenarios + adjacent manifests | Built, tested |
| `matb_integration/scenario_manifest.py` | Scenario provenance hashing + CSV validation against expected probes/questionnaires | Built, tested |
| `matb_integration/log_converter.py` | CSV → JSONL metrics (SDT d′, TLX, Bedford, ISA, SAGAT) | Built, tested |
| `matb_integration/suhir/` | DEPDF human-nonfailure + mission-outcome model | Built — **PR #5** (not yet on `main`) |
| `webui/backend/` | FastAPI ingestion + study tracker + scenario validation + research bundle exports + auto-fit + analysis endpoints | Built — **PR #6** (stacked on #5) |
| `webui/frontend/` | Next.js tracker/analysis UI (HRV design system) | Phase 1B built; Phase 3A/3B analysis screen built; Screen page built |
| `matb_integration/analysis/stats/` | Frequentist + Bayesian statistics engines (MixedLM, rmcorr, DEPDF drift; PyMC NUTS hierarchical re-fits) | **Phase 3 — done (3A + 3B)** |
| `aircraft_monitor/` | Legacy Rich dashboard | Retained, not the active surface |

**Data flow:** external OpenMATB session → CSV logs → `log_converter` → JSONL metrics → (`suhir` DEPDF fit) → analysis / research console.

## Native sUAS C2 simulator (Linux/headless first-class)

The repository includes a self-contained synthetic small-UAS operations
simulator under `matb_integration/suas/` and `webui/`. It models supervisory
mission actions, fleet state, contacts, alerts, workload/protocol gates,
observer streams, controller lease handoff, checkpoint recovery, debrief
metrics, and deterministic replay verification. It is deliberately a
research instrument: it has no weapons, real-world map data, vehicle control,
external telemetry, or autonomous targeting path.

Linux servers do not need Windows, X11, a desktop session, Docker, or a GPU.
The shipped launcher runs the FastAPI backend and built Next.js UI on loopback
and writes an owner-only SQLite/artifact directory. Windows is not a
requirement; a Windows developer can use WSL2 or Docker, but the supported
offline launcher is POSIX shell (Linux/macOS/WSL) and should be treated as the
deployment contract.

### Install and launch offline

From the repository root (Python 3.12+ and Node.js 20+):

```bash
MATB_VENV="$PWD/.venv-suas" bash scripts/install_suas.sh
MATB_VENV="$PWD/.venv-suas" bash scripts/run_suas.sh
```

Open `http://127.0.0.1:3100/mission/setup` from an operator workstation or
headless browser. The backend health endpoint is
`http://127.0.0.1:8000/health`. Use `--data-dir`, `--backend-port`, and
`--frontend-port` to relocate the local store or avoid port collisions. The
launcher refuses unsafe data roots and refuses non-loopback binds unless
`MATB_FRONTEND_ORIGINS` is explicitly configured.

For development, run the backend and frontend separately as documented in
[`webui/backend/README.md`](webui/backend/README.md) and
[`webui/frontend/README.md`](webui/frontend/README.md). The scenario directory
defaults to `scenarios/suas/`; set `MATB_SIMULATION_SCENARIO_DIR` to use a
validated fixture directory elsewhere.

### Native API surface

- `GET /simulation/scenarios` lists validated YAML scenarios.
- `POST /simulation/sessions` prepares a pseudonymized participant/visit and
  returns a controller lease once. Keep that lease out of logs and URLs; send
  it only as `X-Simulation-Controller` on mutations.
- `POST /simulation/sessions/{id}/start|pause|resume|finish|recover` controls
  lifecycle. A valid controller WebSocket disconnect pauses a running session;
  it never resumes automatically.
- `POST /simulation/sessions/{id}/commands` accepts non-kinetic supervisory
  commands. `GET .../state` is observer-readable and redacts private probe
  truth.
- `WS /simulation/sessions/{id}/stream` is an ordered, bounded stream. A
  lease-bearing connection is the sole controller; a lease-free connection is
  read-only. The first frame is a complete resynchronizing snapshot and the
  `after_sequence` cursor supports reconnects.
- `GET .../debrief` and `GET .../artifacts` are available only after a terminal
  finish/abort and expose relative paths plus hashes, never absolute paths or
  leases.

The safety boundary is intentional: this platform can exercise operator
workload, situation awareness, communications, and supervisory decisions, but
it cannot command a real aircraft or weapon system.

---

## Step-by-step: how to run it

### 1. Install this MATB repository

```bash
git clone https://github.com/strikerdlm/MATB
cd MATB
bash setup.sh
```

`setup.sh` creates this repository's `.venv` and installs MATB bridge /
analysis dependencies. It does **not** install the OpenMATB desktop task
runner, because OpenMATB is intentionally external.

### 2. Install the external OpenMATB runner

Use a separate OpenMATB checkout or install directory. In the examples below,
replace `/path/to/openmatb` with your actual OpenMATB path.

```bash
OPENMATB_DIR=/path/to/openmatb
cd "$OPENMATB_DIR"

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `python main.py` later reports `ModuleNotFoundError: pyglet`, you are not
inside the OpenMATB virtual environment. Activate it again with:

```bash
cd "$OPENMATB_DIR"
. .venv/bin/activate
```

### 3. Build counterbalanced scenarios (optional — pre-baked ones ship in `scenarios/`)

```bash
cd /path/to/MATB
python3 -m matb_integration.scenario_builder \
  --output-dir scenarios/military_aviation \
  --block-duration 900 --seed 42
```

Produces `LOW_workload.txt` / `MEDIUM_workload.txt` / `HIGH_workload.txt`
(≈ 2.9 / 7.5 / 12.1 events·min⁻¹) plus adjacent
`*.txt.manifest.json` files. Each manifest records the generator version,
participant/visit tags when available, workload level, block duration, seed,
scenario SHA-256, expected ISA/SAGAT counts, and questionnaire inclusion. Per-participant
block order is a Latin-square permutation (`block_order_for_participant`).

### 4. Install MATB scenarios into OpenMATB

Copy this repo's scenarios and questionnaires into the external OpenMATB tree:

```bash
cd /path/to/MATB
OPENMATB_DIR=/path/to/openmatb python3 install_to_openmatb.py "$OPENMATB_DIR"
```

This creates, among others:

- `$OPENMATB_DIR/includes/scenarios/military_aviation/low_workload.txt`
- `$OPENMATB_DIR/includes/scenarios/military_aviation/medium_workload.txt`
- `$OPENMATB_DIR/includes/scenarios/military_aviation/high_workload.txt`

### 5. Configure OpenMATB to avoid startup flicker

OpenMATB uses Pyglet for its desktop window. On Wayland/XWayland, remote
desktop, VMs, X11 forwarding, and some multi-monitor setups, the fullscreen
scenario selector can visibly flicker. The stable first-run setup is:

- start windowed (`fullscreen=False`);
- skip the selector by setting `scenario_path` directly;
- skip the startup session-number modal while debugging
  (`display_session_number=False`).

Apply those settings with:

```bash
OPENMATB_DIR=/path/to/openmatb
cd "$OPENMATB_DIR"
cp config.ini config.ini.bak
python - <<'PY'
from pathlib import Path

path = Path("config.ini")
lines = path.read_text().splitlines()
updates = {
    "fullscreen": "False",
    "scenario_path": "military_aviation/low_workload.txt",
    "display_session_number": "False",
}

out = []
for line in lines:
    stripped = line.strip()
    if "=" in stripped and not stripped.startswith("#"):
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            line = f"{key}={updates[key]}"
    out.append(line)

path.write_text("\n".join(out) + "\n")
PY
```

To switch workload levels later, edit `scenario_path` to:

```ini
scenario_path=military_aviation/medium_workload.txt
```

or:

```ini
scenario_path=military_aviation/high_workload.txt
```

After you confirm the app is stable on the target machine, you may try
`fullscreen=True` again for participant data collection. If flicker returns,
keep `fullscreen=False`.

### 6. Run an OpenMATB session

```bash
# Local desktop:
OPENMATB_DIR=/path/to/openmatb
cd "$OPENMATB_DIR"
. .venv/bin/activate
python main.py
```

For Linux/headless CI or servers, use Xvfb and keep `fullscreen=False`:

```bash
OPENMATB_DIR=/path/to/openmatb
Xvfb :100 -screen 0 1920x1080x24 &

cd "$OPENMATB_DIR"
. .venv/bin/activate
DISPLAY=:100 python main.py
```

OpenMATB writes a timestamped session CSV under `$OPENMATB_DIR/sessions/`.

### 7. Convert a session CSV to metrics

```bash
cd /path/to/MATB
python3 -m matb_integration.log_converter "$OPENMATB_DIR/sessions/<run>.csv" \
  --participant P01 --level LOW --block low_workload \
  -o exports/P01_low.jsonl
```

Emits one JSONL record with SYSMON d′ (Hautus log-linear), COMM SDT d′,
NASA-TLX subscales + raw, Bedford, ISA time-series, and SAGAT probe accuracy.

### 8. Fit the Suhir DEPDF (needs all three workload levels of a visit)

```bash
cd /path/to/MATB
python3 -m matb_integration.suhir.cli fit \
  --participant P01 \
  --low LOW.csv --medium MEDIUM.csv --high HIGH.csv \
  --source raw_tlx --out exports/P01_suhir.json
```

Fits the baseline parameters G₀ / P₀ / τ₀ from the three graded-workload
time-to-failure series and writes a parameters JSON. See
[`matb_integration/suhir/README.md`](matb_integration/suhir/README.md).

### 9. Run the research console backend

Use a repository-local virtual environment for the headless backend. The
frontend is documented in the next section.

```bash
cd /path/to/MATB
python3 -m venv ~/.venvs/matb-webui
~/.venvs/matb-webui/bin/pip install -r webui/backend/requirements.txt
cd webui/backend
~/.venvs/matb-webui/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Endpoints: `GET /health`; `POST /participants`, `GET /participants`,
`GET /participants/{id}/visits`; `POST /ingest` (multipart upload of a session
CSV and optional scenario manifest, tagged with participant/visit/level);
`GET /tracker` (the completeness grid); `GET /block` (metrics + manifest validation
summary); `GET /metrics/long`, `GET /fits` (returns `hcf_value` and F-aware P^h curves);
`POST /analysis/run`, `GET /analysis/latest`; `POST /analysis/bayes/run` (202, async
background job), `GET /analysis/bayes/status` (job lifecycle + artifact when done);
`POST /screen` (raw trial payload → scoring → store → refresh all DepdfFit HCF values;
409 on duplicate unless `overwrite=true`; 422 on malformed payloads), `GET /screen`
(per-participant scores, cohort F values, gate status); `GET /exports/research-context`
and `POST /exports/research-bundle` (ZIP containing analysis context, provenance,
scenario manifests, caveats, and frontend ECharts option JSON).
Ingesting all three levels of a visit auto-runs the DEPDF fit.
See [`webui/backend/README.md`](webui/backend/README.md).

### 10. Run the research console frontend

In a second terminal:

```bash
cd /path/to/MATB/webui/frontend
npm install
npm run dev
```

Open `http://localhost:3100`. The frontend defaults to the backend at
`http://localhost:8000`. If you run the backend somewhere else, set the API URL
explicitly:

```bash
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev
```

Recommended first workflow in the console:

1. Go to `Participants` and create `P01`.
2. Go to `Upload` and ingest the LOW, MEDIUM, and HIGH OpenMATB CSVs for the
   same participant / visit.
3. Go to `Tracker` to verify completeness.
4. Go to `Visualization` or `Analysis` after data are ingested.

### 11. Run the statistics engine CLI (Phase 3A/3B)

```bash
cd /path/to/MATB

# Frequentist (Phase 3A):
python3 -m matb_integration.analysis.stats.cli run \
  --metrics-json m.json --fits-json f.json -o artifact.json

# Bayesian sensitivity (Phase 3B):
python3 -m matb_integration.analysis.stats.cli bayes \
  --metrics-json m.json --fits-json f.json -o bayes.json \
  [--seed SEED] [--draws DRAWS] [--tune TUNE] [--chains CHAINS]
```

`m.json` and `f.json` are the JSON bodies returned by `GET /metrics/long` and
`GET /fits` respectively. The frequentist command writes a fully-provenance-stamped
JSON artifact; the Bayesian command writes a separate artifact (BAYES_VERSION 1.0.0)
with 95% ETIs, R̂, ESS, and per-model diagnostics — never extending the frequentist
artifact.

### 12. Run the baseline neurocognitive screen (Phase 10 #20)

Navigate to `http://localhost:3100/screen` in a browser:

1. Select an unscreened participant from the picker.
2. The four-subtest battery launches fullscreen in es-CO Spanish (~10–12 min):
   Simple RT (30 trials), Choice RT (30 trials, 2-choice arrows), 2-back letters
   (60 trials, consonants only), pursuit tracking (90 s sum-of-sines).
3. The backend scores raw trials, computes validity (≥ 80% usable per subtest),
   derives a cohort-z composite F/F₀ = 1 + 0.05·z̄ (clamped [0.85, 1.15]),
   and refreshes `hcf_value` / `hcf_source` on all existing DepdfFit rows.
4. Subsequent DEPDF fits automatically use the stored F; the P^h curve switches
   from Eq. 5.16 (F = F₀) to full Eq. 5.1.

Use `?fast=1` query parameter for a reduced-trial dev/e2e run (same scoring logic).

### 13. Run the tests

```bash
# bridge + protocol + suhir + sagat + screen library tests:
conda activate matb
python -m pytest tests/ -v   # 241 collected (237 pass, 4 skip)

# research-console backend tests (includes provenance/export + screen/HCF tests):
cd webui/backend && python -m pytest -q   # 46 collected

# frontend tests:
cd ../frontend && npm test -- --run   # 36 pass
npm run typecheck
npm run build

# native sUAS gates (Linux/headless):
cd /path/to/MATB
PYTHONPATH=. .venv-suas/bin/pytest tests/suas -q                 # 161 pass
PYTHONPATH=. .venv-suas/bin/pytest tests/suas -q -m 'slow or performance'
bash tests/scripts/test_suas_scripts.sh
bash scripts/test_suas_offline.sh
# browser protocol/accessibility/reconnect/responsive suite:
cd webui/frontend
MATB_VENV=/path/to/MATB/.venv-suas npm run test:e2e
```

---

## Capabilities (current)

- **OpenMATB-compatible four-task workflow:** generated scenarios target system monitoring (SYSMON), tracking (TRACK), communications (COMM), and resource management (RESMAN), with operator input and per-task logging handled by an external task runner.
- **Graded mental-workload blocks** (LOW/MEDIUM/HIGH) calibrated to the Pontiggia et al. (2024) event-rate range, generated and per-participant counterbalanced.
- **Workload & SA instruments:** instantaneous ISA (1–10), post-block NASA-TLX (6 subscales) and Bedford (1–10), and SAGAT freeze-probe situational-awareness capture. Spanish questionnaire assets included (NASA-TLX Spanish is psychometrically validated; ISA/Bedford Spanish are functional-equivalence translations — see `docs/research/scales/scale_validation_es.md`).
- **Analysis-ready metrics:** signal-detection d′ (log-linear correction), reaction times, hit/miss/false-alarm counts, TLX subscales, Bedford, ISA series, SAGAT accuracy — all as structured JSONL.
- **Probabilistic mission-outcome model (suhir):** Suhir's double-exponential human-nonfailure DEPDF (Eq. 5.1/5.16), FOAT calibration (Eq. 5.19–5.21), Weibull degradation, and mission-outcome composition (Eq. 5.10), validated against the book's own Table 5.1 and Example 5.1.
- **Research console backend:** file ingestion with integrity guards (sha256 dedup, cross-cell mislabel prevention, overwrite confirmation, validation), a derived study-completeness grid, and auto DEPDF fitting per completed visit.
- **Scenario provenance + validation:** every generated scenario file can carry an adjacent deterministic manifest. The research console stores manifest SHA-256, validation status, validation issues, and compact manifest summaries per ingested block; CSVs without a manifest are retained but explicitly flagged.
- **Reproducibility exports:** backend and frontend can export a research bundle ZIP with participants, visits, tracker cells, tidy metrics, DEPDF fits, latest frequentist/Bayesian artifacts, block validation metadata, scenario manifests, caveats, and publication-grade ECharts option JSON for the analysis figures.
- **Baseline neurocognitive screen:** browser-administered 4-subtest battery (~10–12 min) in es-CO Spanish — Simple RT, Choice RT, 2-back working memory, and pursuit tracking. Raw trials scored server-side (`matb_integration/screen/`; stdlib-only); validity gates (≥ 80% usable per subtest); cohort-z composite F/F₀ clamped [0.85, 1.15]. A confirmed screen refreshes `hcf_value` on all existing DepdfFit rows and switches the P^h curve from Eq. 5.16 to full Eq. 5.1. Mapping is exploratory-labeled (no validated external standard). Endpoints: `POST /screen`, `GET /screen`.

---

## Latest developments

- **Suhir DEPDF mission-outcome layer** (`matb_integration/suhir/`, PR #5): turns the platform into a calibration rig for Ephraim Suhir's *Human-in-the-Loop* (2018) probabilistic model — the graded LOW/MED/HIGH scenarios serve as the elevated-workload levels his FOAT calibration requires. Design + plan in `docs/superpowers/specs/` and `docs/superpowers/plans/`.
- **Removed broken OpenMATB submodule** (`openmatb @ 2d9e20a`): the vendored gitlink pointed to a GitHub source that now returns 404, so the submodule and `.gitmodules` were deleted. SAGAT probe banks now live in `matb_integration/questionnaires/`; `install_to_openmatb.py` copies repo-owned assets into a separate OpenMATB checkout/install when one is available.
- **MATB Research Console — backend** (`webui/backend/`, PR #6): FastAPI + SQLModel (SQLite) console for the planned longitudinal study (**12 participants × 6 visits × 3 workload levels**, every 3 days over 15 days). Ingests OpenMATB CSVs (reusing `matb_integration` as a library — no metric logic duplicated), tracks completeness, and auto-fits the DEPDF per visit.
- **Scenario provenance + research bundles** (`matb_integration/scenario_manifest.py`, `webui/backend/app/routers/exports.py`): scenario generation now writes adjacent deterministic manifests; ingestion stores per-block manifest hashes and validation issues; tracker/block views expose validation summaries; `/exports/research-context` and `/exports/research-bundle` assemble analysis-ready JSON, caveats, scenario manifests, and frontend figure option JSON into a reproducible ZIP.
- **Headless frontend QA + responsive shell** (`webui/frontend/src/components/layout/`): browser-verified on a headless server at `127.0.0.1:3100` with the backend at `127.0.0.1:8000`; CORS now allows both `localhost` and `127.0.0.1` dev origins, the app includes an icon route, Analysis avoids expected 404 noise on empty datasets, and the mobile shell stacks the nav above content instead of forcing horizontal page overflow.
- **Phase 3A — frequentist statistics engine** (`matb_integration/analysis/stats/`): standalone library (pandas + statsmodels + scipy) implementing Q1 workload-level effects (MixedLM, 2-df Wald omnibus, Holm pairwise contrasts gated on BH-FDR), Q2 visit trajectories (level-adjusted slope), Q3 repeated-measures correlation (Bakdash & Marusich 2017 ANCOVA rmcorr, validated to 1e-9 against the published oracle), and Q4 DEPDF parameter drift (g0/p0/tau0 ~ visit). First-class `ok | insufficient_data | not_estimable` statuses, effect sizes with 95% CI, rmANOVA complete-case sensitivity, full provenance (input fingerprint, library versions, engine v1.0.0). CLI and backend endpoints included; `/analysis` frontend screen with confirmatory family table, Q1–Q4 cards, and provenance footer. Live end-to-end verified with a 48-CSV synthetic cohort.
- **Phase 3B — async Bayesian sensitivity** (`matb_integration/analysis/stats/bayes.py`): PyMC NUTS hierarchical re-fits of Q2 (per confirmatory metric, level indicators included) and Q4 (per DEPDF parameter). Pinned priors: coefficients Normal(0, 2.5·sd(y)); SDs HalfNormal(sd(y)). Outputs 95% equal-tailed intervals (ETI) with per-model diagnostics (R̂, ESS, divergences, seed/chains/draws/tune); "not converged" if max R̂ > 1.01 or any divergence. Separate artifact (BAYES_VERSION 1.0.0) — never extends the frequentist artifact; gates (gate_q2/gate_q4) reused. Backend: `POST /analysis/bayes/run` returns 202 and spawns a background worker (caches by fingerprint+bayes_version; re-POST returns the active job); `GET /analysis/bayes/status` reports queued|running|done|failed with the artifact attached on completion. Frontend: Bayesian section on `/analysis` with 2-s polling, posterior tables (mean/ETI/R̂/ESS per parameter), red "not converged" badge, and sampler+priors provenance footnote. Live e2e 2026-06-04 on the 48-CSV cohort: job done in ~36 s; Bayesian d′ visit slope +0.124 ETI [0.080, 0.160], converged, consistent with frequentist +0.127; degenerate synthetic responses correctly flagged not-converged (R̂ up to 3.3, hundreds of divergences); cache hit on re-POST confirmed.
- **Phase 10 #20 — baseline neurocognitive screen** (`matb_integration/screen/`, `webui/frontend/src/components/screen/`): 4-subtest browser battery in es-CO Spanish (~10–12 min). Subtests: Simple RT (30 trials; < 150 ms anticipations discarded), Choice RT (30 trials, 2-choice arrows, accuracy ≥ 60% gate), 2-back letters (60 trials, consonants only; d′ via Hautus helper; SOA gaps derived server-side), pursuit tracking (90 s sum-of-sines, normalized RMS error). Scoring in `matb_integration/screen/` (stdlib-only, raw-trials-first, re-derivable). Pre-registered validity: ≥ 80% usable per subtest; cohort-z composite F/F₀ = 1 + 0.05·z̄ clamped [0.85, 1.15]; gates: ≥ 3 screened, ≥ 2 valid values per metric. F enters DEPDF at evaluation only; every screen ingest refreshes `hcf_value`/`hcf_source` on all existing DepdfFit rows; new fits pick it up automatically. This closes the F = F₀ assumption. Framing: mapping is exploratory — no validated external standard. Live e2e 2026-06-04: bot's sub-150 ms presses invalidated Simple RT; F correctly computed from 3 remaining valid metrics; cohort gate held fits at F₀ below 3 screens, then refreshed all 16 fits; F > 1 raised P^h, F < 1 lowered it. Tests: 46 backend, 36 frontend.
- **Phase 1B frontend** (complete as of Phase 10 #20): a Next.js/TypeScript UI mirroring the HRV "Mission Control" design system. Includes Tracker, Participants, Upload, Visualization, Analysis, and Screen pages.

### Readiness

- **Pilot an OpenMATB session with d′ + NASA-TLX/Bedford/ISA + Latin-square counterbalancing:** ready when pointed at a working external OpenMATB install; no real-participant data collected yet.
- **DEPDF analysis + research-console ingestion/tracking:** built and tested (in open PRs).
- **Inferential statistics (Phase 3 — complete):** frequentist (Phase 3A) and Bayesian sensitivity (Phase 3B) both built and live end-to-end verified; CLI artifacts match backend runs to fingerprint level.
- **Full Q1-grade study (physiology sync + participant data):** not yet — LSL physiology integration and a real data-collection run remain.

---

## Legacy aircraft-monitoring dashboard

The original Rich terminal dashboard remains in `aircraft_monitor/` for demos and as the historical base of the project. It is no longer the active research surface.

```bash
pip install -r requirements.txt
python -m aircraft_monitor                 # combined demo
python -m aircraft_monitor.demo_uav        # UAV demo
python -m aircraft_monitor.demo_fighter    # fighter demo
python -m aircraft_monitor experiment --headless --research-modality uas --seed 42
```

It runs headless automatically when stdout is not a TTY; `AIRCRAFT_MONITOR_HEADLESS=true|false` forces the mode. Generated files default to `./exports/` (override with `--research-output-dir` or `AIRCRAFT_MONITOR_OUTPUT_DIR`).

---

## Research background & roadmap

The platform follows the AF-MATB (Miller et al., 2014) and USAARL MATB (Vogl et al., 2024) lineage. A peer-review-grade evidence audit is maintained in [`docs/research/military-aviation-platform/research_evidence_review.md`](docs/research/military-aviation-platform/research_evidence_review.md).

### Common human-factors core

| Construct | Best parameterization | Primary measures |
|---|---|---|
| Mental workload | Event rate, concurrent panels, alert frequency, response window, automation level, mission-phase complexity | NASA-TLX, instantaneous ISA 1–10, response latency, missed events, dual-task decrement, optional HR/HRV/EEG/eye-tracking |
| Situation awareness | Freeze-point query probes, map/radar uncertainty, hidden failures, stale datalink, conflict prediction | SAGAT perception/comprehension/projection probes, contact recall, threat prioritization, route prediction |
| Trust in automation | Reliability, false-alarm/missed-detection rate, confidence display, handoff transparency | Automation use, override rate, agreement, trust questionnaire, recovery after failure |
| Attention management | Visual salience, alert modality, panel density, competing messages, task-switch frequency | Time to first response, detection rate, communication errors, dwell time |
| Decision quality | Ambiguous threats, ROE, fuel/range tradeoffs, lost-link procedures, re-tasking pressure | Correct-action rate, time to decision, unsafe-action count, mission score |
| Fatigue / sustained ops | Trial duration, vigilance periods, monotonous monitoring, circadian/sleep-loss protocols | Performance slope, lapses, delayed responses, subjective sleepiness |

Situation awareness is treated as a three-level construct — perception, comprehension, projection [Endsley, 1995a/b; Wickens, 2002]. The platform targets four operational modalities (UAS/RPA, swarm s-UAS, fighter, transport/tanker/ISR/MUM-T); the detailed parameter matrices for each are in the evidence-review document.

### Phased roadmap (status)

| Phase | Goal | Status |
|---|---|---|
| 1 | Research instrumentation (JSONL logger, seeds, trial metadata, workload prompts) | Done |
| — | **OpenMATB-compatible integration** (4-task scenarios, ISA/TLX/Bedford/SAGAT assets, log conversion; runtime external) | **Done for scenario/log workflow; engine not vendored** |
| — | **Scenario builder + log converter** (counterbalancing, d′, SDT, JSONL) | **Done** |
| — | **Suhir DEPDF mission-outcome model** | **Done (PR #5)** |
| — | **Research console — data model + ingestion + tracker (backend)** | **Done (PR #6)** |
| — | **Research console — frontend (tracker + viz + analysis)** | **Done (Phase 1B)** |
| — | **Frequentist statistics engine (MixedLM, rmcorr, DEPDF drift, CLI + endpoints)** | **Done (Phase 3A)** |
| — | **Bayesian sensitivity layer (PyMC, async)** | **Done (Phase 3B)** |
| 9 | Multimodal physiology (LSL) + reproducibility (scenario manifests, research bundles, practice criterion) | **P0 scenario manifests + research bundle export — Done**; LSL and practice criterion planned |
| 10 | Population-specific stressor packs (fighter/RPA/transport-MUM-T) + BIDS-derivative export + baseline neurocognitive screen | **#20 screen — Done**; #10–11 LSL, #13–14 practice criterion, #15–17 stressor packs, #18 BIDS planned |
| 11 | Adaptive automation engine (performance/physiology-driven handoffs, transparency cues) | Planned (#19) |

---

## References

- Endsley, M. R. (1995a). Measurement of situation awareness in dynamic systems. *Human Factors*, 37(1), 65–84. https://doi.org/10.1518/001872095779049499
- Endsley, M. R. (1995b). Toward a theory of situation awareness in dynamic systems. *Human Factors*, 37(1), 32–64. https://doi.org/10.1518/001872095779049543
- Levulis, S. J., DeLucia, P. R., & Kim, S. Y. (2018). Effects of touch, voice, and multimodal input … manned-unmanned teaming. *Human Factors*, 60(8), 1117–1129. https://doi.org/10.1177/0018720818788995
- Miller, W. D. et al. (2014). *The U.S. Air Force-developed adaptation of the Multi-Attribute Task Battery (AF-MATB)*. DTIC ADA611870.
- NASA (2011). *The Multi-Attribute Task Battery II (MATB-II)*. https://ntrs.nasa.gov/api/citations/20110014456/downloads/20110014456.pdf
- Onnasch, L., Wickens, C. D., Li, H., & Manzey, D. (2014). Human performance consequences of stages and levels of automation. *Human Factors*, 56(3), 476–488. https://doi.org/10.1177/0018720813501549
- Pontiggia, A., Gomez-Merino, D., & Quiquempoix, M. (2024). MATB for assessing different mental workload levels. *Frontiers in Physiology*, 15, 1408242. https://doi.org/10.3389/fphys.2024.1408242
- Suhir, E. (2018). *Human-in-the-Loop: Probabilistic Modeling of an Aerospace Mission Outcome*. CRC Press.
- Vogl, J., McCurry, C. D., Bommer, S., & Atchley, J. A. (2024). The USAARL Multi-Attribute Task Battery. *Frontiers in Neuroergonomics*, 5, 1435588. https://doi.org/10.3389/fnrgo.2024.1435588
- Wickens, C. D. (2002). Situation awareness and workload in aviation. *Current Directions in Psychological Science*, 11(4), 128–133. https://doi.org/10.1111/1467-8721.00184

The full modality parameter matrices and the complete reference list live in the [evidence-review document](docs/research/military-aviation-platform/research_evidence_review.md).

## License

MIT License — see [LICENSE](LICENSE).
