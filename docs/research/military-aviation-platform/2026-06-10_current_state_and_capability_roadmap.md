# MATB Current State and Capability Roadmap

**Date.** 2026-06-10
**Repository scope.** `/root/repos/MATB`
**Purpose.** Summarize the current state of the app, compare it with public NASA / USAF / DoD / FAA / ESA / EASA directions, and identify research-capable features that fit the existing development path.

---

## 1. Executive Summary

The app is no longer just a terminal aircraft-monitoring demo. It has become a layered OpenMATB research platform with a Python integration layer, a FastAPI/Next.js research console, a DEPDF mission-outcome model, frequentist and Bayesian analysis engines, SAGAT support, and a browser-based baseline neurocognitive screen. The strongest current surface is post-session ingestion, scoring, study tracking, and analysis; the weakest remaining surface is real-time experimental control, physiology synchronization, adaptive automation, and operational stressor modelling.

The external research scan supports the existing direction. NASA MATB-II established configurable human-performance/workload research with task/event configuration and output files. OpenMATB emphasized customization, extensibility, and replicability. USAF AF-MATB and USAARL MATB moved the paradigm toward script generation, event triggers, richer logging, dynamic demand transitions, automation reliability, adaptive handoffs, and trust/workload studies. FAA and EASA sources do not show direct public MATB deployments in the same way, but they strongly support regulator-grade human-factors assessment, workload/performance linkage, simulation evidence, certification-facing documentation, and human-centered automation/AI.

The next features should not be generic dashboards. They should extend the current platform into a real research instrument: synchronized physiology via LSL, BIDS-style exports, scenario provenance, adaptive automation/reliability manipulation, validated real-time workload classifiers, eye-tracking/pupillometry pipelines, stressor packs for fighter/RPA/transport/MUM-T/rotorcraft/space-robotic operations, and publishable report generation.

---

## 2. Current State of the App

### 2.1 Product Architecture

The repository currently has four active layers:

| Layer | Current implementation | Status |
|---|---|---|
| OpenMATB engine | `openmatb/` vendored engine with canonical tasks, plugins, scenarios, questionnaires, SAGAT plugin, LSL plugin code present in OpenMATB | Built; submodule currently modified in working tree |
| Integration layer | `matb_integration/` scenario builder, log converter, SAGAT helpers, Suhir DEPDF model, neurocognitive screen scoring, statistics engines | Built and tested in code, but local Python dependency set is incomplete |
| Research console backend | `webui/backend/` FastAPI app with participants, visits, block ingestion, tracker, metrics, fits, analysis, Bayesian jobs, screen endpoints | Built |
| Research console frontend | `webui/frontend/` Next.js app with Tracker, Participants, Upload, Visualization, Analysis, and Screen pages | Built; frontend unit tests pass |

The legacy `aircraft_monitor/` package remains in the repo, but the active research surface is now OpenMATB + `matb_integration` + `webui`.

### 2.2 Implemented Research Capabilities

**Scenario generation and counterbalancing.** `matb_integration/scenario_builder.py` generates LOW/MEDIUM/HIGH OpenMATB scenario files with event-rate tuning, track/resman difficulty parameters, ISA probe timing, optional NASA-TLX/Bedford, optional SAGAT freezes, and Latin-square workload ordering.

**Log conversion and metrics.** `matb_integration/log_converter.py` converts OpenMATB CSV logs into structured JSONL-style records with SYSMON/COMM signal-detection metrics, reaction times, NASA-TLX, Bedford, ISA series, and SAGAT probe accuracy. The converter uses a Hautus-style log-linear correction for d-prime.

**DEPDF mission-outcome model.** `matb_integration/suhir/` implements Suhir-style human nonfailure and mission-outcome modelling, including per-level calibration, MWL normalization, HCF mapping, and per-participant fit reporting.

