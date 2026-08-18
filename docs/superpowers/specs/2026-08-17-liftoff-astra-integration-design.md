# Liftoff–ASTRA Research Integration Design

**Status:** Approved design
**Date:** 2026-08-17
**Canonical implementation owner:** `MATB/` for task sessions and performance; `HRV/` for Polar H10 acquisition and physiological analysis
**Target protocol:** ASTRA 2026, three visits: T0, DM8, DM15

## 1. Purpose

Integrate the commercial PC edition of Liftoff into ASTRA as a manual first-person-view (FPV) performance task. Liftoff complements, but does not replace, the existing OpenMATB and native sUAS instruments:

- OpenMATB remains the controlled multi-attribute workload manipulation.
- Native MATB sUAS remains the supervisory command-and-control task.
- Liftoff measures continuous manual FPV control.
- HRV owns Polar H10 RR data, signal quality, and physiological interpretation.

The integration is a research instrument. It must not produce diagnosis, fitness-for-duty, readiness clearance, pilot certification, or operational go/no-go decisions.

## 2. Fixed decisions

1. Use the unmodified commercial Liftoff PC application.
2. Consume only Liftoff's documented UDP telemetry output.
3. Bind the telemetry receiver to loopback, normally `127.0.0.1:9001`.
4. Use a file-first architecture; LSL is an optional mirror, never the sole record.
5. MATB owns task metadata, telemetry, results, deviations, derived performance metrics, and sealed artifacts.
6. HRV owns Polar recording, RR persistence, cleaning, quality control, and baseline/task/recovery metrics.
7. Use exactly three visits: T0/day 0, DM8/day 8, and DM15/day 15.
8. Use one fixed neutral racing/time-trial condition, not combat, multiplayer, or freestyle, for primary inference.
9. Use a monitor and RC transmitter; do not use VR or a gamepad in the initial ASTRA study.
10. Preserve component outcomes; do not create a single composite pilot score.
11. Do not train a workload, fatigue, or vigilance classifier on the ASTRA cohort.

## 3. Non-goals

- Modifying, injecting into, reverse-engineering, or reading Liftoff process memory.
- Automating participant controller input.
- Treating Steam leaderboards as research records.
- Implementing real-aircraft control or external vehicle telemetry.
- Adaptive automation based on real-time physiology.
- Real-time fitness or readiness decisions.
- Replacing the MATB LOW/MEDIUM/HIGH workload protocol.
- Making LSL or XDF mandatory for the first release.

## 4. Architecture

```text
Liftoff commercial PC application
       |
       | official UDP telemetry on loopback
       v
MATB Liftoff collector
       |-- raw framed packets
       |-- canonical telemetry JSONL
       |-- protocol markers
       |-- visible-result verification
       v
MATB Liftoff session + sealed artifact bundle
       |
       | session UUID + marker times + source hashes
       v
HRV Polar linkage and baseline/task/recovery analysis
       |
       v
Combined ASTRA research export
```

The task and physiology pathways are independently durable. A Polar failure does not erase valid flight data, and an HRV service outage does not prevent later attachment. A Liftoff telemetry failure does not corrupt the HRV source record.

## 5. Repository boundaries

### 5.1 MATB

Create a Liftoff-specific domain package:

```text
matb_integration/liftoff/
├── __init__.py
├── protocol.py
├── receiver.py
├── records.py
├── session.py
├── quality.py
└── metrics.py
```

Responsibilities:

- `protocol.py`: supported packet profile, strict binary decoder, schema identity.
- `receiver.py`: bounded UDP socket, packet sequencing, health state, raw framing.
- `records.py`: immutable telemetry and marker value objects.
- `session.py`: prepare/start/phase/finish/abort lifecycle and durable recorder orchestration.
- `quality.py`: packet loss, gaps, ordering, clock, and schema validation.
- `metrics.py`: deterministic kinematic and controller-input metrics.

Add isolated backend files:

```text
webui/backend/app/
├── liftoff_models.py
├── liftoff_schemas.py
├── liftoff_persistence.py
└── routers/liftoff.py
```

