# OpenMATB Mission Expansion Manual

This manual captures a concrete plan for extending OpenMATB to cover two high-value aviation contexts—Unmanned Aircraft Systems (UAS) operators and high-performance aircraft crews—using the existing plugin-driven architecture. The current implementation work is attributed to **Dr Diego Malpica, Aerospace Medicine**, who is curating these enhancements for translational research use.

## 1. Architecture Reference Points

OpenMATB exposes each task as a plugin derived from `AbstractPlugin`, which already manages lifecycle, widget scaffolding, and logging hooks:

```143:151:plugins/abstractplugin.py
    def start(self):
        if self.verbose:
            print('Start ', self.alias)
            print('with keys ', self.keys)
        self.alive = True
        self.create_widgets()
        self.log_all_parameters(self.parameters)
        self.show()
        self.resume()
```

Scenarios bind those plugins at runtime, so new training tasks only need scenario directives plus a concrete plugin class:

```17:48:core/scenario.py
class Scenario:
    '''
    This object converts scenario to Events, loads the corresponding plugins,
    and checks that some criteria are met (e.g., acceptable values)
    '''
    def __init__(self, contents=None):
        self.events = list()
        self.plugins = dict()

        if contents is None:
            scenario_path = P['SCENARIOS'].joinpath(get_conf_value('Openmatb', 'scenario_path'))
            if scenario_path.exists():
                contents = open(scenario_path, 'r').readlines()
                logger.log_manual_entry(scenario_path, key='scenario_path')
            else:
                errors.add_error(_('%s was not found') % str(scenario_path), fatal = True)

        # Convert the scenario content into a list of events #
        # (Squeeze empty and commented [#] lines)
        self.events = [Event.parse_from_string(line_n, line_str) for line_n, line_str
                       in enumerate(contents)
                       if len(line_str.strip()) > 0 and not line_str.startswith("#")]

        # Next load the scheduled plugins into the class, so we can check potential errors
        # But first, check that only available plugins are mentioned
        for event in self.events:
            if not hasattr(globals()['plugins'], event.plugin.capitalize()):
                errors.add_error(_('Scenario error: %s is not a valid plugin name (l. %s)') % (event.plugin, event.line), fatal = True)

        self.plugins = {name: getattr(globals()['plugins'], name.capitalize())()
                        for name in self.get_plugins_name_list()}
```

The plan below assumes we keep leveraging those extension seams.

## 2. Use Case 1 – UAS Operator Workflows