**Statistics engine.** `matb_integration/analysis/stats/` implements a pre-specified frequentist engine for Q1-Q4 analyses: workload-level effects, visit trajectories, repeated-measures correlation, DEPDF parameter drift, rmANOVA sensitivity, multiplicity handling, provenance, and library-version capture. `bayes.py` adds async PyMC/NUTS Bayesian sensitivity.

**Neurocognitive screen.** `matb_integration/screen/` plus `webui/frontend/src/components/screen/` implement a baseline browser battery: Simple RT, Choice RT, 2-back, and pursuit tracking. The backend stores raw trials and derived scores, applies validity gates, and maps the cohort-z composite to exploratory HCF values.

**Research console.** `webui/backend/app/models.py` defines participants, visits, blocks, DEPDF fits, screen results, frequentist analysis artifacts, and Bayesian result jobs. The frontend exposes data tracking, participant creation, session upload, visualization, analysis execution, Bayesian status polling, and screen administration.

### 2.3 Build and Test Health on 2026-06-10

Tests were run from the current workspace.

| Suite | Command | Result |
|---|---|---|
| Frontend | `npm test -- --run` in `webui/frontend` | Passed: 29 tests / 5 files |
| Root Python tests | `python3 -m pytest tests -q` | Blocked at collection: missing `statsmodels` |
| Backend Python tests | `python3 -m pytest -q` in `webui/backend` | Blocked at import: missing `sqlmodel` |

This looks like an environment/dependency issue rather than evidence of failing behavior. The backend requirements include `sqlmodel`, `pandas`, `statsmodels`, `pymc`, `numpy`, and `scipy`, but the root `requirements.txt` does not include the statistics stack even though root tests import it. That should be cleaned up by adding a root development requirements file or documenting that root analysis tests require `webui/backend/requirements.txt`.

### 2.4 Documentation Drift

The top-level `README.md` is mostly current and describes the frontend as built. `webui/README.md` is stale: it still says the frontend is pending. This should be updated because it contradicts the current implementation.

---

## 3. External Benchmark Scan

### 3.1 NASA MATB-II

NASA's MATB-II user guide describes MATB-II as a computer-based task for operator performance and workload research. It preserved the core MATB tasks and added configuration options, training/testing modes, configurable timeouts, RESMAN tank/pump settings, modifiable event files, and detailed output files. NASA's NTRS page identifies the report as NASA/TM-2011-217164, public, with publication date July 1, 2011.

**Implication for this app:** the current platform is aligned with the NASA lineage because it uses OpenMATB and already converts task logs. The remaining NASA-style gap is not task existence; it is stronger scenario provenance, versioned event files, and end-to-end run manifests that make each experiment exactly auditable.

### 3.2 OpenMATB Research Lineage

Cegarra et al. (2020) argued that a modern MATB implementation should support task customization, software extensibility, and experiment replicability. Their paper specifically emphasizes open source code, auditable scenario files, plugin architecture, and synchronization with psychophysiological devices.

**Implication for this app:** the repo already benefits from OpenMATB's open-source architecture, but the app should expose those strengths in the console: scenario diffing, scenario manifest validation, plugin status, and synchronized physiology markers.

### 3.3 USAF / DoD AF-MATB

Public DTIC and Consensus metadata identify AF-MATB as a U.S. Air Force-developed adaptation of MATB. The 2014 updated version added documentation for configuring and using the software, richer performance logs, serial/digital port event triggering for real-time state synchronization, and task modes based on prior automation/workload paradigms.

**Implication for this app:** the next practical step is a hardware/software trigger layer: marker export, external device sync, digital/serial/LSL event triggers, and task-state synchronization. This fits directly with the existing OpenMATB plugin architecture.

### 3.4 USAARL / DoD MATB

Vogl et al. (2024) present the USAARL MATB as a modernized aviation-like research platform for performance modeling, cognitive workload assessment, adaptive automation, and trust in automation. It retains the four classical subtasks while adding subtask variations, dynamic demand transitions, and performance-driven adaptive automation handoffs. The paper also notes that USAARL MATB can manipulate automation reliability and support studies of trust in imperfect automation.

