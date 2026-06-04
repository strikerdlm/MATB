# 🛩️ MATB — Military Aviation Research Platform

A Python research platform for **multi-attribute task battery (MATB)** human-factors studies in military aviation. It pairs a vendored **OpenMATB** task engine (the four canonical MATB tasks + workload/SA instruments) with a Python bridge that builds counterbalanced scenarios, converts session logs into analysis-ready metrics, and applies a probabilistic mission-outcome model. A FastAPI research console for longitudinal data collection and analysis is in active development.

> **Author:** Dr. Diego Malpica, MD — Aerospace Medicine, Colombian Aerospace Force (FAC).
> Research targets: *Aerospace Medicine and Human Performance*, *Human Factors*, *Frontiers in Neuroergonomics*.

---

## What this is (and what it is not)

This repository has evolved from a terminal aircraft-monitoring demo into a research platform built around **OpenMATB**. The active research surface is OpenMATB + the `matb_integration` bridge, **not** the original Rich dashboard (which is retained as a legacy/secondary tool — see [Legacy dashboard](#legacy-aircraft-monitoring-dashboard)).

It is a **research instrument**, not a clinical or certified safety tool. Statistical and modelling outputs use comparative, evidence-based framing (effect sizes, confidence/credible intervals).

---

## Architecture

```
MATB/
├── openmatb/                 # Vendored OpenMATB v1.4.x submodule — the task engine
│                             #   (SYSMON, TRACK, COMM, RESMAN + ISA / NASA-TLX / Bedford / SAGAT)
├── matb_integration/         # Python bridge layer (no OpenMATB install needed to use it)
│   ├── scenario_builder.py   #   ResearchProtocol → OpenMATB .txt; Latin-square counterbalancing
│   ├── log_converter.py      #   OpenMATB CSV → structured JSONL metrics (d′, TLX, Bedford, ISA, SAGAT)
│   ├── suhir/                #   Suhir (2018) DEPDF probabilistic mission-outcome model  [PR #5]
│   ├── questionnaires/       #   EN/ES NASA-TLX, ISA, Bedford scale assets
│   └── analysis/             #   descriptive analysis helpers
├── webui/                    # MATB Research Console (FastAPI backend; Next.js UI pending)  [PR #6]
│   └── backend/              #   ingestion + study-completeness tracker + auto DEPDF fit
├── scenarios/military_aviation/   # Pre-baked LOW / MEDIUM / HIGH scenarios
├── aircraft_monitor/         # Legacy Rich terminal dashboard (secondary)
├── tests/                    # Bridge + protocol + SAGAT + analysis tests
├── setup.sh                  # One-shot clone-to-running install
└── docs/                     # Research evidence review, specs, plans
```

| Component | Role | Status |
|---|---|---|
| `openmatb/` submodule | The MATB task runner (operator-in-the-loop) | Built; 3 Diego-authored headless fixes; Xvfb smoke-verified |
| `matb_integration/scenario_builder.py` | Generate counterbalanced LOW/MED/HIGH scenarios | Built, tested |
| `matb_integration/log_converter.py` | CSV → JSONL metrics (SDT d′, TLX, Bedford, ISA, SAGAT) | Built, tested |
| `matb_integration/suhir/` | DEPDF human-nonfailure + mission-outcome model | Built — **PR #5** (not yet on `main`) |
| `webui/backend/` | FastAPI ingestion + study tracker + auto-fit + analysis endpoints | Built — **PR #6** (stacked on #5) |
| `webui/frontend/` | Next.js tracker/analysis UI (HRV design system) | Phase 1B built; Phase 3A analysis screen built |
| `matb_integration/analysis/stats/` | Frequentist + Bayesian statistics engines (MixedLM, rmcorr, DEPDF drift; PyMC NUTS hierarchical re-fits) | **Phase 3 — done (3A + 3B)** |
| `aircraft_monitor/` | Legacy Rich dashboard | Retained, not the active surface |

**Data flow:** OpenMATB session → CSV logs → `log_converter` → JSONL metrics → (`suhir` DEPDF fit) → analysis / research console.

---

## Step-by-step: how to run it

### 1. Install (engine + assets)

```bash
git clone --recurse-submodules https://github.com/strikerdlm/MATB
cd MATB
bash setup.sh
```

`setup.sh` initialises the `openmatb` submodule, creates a venv at `openmatb/.venv`, installs engine deps (pyglet, pylsl, rstr, rich, pydantic, pytest), and copies the military-aviation questionnaires + scenarios into `openmatb/includes/`.

### 2. Build counterbalanced scenarios (optional — pre-baked ones ship in `scenarios/`)

```bash
python3 -m matb_integration.scenario_builder \
  --output-dir scenarios/military_aviation \
  --block-duration 900 --seed 42
```

Produces `LOW_workload.txt` / `MEDIUM_workload.txt` / `HIGH_workload.txt`
(≈ 2.9 / 7.5 / 12.1 events·min⁻¹). Per-participant block order is a Latin-square
permutation (`block_order_for_participant`).

### 3. Run a session

```bash
# Linux / headless (CI, servers):
Xvfb :100 -screen 0 1920x1080x24 &
cd openmatb && DISPLAY=:100 .venv/bin/python main.py

# Windows:   cd openmatb && .venv/Scripts/python main.py
# macOS:     cd openmatb && .venv/bin/python main.py
```

OpenMATB writes a timestamped session CSV under `openmatb/sessions/`.

### 4. Convert a session CSV to metrics

```bash
python3 -m matb_integration.log_converter openmatb/sessions/<run>.csv \
  --participant P01 --level LOW --block low_workload \
  -o exports/P01_low.jsonl
```

Emits one JSONL record with SYSMON d′ (Hautus log-linear), COMM SDT d′,
NASA-TLX subscales + raw, Bedford, ISA time-series, and SAGAT probe accuracy.

### 5. Fit the Suhir DEPDF (needs all three workload levels of a visit)

```bash
python3 -m matb_integration.suhir.cli fit \
  --participant P01 \
  --low LOW.csv --medium MEDIUM.csv --high HIGH.csv \
  --source raw_tlx --out exports/P01_suhir.json
```

Fits the baseline parameters G₀ / P₀ / τ₀ from the three graded-workload
time-to-failure series and writes a parameters JSON. See
[`matb_integration/suhir/README.md`](matb_integration/suhir/README.md).

### 6. Run the research console backend (PR #6)

```bash
python3 -m venv ~/.venvs/matb-webui
~/.venvs/matb-webui/bin/pip install -r webui/backend/requirements.txt
cd webui/backend
~/.venvs/matb-webui/bin/uvicorn app.main:app --reload --port 8000
```

Endpoints: `GET /health`; `POST /participants`, `GET /participants`,
`GET /participants/{id}/visits`; `POST /ingest` (multipart upload of a session
CSV, tagged with participant/visit/level); `GET /tracker` (the completeness
grid); `GET /metrics/long`, `GET /fits`; `POST /analysis/run`,
`GET /analysis/latest`; `POST /analysis/bayes/run` (202, async background
job), `GET /analysis/bayes/status` (job lifecycle + artifact when done).
Ingesting all three levels of a visit auto-runs the DEPDF fit.
See [`webui/backend/README.md`](webui/backend/README.md).

### 7. Run the statistics engine CLI (Phase 3A/3B)

```bash
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

### 8. Run the tests

```bash
# bridge + protocol + suhir + sagat tests:
python3 -m pytest tests/ -v

# research-console backend tests:
cd webui/backend && ~/.venvs/matb-webui/bin/python -m pytest -q
```

---

## Capabilities (current)

- **Four canonical MATB tasks** via OpenMATB: system monitoring (SYSMON), tracking (TRACK), communications (COMM), resource management (RESMAN), with operator input and per-task logging.
- **Graded mental-workload blocks** (LOW/MEDIUM/HIGH) calibrated to the Pontiggia et al. (2024) event-rate range, generated and per-participant counterbalanced.
- **Workload & SA instruments:** instantaneous ISA (1–10), post-block NASA-TLX (6 subscales) and Bedford (1–10), and SAGAT freeze-probe situational-awareness capture. Spanish questionnaire assets included (NASA-TLX Spanish is psychometrically validated; ISA/Bedford Spanish are functional-equivalence translations — see `docs/research/scales/scale_validation_es.md`).
- **Analysis-ready metrics:** signal-detection d′ (log-linear correction), reaction times, hit/miss/false-alarm counts, TLX subscales, Bedford, ISA series, SAGAT accuracy — all as structured JSONL.
- **Probabilistic mission-outcome model (suhir):** Suhir's double-exponential human-nonfailure DEPDF (Eq. 5.1/5.16), FOAT calibration (Eq. 5.19–5.21), Weibull degradation, and mission-outcome composition (Eq. 5.10), validated against the book's own Table 5.1 and Example 5.1.
- **Research console backend:** file ingestion with integrity guards (sha256 dedup, cross-cell mislabel prevention, overwrite confirmation, validation), a derived study-completeness grid, and auto DEPDF fitting per completed visit.

---

## Latest developments

- **Suhir DEPDF mission-outcome layer** (`matb_integration/suhir/`, PR #5): turns the platform into a calibration rig for Ephraim Suhir's *Human-in-the-Loop* (2018) probabilistic model — the graded LOW/MED/HIGH scenarios serve as the elevated-workload levels his FOAT calibration requires. Design + plan in `docs/superpowers/specs/` and `docs/superpowers/plans/`.
- **MATB Research Console — backend** (`webui/backend/`, PR #6): FastAPI + SQLModel (SQLite) console for the planned longitudinal study (**12 participants × 6 visits × 3 workload levels**, every 3 days over 15 days). Ingests OpenMATB CSVs (reusing `matb_integration` as a library — no metric logic duplicated), tracks completeness, and auto-fits the DEPDF per visit.
- **Phase 3A — frequentist statistics engine** (`matb_integration/analysis/stats/`): standalone library (pandas + statsmodels + scipy) implementing Q1 workload-level effects (MixedLM, 2-df Wald omnibus, Holm pairwise contrasts gated on BH-FDR), Q2 visit trajectories (level-adjusted slope), Q3 repeated-measures correlation (Bakdash & Marusich 2017 ANCOVA rmcorr, validated to 1e-9 against the published oracle), and Q4 DEPDF parameter drift (g0/p0/tau0 ~ visit). First-class `ok | insufficient_data | not_estimable` statuses, effect sizes with 95% CI, rmANOVA complete-case sensitivity, full provenance (input fingerprint, library versions, engine v1.0.0). CLI and backend endpoints included; `/analysis` frontend screen with confirmatory family table, Q1–Q4 cards, and provenance footer. Live end-to-end verified with a 48-CSV synthetic cohort.
- **Phase 3B — async Bayesian sensitivity** (`matb_integration/analysis/stats/bayes.py`): PyMC NUTS hierarchical re-fits of Q2 (per confirmatory metric, level indicators included) and Q4 (per DEPDF parameter). Pinned priors: coefficients Normal(0, 2.5·sd(y)); SDs HalfNormal(sd(y)). Outputs 95% equal-tailed intervals (ETI) with per-model diagnostics (R̂, ESS, divergences, seed/chains/draws/tune); "not converged" if max R̂ > 1.01 or any divergence. Separate artifact (BAYES_VERSION 1.0.0) — never extends the frequentist artifact; gates (gate_q2/gate_q4) reused. Backend: `POST /analysis/bayes/run` returns 202 and spawns a background worker (caches by fingerprint+bayes_version; re-POST returns the active job); `GET /analysis/bayes/status` reports queued|running|done|failed with the artifact attached on completion. Frontend: Bayesian section on `/analysis` with 2-s polling, posterior tables (mean/ETI/R̂/ESS per parameter), red "not converged" badge, and sampler+priors provenance footnote. Library tests 40 (3 Bayesian incl. seeded NUTS recovery); backend 34 (3 job-lifecycle); frontend 21. Live e2e 2026-06-04 on the 48-CSV cohort: job done in ~36 s; Bayesian d′ visit slope +0.124 ETI [0.080, 0.160], converged, consistent with frequentist +0.127; degenerate synthetic responses correctly flagged not-converged (R̂ up to 3.3, hundreds of divergences); cache hit on re-POST confirmed.
- **Phase 1B frontend** (complete as of Phase 3B): a Next.js/TypeScript UI mirroring the HRV "Mission Control" design system. Includes Tracker, Participants, Upload, Visualization, and Analysis screens (including the Bayesian section).

### Readiness

- **Pilot an OpenMATB session with d′ + NASA-TLX/Bedford/ISA + Latin-square counterbalancing:** ready (verified headless via Xvfb; no real-participant data collected yet).
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
| — | **OpenMATB integration** (real inner loop, 4 tasks, ISA/TLX/Bedford/SAGAT, headless fixes) | **Done** |
| — | **Scenario builder + log converter** (counterbalancing, d′, SDT, JSONL) | **Done** |
| — | **Suhir DEPDF mission-outcome model** | **Done (PR #5)** |
| — | **Research console — data model + ingestion + tracker (backend)** | **Done (PR #6)** |
| — | **Research console — frontend (tracker + viz + analysis)** | **Done (Phase 1B)** |
| — | **Frequentist statistics engine (MixedLM, rmcorr, DEPDF drift, CLI + endpoints)** | **Done (Phase 3A)** |
| — | **Bayesian sensitivity layer (PyMC, async)** | **Done (Phase 3B)** |
| 9 | Multimodal physiology (LSL) + reproducibility (practice criterion, version-pinned manifests) | Partial / planned |
| 10 | Population-specific stressor packs (fighter/RPA/transport-MUM-T) + BIDS-derivative export + baseline neurocognitive screen | Planned |
| 11 | Adaptive automation engine (performance/physiology-driven handoffs, transparency cues) | Planned |

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