Recent FAA research catalogued the KSAOs UAS crews need—airspace knowledge, mission planning, multi-sensor prioritisation, crew resource management, and stress tolerance—highlighting gaps in standardized training for BVLOS, multi-ship, and payload-intensive ops ([FAA UAS KSA study](https://www.faa.gov/sites/faa.gov/files/data_research/research/med_humanfacs/oamtechreports/202114.pdf)). Colombian deployments add further constraints: the national power grid uses UAS to inspect mountainous transmission lines, but fragmented regulation and limited certified BVLOS corridors complicate scaling ([Unmanned Aircraft Systems: A Latin American Review and Analysis from the Colombian Context](https://www.mdpi.com/2076-3417/13/3/1801)). Medellín’s proposed BVLOS corridors demand risk-aware routing to avoid dense urban terrain, implying the need for high-fidelity scheduling and sense-and-avoid tasks as we model in OpenMATB ([Risk-Based Design of Urban UAS Corridors](https://www.mdpi.com/2504-446X/9/12/815)).

| Module | Goal | Implementation Notes |
| --- | --- | --- |
| **Multi-UAV Mission Director** | Allocate automation resources across up to four simulated aircraft, forcing prioritisation of “launch, surveillance, divert, recover” chains. | Extend `plugins/scheduling.py` to render column-per-aircraft timelines with automation takeover toggles. Add events like `missiondirector;assign;uav2,surveillance,03:00`. |
| **Sense-and-Avoid & Geofence Monitor** | Train sense-and-avoid reasoning (declare traffic conflicts, select maneuvers within timeouts). | New plugin `senseandavoid.py` using text/gauge overlays and flashing alerts. Parameters: conflict rate, separation minima, allowable maneuvers. Scenario events drive intruder azimuth and altitude bands. |
| **Payload & Sensor Management** | Practice simultaneous sensor slewing, target confirmation, and bandwidth rationing. | Derive from `AbstractPlugin` to manage a grid of “sensor pods” with energy budgets. Each task update adjusts signal fidelity; operator must queue shots while respecting downlink capacity. |
| **Datalink & Crew Coordination** | Recreate high-volume chat/datalink message parsing plus crew callouts. | Build on `plugins/datalink.py` to stream controller–pilot data link (CPDLC) style prompts with prioritisation (aligned with NASA CPDLC workload findings [NASA TM–2020-0010384](https://ntrs.nasa.gov/api/citations/20200010384/downloads/20200010384.pdf); [NTRS 1989-0002355](https://ntrs.nasa.gov/citations/19890002355)). Keyboard shortcuts (UP/DOWN/ENTER) support queue triage, while scenario hooks drive message mixes. |

### UAS Reference Scenarios

- Added `includes/scenarios/uas_basic.txt`, a five-minute demonstration scenario that starts the legacy MATB tasks plus Mission Director, Sense-and-Avoid, Payload Manager, Datalink, and Physio Monitor. It scripts UAV assignments, two deconfliction events, multi-sensor load juggling, and CPDLC-style prompts so research teams can evaluate the modules together or reuse it as a template when generating progressive difficulty ramps via `scenario_generator.py`.
- Added `includes/scenarios/uas_bvlos.txt`, a BVLOS stress drill with three simultaneous aircraft, persistent datalink traffic, repeated sense-and-avoid conflicts, and payload juggling. This scenario is useful for benchmarking automation assistance or experimenting with adaptive autonomy toggles.

### Scenarios & Metrics

1. **Mission build-up** – start with two aircraft and low conflict density, add additional UAVs plus payload events every 90 s.
2. **Geofence breach drills** – randomly move virtual no-fly bubbles; operator must re-task aircraft within 10 s to avoid breach.
3. **Lost link and handover** – feed tasks that force mid-scenario plug-in swap (`missiondirector;failradio;uav3`), requiring the trainee to initiate scripted recovery.

Log lines of type `state`/`performance` already capture widget values. Add domain metrics: e.g., “time-in-breach,” “payload latency,” “conflict resolution choice,” and stream them through the existing LSL plugin for real-time analytics.

### Mission Director Implementation Status

- Added `plugins/missiondirector.py`, which exposes scenario commands `assign`, `complete`, `automation`, `conflict`, and `clearconflict` for up to six UAVs. Each row shows mission name, automation mode, countdown timers, and alerts, while overdue feedback flashes whenever conflicts are active.
- Scenario example:

  ```text
  0:00:05;missiondirector;start
  0:00:05;missiondirector;assign;uav1,launch,300
  0:00:30;missiondirector;automation;uav1,auto
  0:02:00;missiondirector;conflict;uav1,geofence
  0:02:10;missiondirector;clearconflict;uav1
  0:05:10;missiondirector;complete;uav1
  ```

- Performance metrics emitted: `mission_assign`, `mission_mode`, `mission_alert`, enabling correlation with other MATB workloads.
- Multi-ship endurance tracker: `missiondirector;endurance;UAV1,2700,600` starts a 45-minute endurance clock (optional warning threshold in seconds). The table now shows both task time and remaining endurance, emitting `mission_endurance_set` and `mission_endurance_low` as timers cross thresholds.
- Automated handover protocol: `missiondirector;handover;UAV1,GCS-Bravo,start` and `missiondirector;handover;UAV1,GCS-Bravo,complete` document custody changes, logging `mission_handover_initiate` / `mission_handover_complete` and surfacing “Handover→GCS-Bravo” in the alert column.

### Sense-and-Avoid Implementation Status

- Added `plugins/senseandavoid.py`, which displays a live intruder table (bearing, range, altitude delta, time-to-impact, status) and drives overdue feedback whenever conflicts exceed prescribed TTI or remain unresolved. Scenario commands include:
  - `senseandavoid;spawn;INTR1,090,2.0,300,45` (bearing 090°, 2nm, +300 ft, 45 s to conflict)
  - `senseandavoid;resolve;INTR1,turn right 20°`
  - `senseandavoid;clear;INTR1`
  - `senseandavoid;thresholds;1.0,400`
- Metrics logged: `saa_spawn`, `saa_resolve` (with resolution time), `saa_overdue`, and `saa_thresholds`, enabling comparisons against NASA asymptotic workload measures and FAA detect-and-avoid timing guidance.
- Geofence overlay: use `senseandavoid;geofence;0.1|0.1,0.9|0.1,0.9|0.8,0.1|0.8` to define a no-fly polygon (normalized coordinates) or `senseandavoid;geofence;clear` to remove it. `senseandavoid;position;UAV1,0.45,0.35` updates aircraft positions, drives the ASCII map overlay, and emits `geofence_breach` / `geofence_recover` whenever a platform crosses the boundary.

### Payload & Sensor Management Implementation Status

- Added `plugins/payloadmanager.py`, which tracks sensor pods (energy %, assigned target, bandwidth) against total link capacity. Automatic depletion/recharge behaviour simulates power/bandwidth constraints; overdue alarms fire if total Mbps exceed the configured capacity or a pod goes fully depleted.
- Scenario hooks:

  ```text
  0:00:05;payloadmanager;start
  0:00:10;payloadmanager;activate;CamA,Target-Alpha,12
  0:00:20;payloadmanager;priority;CamA,18
  0:00:30;payloadmanager;activate;IRST,Target-Bravo,22
  0:02:00;payloadmanager;standby;CamA
  0:02:10;payloadmanager;recharge;CamA
  0:03:00;payloadmanager;capacity;60
  ```

- Logged metrics include `payload_activate`, `payload_priority`, `payload_overbandwidth`, `payload_depleted`, and `payload_overdue`, enabling post-run analysis of resource strategy versus mission outcomes.

### Datalink & Crew Coordination Implementation Status

- Added `plugins/datalink.py`, echoing NASA CPDLC evaluations showing reduced taxi time and voice congestion when digital messaging is available, yet highlighting situations that still demand rapid response ([NASA TM–2020-0010384](https://ntrs.nasa.gov/api/citations/20200010384/downloads/20200010384.pdf); [NTRS 19890002355](https://ntrs.nasa.gov/citations/19890002355)). The plugin displays an ordered queue (ID, channel, priority, remaining time, text) with keyboard navigation (UP/DOWN) and acknowledgement (ENTER) plus scenario hooks:

  ```text
  0:00:05;datalink;start
  0:00:07;datalink;message;MSG1,ATC,PRIO,HOLD SHORT RWY 28,25
  0:00:20;datalink;message;MSG2,UAVOPS,NORM,Update LL track,40
  0:00:35;datalink;forceack;MSG1
  0:01:00;datalink;clear;*
  ```

- Automatically logs `datalink_receive`, `datalink_ack` (with response time), `datalink_miss`, `datalink_drop`, and `datalink_clear`. Overdue feedback flashes when time-to-impact expires, enabling researchers to correlate message density against NASA-TLX/RSME scores in complex crew simulations.

### Energy & G-Envelope Implementation Status

- Added `plugins/energymanager.py`, which sequences high-G events (name, target G, duration), tracks cumulative G-seconds, and decrements an energy reserve to simulate pilot fatigue during high-performance sorties. Scenario commands:
  - `energymanager;event;ENGAGE,5.5,35,5` (optional fourth field delays the start by 5 s so crews can rehearse ramps before they hit)
  - `energymanager;warning;5.0,4` (set G-onset warning threshold and lead time)
  - `energymanager;overg;6.3`
  - `energymanager;energy;85`
- The widget now includes a predictive G-meter that plots the warning threshold (`W`), structural limit (`L`), and the upcoming/active target (`T`). When an event whose `target_g` exceeds the configured warning threshold enters the lead window, the plugin emits `g_onset_warning` and highlights the gauge so pilots can brief the pull before it begins.
- Logged metrics cover the additional behaviors: `energy_event_schedule` now includes the queued delay, `energy_warning_config` records threshold changes for provenance, and `g_onset_warning` timestamps each scripted ramp alert alongside the existing `energy_event_start`, `energy_event_complete`, `energy_overg`, and `energy_alert` series.

### Weapons Inventory & Loadout Implementation Status

- Added `plugins/weaponsinventory.py`, which keeps a running tally of missiles, bombs, and expendables per weapon type. Scenario commands:
  - `weaponsinventory;load;AIM9,4` – initialises the loadout with the specified capacity (also used to reset a store mid-run).
  - `weaponsinventory;expend;AIM9,1` – decrements the remaining count, emitting `weapon_expended` (with remaining rounds) and `weapon_empty` when a store hits zero.
  - `weaponsinventory;reload;AIM9,2` – tops up the selected store without exceeding its configured capacity; omit the amount to backfill to 100%.
- The widget lists each weapon as `NAME | remaining/capacity` and flashes overdue feedback when any store drops below the configured `lowwarnratio` (default 25%). Use this to cue threat/crew coordination scripts (e.g., “switch to FOX-3 only”).

### Emergency Stack & Failure Cascades Implementation Status

- Added `plugins/emergencystack.py`, which lists cascading failures plus step-by-step checklists so pilots can drill “hydraulic pressure low” or “GEN BUS OFF” sequences during heavy workload. Scenario commands:
  - `emergencystack;trigger;HYD1,HYD PRESS LOW,Switch pumps|Check breakers|Monitor temps`
  - `emergencystack;stepdone;HYD1,0`
  - `emergencystack;resolve;HYD1`
- Metrics (`emergency_trigger`, `emergency_step`, `emergency_resolve`) let researchers quantify compliance time and residual risk, while overdue cues flash until every emergency is resolved or cleared.

### Threat Prioritisation & Weapons Timeline Implementation Status

- Added `plugins/threatboard.py`, which lists each airborne threat with its sector, range, weapon hint, and time-to-impact. Scenario commands:
  - `threatboard;spawn;TH1,035,14,R73,45`
  - `threatboard;engage;TH1,FOX3`
  - `threatboard;reprioritize;TH1,010,10`
  - `threatboard;resolve;TH1,SPLASH`
  - `threatboard;countermeasure;chaff,2` (deploy two rounds of the named expendable; `flare` is also supported)
- The widget now reserves a footer row for expendable stocks (`Chaff x/x | Flare y/y`), and the plugin logs `countermeasure_deploy`, `countermeasure_empty`, and `countermeasure_low` so mission directors can correlate threat pressure with remaining defensive options. Metrics emitted (`threat_spawn`, `threat_engage`, `threat_resolve`, `threat_overdue`, `threat_drop`) still allow researchers to correlate FOX timing with workload measures, while the countermeasure traces expose how often crews resort to chaff/flare in QRA-style drills.

### Cockpit Audio Warnings Implementation Status

- Added `plugins/audioalerts.py`, an invisible helper that plays WAV cues when scenario commands fire. Typical flow:
  - `audioalerts;register;overg,includes/sounds/overg.wav`
  - `audioalerts;play;overg`
  - `audioalerts;stopcue;overg`
  - `audioalerts;volume;0.75` (sets default playback volume for all cues)
- The plugin caches registered files, degrades gracefully if `pyglet`/audio hardware are missing, and logs `audio_register`, `audio_play`, `audio_stop`, `audio_volume`, and `audio_error` events so researchers can align auditory prompts with workload spikes. Pair this with Energy Manager or Threat Board rules to mimic ALR/voice callouts without hardcoding audio playback in every plugin.

### Automation Hooks Implementation Status

- Added `plugins/automationhooks.py`, which provides a central place to flip other modules between manual and auto modes. Scenario rule syntax:
  - `automationhooks;rule;missiondirector,mission_alert,0,AUTO`
  - `automationhooks;enable;1`
  - `automationhooks;disable;1`
- Each rule logs `automation_rule` for traceability; when enabled, the plugin can be extended to bind thresholds to key metrics (e.g., autopiloting Mission Director when Sense-and-Avoid overdue alarms accumulate).

### Failure Injection Module

- Added `plugins/failureinjector.py`, which schedules downstream plugin calls at future times, enabling automated cascade drills without hardcoding timestamps. Example:
  - `failureinjector;schedule;emergencystack,trigger,HYD1|HYD PRESS LOW|Switch pumps|Check breakers|Monitor temps,40`
  - `failureinjector;schedule;physiooverlay,apply,#000000AA|8,40`
  - `failureinjector;schedule;emergencystack,resolve,HYD1,80`
- The injector calls the target plugin’s method when the delay expires and emits `failure_schedule`, `failure_execute`, and `failure_error` metrics so analysts can validate automation logic.

## 3. Use Case 2 – High-Performance Aircraft Crews

Fighter and aerobatic pilots juggle extreme G-management, rapid sensor/weapon reconfiguration, and threat triage while coping with physiological load ([Cognitive Workload Analysis of Fighter Aircraft Pilots](https://www.researchgate.net/publication/339905636_Cognitive_Workload_Analysis_of_Fighter_Aircraft_Pilots_in_Flight_Simulator_Environment); [Frontiers review on MATB & pilot workload](https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2024.1408242/full)). To reflect that:

| Module | Goal | Implementation Notes |
| --- | --- | --- |
| **Energy & G-Envelope Manager** | Enforce coordinated G-onset schedules, fuel/energy balance, and heat management. | Plugin visualises energy-maneuverability diagrams; joystick input or keyboard commands select bank/pitch rates. Over-G events trigger penalties and overdue alarms. |
| **Threat Prioritisation & Weapons Timeline** | Train rapid reprioritisation of radar/IRS threats, weapon pairing, and “Fox” timelines. | Implemented via `plugins/threatboard.py`, which displays sector, range, weapon hint, and time-to-impact so operators can call FOX within deadlines. |
| **Emergency Stack & Failure Cascades** | Drill hydraulic/electrical failures during high workload. | Scenario engine injects failure events that pause other tasks until a checklist widget (HTML instructions plugin) is satisfied. Track compliance time and residual risk. |
| **Physiological Stress Overlays** | Combine MATB load with hypoxia or high-G cues (e.g., blurred widgets, delayed inputs). | Use scenario parameters to degrade widget brightness or inject lag to emulate tunnel vision; pair with `labstreaminglayer` to tag when overlays are active for neuro/biometric research. |

### HPA Reference Scenario

- Added `includes/scenarios/hpa_overlay.txt`, a three-minute sortie that runs Energy Manager, Threat Board, Datalink, Physio Monitor, Physio Overlay, Emergency Stack, Failure Injector, and the legacy MATB tasks. It schedules a BFM-like sequence (ENTRY/SETUP/ENGAGE/DEFENSIVE/Egress), injects an over-G excursion, launches two threat timelines (`TH1`, `TH2`), and lets the Failure Injector automatically trigger and resolve hydraulic failures while dimming the display.

### Testing Flow

1. **Baseline sortie** – run existing MATB core tasks to capture personal baselines.
2. **Incremental overlays** – add Energy Manager + Threat Board while keeping COMM/RESMAN active.
3. **Stress cocktail** – apply visual occlusion or lag modifiers during a combined event storm to observe breakdown thresholds, mirroring findings that high workload plus physiological stress degrade tracking first.

Instrumentation focus: measure time to correct weapon–threat pairing, number of over-G events, recovery timeline adherence, and ability to maintain COMM accuracy while coping with failure cascades.

## 4. Cross-Cutting Enhancements

1. **Scenario Templates & Difficulty Ramps** – Use the shipped `tools/scenario_templates.py` CLI to emit reproducible “UAS BVLOS,” “HPA overlay,” and automated training scenarios with a single command. Difficulty (1–10) now scales event spacing, deadlines, and failure rate through `DifficultyProfile`, so labs can hand out level-tagged workloads that map to NASA‑TLX/HRV expectations without editing raw scenario text.
2. **Automation & Solver Hooks** – Extend plugin parameters to expose per-task automation states (e.g., `automaticsolver=True` for autopilot hold, or AI radio assistance) so experiments can toggle mixed-initiative strategies.
3. **Performance Analytics** – Expand `core/logger.py` to summarise mission-level KPIs (mission success %, violation counts) immediately after each scenario and optionally publish over LSL for synchronising with EEG/fNIRS streams.
4. **Human–Machine Interface Fit** – Document joystick and HOTAS bindings for the new plugins (axis reversal already supported in `track` plugin). For UAS payload work, allow mouse + keyboard fallback to keep the software accessible.

## 4.1 Acute HRV Workload Feature

Recent pilot studies show that heart-rate-variability (HRV) indices react fast enough to track workload spikes during flight segments. Increased sympathetic dominance (rising LF power, LF/HF ratio) plus depressed parasympathetic markers (falling RMSSD) aligned with high mental demands in an A320 traffic-pattern experiment, while SDNN captured global variability shifts ([Frontiers Neuroergonomics 2025](https://www.frontiersin.org/journals/neuroergonomics/articles/10.3389/fnrgo.2025.1672492/pdf)). A systematic review focused on pilots found RMSSD, SDNN, LF, HF, LF/HF, and pNN50 to be the most frequently reported acute markers in MATB-style paradigms when paired with NASA-TLX or RSME scores ([Detecting and Predicting Pilot Mental Workload Using HRV](https://pmc.ncbi.nlm.nih.gov/articles/PMC11207491/)).

### Feature Goals

1. Stream ECG-derived R–R intervals into OpenMATB in real time (preferred: `labstreaminglayer` plugin) and compute metrics on rolling windows (e.g., 30 s, 60 s).
2. Surface a compact workload bar that combines z-scored RMSSD (parasympathetic), LF/HF (sympathetic balance), and SDNN (overall variability). Highlight “acute” shifts when consecutive windows breach configurable deltas (e.g., RMSSD drop >15% from personal baseline).
3. Log per-window metrics to `performance` entries so HRV signatures can be replayed alongside MATB task outcomes.

### Implementation Sketch

| Component | Notes |
| --- | --- |
| `plugins/physiomonitor.py` | Derive from `AbstractPlugin`. Accept stream metadata (`lsl_stream`, `window_seconds`, `baseline_seconds`). Maintain a deque of NN intervals, compute time-domain (RMSSD, SDNN, pNN50) and frequency-domain metrics (LF, HF, LF/HF) using Welch or Lomb–Scargle. |
| Visualization | Use stacked spark-lines + gauge: RMSSD line (green), LF/HF bar (red if > threshold), textual SDNN. Reuse `taskfeedback` to flash when thresholds exceed “acute” levels. |
| Baseline calibration | At scenario start, collect `baseline_seconds` of data while workload is low; store means to normalise subsequent z-scores. |
| Alerts & Logging | When `rmssd_delta < -delta_rmssd` or `lfhf_delta > delta_lfhf`, emit `performance,hrv,acute_event=1` rows. Provide optional hook to pause or annotate other tasks. |

### Display/Analysis Suggestions

- Overlay HRV panel above Mission Director or Energy Manager widgets so trainees see physiological consequences alongside task load.
- Offer “HRV trend” timeline in debrief: aggregate window metrics, mark MATB events (e.g., COMM prompt) to spot causality.
- Allow export of per-window metrics via CSV or LSL for external analytics (EEG co-analysis, adaptive automation research).

This modular approach keeps acquisition (via LSL) decoupled from visualisation, while aligning with validated HRV markers for acute workload detection.

### 4.2 Physiological Overlays & Polar RR Link

- Added `plugins/physiooverlay.py`, which can tint the entire display (e.g., tunnel vision, high-G blackout) for scripted durations. Scenario example: `physiooverlay;apply;#000000AA,8`.
- Added `plugins/polarrlink.py`, an optional bridge that listens to a Polar H10 belt (via the official Polar BLE SDK characteristics) and emits raw RR intervals onto an LSL stream. This plugin relies on Polar’s published SDK that exposes live RR in milliseconds over Bluetooth ([Polar SDK release](https://www.polar.com/en/about_polar/press_room/polar_releases_polar_sdk_and_team_pro_api_allowing_developers_to_tap_into_its_proprietary_heart_rate); [Polar research tools](https://www.polar.com/en/science/research-tools/)). Configure it with the device’s MAC/UUID: `polarrlink;set;deviceid,XX:XX:XX:XX:XX:XX`, then `polarrlink;start`. The feature is optional—if `bleak` or an H10 sensor are unavailable, the plugin simply warns and leaves the existing Physio Monitor untouched.

### 4.3 Scenario Template CLI

- `tools/scenario_templates.py` now exposes three templates: `uas_bvlos`, `hpa_overlay`, and `training`. All accept `--duration`, `--difficulty` (1–10), and `--output`, letting scenario designers materialise level-tagged drills directly under `includes/scenarios/` without copying boilerplate.
- Difficulty is enforced through `DifficultyProfile.from_level()`, which binds event spacing, deadline multipliers, concurrency caps, and failure injection rate so that level numbers translate to repeatable workload bands. The generated files annotate those parameters at the top for audit.
- The UAS and HPA templates inject plugin start/stop rows (Mission Director, Sense-and-Avoid, Payload Manager, Datalink, Physio Monitor/Overlay, Threat Board, Emergency Stack, Failure Injector, Composite Score) plus Polar link hooks, keeping instrumentation consistent with the metrics catalog.
- The new `training` template scaffolds a seven-minute automated familiarisation block that sequences TRACK → SYSMON → COMM → RESMAN → combined phases, matching the USAARL learning-control guidance and the pending `autotraining` plugin spec in §11.2.
- Examples:

  ```bash
  python tools/scenario_templates.py --template uas_bvlos --difficulty 6 --duration 480 --output includes/scenarios/uas_lvl6.txt
  python tools/scenario_templates.py --template hpa_overlay --difficulty 8 --duration 240 --output includes/scenarios/hpa_lvl8.txt
  python tools/scenario_templates.py --template training --duration 420 --output includes/scenarios/autotraining_lvl3.txt
  ```

- The emitted scenarios can be fed directly into `scenario_generator.py` for additional stochasticity, or versioned as-is to provide deterministic regression fixtures for the CI suite described in §11.6.

### 4.4 Mission-Level Performance Summary & Session Outputs

- `core/performance_summary.py` introduces `PerformanceAggregator`, the canonical sink for every `log_performance` event. It normalises module names/metric keys, tracks numeric vs categorical payloads, and emits derived KPIs for Mission Director, Sense-and-Avoid, Payload Manager, Datalink, Threat Board, and Energy Manager (completion/resolution/over-bandwidth/over-G rates). The contract mirrors the metric tables in §8 so downstream analytics always receive the same fields.
- At run teardown the logger calls `export()` and `export_markdown()` to write `summary.json` and `summary.md` inside each `sessions/user_<id>/<date>/session_*` folder, alongside the scenario/config snapshots described in §11.5–11.7. Both files include metadata (scenario ID, participant info, git hash), scenario duration, derived KPIs, and raw counts, simplifying external ingestion (e.g., lab notebooks, LIMS uploads).
- Researchers can regenerate the summaries offline by replaying log CSVs and piping the events back into `PerformanceAggregator.record()`; the module is pure-Python and deterministic, making it suitable for CI assertions and airworthiness audits.
- `tests/test_performance_summary.py` guards this pipeline: it loads the module dynamically, exercises mixed numeric/categorical aggregation, validates domain KPIs, and ensures Markdown exports render the derived/ raw metric tables the docs promise. Add new metrics/tests in lockstep to keep the documentation, aggregator, and regression suite synchronised.
- Recommended workflow: (1) ensure every plugin emits meaningful `performance,<plugin>,<metric>` rows, (2) run `pytest tests/test_performance_summary.py` plus the broader regression suite, (3) verify the resulting `summary.md` links back to the scenario hash before distributing data outside the lab.

## 5. Step-by-Step Approach

| Phase | Activities | Deliverables |
| --- | --- | --- |
| **1. Baseline & Instrumentation** | Profile existing tasks, confirm logging formats, add KPI summaries. | Benchmark scenarios + logging spec. |
| **2. UAS Module Build** | Implement Mission Director + Sense-and-Avoid plugins, author starter scenarios, add metrics. | `missiondirector.py`, `senseandavoid.py`, `includes/scenarios/uas_basic.txt`. |
| **3. Payload & Datalink Iteration** | Layer payload manager + datalink task, update instructions and questionnaires. | New plugin classes, updated instructions pack. |
| **4. HPA Module Build** | Deliver Energy/G module and Threat Board, script emergency overlays. | `energy_manager.py`, `threatboard.py`, stress overlay utilities. |
| **5. Validation & Research Packaging** | Run pilot studies, tune difficulty, document reproducible setups, publish README/CHANGELOG updates. | Validation report, updated docs, tagged release. |

## 6. Immediate Next Steps

1. **Decide plugin order** – Confirm whether UAS or HPA modules land first so we can branch scenarios accordingly.
2. **Define metrics** – Finalise KPI list (e.g., “geofence breach seconds,” “over-G frequency”) before coding so logging contracts stay stable.
3. **Prototype UI wireframes** – Rough out widget layouts for Mission Director, Sense-and-Avoid, and Energy Manager to surface any container limitations early.
4. **Plan physiological overlays** – If hypoxia/high-G effects are required, align with hardware (e.g., dimming filters, input lag) so scenario designers can flip them via config only.

This plan keeps documentation centralised, ties new features to existing extension seams, and aligns with published research so the new modules remain defensible for both experimental and training communities. Implementation credit: **Dr Diego Malpica, Aerospace Medicine**.

## 7. Military Implementation Roadmap & Reliability Requirements

### 7.1 Alignment with Military MATB Variants

- **Reference platforms**:
  - The recent comprehensive review of MATB for military aircrew assessment highlights its psychometric robustness (construct validity, internal consistency, test–retest reliability) and sensitivity to training effects when standardised protocols are followed ([Multi-Attribute Task Battery for Military Aircrew Assessment](research/Multi Attribute Task Battery for Military Aircrew Assessment A Comprehensive Research Report.md)).
  - USAARL MATB v2.5 and AF-MATB add pre-validated demand levels, script-generation tools, automated training, adaptive automation, and detailed performance logs ([USAARL MATB – Recent Developments](research/The United States Army Aeromedical Research Laboratory Multi-Attribute Task Battery- Recent Developments.md); [AF-MATB adaptation](research/THE USAF ADAPTATION OF THE MAT-B FOR THE ASSESSMENT OF HUMAN OPERATOR WORKLOAD AND STRATEGIC BEHAVIOR.md)).
  - Cognitive-control and biosignal work (HRV, EDA, pupil) using MATB-II shows that physiological signals can distinguish expertise and control levels if task difficulty and confounders are tightly controlled ([MATB-II cognitive control and biosignals](research/Feedback on the Use of Matb-Ii Task for Modeling of Cognitive Control Levels Through PsychoPhysiological Biosignals.md)).
- **Implications for OpenMATB**:
  - OpenMATB must provide: (1) reproducible demand levels, (2) standardised training and familiarisation, (3) integrated subjective scales, and (4) composite multitasking scores that can generalise to higher-fidelity simulators.

### 7.2 Software, Hardware, and Data Requirements

- **Software stack**:
  - **Python environment**: Pin Python and dependency versions (e.g., via `requirements.txt` and a lockfile) and require code to pass `ruff`, `black`, `isort`, `mypy` (strict), and `bandit` before release builds.
  - **Platform**: Support current 64-bit Windows systems for operational use (as in AF-MATB), with testing on at least one Linux environment for research clusters. Require a minimum 60 Hz monitor at 1920×1080 or higher resolution for timing and layout stability.
  - **Timing & logging**: Use `time.monotonic()` for durations, and keep all scenario timing in seconds with explicit conversions. Confirm log timestamps and scenario times are monotonic and synchronised with LSL streams.
- **Hardware assumptions**:
  - **Primary controls**: USB joystick/HOTAS recommended for tracking and HPA modules; keyboard/mouse fallback supported but documented as a secondary modality.
  - **Physiological sensors**: Polar H10 (via `polarrlink.py`) or equivalent ECG/HRV acquisition; EEG/fNIRS/EDA/pupil systems optional but supported via LSL. No physiological data is ever simulated; plugins only consume real sensor streams.
  - **Audio**: Headphones or dedicated speakers for COMM/datalink clarity in shared lab environments.
- **Data management**:
  - Require per-run log folders containing scenario file snapshot, configuration (`config.ini`), plugin parameter dumps, and raw logs. Encourage hashed scenario IDs so that aircrew assessments can be repeated or audited later.

### 7.3 Experimental Protocol Requirements

- **Standardised training and learning control**:
  - Adopt a USAARL-style automated training script (~7 min) that walks subjects through each subtask, input device, and scoring rule and culminates in a short combined run. Provide at least 2–3 practice runs before any data-collection session to control learning effects (as recommended in the aircrew assessment review).
  - Maintain a library of **pre-validated difficulty levels** (e.g., 10 levels as in USAARL MATB) per module (SYSMon, TRACK, COMM, RESMAN, and new UAS/HPA tasks) so scenarios can be described in terms of difficulty indices rather than only event rates.
- **Subjective and objective measures**:
  - Integrate standard scales—NASA‑TLX, RSME, situation awareness and trust scales—as optional questionnaires before/after MATB runs, with their timing stored in logs and linked to scenario IDs.
  - Require physiological sessions (HRV, EDA, pupil, etc.) to log raw data at known sampling rates, with preprocessing pipelines (e.g., Pan–Tompkins for ECG, standard LF/HF bands) documented and versioned outside OpenMATB.
- **Session protocol**:
  - Specify minimum rest intervals between blocks, environmental conditions (lighting, temperature, noise), and exclusion criteria (sleep, substance use) in study documentation, mirroring protocols used in MATB‑II biosignal and military workload studies.

### 7.4 Development Iteration Plan for Military Reliability

- **Iteration 1 – Baseline parity with USAARL/AF-MATB**:
  - Implement an **Automated Training plugin/scenario** that reads a scripted instruction file and orchestrates single-subtask then multi-subtask runs, logging completion and comprehension checks.
  - Introduce **difficulty presets** for each core and new plugin (e.g., `difficulty=1–10`) that internally map to event rates, failure probabilities, and target thresholds, with documentation tying levels to observed NASA‑TLX/HRV ranges in pilot data.
  - Extend `tools/scenario_templates.py` and/or `scenario_generator.py` to generate scenarios “by workload band” (e.g., 60–90 IMPRINT-equivalent units), even if initially approximated using event density heuristics.
- **Iteration 2 – Adaptive automation and composite scoring**:
  - Build on `automationhooks.py` and `failureinjector.py` to create **adaptive automation policies** driven by observed workload and performance (e.g., if SAA overdue events and HRV acute flags co-occur, temporarily offload tracking or resman subtasks).
  - Implement a **multitasking efficiency score** similar to USAARL’s composite metric: combine normalised subtask performance, task load history, and automation usage into a single index per run for easier comparison across scenarios and simulators.
  - Validate composite scores and automation policies on small cohorts, comparing against subjective scales and operational benchmarks from the military MATB literature.
- **Iteration 3 – Validation, QA, and release discipline**:
  - Establish a **regression test suite**: a fixed set of scenarios (UAS basic/BVLOS, HPA overlay, baseline MATB) that run automatically in CI to verify timing, event ordering, and key log metrics whenever the code changes.
  - Add **scenario and config versioning** in logs (scenario hash, plugin version map, config checksum) to guarantee that any published result can be re-run with identical conditions.
  - Formalise **release criteria** for “research‑ready” and “assessment‑ready” builds: zero linter errors, deterministic outputs for canned scenarios, documented hardware assumptions, and a changelog entry summarising any behaviour that could affect experimental comparability.

Together, these requirements and iterations aim to move OpenMATB from a flexible research platform toward a military-grade assessment tool: reproducible workloads, traceable configurations, validated metrics, and explicit support for adaptive automation and physiological monitoring, all curated under the leadership of **Dr Diego Malpica, Aerospace Medicine**.

## 8. Scientifically Validated Metrics Catalog

This section consolidates the metrics identified from systematic reviews and military MATB research. Metrics are organised by domain (UAS vs HPA) and measurement modality (performance, physiological, subjective). All metrics align with published findings from USAARL MATB, AF-MATB, NASA MATB-II, and peer-reviewed workload studies.

### 8.1 Core Performance Metrics (Both Modules)

| Metric | Unit | Description | Source/Validation |
| --- | --- | --- | --- |
| **Tracking RMSD** | pixels or mm | Root mean square deviation of cursor from target centre; primary manual control index | Comstock & Arnegard 1992; Parasuraman et al. 1993; test–retest r > 0.80 |
| **System Monitoring Detection Rate** | % | Proportion of abnormal events (lights, gauges) correctly detected within timeout | MATB-II User Guide; Cronbach α 0.70–0.85 |
| **System Monitoring Response Time** | ms | Latency from event onset to correct response | Molloy & Parasuraman 1996 |
| **System Monitoring False Alarms** | count | Incorrect responses to non-events; vigilance decrement marker | Parasuraman et al. 1993 |
| **Communications Accuracy** | % | Proportion of correctly tuned radio frequencies following relevant call signs | Santiago-Espada et al. 2011 |
| **Communications Response Time** | ms | Latency from message end to validated frequency change | MATB-II standard |
| **Resource Management Deviation** | units | RMS deviation from target fuel level (2500 units) in tanks A and B | Comstock & Arnegard 1992 |
| **Resource Management Time-in-Range** | % | Proportion of time fuel level within ±500 units of target | Santiago-Espada et al. 2011 |
| **Multitasking Efficiency Score** | composite | Normalised weighted sum of subtask scores adjusted for task load history; USAARL composite model | Vogl et al. 2024; McCurry et al. (in press) |
| **Baud Rate (Human Output)** | bps | Information throughput per Shannon's theory; B_H(i) = RR(i) × B(i) | Liu & Nam 2018 |

### 8.2 UAS-Specific Performance Metrics

| Metric | Unit | Description | Validation Context |
| --- | --- | --- | --- |
| **Mission Assignment Latency** | s | Time from UAV assignment event to operator acknowledgement | Mission Director plugin; aligns with FAA UAS KSA study |
| **Conflict Resolution Time** | s | Time from sense-and-avoid conflict spawn to resolution action | SAA plugin; FAA detect-and-avoid timing guidance |
| **Geofence Breach Duration** | s | Cumulative time any UAV position violates no-fly polygon | BVLOS corridor risk models (Medellín study) |
| **Payload Bandwidth Utilisation** | % | Ratio of active sensor Mbps to total link capacity | Payload Manager plugin |
| **Payload Energy Depletion Events** | count | Instances where sensor pod reaches 0% energy | Resource constraint simulation |
| **Datalink Acknowledgement Rate** | % | Proportion of CPDLC-style messages acknowledged before timeout | NASA TM–2020-0010384 CPDLC workload findings |
| **Datalink Response Latency** | ms | Time from message display to ENTER acknowledgement | Datalink plugin |
| **Lost-Link Recovery Time** | s | Duration from radio-fail event to scripted recovery completion | Failure Injector plugin |
| **Multi-UAV Switching Frequency** | count/min | Rate of attention shifts between UAV rows in Mission Director | Multi-ship workload research |

### 8.3 High-Performance Aircraft (HPA) Specific Metrics

| Metric | Unit | Description | Validation Context |
| --- | --- | --- | --- |
| **Over-G Event Count** | count | Instances where G exceeds aircraft or physiological limit | Energy Manager plugin; fighter workload studies |
| **Cumulative G-Seconds** | G·s | Integral of G-load over time; fatigue proxy | Frontiers review on pilot workload |
| **Energy Reserve Remaining** | % | Simulated pilot energy after G-onset sequence | Energy Manager plugin |
| **Threat Engagement Latency** | s | Time from threat spawn to FOX call | Threat Board plugin |
| **Threat Prioritisation Accuracy** | % | Proportion of highest-TTI threats engaged first | Tactical decision-making research |
| **Weapons–Threat Pairing Errors** | count | Mismatches between selected weapon and threat type | Threat Board plugin |
| **Emergency Checklist Compliance Time** | s | Duration from failure trigger to all checklist steps complete | Emergency Stack plugin |
| **Residual Risk Score** | index | Unresolved emergency steps × severity weight | Emergency Stack plugin |
| **Visual Occlusion Duration** | s | Cumulative time physio overlay dims display (tunnel vision, blackout) | Physio Overlay plugin |

### 8.4 Physiological Metrics (Cross-Cutting)

Based on the systematic review of HRV for pilot MWL (Wang, Houghton & Majumdar 2024) and the Frontiers Neuroergonomics 2025 A320 study, the following indices are recommended:

| Metric | Unit | Domain | Description | MWL Association |
| --- | --- | --- | --- | --- |
| **HR** | bpm | Time | Mean heart rate over window | ↑ with high MWL |
| **SDNN** | ms | Time | Standard deviation of NN intervals; overall ANS variability | ↓ with high MWL |
| **RMSSD** | ms | Time | Root mean square of successive differences; parasympathetic marker | ↓ with high MWL |
| **pNN50** | % | Time | Percentage of successive NN intervals differing >50 ms | ↓ with high MWL |
| **LF Power** | ms² | Frequency | Low-frequency band (0.04–0.15 Hz); mixed sympathetic/parasympathetic | Variable |
| **HF Power** | ms² | Frequency | High-frequency band (0.15–0.40 Hz); parasympathetic | ↓ with high MWL |
| **LF/HF Ratio** | ratio | Frequency | Sympathovagal balance index | ↑ with high MWL |
| **Acute HRV Delta** | z-score | Derived | Window-to-baseline change in RMSSD or LF/HF exceeding threshold | Acute workload spike flag |
| **PFC Activation (fNIRS)** | β-coeff | Neuroimaging | Oxygenated haemoglobin change in prefrontal cortex | ↑ with high MWL (Li et al. 2022) |
| **Pupil Dilation** | mm or index | Ocular | Mean pupil diameter normalised to baseline | ↑ with high MWL |
| **EDA Sympathetic Index** | index | Electrodermal | Time-frequency power in 0.08–0.24 Hz band | ↑ with high MWL (Daviaux et al. 2019) |

### 8.5 Subjective Metrics

| Scale | Dimensions | Administration | Notes |
| --- | --- | --- | --- |
| **NASA-TLX** | Mental Demand, Physical Demand, Temporal Demand, Performance, Effort, Frustration | Post-block or continuous (RSME variant) | Most validated; weighted or raw scores |
| **RSME** | Single dimension (0–150) | During or post-block | Simpler; sensitive to gradual MWL changes |
| **SART** | Situational Awareness (Demand, Supply, Understanding) | Post-block | Recommended for UAS supervisory control |
| **Trust Checklist / TAST** | Trust in Automated Systems | Post-block | Required for adaptive automation studies |
| **Karolinska Sleepiness Scale (KSS)** | Fatigue (1–9) | Pre/post session | Fatigue confound control |

---

## 9. UAS Module Implementation Plan

### 9.1 Current Implementation Status

| Component | Status | Plugin File | Key Scenario Commands |
| --- | --- | --- | --- |
| Mission Director | ✅ Implemented | `plugins/missiondirector.py` | `assign`, `complete`, `automation`, `conflict`, `clearconflict`, `endurance`, `handover` |
| Sense-and-Avoid | ✅ Implemented | `plugins/senseandavoid.py` | `spawn`, `resolve`, `clear`, `thresholds`, `geofence`, `position` |
| Payload Manager | ✅ Implemented | `plugins/payloadmanager.py` | `activate`, `priority`, `standby`, `recharge`, `capacity` |
| Datalink & CPDLC | ✅ Implemented | `plugins/datalink.py` | `message`, `forceack`, `clear` |
| Physio Monitor | ✅ Implemented | `plugins/physiomonitor.py` | LSL stream, HRV computation, acute alerts |
| Polar RR Link | ✅ Implemented | `plugins/polarrlink.py` | `set`, `start` (optional H10 bridge) |
| Failure Injector | ✅ Implemented | `plugins/failureinjector.py` | `schedule` |
| Automation Hooks | ✅ Implemented | `plugins/automationhooks.py` | `rule`, `enable`, `disable` |

### 9.2 Pending UAS Enhancements

| Enhancement | Priority | Rationale | Implementation Notes |
| --- | --- | --- | --- |
| **Voice Synthesis for Datalink** | Low | Auditory channel reduces visual overload | Use TTS for high-priority messages; configurable via `datalink;voice;True` |

### 9.3 UAS Metrics Logging Requirements

All UAS plugins must emit the following log entry types to enable post-run analysis:

```text
# Mission Director
performance,missiondirector,mission_assign,uav=uav1,mission=surveillance,duration=300
performance,missiondirector,mission_mode,uav=uav1,mode=auto
performance,missiondirector,mission_alert,uav=uav1,alert=geofence
performance,missiondirector,mission_complete,uav=uav1,elapsed=298
performance,missiondirector,mission_endurance_set,uav=uav1,duration_s=2700,threshold_s=600
performance,missiondirector,mission_endurance_low,uav=uav1,remaining_s=540
performance,missiondirector,mission_handover_initiate,uav=uav1,target=GCS-Bravo
performance,missiondirector,mission_handover_complete,uav=uav1,target=GCS-Bravo

# Sense-and-Avoid
performance,senseandavoid,saa_spawn,id=INTR1,bearing=090,range=2.0,alt_delta=300,tti=45
performance,senseandavoid,saa_resolve,id=INTR1,resolution=turn_right_20,response_time_ms=3200
performance,senseandavoid,saa_overdue,id=INTR1
performance,senseandavoid,saa_clear,id=INTR1
performance,senseandavoid,geofence_breach,uav=UAV1,x=0.92,y=0.88
performance,senseandavoid,geofence_recover,uav=UAV1,x=0.45,y=0.35

# Payload Manager
performance,payloadmanager,payload_activate,pod=CamA,target=Alpha,bandwidth=12
performance,payloadmanager,payload_overbandwidth,total_mbps=65,capacity=60
performance,payloadmanager,payload_depleted,pod=CamA

# Datalink
performance,datalink,datalink_receive,id=MSG1,channel=ATC,priority=PRIO
performance,datalink,datalink_ack,id=MSG1,response_time_ms=4500
performance,datalink,datalink_miss,id=MSG1
```

---

## 10. High-Performance Aircraft (HPA) Module Implementation Plan

### 10.1 Current Implementation Status

| Component | Status | Plugin File | Key Scenario Commands |
| --- | --- | --- | --- |
| Energy & G-Envelope Manager | ✅ Implemented | `plugins/energymanager.py` | `event`, `overg`, `energy`, `warning` |
| Weapons Inventory & Loadout | ✅ Implemented | `plugins/weaponsinventory.py` | `load`, `expend`, `reload` |
| Threat Board | ✅ Implemented | `plugins/threatboard.py` | `spawn`, `engage`, `reprioritize`, `resolve`, `countermeasure` |
| Weather/Visibility Layer | ✅ Implemented | `plugins/weatheroverlay.py` | `set`, `clear` |
| Cockpit Audio Warnings | ✅ Implemented | `plugins/audioalerts.py` | `register`, `play`, `stopcue`, `volume` |
| Emergency Stack | ✅ Implemented | `plugins/emergencystack.py` | `trigger`, `stepdone`, `resolve` |
| Physio Overlay | ✅ Implemented | `plugins/physiooverlay.py` | `apply` (tint, duration) |
| Automation Hooks | ✅ Implemented | `plugins/automationhooks.py` | Shared with UAS |
| Failure Injector | ✅ Implemented | `plugins/failureinjector.py` | Shared with UAS |

### 10.2 Pending HPA Enhancements

| Enhancement | Priority | Rationale | Implementation Notes |
| --- | --- | --- | --- |
| **Helmet-Mounted Display (HMD) Mode** | Low | Simulate off-boresight cueing | Overlay target designator on tracking task; scenario command `hmd;cue;TH1` |

### 10.3 HPA Metrics Logging Requirements

```text
# Energy Manager
performance,energymanager,energy_event_schedule,name=ENGAGE,target_g=5.5,duration=35,delay=5
performance,energymanager,energy_event_start,name=ENGAGE
performance,energymanager,energy_event_complete,name=ENGAGE,cumulative_g_seconds=192
performance,energymanager,energy_overg,g=6.3
performance,energymanager,energy_alert,reserve=15
performance,energymanager,energy_warning_config,threshold_g=5.0,lead_s=4.0
performance,energymanager,g_onset_warning,name=ENGAGE,target_g=5.5,lead_s=3.0

# Threat Board
performance,threatboard,threat_spawn,id=TH1,sector=035,range=14,weapon=R73,tti=45
performance,threatboard,threat_engage,id=TH1,weapon=FOX3,latency_ms=2800
performance,threatboard,threat_resolve,id=TH1,outcome=SPLASH
performance,threatboard,threat_overdue,id=TH1
performance,threatboard,threat_drop,id=TH1
performance,threatboard,countermeasure_deploy,type=chaff,count=2,target=TH1
performance,threatboard,countermeasure_low,chaff=1,flare=1

# Weather Overlay
performance,weatheroverlay,weather_set,description=IMC ceiling 800ft
performance,weatheroverlay,weather_clear,description=IMC ceiling 800ft

# Audio Alerts
performance,audioalerts,audio_register,cue=overg,path=includes/sounds/overg.wav
performance,audioalerts,audio_play,cue=overg
performance,audioalerts,audio_volume,value=0.75
performance,audioalerts,audio_error,cue=overg,reason=pyglet_missing

# Weapons Inventory
performance,weaponsinventory,weapon_load,name=AIM9,count=4
performance,weaponsinventory,weapon_expended,name=AIM9,count=1,remaining=3
performance,weaponsinventory,weapon_reload,name=AIM9,count=2,remaining=5
performance,weaponsinventory,weapon_empty,name=AIM9

# Emergency Stack
performance,emergencystack,emergency_trigger,id=HYD1,label=HYD_PRESS_LOW
performance,emergencystack,emergency_step,id=HYD1,step=0,label=Switch_pumps,time_ms=4200
performance,emergencystack,emergency_resolve,id=HYD1,total_time_ms=18500
```

---

## 11. Cross-Cutting Implementation Requirements

### 11.1 Difficulty Presets & IMPRINT Integration

Per USAARL MATB v2.5, each plugin should expose a `difficulty` parameter (1–10) that internally maps to event rates, thresholds, and automation availability. The mapping must be documented so scenarios can be described in terms of difficulty indices rather than raw event counts.

| Difficulty | Event Rate Multiplier | Automation Availability | Expected NASA-TLX Range |
| --- | --- | --- | --- |
| 1–3 | 0.5× baseline | Full auto available | 20–40 |
| 4–6 | 1.0× baseline | Partial auto | 40–60 |
| 7–10 | 1.5–2.0× baseline | Manual only | 60–90 |

The `tools/scenario_templates.py` CLI should accept `--difficulty` to generate scenarios at the specified band.

### 11.2 Automated Training Module

Implement a `plugins/autotraining.py` that:

1. Reads a scripted instruction file (audio + text prompts).
2. Orchestrates single-subtask familiarisation runs (tracking only, SYSMON only, etc.).
3. Culminates in a combined 5-min run.
4. Logs comprehension checks and completion status.
5. Total duration ~7 min, matching USAARL protocol.

### 11.3 Composite Scoring Module

Implement a `plugins/compositescore.py` that:

1. Subscribes to performance events from all active plugins.
2. Computes per-subtask z-scores relative to baseline or population norms.
3. Weights subtasks by task load history (higher weight for periods of high demand).
4. Emits a single `composite_efficiency` metric per run.
5. Optionally factors in automation usage (penalty for excessive auto reliance).

### 11.4 Adaptive Automation Policy Engine

Extend `plugins/automationhooks.py` to:

1. Accept threshold rules based on observed metrics (e.g., `if saa_overdue_count > 2 AND hrv_acute_flag == 1 THEN enable tracking_auto`).
2. Log all automation state changes with triggering metric values.
3. Support manual override by operator (toggle key).

### 11.5 Scenario & Config Versioning

Every log folder must contain:

- `scenario_snapshot.txt` – exact copy of scenario file.
- `config_snapshot.ini` – exact copy of config.ini.
- `plugin_versions.json` – map of plugin name → git commit hash or version string.
- `scenario_hash` – SHA-256 of scenario file for audit.

### 11.6 Regression Test Suite

Establish `tests/regression/` with:

- `test_uas_basic.py` – runs `uas_basic.txt`, asserts key log metrics within expected ranges.
- `test_hpa_overlay.py` – runs `hpa_overlay.txt`, asserts G-event count and threat timing.
- `test_baseline_matb.py` – runs legacy MATB scenario, asserts SYSMON/TRACK/COMM/RESMAN metrics.

CI must execute these on every commit; failures block merge.

### 11.7 User Identification & Session History

- **Configuration**: set the active participant in `config.ini` under `[User]` with numeric `id`, plus optional `name`, `cohort`, and `notes`. The UI banner echoes these fields at runtime.

- **Configuration**: set the active participant in `config.ini` under `[User]` with numeric `id`, plus optional `name`, `cohort`, and `notes`. The UI banner echoes these fields at runtime.
- **Session storage**: every run is saved under `sessions/user_<id>/<YYYY-MM-DD>/session_<id>_<timestamp>/` so longitudinal datasets stay partitioned per subject.
- **Artifacts per user**: the app now maintains `sessions/user_<id>/history.json` (chronological list of runs with scenario labels, hashes, summary paths, and durations) and a global `sessions/users_index.json` registry so labs can query multi-user datasets quickly.
- **Exports**: both `summary.json` and `summary.md` include the user metadata, and file names incorporate the user ID to simplify downstream analysis scripts.

---

## 12. Validation & Reliability Checklist

Before any scenario is declared "assessment-ready", verify:

| Criterion | Method | Threshold |
| --- | --- | --- |
| **Timing Accuracy** | Compare log timestamps to external stopwatch | ≤ 50 ms drift over 10 min |
| **Event Ordering** | Audit log for out-of-order events | 0 violations |
| **Deterministic Output** | Run same scenario twice, compare logs | Identical event sequence |
| **Subjective Scale Integration** | Verify NASA-TLX/RSME logs linked to scenario ID | 100% linkage |
| **Physiological Sync** | Compare LSL timestamps to log timestamps | ≤ 100 ms offset |
| **Practice Effect Control** | 2–3 familiarisation runs before data collection | Documented in protocol |
| **Difficulty Calibration** | Pilot data confirms expected NASA-TLX range | ±10 points of target |

---

## 13. Research-Backed Recommendations

1. **Sample Size**: Target n ≥ 20 for workload studies to achieve power ≥ 0.80 (per Liu & Nam 2018 pilot study guidance).
2. **Session Duration**: 15–30 min for assessment; 45–60 min for training (per MATB-II User Guide).
3. **Rest Intervals**: Minimum 3 min between blocks to allow HRV recovery.
4. **Environmental Controls**: Document lighting (lux), temperature (°C), and ambient noise (dB) in logs.
5. **Exclusion Criteria**: Sleep < 6 h, caffeine within 4 h, energy drinks within 6 h (per Daviaux et al. 2019 protocol).
6. **HRV Window Length**: 5 min for frequency-domain metrics; 30–60 s rolling windows for acute detection (per Task Force 1996 guidelines).
7. **Baseline Calibration**: Collect 5 min resting baseline before first task block for HRV normalisation.

---

## 14. Documentation Alignment Plan

To keep the shipped application, the wiki (`Docs/OpenMATB.wiki`), and this manual in sync, execute the following loop every release:

1. **Baseline Audit (Week 1)**  
   - Review `Home.md`, `How-to-install-OpenMATB.md`, and `The-configuration-file-(config.ini).md` to ensure they reference the `[User]` section, per-user session folders, and the new provenance banner.  
   - Verify that every link under “Basic features” points to current plugin behaviour (compare against `plugins/*.py` commits referenced in `plugin_versions.json`).

2. **Advanced Module Update (Week 2)**  
   - Author new wiki pages for the UAS/HPA plugins (`missiondirector`, `senseandavoid`, `payloadmanager`, `datalink`, `energymanager`, `threatboard`, `emergencystack`, `automationhooks`, `failureinjector`, `physiomonitor`, `polarrlink`, `physiooverlay`).  
   - Cross-link these pages from `Home.md` and `Main-differences-between-the-published-implementations...md`.

3. **Analytics & Export Guidance (Week 3)**  
   - Expand `Sample-script-Replication...md` and `How-to-modify-automatic-performance-computation.md` with instructions on consuming `summary.json`, `summary.md`, and `history.json`.  
   - Add a “Data management” page explaining `sessions/users_index.json`, per-user `history.json`, hotkeys (F6/F7), and integration tips for neurophysiology teams.

4. **Verification & Sign-off (Week 4)**  
   - Run the regression suite plus a documentation lint (check for stale links).  
   - Capture screenshots of the provenance banner and attach them to `Internationalization.md` to confirm translations.  
   - Record outcomes in `Docs/OpenMATB.wiki/How-to-build-a-scenario-file.md` (append “Release QA” section) and log the doc version in `Docs/Manual.md`.

Implementation credit: **Dr Diego Malpica, Aerospace Medicine**.