**Implication for this app:** adaptive automation and trust/reliability manipulation are the most important high-value additions after physiology sync. The app should support automation reliability per subtask, adaptive handoff policies, and trust calibration metrics, not just static workload levels.

### 3.5 FAA

The FAA Human Factors Design Standard (HF-STD-001B) is a comprehensive reference tool for FAA and contractor human-factors professionals, and it explicitly frames human factors as critical to aviation safety/effectiveness across planning, analysis, development, implementation, and in-service activities. A separate FAA Office of Aerospace Medicine report examined the relationship between NASA-TLX subscale ratings and Flight Technical Error during HUD takeoff guidance, reinforcing the need to connect subjective workload to objective performance.

**Implication for this app:** regulator-facing value will come from linking workload ratings to objective performance and traceable analysis artifacts. The existing statistics provenance is a strength; the app should add certification-style traceability from scenario -> raw log -> metric -> model -> report.

### 3.6 EASA

EASA's rotorcraft human-factors rulemaking task explicitly targets human factors and pilot workload issues that could lead to accidents/incidents. EASA's eMCO-SiPO project focuses on extended minimum crew operations and single-pilot operations, including workload, situation awareness, decision-making, crew coordination, fatigue, simulator experiments, and real-world simulated scenarios. EASA's AI Roadmap 2.0 is framed as a human-centric approach to AI in aviation.

**Implication for this app:** EASA-aligned capability should focus on human-centered automation, eMCO/SiPO-like workload and decision-making scenarios, fatigue risk, and evidence artifacts from simulations. This app can become a low-cost research console for those questions.

### 3.7 ESA

No direct public ESA MATB deployment was found in the targeted web search. ESA material does show adjacent human-robot teaming concerns; the Rollin' Justin teleoperation example explicitly frames robot autonomy as a way to reduce astronaut mental workload.

**Implication for this app:** do not claim ESA uses MATB publicly. Instead, add a space-supervisory-control scenario pack: remote robot/task-package supervision, communication delay, resource constraints, and workload/SA monitoring.

---

## 4. Research Gaps and Feature Opportunities

### 4.1 Highest-Priority Product Gaps

| Gap | Why it matters | Existing local anchor |
|---|---|---|
| Physiology synchronization is not first-class in the console | Modern MATB/neuroergonomics work expects synchronized EEG/ECG/GSR/pupil/eye-tracking markers | OpenMATB has plugin patterns; backend has metrics/fits model; stats engine has provenance |
| Adaptive automation is not implemented as an experimental condition | USAARL MATB and AF-MATB emphasize automation/reliability and performance-driven handoffs | Current workload and fit pipelines can supply performance/HCF signals |
| No scenario manifest/provenance UI | Q1-grade reproducibility requires seed, event schedule, task parameters, software versions, hardware streams, and questionnaire assets | Scenario builder already uses deterministic seeds |
| No BIDS-style export | Physiology and behavioral datasets need interoperable exports | Current metrics JSON and DB models can be transformed |
| No operational stressor packs beyond simple workload | Fighter/RPA/transport/rotorcraft/space operations require different stressors | Existing scenario builder and SAGAT bank can be extended |
| No real-time classifier loop | Current analysis is mostly post hoc; adaptive systems require online state estimation | Backend has async Bayesian jobs; screen produces baseline HCF |
| Documentation and dependency packaging drift | Stale docs and split requirements slow reproducibility | README and requirements files are easy to fix |

### 4.2 Feature Roadmap

#### Feature 1: LSL Event and Physiology Gateway

Add first-class LSL marker export for scenario events, task state, workload level, SAGAT freezes, questionnaire prompts, participant responses, and automation state. Add optional LSL inlet capture for ECG, EEG, GSR, SpO2, respiration, eye-tracking, and pupillometry streams.

Implementation fit:

