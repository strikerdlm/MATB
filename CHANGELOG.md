# Changelog

All notable changes to OpenMATB will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### Visual & Accessibility Controls
- Added `ui_scale` and `colorblind_mode` to `config.ini` and surfaced them in the Streamlit config studio.
- `ui_scale` scales 2D fonts and widget spacing without altering any scenario timing or KPI computations.
- `colorblind_mode` enforces an aeronautical status palette (normal/advisory/caution/warning/inoperative) that remains legible without relying solely on red/green discrimination.

#### Mission Director 2D Status Strip
- Refined `plugins/missiondirector.py` to render each UAV on a fixed-width, text-only status line
  (`UAV | MISSION | MODE | TASK | ENDUR | ALERTS`) consistent with UAS mission summary strips.
- Representation remains strictly 2D and backwards compatible with existing logs and scenarios; only
  presentation changed, preserving MATB psychometric validity.

#### VTOL, Payload, and Swarm 2D Strips
- Updated `plugins/vtolmanager.py` to show each VTOL on a fixed-width line with phase, time in phase,
  battery percentage plus an ASCII bar, power multiplier, and alert tags, without changing any
  underlying VTOL timing, power, or logging logic.
- Updated `plugins/vtolpower.py` to render VTOL energy reserves as remaining/capacity with a
  percentage bar, ordered from lowest remaining fraction first for quick scan while preserving
  existing `vtol_power_*` metrics.
- Updated `plugins/launchrecovery.py` so active launch/recovery legs appear as `UAV | Phase | Method |
  TGO | bar`, sorted by earliest deadline.
- Updated `plugins/payloadmanager.py` and `plugins/sensorresource.py` to display per-sensor lines with
  bandwidth and energy plus ASCII bars and a total link-capacity bar, making over-capacity states more
  glanceable while keeping all `payload_*` and `sensor_*` metrics unchanged.
- Updated `plugins/swarmformation.py` to add a manual-overrides-versus-limit bar and to list MANUAL
  members first, while retaining existing `swarm_*` cognitive-overload metrics.

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
- **Config programming UI**:
  - `tools/config_portal.py` Streamlit front-end edits `config.ini`, enforces the MATB-required fields (language, screen index, fullscreen, `clock_speed`, scenario path, session numbering), and shows Manual §11 guidance alongside the form.
  - Adds `streamlit` to `requirements.txt`.

- **Voice Generation System (OpenAI TTS)**:
  - New `tools/voice_generator.py` module for ATC-style voice generation using OpenAI's gpt-4o-mini-tts model
  - Air Traffic Controller voice characteristics following ICAO/FAA radio communication standards
  - 11 voice options: alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer, verse
  - Configurable voice parameters: accent, emotional range, intonation, speed (0.25x-4.0x), tone
  - Voice presets for common scenarios: ATC male/female (EN/ES), military tactical, briefing instructor, urgent alerts
  - Features:
    - Single text-to-speech generation
    - Callsign audio generation with NATO phonetic alphabet
    - Frequency audio generation
    - Instruction script audio generation
    - Full phonetic alphabet pack generation
    - MATB voice pack generation (compatible with communications plugin)
  - Intelligent caching system with hash-based deduplication
  - CLI interface for batch generation
  - Streamlit integration with dedicated 🎙️ Voice Generator tab
  - Spoken instructions generation in 📖 Instrucciones tab
  - Adds `openai>=1.40.0` to `requirements.txt`

#### TacticalDisplay Widget (2D Spatial Overlays)
- New `core/widgets/tacticaldisplay.py` widget per update_plan.md Section 2.5:
  - Lightweight 2D tactical overlay using pyglet primitives
  - Geofence polygon visualization with dynamic color based on breach status
  - UAV/entity position display with configurable icon types (diamond, circle, triangle, square)
  - Status-based coloring using STATUS_COLORS palette
  - Breach highlighting for entities outside geofence
  - Background grid for spatial reference
  - Integrated into `plugins/senseandavoid.py` for visual geofence monitoring

#### Automation Hooks Visual Feedback
- Enhanced `plugins/automationhooks.py` per update_plan.md Section 3.8:
  - Visual status display showing Automation ACTIVE/INACTIVE state
  - Rules list widget showing all registered automation rules
  - Recently fired rule indicators (★) that persist for 3 seconds
  - Operator symbols for rule conditions (>, ≥, <, ≤, =, ≠, #)
  - Configurable via `showvisualfeedback` parameter

#### Mission Director Progress Bars
- Enhanced `plugins/missiondirector.py` per update_plan.md Section 3.1:
  - Progress bars for mission task time remaining
  - Progress bars for endurance time remaining
  - Updated header to show progress bar columns
  - Faster update rate (500ms) for responsive bars

#### Layout Convention Standardization
- Updated default `taskplacement` values per update_plan.md Section 2.3:
  - Fighter/HPA overlays now default to `topright`: `energymanager`, `weaponsinventory`, `emergencystack`
  - UTM/BVLOS overlays now default to `bottomright`: `datalink`
  - Layout convention: top-left (MATB core), top-right (HPA), bottom-left (UAS payload), bottom-mid (mission), bottom-right (UTM/SAA)

### Fixed

- **`plugins/senseandavoid.py`**: Removed duplicate `_update_intruder_widget` method that was overwriting the progress-bar implementation with a basic version lacking TTI bars
- **`plugins/vtolmanager.py`**: Fixed incorrect gettext fallback that attempted to import non-existent `builtins._`; now falls back to identity function when gettext is not available
- **`plugins/payloadmanager.py`**, **`plugins/sensorresource.py`**: Corrected link capacity bar calculation to show remaining capacity (bar shrinks as bandwidth consumed) per Manual.md section 4.6 conventions
- **`plugins/launchrecovery.py`**, **`plugins/swarmformation.py`**: Fixed newline escape sequences (`'\\n'` → `'\n'`) that caused literal `\n` to appear in widget text instead of line breaks

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