Do not add Liftoff fields to native sUAS `SimulationSession`. Extract reusable atomic-write/checksum primitives from `matb_integration/suas/recording/` into a domain-neutral recording module, while leaving compatibility imports so the existing sUAS contract and tests remain valid.

Add frontend surfaces:

```text
webui/frontend/src/app/liftoff/
├── setup/page.tsx
├── session/page.tsx
└── debrief/page.tsx
```

### 5.2 HRV

The HRV repository remains authoritative for:

- Polar H10 BLE acquisition.
- RR parsing and normalization.
- RR signal quality and artifact reporting.
- Persistent HRV measurement records.
- Baseline/task/recovery analysis.

Extend `app/polar_h10_recorder.py` to write a machine-readable timing sidecar. Reuse `POST /api/research/hrv/upload` for persistent analysis where possible. Any new task-capture request/response model belongs in HRV, not MATB.

### 5.3 Obsidian ASTRA vault

After software and pilot acceptance, update the canonical ASTRA operations manual and protocol documents. The software design must not silently redefine the approved research protocol.

## 6. Study-protocol configuration

Replace distributed six-visit assumptions with one backend-owned immutable protocol definition:

```text
protocol_id: astra-2026
protocol_version: 1.0.0
visits:
  - ordinal: 1
    code: T0
    scheduled_day: 0
  - ordinal: 2
    code: DM8
    scheduled_day: 8
  - ordinal: 3
    code: DM15
    scheduled_day: 15
```

The backend registry contains `astra-2026` and a compatibility profile for the existing six-visit study. Deployment selects exactly one profile. The backend exposes the selected profile through a read-only endpoint, and the frontend, completeness grid, participant creation, simulation schemas, visualization, and exports consume that endpoint or backend-derived visit records instead of carrying `N_VISITS = 6`.

An empty database is initialized with a study-metadata record containing protocol ID, version, and schedule hash. Startup refuses write-mode operation when that record conflicts with the selected deployment profile. Existing six-visit databases must not be rewritten automatically. ASTRA deployment uses a new database initialized for `astra-2026`; legacy databases retain their original schedule and remain independently readable under the compatibility profile.

## 7. Visit protocol

### 7.1 Recorded sequence at every visit

1. Equipment/configuration readiness: approximately 2 minutes.
2. KSS and pre-task contextual questions.
3. Seated Polar H10 baseline: 5 minutes.
4. Continuous Liftoff time-trial block: 15 minutes.
5. Seated recovery: 5 minutes.
6. NASA-TLX and technical-deviation review.
7. Visible-result verification, Polar linkage, and artifact sealing.

Expected burden is 30–35 minutes per Liftoff visit.

### 7.2 Familiarization

T0 familiarization uses a separate practice track before the physiological baseline. Completion criterion:

- Three consecutive completed laps.
- Lap-time coefficient of variation no greater than 10%.
- No more than one restart across those laps.
- Maximum familiarization time of 20 minutes.

If the criterion is not achieved, record `familiarization_incomplete`. Retain the session for feasibility reporting but exclude it from the primary longitudinal performance analysis.

DM8 and DM15 use a two-minute unrecorded practice-track refresher before baseline.

### 7.3 MATB/Liftoff order

Assign six participants to each fixed sequence:

- Sequence A: MATB, quiet break, Liftoff.
- Sequence B: Liftoff, quiet break, MATB.

Retain each participant's sequence across all visits. Use at least ten quiet minutes between tasks and include sequence as a statistical covariate.

## 8. Standardized Liftoff condition

Freeze and hash:

- Liftoff build/version.
- Track identifier and revision.
- Drone/component configuration.
- Flight-controller mode.
- Camera angle and field of view.
- Rates, expo, and controller calibration.
- Battery and damage settings.
- Environment/weather.
- Graphics profile, resolution, and display refresh rate.
- RC controller model and firmware.
- Audio level.
- Telemetry stream profile.

Use a neutral offline racing/time-trial task. Primary inference must not depend on combat, multiplayer, Steam account rank, online opponents, or public leaderboards.