- Add `matb_integration/sync/lsl.py` with marker schemas.
- Add backend tables for `PhysiologyStream` and `SyncEventManifest`.
- Add console view showing active streams, dropped samples, clock offset, and marker counts.
- Export aligned physiology sidecars with session artifacts.

Research value:

- Supports OpenMATB's extensibility goal.
- Enables MATB workload classifiers and personalized workload modelling.
- Makes the platform usable with EEG/ECG/eye-tracking labs.

#### Feature 2: Scenario Manifest and Reproducibility Validator

Every generated or uploaded scenario should produce a manifest:

- scenario builder version
- OpenMATB version/submodule commit
- questionnaire file hashes
- SAGAT bank hash
- workload parameters
- event counts/rates
- random seed
- expected probes/freezes
- participant block order
- hardware/LSL streams expected

The backend can validate uploaded CSVs against the manifest and flag missing events, wrong workload labels, absent questionnaires, or impossible timing.

#### Feature 3: Adaptive Automation and Reliability Conditions

Add automation as a structured experimental condition, not a single note:

- `automation_level`: manual, advisory, shared, supervised, full
- `automation_reliability`: per subtask probability of correct intervention
- `automation_failure_mode`: miss, false alarm, delayed handoff, wrong recommendation
- `handoff_policy`: fixed, threshold performance, workload classifier, HCF-adjusted, random control
- `transparency_mode`: none, confidence display, rationale display, future-state preview

Research value:

- Matches USAARL MATB's performance-driven handoff direction.
- Enables trust calibration and automation bias studies.
- Lets DEPDF/HCF outputs drive adaptive policies.

#### Feature 4: Trust and Automation Calibration Module

Add pre/post and repeated trust probes:

- trust in automation
- perceived reliability
- reliance/compliance behavior
- override rate
- agreement/disagreement with advisory automation
- calibration error: subjective trust minus actual reliability/performance

This should be integrated into the analysis engine as a new confirmatory/exploratory family.

#### Feature 5: Composite Performance and Task Load Profile

Create a composite MATB score that does not hide task-level data:

- task-level z scores by participant/session
- load profile: time with 0/1/2/3 active discrete events
- continuous task burden: tracking RMSE and RESMAN deviation
- composite score with confidence/uncertainty
- sensitivity view: score with and without subjective workload

This should live beside existing d-prime and DEPDF fits, not replace them.

#### Feature 6: Eye-Tracking and Pupillometry Pipeline

Add a pipeline for AOI and pupil features:

- fixation duration by AOI
- dwell time by task panel
- scanpath entropy
- transition matrix between task areas
- time-to-first-fixation after alerts
- pupil baseline correction
- event-locked pupil dilation response

Research value:

- FAA/EASA workload questions often require linking display design, workload, and performance.
- Recent MATB papers warn that average pupil size can be misleading; event-locked and stage-specific metrics are more defensible.

#### Feature 7: Operational Stressor Packs

Add scenario packs that fit the already military-aviation-focused design:

| Pack | Capabilities |
|---|---|
| Fighter | hypoxia onset/recovery, G-load/AGSM state, spatial disorientation, sensor failure, threat prioritization, ROE ambiguity, team SA probes |
| RPA | multi-aircraft supervision, lost-link events, target ID ambiguity, civilian-presence annotations, shift-work/fatigue timeline, kill-chain decision stressors |
| Transport/tanker | sustained ops, air-to-air refueling states, crew coordination, weather/diversion decisions, fuel/range tradeoffs |
| Rotorcraft/eMCO-SiPO | high-integration cockpit, degraded automation, single-pilot workload, non-normal procedure queueing, crew/remote-support coordination |
| Space robotics | delayed command loops, supervisory autonomy, robot task packages, habitat/resource monitoring, communication dropout |

Each pack should ship with:

- scenario templates
- SAGAT question bank
- expected metrics
- validity assumptions
- examples for low/medium/high workload
- contraindications/limitations for interpreting results

#### Feature 8: Online Workload Classifier

