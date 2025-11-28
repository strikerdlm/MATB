# Changelog

All notable changes to OpenMATB will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Real-Time HRV Combat Scenario Integration
Implementation of Manual.md Section 17-18 roadmap for physiological monitoring during combat scenarios.

- **Enhanced `plugins/polarrlink.py`**:
  - Auto-reconnect with exponential backoff on BLE disconnection
  - Battery level monitoring and logging
  - Signal quality estimation based on artifact rate
  - Monotonic timestamps for reproducibility
  - Kubios-style artifact rejection (300-2000ms bounds, 20% delta threshold)
  - `RRPacket` dataclass for immutable RR interval data
  - BLE device scanning via `scan` command
  - Comprehensive logging: `polar_start`, `polar_connect`, `polar_disconnect`, `polar_battery`, `polar_status`, `polar_error`

- **Enhanced `plugins/physiomonitor.py`**:
  - Baseline calibration with z-score normalization
  - Rolling window HRV computation (RMSSD, SDNN, pNN50, LF, HF, LF/HF)
  - Durantin overload detection (quadratic LF/HF model for mental overload)
  - Workload classification: low/medium/high/overload
  - Acute workload alerts with configurable thresholds
  - Data export to CSV/JSON for offline analysis
  - Public API for automation hooks integration: `get_latest_snapshot()`, `get_workload_level()`, `is_overload_detected()`
  - `HRVSnapshot` and `BaselineStats` dataclasses
  - Scenario commands: `baseline;start/stop/reset`, `threshold;metric,value`, `export;path`

- **New scenario templates in `tools/scenario_templates.py`**:
  - `hrv_combat`: Combat scenario with HRV baseline calibration, progressive workload ladder, and HRV-triggered automation rules
  - `hrv_mumt`: Hybrid MUM-T scenario combining fighter tasks with UAV supervision for dual-task interference research

- **Example scenario**: `includes/scenarios/hrv_combat_demo.txt`
  - 10-minute scenario with 2-minute baseline calibration
  - Progressive workload phases: Low → Medium → High → Overload
  - HRV-triggered automation rules for adaptive workload management
  - Fighter and UAV task integration
- **Enhanced `core/performance_summary.py`**:
  - Adds Physio Monitor KPI block summarising RMSSD/SDNN/LF-HF stats
  - Reports HRV workload distributions, alert totals, and overload counts in JSON/Markdown summaries
- **Session HRV exports**:
  - Physio Monitor now auto-writes `rr_intervals.csv`, `hrv_windows.csv`, `hrv_windows.parquet`, `hrv_alerts.json`, and `hrv_baseline.json` inside each session's `hrv/` directory
  - Polar RR Link emits `polar_metadata.json` with device, battery, and provenance fields for every run
- **New tooling**:
  - `tools/hrv_validate.py` CLI validates HRV export folders (RR stats, window CSV/parquet consistency, alerts, baseline, Polar metadata)

### Changed

- Scenario templates now include Polar RR Link and Physio Monitor by default for physiological instrumentation
- Physio Monitor baseline exports now log `hrv_export` entries for provenance
- Polar RR Link now validates dependencies before setting the plugin alive state, preventing inconsistent starts
- requirements now include `pandas` + `pyarrow` so HRV parquet exports and validators install cleanly
- VTOL Manager performance events now emit key–value payloads (`vtol_phase_change`, transition states, power alerts, battery/stability metrics) so logs, summaries, and downstream analytics stay self-describing

### Research References

Implementation based on peer-reviewed research:
- Durantin et al. 2014: LF/HF may decrease at overload (DOI: 10.1016/j.bbr.2013.10.042)
- Koskelo et al. 2024: Military flight HRV (DOI: 10.1016/j.apergo.2024.104370)
- Pontiggia et al. 2024: MATB workload assessment (DOI: 10.3389/fphys.2024.1408242)
- Makowski et al. 2021: NeuroKit2 (DOI: 10.3758/s13428-020-01516-y)

### Implementation Credit

Dr Diego Malpica, Aerospace Medicine