The calibration pilot must select a track that yields:

- 70–90% successful lap completion.
- No strong ceiling or floor effect.
- At least three valid laps in 15 minutes for most trained pilot participants.
- Moderate workload without severe simulator sickness.
- Median telemetry packet loss below 1%.

Freeze the selected track, configuration, and reference trajectory before participant enrollment. Pause collection after a forced software update until the telemetry characterization and acceptance smoke test pass again.

## 9. Liftoff session persistence

### 9.1 `LiftoffSession`

| Field | Contract |
|---|---|
| `id` | UUID string, primary key |
| `participant_id` | FK to pseudonymized MATB participant |
| `visit_id` | FK to T0, DM8, or DM15 visit |
| `attempt_number` | Positive integer; database uniqueness on participant, visit, and attempt |
| `protocol_id` | `astra-2026` |
| `protocol_version` | Immutable protocol version |
| `liftoff_build` | Recorded build identifier |
| `configuration_sha256` | Frozen settings/configuration hash |
| `track_id` | Frozen track identity |
| `telemetry_profile` | `liftoff-telemetry-all-v1` |
| `status` | `PREPARED`, `BASELINE`, `TASK`, `RECOVERY`, `FINISHED`, `ABORTED`, `INTERRUPTED` |
| `validity` | `valid`, `partial`, `invalid`, `pending_review` |
| `artifact_root` | Private session directory |
| `hrv_measurement_id` | Nullable authoritative HRV identifier |
| `hrv_file_sha256` | Nullable HRV source hash |
| `sync_quality` | `good`, `acceptable`, `poor`, `missing` |
| `metrics_json` | Nullable sealed derived summary |
| timestamps | UTC creation/start/finish/interruption timestamps |

### 9.2 Supporting tables

- `LiftoffArtifact`: session, kind, relative path, SHA-256, size, creation time.
- `LiftoffDeviation`: session, phase, bounded code, severity, time, disposition.
- `LiftoffResult`: verified visible race outcomes, observer restart count, provenance for each field, and source screenshot artifact.

Allow multiple attempts only after technical invalidity. The first valid attempt is the analysis attempt. Poor participant performance never authorizes a retake.

## 10. Lifecycle

```text
PREPARED -> BASELINE -> TASK -> RECOVERY -> FINISHED
     |          |          |          |
     +----------+----------+----------+-> ABORTED
                                    \----> INTERRUPTED
```

Rules:

- No phase may be skipped.
- No task start without a valid configuration hash and telemetry readiness.
- A finished session becomes immutable after sealing.
- A process restart marks active sessions `INTERRUPTED` until reviewed.
- Recovery appends records; it does not rewrite existing telemetry or markers.
- Lifecycle corrections use append-only amendments.

## 11. Telemetry protocol

Configure Liftoff to emit the full documented profile to loopback. The supported first profile is `liftoff-telemetry-all-v1`.

Before collection, capture and retain official-profile golden packets. Characterize packet size, little-endian layout, field order, quaternion ordering, axis orientation, native units, motor count, and expected rate. The decoder must reject rather than guess after a schema mismatch.

### 11.1 Canonical record

```json
{
  "schema_version": "liftoff-telemetry-v1",
  "session_id": "uuid",
  "sequence": 1,
  "received_monotonic_ns": 0,
  "received_utc": "2026-08-17T14:00:00.000000Z",
  "simulator_time": 0.0,
  "position_native": [0.0, 0.0, 0.0],
  "attitude_native": [0.0, 0.0, 0.0, 1.0],
  "velocity_native": [0.0, 0.0, 0.0],
  "angular_rate_native": [0.0, 0.0, 0.0],
  "processed_input": [0.0, 0.0, 0.0, 0.0],
  "battery_voltage": 0.0,
  "charge_percent": 0.0,
  "motor_rpm": [0.0, 0.0, 0.0, 0.0]
}
```

Keep values labeled `native` until characterization proves units and frames. Preserve simulator time for within-flight dynamics, host monotonic time for ordering and cross-stream alignment, and UTC for external linkage/audit.