Build an online model layer that can consume performance and physiology:

- baseline model: rule-based thresholds
- statistical model: mixed-effects or Bayesian participant-specific posterior
- ML model: personalized classifier trained on participant/session data
- outputs: workload probability, uncertainty, drift, and recommended handoff

The classifier should be opt-in and should always display uncertainty. The literature supports personalized models more strongly than universal classifiers, so the default should be participant-specific once enough data exist.

#### Feature 9: BIDS-Derivative Export

Export sessions in a BIDS-like layout:

```text
dataset_description.json
participants.tsv
sub-P01/
  ses-visit01/
    beh/
      sub-P01_ses-visit01_task-matb_events.tsv
      sub-P01_ses-visit01_task-matb_events.json
      sub-P01_ses-visit01_task-matb_metrics.tsv
    physio/
      sub-P01_ses-visit01_task-matb_recording-ecg_physio.tsv.gz
```

This will make the platform easier to audit, share, and analyze outside the app.

#### Feature 10: Study Operations Dashboard

Add operational controls needed for a real longitudinal study:

- participant schedule view
- randomization/counterbalancing assignment
- upcoming visit queue
- protocol deviations
- missing data reasons
- screen validity status
- exported artifact registry
- analysis lock/freeze button for pre-registered outputs

This fits the current tracker and participants pages.

#### Feature 11: Publication Report Generator

Add a backend/frontend report generator that exports:

- CONSORT/STROBE-style cohort flow
- completeness table
- workload manipulation check
- descriptive plots
- Q1-Q4 results
- Bayesian sensitivity summary
- DEPDF parameter table
- provenance and caveats
- markdown/Quarto output

This is a natural extension of the existing analysis artifact and would reduce manual manuscript work.

---

## 5. Implementation Priority

| Priority | Feature | Rationale |
|---|---|---|
| P0 | Fix dependency packaging and stale docs | Required for reproducibility and contributor onboarding |
| P0 | Scenario manifest/provenance validator | Low risk, high value, uses existing scenario and ingest code |
| P1 | LSL marker outlet + physiology stream registry | Unlocks neuroergonomics and real-time workload research |
| P1 | Adaptive automation condition schema | Enables USAARL-style research without waiting for ML |
| P1 | BIDS-style export | Makes data portable and publishable |
| P2 | Eye-tracking/pupillometry features | Strong research value but depends on sync infrastructure |
| P2 | Composite performance/task-load profile | Useful analysis improvement; can be implemented from existing metrics |
| P2 | Operational stressor packs | High value, but needs careful validation and scenario design |
| P3 | Online workload classifier | Should wait until synchronized data and enough participant records exist |
| P3 | Publication report generator | Valuable after artifact schemas stabilize |

---

## 6. Concrete Next Development Tasks

1. Create `requirements-dev.txt` or update root requirements so `python3 -m pytest tests -q` can collect analysis tests without relying on backend requirements implicitly.
2. Update `webui/README.md` to reflect the built frontend and current pages.
3. Add `ScenarioManifest` dataclass and JSON writer to `matb_integration/scenario_builder.py`.
4. Store scenario manifests during backend ingest and expose them in `/block`.
5. Add LSL marker outlet abstraction with a no-op fallback when `pylsl` is absent.
6. Add a `sync_status` backend endpoint and frontend diagnostics panel.
7. Add automation-condition fields to the scenario manifest before implementing adaptive behavior.
8. Add BIDS-like export command for metrics/fits/screen results.

---

## 7. Evidence Quality Notes

Scite and Crossref were used to verify key DOI-bearing references. The retrieved Scite records for the main MATB papers used here did not return retraction notices in the visible metadata. Claims about NASA, FAA, EASA, and ESA were checked against official pages. Claims about AF-MATB were supported by public DTIC search metadata and Consensus-indexed records; direct DTIC PDF retrieval was blocked from the current environment, so AF-MATB details should be rechecked manually before quoting exact report text in a manuscript.

