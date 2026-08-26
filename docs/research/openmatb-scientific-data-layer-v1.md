# OpenMATB scientific data layer v1

## Purpose and scope

This additive layer brings the tracked OpenMATB runtime substantially closer
to the USAARL MATB output model while preserving the original six-column
OpenMATB session CSV and replay behavior. It is for controlled human-factors
research and training evaluation. It is not a medical device, operational
readiness score, personnel-selection instrument, or authority for adaptive
automation.

The implementation is informed by the USAARL MATB description
([DOI 10.3389/fnrgo.2024.1435588](https://doi.org/10.3389/fnrgo.2024.1435588)),
OpenMATB's published design
([DOI 10.3758/s13428-020-01364-w](https://doi.org/10.3758/s13428-020-01364-w)),
and recent MATB workload research
([DOI 10.3389/fphys.2024.1408242](https://doi.org/10.3389/fphys.2024.1408242)).
The cited papers support the task/measurement rationale; they do not validate
this repository's implementation or establish fitness for a military decision.

## Capability comparison

| Capability | Previous repository path | Scientific data layer v1 | USAARL comparison |
| --- | --- | --- | --- |
| Event/performance log | Six-column CSV written at task update intervals | Preserved byte-for-byte as `events.csv` | Retains event markers and legacy analysis compatibility |
| Continuous state | Task-dependent performance rows only | Deadline-based, observed state samples at 20 Hz by default | Implements per-loop-style state assessment at a declared independent sampling deadline |
| Missed observations | Not explicit | `missed_ticks`, interval, lateness, completeness, gaps, and non-monotonic timestamp checks | More explicit timing provenance; no synthetic catch-up rows |
| System monitoring | HIT/MISS/FA and RT in adjacent legacy rows | Stable alert trials with onset, deadline, response, RT, outcome, actor, and linked event sequence | Supports RT, accuracy, and published timeout-relative scoring |
| Communications | Radio/frequency outcome and RT in adjacent rows | Stable prompt trials with radio/frequency element accuracy | OpenMATB exposes two response elements, so USAARL three-element accuracy is explicitly `not_computable` |
| Tracking | Deviation/in-target legacy rows | Raw 20 Hz cursor, deviation, in-target state, mean/RMSE, and optional scaled scores | USAARL scaled error is separately named and remains lower-is-better |
| Resource management | Tank deviation/in-tolerance legacy rows | Raw levels, targets, signed deviations, tolerance state, and pump-state matrix | USAARL signed score is emitted only for its published 2,000-unit target configuration |
| Subjective workload | Blocking legacy ISA 1–5 plus post-block scales | Concurrent, nonblocking ISA-10 with latency/timeout; legacy NASA-TLX/Bedford remain available and receive structured raw-value trials | Provides value and RT without pausing concurrent MATB tasks |
| Automation/load | Parameters and events | Per-sample automation vector, pending trial IDs, discrete task-load count | Implements the requested automation-state and discrete-loading matrices in tidy columns/JSON |
| Output integrity | CSV plus optional adjacent manifest | Versioned dictionary, CSV, Parquet, summary, quality report, SHA-256 inventory, ZIP, partial-run marker | Immediately processable and independently integrity-checkable |
| Research-console intake | CSV plus optional scenario manifest | Adds bounded `.matb.zip` intake, metadata-only SQL persistence, and verified artifact download | High-rate raw data remain in the immutable bundle rather than being expanded into SQL |

## Bundle contract

A completed run produces `<legacy-stem>.matb.zip` beside the original CSV and
an inspectable `<legacy-stem>.research/` directory:

| Artifact | Role |
| --- | --- |
| `events.csv` | Unchanged OpenMATB event/performance stream |
| `samples.csv` | Authoritative observed state samples |
| `samples.parquet` | Typed columnar copy of `samples.csv` |
| `trials.csv` | One row per discrete alert, prompt, or workload response |
| `summary.json` | Descriptive raw metrics plus direction-explicit scores |
| `manifest.json` | Runtime, scenario, clock-origin, scoring-threshold, and durability provenance |
| `data_dictionary.json` | Generated field/type/unit/nullability/direction contract |
| `quality.json` | Sampling completeness, latency, gaps, and issue codes |
| `checksums.sha256` | SHA-256 for every other artifact |
| `partial-run.json` | Present only after interruption or recoverable recording failure |

The validator rejects traversal, nested or duplicate ZIP members, excessive
entry/count sizes, missing artifacts, checksum mismatches, schema/header
mismatches, invalid Parquet magic, and inconsistent complete/partial markers.

## Timing semantics

`scheduled_monotonic_ns` is the most recent elapsed 20 Hz deadline and
`observed_monotonic_ns` is when the state was actually read. If the UI loop is
late, the recorder writes one real observation and increments `missed_ticks`;
it never fabricates past states. UTC is derived from a single session UTC and
monotonic origin so wall-clock corrections cannot make within-run time run
backward.

The default engineering warnings are:

- completeness below 99%;
- p95 deadline lateness above 10 ms;
- maximum observed gap above 250 ms;
- any non-monotonic timestamp (error).

These are data-quality gates, not universal psychometric validity criteria.
Run a hardware/OS/display pilot with the intended joystick, audio device,
background services, and endpoint-security controls before data collection.
The deterministic 30-minute scheduler test checks arithmetic drift; it does not
replace end-to-end timing validation. General software timing limitations are
discussed in [DOI 10.7717/peerj.9414](https://doi.org/10.7717/peerj.9414).

## Scores and direction

Raw values are authoritative. Every transformed score records a formula ID,
status, unit, and direction. No global or readiness composite is produced.

- RT efficiency (higher is better):
  `100 × (timeout_ms - RT_ms) / timeout_ms`, clamped to 0–100; a miss or
  timeout is zero. The canonical and USAARL-compatible names are separate even
  when the numerical transform is the same.
- Tracking canonical performance (higher is better): `100 - scaled_error`.
  USAARL scaled error (lower is better):
  `100 × mean_deviation / experimenter_tracking_range`.
- Resource canonical performance (higher is better):
  `100 - 100 × mean_absolute_deviation / experimenter_resource_range`, clamped
  to 0–100. USAARL signed scaling is target-centric rather than a conventional
  higher-is-better score and is compatible only when the target is 2,000.
- Communications canonical element accuracy uses the two OpenMATB response
  elements (radio and frequency). The USAARL three-element metric remains null
  instead of inventing a third element.

If an experimenter-defined range is absent, the corresponding score is null
with `missing_threshold`. Thresholds can be supplied in the scenario manifest
under `parameters.scientific_scoring.tracking_range` and
`parameters.scientific_scoring.resource_range`. Define and preregister them
before inspecting outcomes.

NASA-TLX remains a post-block instrument. Its legacy `raw_tlx` sum (0–60 for
the repository's 0–10 items) is retained for compatibility, while
`raw_tlx_mean_0_10` and `raw_tlx_0_100` make the scale explicit. Do not mix
these representations in one analysis.

## Research-console workflow

Use the upload page's preferred **Scientific bundle (.matb.zip)** mode, or call:

```text
POST /ingest-bundle
GET  /blocks/{block_id}/artifacts
GET  /blocks/{block_id}/artifacts/{name}
GET  /blocks/{block_id}/bundle
```

Set `MATB_OPENMATB_BUNDLE_DIR` to an institution-controlled storage location.
The console records block/bundle/artifact metadata in SQLite, but does not copy
high-rate samples into relational rows. Artifact and whole-bundle downloads
are hashed again before serving.

## Minimum scientific acceptance work

Before using these outputs with military personnel:

1. Obtain protocol, consent, privacy, records-retention, and command/IRB or
   equivalent human-research approvals appropriate to the jurisdiction.
2. Freeze the scenario, software commit, hardware, OS, sampling rate, response
   devices, audio calibration, task instructions, language, and score
   thresholds before confirmatory collection.
3. Conduct usability/cognitive interviews and a counterbalanced pilot in the
   target population. Examine practice, fatigue, order, language, handedness,
   device, rank/role, and prior gaming/aviation-experience effects.
4. Report raw task outcomes and data quality before normalized scores. Treat
   automation exposure as an experimental condition, not a participant trait.
5. Establish test-retest reliability, sensitivity to the intended workload
   manipulation, convergent/discriminant validity, missing-data rules, and
   measurement invariance before comparing groups.
6. Predefine exclusion and partial-run handling. Never silently discard timing
   warnings or impute missed 20 Hz samples as observed state.
7. Keep any physiology stream synchronized through a separately validated
   acquisition contract. Lab Streaming Layer is a plausible integration path
   ([DOI 10.1162/imag.a.136](https://doi.org/10.1162/imag.a.136)) but typed
   physiology ingestion is intentionally outside v1.
8. Do not use task scores alone for diagnosis, deployability, promotion,
   discipline, credentialing, weapon assignment, or autonomous adaptation.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python -m pytest \
  tests/test_scientific_data_core.py \
  tests/test_scientific_data_bundle.py \
  tests/test_scientific_data_summary.py \
  tests/test_scientific_data_soak.py -q

cd openmatb
PYTHONDONTWRITEBYTECODE=1 python -m pytest \
  tests/test_research_runtime.py \
  tests/test_instantaneousworkload_logic.py \
  tests/test_sysmon_logic.py \
  tests/test_communications_logic.py -q
```