### 11.2 Receiver constraints

- Loopback bind only.
- Explicit packet-size allowlist.
- Bounded queue with recorded overflow count.
- Nonfinite values rejected.
- Unsupported motor count rejected.
- Duplicate/out-of-order packets counted and retained only in raw evidence.
- Twenty valid packets within two seconds required for readiness.
- Raw payloads framed with sequence, monotonic receive time, UTC receive time, and payload length.

Store both `telemetry.raw` and canonical `telemetry.jsonl`.

## 12. Markers

`markers.jsonl` is append-only and contains:

- `recording_started`
- `baseline_started`
- `baseline_finished`
- `task_started`
- `task_finished`
- `recovery_started`
- `recovery_finished`
- `recording_finished`
- `questionnaires_completed`
- `session_sealed`

Each marker includes session ID, phase, source, sequence, UTC, monotonic time, and optional bounded reason code. Corrections are new amendment markers and never edits.

## 13. Polar H10 contract

Use one continuous H10 recording from before baseline through recovery.

The HRV recorder timing sidecar contains:

```text
schema_version
recorder_version
capture_id
external_session_id
participant_id
recording_start_utc
recording_end_utc
start_monotonic_ns
end_monotonic_ns
device_identifier_hash
rr_count
rr_file_sha256
```

At debrief:

1. Select the RR file and sidecar.
2. Validate participant and session UUID.
3. Submit RR data to HRV with exact recording start time.
4. Convert MATB phase markers into RR index boundaries using cumulative RR time.
5. Request baseline/task/recovery analysis from HRV.
6. Store the returned measurement ID as authoritative.
7. Store hashes, linkage metadata, quality summary, and derived phase metrics in MATB.

MATB does not become a second authoritative RR store. It records `physiology-link.json`; combined exports retrieve or include the authorized HRV artifact separately.

Do not import the legacy uncalibrated `high_workload_probability` as a study outcome.

## 14. Synchronization quality

### Good

- Same workstation.
- Common monotonic timing is present.
- No clock discontinuity.
- Estimated uncertainty at or below 100 ms.
- Liftoff packet loss below 1%.

### Acceptable

- UTC timing is present without a common monotonic origin.
- Estimated uncertainty at or below 1 second.
- Liftoff packet loss below 5%.
- Baseline/task/recovery comparisons are allowed; event-level coupling is not.

### Poor

- Uncertainty exceeds 1 second, a clock discontinuity occurred, or packet loss is at least 5%.
- Physiology may be summarized by broad phase only.

### Missing

- No valid Polar record is linked.

## 15. Artifact bundle

```text
liftoff/<session_uuid>/
├── session-manifest.json
├── liftoff-configuration.json
├── telemetry.raw
├── telemetry.jsonl
├── markers.jsonl
├── results.json
├── result-screen.png
├── questionnaires.json
├── physiology-link.json
├── telemetry-quality.json
├── metrics.json
├── debrief.json
├── partial-run.json
└── checksums.sha256
```

`partial-run.json` exists only for interrupted/aborted sessions. High-rate data remains in files, not SQL rows. All writes are same-directory atomic writes; sealed files receive SHA-256 entries. A sealed bundle cannot be overwritten.

The manifest includes participant pseudonym, visit, attempt, protocol/version, Liftoff build, hardware, controller, display, track, settings, task order, source hashes, and validity.

## 16. Outcomes

### 16.1 Primary performance outcomes

- Valid laps completed in 15 minutes.
- Median valid lap time.
- Best valid lap time.
- Lap-completion proportion.
- Crash/restart count.

Valid-lap count and lap times come from the visible race results and require manual verification against `result-screen.png`. Crash/restart count comes from the standardized observer record and is reconciled against telemetry reset candidates; discrepancies remain explicit deviations. Steam leaderboards are excluded.

### 16.2 Secondary telemetry outcomes