No direct public ESA, EASA, or FAA MATB deployment was found in the targeted searches. The report therefore treats those organizations as adjacent human-factors and regulator sources, not as direct MATB users.

---

## References and Source Links

- Ahlstrom, V. (2016). *Human Factors Design Standard (DOT/FAA/HF-STD-001B).* Federal Aviation Administration. https://hf.tc.faa.gov/publications/2016-12-human-factors-design-standard/
- Cegarra, J., Valery, B., Avril, E., Calmettes, C., & Navarro, J. (2020). OpenMATB: A Multi-Attribute Task Battery promoting task customization, software extensibility and experiment replicability. *Behavior Research Methods, 52*, 1980-1990. https://doi.org/10.3758/s13428-020-01364-w
- EASA. (2023). *EASA Artificial Intelligence Roadmap 2.0: A human-centric approach to AI in aviation.* https://www.easa.europa.eu/en/document-library/general-publications/easa-artificial-intelligence-roadmap-20
- EASA. (2019). *RMT.0713 Human Factor in rotorcraft design.* https://www.easa.europa.eu/en/newsroom-and-events/events/rmt0713-human-factor-rotorcraft-design
- EASA. (n.d.). *eMCO-SiPO Extended Minimum Crew Operations - Single Pilot Operations: Safety Risk Assessment Framework.* https://www.easa.europa.eu/en/research-projects/emco-sipo-extended-minimum-crew-operations-single-pilot-operations-safety-risk
- ESA. (2018). *DLR's Rollin' Justin robot.* https://www.esa.int/ESA_Multimedia/Images/2018/08/DLR_s_Rollin_Justin_robot
- Kong, Y., Posada-Quintero, H. F., Gever, D., Bonacci, L., Chon, K. H., & Bolkhovsky, J. (2022). Multi-Attribute Task Battery configuration to effectively assess pilot performance deterioration during prolonged wakefulness. *Informatics in Medicine Unlocked, 28*, 100822. https://doi.org/10.1016/j.imu.2021.100822
- Kratchounova, D., Choi, I., Mofle, T. C., Miller, L., Stevenson, S., & Humphreys, M. (2021). *Exploring the Relationship between Flight Technical Error and NASA-TLX Subscale Ratings when Using HUD Localizer Takeoff Guidance in Lieu of Currently Required Infrastructure.* FAA Office of Aerospace Medicine, DOT/FAA/AM-21/29. https://www.faa.gov/data_research/research/med_humanfacs/oamtechreports/2020s/2021/202129
- Miller, W. D., Jr. et al. (2014). *An Updated Version of the U.S. Air Force Multi-Attribute Task Battery (AF-MATB).* AFRL-RH-WP-SR-2014-0001, DTIC ADA611870. https://apps.dtic.mil/sti/tr/pdf/ADA611870.pdf
- Pontiggia, A., Gomez-Merino, D., Quiquempoix, M., et al. (2024). MATB for assessing different mental workload levels. *Frontiers in Physiology, 15*, 1408242. https://doi.org/10.3389/fphys.2024.1408242
- Pontiggia, A., Fabries, P., Beauchamps, V., et al. (2024). Combined Effects of Moderate Hypoxia and Sleep Restriction on Mental Workload. *Clocks & Sleep, 6*(3), 338-358. https://doi.org/10.3390/clockssleep6030024
- Santiago-Espada, Y., Myer, R. R., Latorella, K. A., & Comstock, J. R., Jr. (2011). *The Multi-Attribute Task Battery II (MATB-II) Software for Human Performance and Workload Research: A User's Guide.* NASA/TM-2011-217164. https://ntrs.nasa.gov/citations/20110014456
- Vogl, J., McCurry, C. D., Bommer, S., & Atchley, J. A. (2024). The United States Army Aeromedical Research Laboratory Multi-Attribute Task Battery. *Frontiers in Neuroergonomics, 5*, 1435588. https://doi.org/10.3389/fnrgo.2024.1435588