- Active flight duration.
- Path length after unit validation.
- Mean and 95th-percentile speed.
- Angular-rate RMS and 95th percentile.
- Control-input RMS.
- Control-input saturation fraction.
- Control reversal rate.
- Input entropy.
- Filtered control smoothness.
- Path deviation from the frozen reference trajectory.
- Within-session lap consistency.

Publish algorithms, filters, windowing, units, and missingness rules with every metric version. Do not combine these into a single score.

### 16.3 Physiological outcomes

- Mean heart rate by phase.
- `lnRMSSD` by phase.
- Baseline-to-task `ΔlnRMSSD`.
- Task-to-recovery `ΔlnRMSSD`.
- RR artifact percentage and usable coverage.

LF/HF is not a primary endpoint.

### 16.4 Contextual outcomes

- KSS.
- NASA-TLX total and six subscales.
- Previous FPV/gaming experience.
- Sleep and ActiGraph context.
- MATB/Liftoff task order.
- Familiarization status.
- Technical deviations.

## 17. Statistical contract

Treat the cohort (`n=12`) as exploratory/feasibility research.

Continuous outcomes use a participant-random-intercept mixed model:

```text
outcome ~ visit + sequence + prior_FPV_experience + (1 | participant)
```

Count outcomes use Poisson or negative-binomial mixed models after dispersion assessment. Prespecified visit contrasts are:

1. T0 versus DM8.
2. T0 versus DM15.
3. DM8 versus DM15 as secondary.

Report effect estimates, confidence intervals, standardized effect sizes, model diagnostics, and missingness. Apply multiplicity control to secondary outcomes. Cross-modal HRV/MATB/Liftoff associations are exploratory. No classifier training is permitted.

## 18. Validity rules

| Condition | Required disposition |
|---|---|
| No valid UDP packets before start | Block start |
| Unknown packet schema | Block start and retain diagnostic raw packet |
| Packet loss 1–5% | `partial`, researcher review |
| Packet loss ≥5% | Invalidate telemetry-derived outcomes |
| Polar failure | Preserve performance, mark physiology missing |
| Missing visible result | Preserve telemetry, invalidate primary lap outcomes |
| Liftoff crash | Seal partial run; technical retake allowed |
| MATB crash | Recover append-only evidence; do not infer completion |
| Configuration mismatch | Block start |
| Liftoff build change | Suspend collection pending recalibration |
| Familiarization incomplete | Exclude from primary performance analysis |
| Visible stutter/performance failure | Deviation and affected-run invalidation |

## 19. API surface

Backend routes are scoped under `/liftoff`:

- `GET /liftoff/protocol`
- `GET /liftoff/readiness`
- `POST /liftoff/sessions`
- `GET /liftoff/sessions/{id}`
- `POST /liftoff/sessions/{id}/baseline/start`
- `POST /liftoff/sessions/{id}/baseline/finish`
- `POST /liftoff/sessions/{id}/task/start`
- `POST /liftoff/sessions/{id}/task/finish`
- `POST /liftoff/sessions/{id}/recovery/start`
- `POST /liftoff/sessions/{id}/recovery/finish`
- `POST /liftoff/sessions/{id}/abort`
- `POST /liftoff/sessions/{id}/results`
- `POST /liftoff/sessions/{id}/physiology-link`
- `POST /liftoff/sessions/{id}/questionnaires`
- `POST /liftoff/sessions/{id}/seal`
- `GET /liftoff/sessions/{id}/debrief`
- `GET /liftoff/sessions/{id}/artifacts`

Use strict Pydantic schemas with `extra="forbid"`, bounded strings, pseudonym patterns, lifecycle preconditions, one-time controller/session authority, and stable public error codes.

## 20. Frontend behavior

### Setup

- Select participant and T0/DM8/DM15 visit.
- Display attempt history and block unauthorized retakes.
- Verify Liftoff build/configuration hash.
- Verify telemetry readiness.
- Confirm controller/display/track settings.
- Confirm Polar recording has started or explicitly approve performance-only collection.

### Session

- Show phase timer and transition controls.
- Show telemetry packet rate, loss estimate, last-packet age, and schema status.
- Never show diagnostic filesystem paths or Steam identity.
- Make phase transitions explicit and confirmation-gated.
- Preserve operator usability if HRV is unavailable.

### Debrief

- Enter visible race outcomes.
- Require result screenshot.
- Link Polar file/sidecar.
- Complete NASA-TLX.
- Review quality and deviations.
- Seal only after all mandatory fields pass.

## 21. Security and privacy

- Loopback UDP only.
- Pseudonymized participant IDs only.
- Do not persist Steam usernames/account identifiers.
- Use a neutral research Steam account.
- Resolve artifacts beneath one configured root; reject traversal and symlink escapes.
- Bound file sizes, packet queues, and upload lengths.
- Keep HRV service credentials backend-only.
- Never return raw device addresses or absolute paths.
- Record audit-safe deviations without free-text personal data.
- Make exports non-cacheable and integrity-verifiable.
- Obtain written permission for institutional research use of the commercial application.

## 22. Verification

### Unit tests

- Golden packet decoding.
- Packet-size, NaN/Inf, and motor-count rejection.
- Sequence, timestamp, and marker ordering.
- Three-visit protocol generation.
- Lifecycle preconditions.
- Deterministic metrics and filter versions.
- Checksum creation/verification.
- First-valid-attempt and technical-retake rules.

### Integration tests

- Synthetic UDP sender at expected rate.
- Loss, duplication, reorder, malformed packet, and silence cases.
- Prepare through seal lifecycle.
- Partial-run recovery.
- HRV success, delay, duplicate, mismatch, and outage.
- Artifact reproducibility and checksum audit.
- Three-visit completeness tracking and export.

### Browser tests

- Setup readiness and visit selection.
- Baseline/task/recovery transitions.
- Telemetry warnings.
- Results/screenshot verification.
- Polar linkage.
- Debrief and export.

### Hardware acceptance

- Commercial Liftoff plus designated RC controller.
- Polar H10 recording.
- Thirty-minute telemetry soak.
- Bluetooth disconnect.
- UDP interruption.
- Liftoff crash/restart.
- MATB backend restart.
- Clock-step detection.
- Offline operation.
- Checksum verification on a second machine.

## 23. Pilot release gate

Before enrolling ASTRA participants:

- At least four pilot users complete three recorded sessions each.
- Median telemetry loss is below 1%.
- No bundle is unrecoverably lost.
- HRV linkage succeeds in at least 90% of pilot sessions.
- No clock/schema error remains unresolved.
- Selected-track completion is 70–90%.
- No severe simulator-sickness event occurs.
- A second operator completes the SOP without developer assistance.

## 24. Delivery sequence

1. Centralize the three-visit ASTRA protocol and remove six-visit assumptions.
2. Characterize and implement the strict Liftoff UDP contract.
3. Add file-first lifecycle, markers, and sealed artifacts.
4. Add Liftoff persistence and backend API.
5. Add setup/session/debrief frontend workflow.
6. Add precise Polar timing sidecars and post-session HRV linkage.
7. Add quality and performance metrics.
8. Extend tracker and combined research exports.
9. Complete automated and hardware verification.
10. Run the calibration pilot, freeze the build, and publish the ASTRA SOP.

## 25. Acceptance criteria

The integration is ready for ASTRA participant collection only when:

1. T0, DM8, and DM15 are the only generated visits in a new ASTRA database.
2. A real commercial Liftoff session produces a valid sealed bundle without process modification.
3. Raw packets re-decode deterministically to the stored canonical telemetry.
4. Phase markers and Polar timing produce a documented synchronization grade.
5. The HRV record is authoritative and referenced by identifier/hash from MATB.
6. Primary visible outcomes and secondary telemetry metrics are reproducible.
7. Interrupted sessions remain partial and cannot masquerade as complete.
8. Native sUAS runtime and OpenMATB ingestion/analysis regressions pass; only visit-count expectations intentionally change under the `astra-2026` profile.
9. Hardware acceptance and pilot release gates pass.
10. The ethics/protocol documentation and written software-use permission are in place.
