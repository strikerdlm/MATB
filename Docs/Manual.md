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
- Added `includes/scenarios/uas_military_ex.txt`, a seven-minute patrol meant for ScanEagle/NightEagle detachments. It boots `platformprofile`, `operatorcapacity`, and `vtolmanager`, spins up three UAV timelines, injects Sense-and-Avoid conflicts plus VTOL transition confirmations, and uses `failureinjector` to drive scripted datalink bursts and geofence violations. The scenario logs `platform_profile_*`, `operator_capacity_*`, and `vtol_*` metrics in the same run so mission summaries can quantify how well crews stayed inside validated workload bands while handling BVLOS traffic.

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

### Helmet-Mounted Display Cueing Implementation Status

- Added `plugins/hmdoverlay.py`, which renders simplified off-boresight cues (label, azimuth, elevation, optional timeout) so experiments can script “look high-right” or “threat 20° low” prompts. Scenario commands:
  - `hmdoverlay;cue;TH1,15,-5,3` – shows TH1 at +15° azimuth, -5° elevation for 3 seconds.
  - `hmdoverlay;cue;LEAD,0,10` – persistent cue (no timeout) until `hmdoverlay;clear;`.
  - `hmdoverlay;clear;` – removes the current cue immediately.
- Metrics logged: `hmd_cue` (with label/angles/duration) and `hmd_clear` so analysts can sync gaze/head movement data with scripted cueing events. The widget defaults to “No HMD cue” when no overlay is active and automatically clears timed prompts when the duration elapses.

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
- Added `includes/scenarios/hpa_qra_ex.txt`, a four-and-a-half-minute Quick Reaction Alert drill that combines `energymanager`, `threatboard`, `weaponsinventory`, `platformprofile`, `datalink`, and `emergencystack`. The sortie walks through ENTRY/SETUP/ENGAGE/DEFENSIVE energy segments, launches sequential TH1–TH3 tracks, forces AIM-9/AIM-120 expenditure decisions, and scripts a hydraulic failure via `failureinjector` so researchers can correlate threat pressure, weapon usage, and emergency compliance times inside one canned scenario.

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
- The new `training` template scaffolds a seven-minute automated familiarisation block that sequences TRACK → SYSMON → COMM → RESMAN → combined phases, matching the USAARL learning-control guidance and the `autotraining` plugin described in §11.2.
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

### 4.5 MUM-T Scenario Ladder (Hybrid Fighter + UAS)

To exercise the full set of fighter and UAS plugins in a single progression, three new scenarios ship under `includes/scenarios/`. They follow the workload ladder recommended in the FAA BVLOS ARC report (2022), NASA’s recent sUAS crew-role guidance (NASA/TM–20250002531), Airbus’s 2024 MUM-T demonstrations, and the swarm workload findings reported by Kostenko et al. (2022, Frontiers in Psychology). Each file scales event density, automation availability, and physiological stressors so labs can step participants from introductory coordination drills to overload conditions without editing raw scenario text.

| Scenario file | Duration | Difficulty | Primary goals | Key plugins / features |
| --- | --- | --- | --- | --- |
| `mumt_ramp_lvl1.txt` | 7 min | 3/10 | Two-UAV launch + fighter support with basic deconfliction | `missiondirector`, `senseandavoid`, `payloadmanager`, `datalink`, `operatorcapacity`, `platformprofile`, `energymanager`, `threatboard`, `weaponsinventory`, `vtolmanager`, `launchrecovery`, `mumtcoordination` |
| `mumt_ramp_lvl2.txt` | 9 min | 6/10 | Tri-ship coordination, VTOL relay, adaptive automation, emergency drills | Level 1 set + `sensorresource`, `targetuncertainty`, `controltransfer`, `automationhooks`, `failureinjector`, `audioalerts`, `hmdoverlay`, `physiooverlay`, `datalink` TTS |
| `mumt_ramp_lvl3.txt` | 12 min | 9/10 | Full-spectrum fighter + UAS teaming with HRV-triggered automation, swarm control, BVLOS sensory loss, UTM restrictions, and flight termination decisions | Level 2 set + `polarrlink`/`physiomonitor` baseline collection, `bvlossensory`, `utmintegration`, `flighttermination`, `swarmformation`, `vtolpower`, `dualtasksensor` |

Implementation notes:

1. **Progressive mission design** – Level 1 mirrors ScanEagle/NightEagle style sorties (USAARL MATB references) by pairing simple launch/recovery with single-threat energy events and a single MUM-T coordination request. Level 2 adds VTOL relay timelines, adaptive automation rules tied to mission alerts, datalink voice synthesis (pyttsx3) for PRIO/CRIT messages, and scripted handovers (`controltransfer`) so teams rehearse NASA’s mixed-role procedures. Level 3 introduces all remaining combat extensions: HRV-driven automation (Durantin et al. 2014 LF/HF model), swarm overrides, BVLOS sensory deprivation, UTM replan drills, flight-termination prompts, VTOL power budgeting, and dual-task sensor training overlaying MATB track performance.
2. **Physiological instrumentation** – Level 3 begins with a two-minute baseline (`polarrlink;start` + `physiomonitor;baseline;start`) before spinning up combat plugins, enabling live RMSSD/LF/HF z-score tracking. Automation hooks export `physiomonitor` metrics so adaptive policies can pause payload tasks or extend deadlines when overload signatures appear.
3. **Scenario hooks** – All files log the newer domain metrics (`control_transfer_*`, `swarm_*`, `vtol_power_*`, `termination_*`, `sensory_cue_*`, etc.) and exercise the voice-enabled datalink path (`datalink;voice;True,PRIO|CRIT`), fulfilling the instrumentation requirements outlined in §§9–14. Researchers can launch the ladder sequentially during familiarisation (Level 1), training (Level 2), and evaluation (Level 3) or select a specific rung via `python openmatb.py --scenario includes/scenarios/mumt_ramp_lvlX.txt`.
4. **Research traceability** – Inline comments in each file cite the supporting sources (FAA BVLOS ARC 2022; NASA/TM–20250002531; Airbus 2024 MUM-T story; Kostenko et al. 2022). This keeps the provenance of workload levels and coordination tactics explicit for IRB packages and military QA audits.

The ladder dovetails with the existing scenario template CLI: pass `--template hpa_overlay` or `uas_bvlos` for legacy cases, then run the MUM-T ramp to measure transfer and dual-task interference under tightly controlled, reference-backed workloads.

### 4.6 2D Visual Conventions for ASCII Panels

The UAS and HPA modules share a small set of cockpit-inspired 2D conventions so that Mission Director, Sense-and-Avoid, Datalink, Threat Board, Energy Manager, VTOL, payload, and swarm panels can be interpreted consistently while preserving MATB-style psychometric validity.

- **Purely 2D, text-only**  
  All task widgets remain flat, textual/ASCII panels (no 3D, no perspective views). Changes described here are presentation-only: they do not alter scenario timing, event logic, scoring rules, or log formats.

- **Progress bars (`████░░░░░`)**  
  All bars are rendered by a shared helper (`AbstractPlugin.format_progress_bar(fraction, length)`), where `fraction` is always clamped to [0, 1]:
  - **Time-to-go / deadlines** (Sense-and-Avoid intruders, Datalink messages, Threat Board contacts, Launch & Recovery phases, Energy Manager events): `fraction = remaining_time / scripted_duration`. A full bar indicates the start of the window; the bar empties as the deadline approaches.
  - **Capacity / reserves** (Payload Manager link Mbps, Sensor Resource link capacity, VTOL Manager battery, VTOL Power reserves, Energy Manager energy reserve): `fraction = current_value / maximum_value`. Bars shrink as capacity is consumed.
  - **Discrete limits** (Swarm manual overrides vs. `maxmanualoverrides`): `fraction = current_count / limit`. Bars make cognitive-load breaches visible at a glance.

- **Sort order / urgency-first lists**  
  - Intruders and threats are ordered by **increasing time-to-impact (TTI)**.  
  - Datalink queues retain scenario order but always show remaining time and a bar per message.  
  - VTOL launch/recovery sequences are ordered by **earliest deadline**.  
  - Where multiple VTOL power profiles are configured (`vtolpower.py`), rows are ordered by **lowest remaining fraction** first.  
  These orderings are visual only; underlying metric keys and timestamps are unchanged.

- **Per-plugin strip formats (examples)**  
  - **VTOL Manager (`vtolmanager.py`)** – `UAV | PHASE | t_phase | Batt% + bar | Power x | Alerts`. Alerts include battery status (NORMAL/WARNING/CRITICAL/EMPTY), pending or overdue transitions, and the latest stability value.  
  - **VTOL Power (`vtolpower.py`)** – `UAV | remaining/capacity | % + bar | Status`. Complements VTOL Manager by focusing purely on energy reserves.  
  - **Launch & Recovery (`launchrecovery.py`)** – `UAV | Phase | Method | TGO | bar`, one row per active catapult/skyhook leg.  
  - **Payload Manager (`payloadmanager.py`)** – one line per sensor with bandwidth, energy %, and an energy bar, plus a final **Total BW** line with a link-capacity bar.  
  - **Sensor Resource (`sensorresource.py`)** – capacity/load header with bar, followed by per-pod bandwidth rows (and per-sensor bars when active).  
  - **Swarm Formation (`swarmformation.py`)** – formation + mode header, a **manual overrides / limit** bar, then AUTO/MANUAL status for each member (manual units listed first).

- **Status colour semantics**  
  - The same aeronautical status levels defined in `core.constants.STATUS_LEVELS` (NORMAL, ADVISORY, CAUTION, WARNING, INOPERATIVE) and their associated palette are reused across plugins.  
  - When **colorblind mode** is enabled in `config.ini` or the Streamlit portal, these colours map to a palette that remains legible without relying on red/green alone; the text content and ordering described above are identical.

These conventions are shared across current and future UAS/HPA/MUM‑T plugins so that participants can transfer visual search strategies without learning a new legend for each task.

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

#### 7.2.1 System Requirements

| Component | Minimum | Recommended | Notes |
|-----------|---------|-------------|-------|
| **Operating System** | Windows 10 64-bit | Windows 10/11 64-bit | Linux supported for research clusters |
| **Python** | 3.10 | 3.11 | 3.12+ untested; pin version via `requirements.txt` |
| **CPU** | Dual-core 2.0 GHz | Quad-core 3.0 GHz+ | HRV processing benefits from multi-core |
| **RAM** | 4 GB | 8 GB+ | 16 GB if running LSL + EEG/fNIRS streams |
| **GPU** | OpenGL 2.1 capable | Dedicated GPU | Integrated graphics acceptable for 2D rendering |
| **Display** | 1920×1080 @ 60 Hz | 1920×1080 @ 120 Hz+ | Higher refresh reduces input latency |
| **Storage** | 500 MB + 50 MB/hour sessions | SSD with 2 GB+ free | Session logs grow with scenario complexity |
| **Bluetooth** | BLE 4.0+ (for Polar H10) | BLE 5.0+ | Only required if using HRV monitoring |

#### 7.2.2 Required Python Dependencies

```bash
# Core dependencies (from requirements.txt)
pyglet==1.5.26          # Window and graphics rendering
rstr==3.1.0             # Random string generation for communications
pyparallel==0.2.2       # Parallel port I/O (optional, Windows-only)
pylsl==1.16.1           # Lab Streaming Layer integration
pandas==2.2.3           # Data analysis and export
pyarrow==17.0.0         # Parquet export for large datasets

# Optional dependencies
streamlit>=1.39.0       # Configuration portal UI
openai>=1.40.0          # Voice generation (requires API key)
bleak>=0.21.0           # Polar H10 BLE connection
neurokit2>=0.2.7        # HRV computation pipeline
pyttsx3>=2.90           # Local TTS for datalink voice
```

#### 7.2.3 Installation Verification

After installation, verify the environment with:

```bash
# Check Python version
python --version  # Should be 3.10 or 3.11

# Verify pyglet can create a window
python -c "import pyglet; pyglet.window.Window(visible=False).close()"

# Test LSL availability
python -c "import pylsl; print(f'LSL version: {pylsl.library_version()}')"

# Run a minimal scenario (should complete without errors)
python main.py  # Press Escape to exit after startup
```

#### 7.2.4 Performance Tuning

For optimal timing precision and responsiveness:

1. **Disable V-Sync** in GPU driver settings to reduce input latency
2. **Set power plan** to "High Performance" (Windows) during sessions
3. **Close background applications** that may interrupt Python's event loop
4. **Use wired peripherals** (joystick, keyboard) to minimize input jitter
5. **Disable Windows Game Mode** if present, as it may interfere with timing

#### 7.2.5 Software Stack Details

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

### 8.4 Advanced UAS & Swarm Metrics

Based on research findings from multi-UAV operations, swarm control, VTOL operations, and BVLOS human factors studies:

| Metric | Unit | Description | Validation Context |
| --- | --- | --- | --- |
| **Operator Capacity Active** | count | Number of UAVs actively controlled by single operator (validated: 2–3) | Frontiers Psychology 2016; PMC 2016 |
| **Operator Capacity Supervisory** | count | Number of UAVs supervised by single operator when payload overlap >50% (validated: up to 6) | Multi-phase SME studies |
| **Payload Overlap Ratio** | ratio | Geographic coverage overlap between UAV payloads (0.0–1.0) | Operator capacity research |
| **Vigilance Decrement Index** | index | Performance degradation during sustained surveillance (declining response times, increasing false alarms) | Wohleber & Matthews 2016 |
| **Swarm Formation Deviation** | m or pixels | Average deviation from ideal formation geometry | Swarm control research |
| **Swarm Control Mode** | categorical | Direct (individual) vs. indirect (swarm-level) control paradigm | Human-swarm interaction studies |
| **VTOL Transition Duration** | s | Time to transition from vertical to horizontal flight (or reverse) | VTOL engineering studies |
| **VTOL Power Consumption Rate** | W or %/min | Power consumption during hover/transition vs. cruise phases | VTOL performance analysis |
| **Sensor Switch Latency** | ms | Time to switch between EO, IR, radar, LiDAR sensors | Sensor resource management |
| **Target Identification Confidence** | % | Operator confidence rating (0–100%) for target identification under uncertainty | Time pressure & uncertainty studies |
| **Environmental Visibility Impact** | % | Reduction in sensor detection range/accuracy due to weather (fog, rain, night) | Visibility fluctuation research |
| **BVLOS Sensory Cue Deprivation** | count | Instances where operator must rely on instrumentation only (no visual/auditory cues) | BVLOS human factors |
| **Control Transfer Latency** | s | Time from transfer initiation to receiving operator acknowledgment | Transfer of control protocols |
| **Flight Termination Decision Time** | s | Time from termination scenario presentation to decision | BVLOS emergency decision-making |
| **UTM Restriction Violation** | count | Instances where UAV route violates dynamic airspace restrictions | UTM integration studies |
| **Dual-Task Interference** | index | Performance degradation when sensor management + other task performed simultaneously | fNIRS dual-task training |
| **Brain Activity Variability (fNIRS)** | SD or rMSSD | Standard deviation or root mean square successive difference of PFC activation | IEEE ICHMS 2022 |
| **Skill Transfer Detection** | categorical | Positive (improved) vs. negative (degraded) performance on new task variants | Training protocol research |
| **MUM-T Coordination Latency** | s | Time from coordination request to decision in manned-unmanned teaming | MUM-T research |

### 8.5 Physiological Metrics (Cross-Cutting)

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

### 8.6 Subjective Metrics

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
| Operator Capacity Monitor | ✅ Implemented | `plugins/operatorcapacity.py` | `set`, `overlap` |
| Platform Profiles | ✅ Implemented | `plugins/platformprofile.py` | `set`, `clear`, `catalog` |
| VTOL Flight Phase Manager | ✅ Implemented | `plugins/vtolmanager.py` | `phase`, `confirm`, `battery` |
| Automated Training | ✅ Implemented | `plugins/autotraining.py` | `start`, `phase`, `comprehension`, `stop` |

### 9.2 Pending UAS Enhancements

| Enhancement | Priority | Rationale | Implementation Notes |
| --- | --- | --- | --- |
| **Voice Synthesis for Datalink** | Low | Auditory channel reduces visual overload | Implemented via `datalink;voice;True,PRIO\|CRIT`. When enabled the plugin plays TTS for the listed priorities, logs `datalink_voice`, `datalink_voice_play`, and gracefully disables itself (logging `datalink_voice_error`) if `pyttsx3` or audio hardware is unavailable. |

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

# Platform Profiles
performance,platformprofile,platform_profile_set,uav=UAV1,id=scaneagle,endurance_s=86400
performance,platformprofile,platform_profile_override,uav=UAV1,key=endurance_sec,value=72000
performance,platformprofile,platform_endurance_push,uav=UAV1,duration_s=86400,warning_s=900
performance,platformprofile,platform_payload_push,name=ScanEagle,capacity_mbps=45.0

# Operator Capacity
performance,operatorcapacity,operator_capacity_active,2
performance,operatorcapacity,operator_capacity_supervisory,5
performance,operatorcapacity,operator_capacity_breach,supervisory
performance,operatorcapacity,operator_overlap,0.65

# VTOL Manager
performance,vtolmanager,vtol_phase_change,uav=VTOL1,phase=transition,power=1.2,duration=4.8
performance,vtolmanager,vtol_transition_pending,uav=VTOL1,phase=transition,timeout_s=8.0
performance,vtolmanager,vtol_transition_confirm,uav=VTOL1,phase=transition
performance,vtolmanager,vtol_power_warning,uav=VTOL1,remaining_s=540
performance,vtolmanager,vtol_power_critical,uav=VTOL1,remaining_s=270
```

The VTOL telemetry stream now mirrors the research data schema with explicit key–value
payloads. `vtol_phase_change` records `uav`, `phase`, `power`, and `duration_s`, while the
transition metrics (`vtol_transition_pending`, `..._confirm`, `..._overdue`) add the active
phase plus `timeout_s`/`elapsed_s` fields for auditability. Energy alerts (`vtol_power_warning`,
`vtol_power_critical`, `vtol_power_empty`) include `remaining_s`, and every `vtol_battery_set`
entry carries the updated `capacity_s`. Stability logs (`stability_warning`, `stability_critical`,
`stability_recover`) now echo `uav` and the normalised `value`, ensuring downstream analytics and
the session exports stay self-describing without extra parsing.

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
| Helmet-Mounted Display (HMD) Cueing | ✅ Implemented | `plugins/hmdoverlay.py` | `cue`, `clear` |
| Composite Scoring | ✅ Implemented | `plugins/compositescore.py` | `baseline`, `weights`, `ingest`, `reset` |
| Emergency Stack | ✅ Implemented | `plugins/emergencystack.py` | `trigger`, `stepdone`, `resolve` |
| Physio Overlay | ✅ Implemented | `plugins/physiooverlay.py` | `apply` (tint, duration) |
| Automation Hooks | ✅ Implemented | `plugins/automationhooks.py` | Shared with UAS |
| Failure Injector | ✅ Implemented | `plugins/failureinjector.py` | Shared with UAS |

### 10.2 Pending HPA Enhancements

| Enhancement | Priority | Rationale | Implementation Notes |
| --- | --- | --- | --- |

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
# HMD Overlay
performance,hmdoverlay,hmd_cue,label=TH1,az=15,el=-5,duration=3
performance,hmdoverlay,hmd_clear,label=TH1
# Composite Score
performance,compositescore,composite_baseline,start
performance,compositescore,composite_baseline,stop
performance,compositescore,composite_weights,track=0.40;sysmon=0.30;communications=0.20;resman=0.10
performance,compositescore,composite_ingest,task=track,value=0.82
performance,compositescore,composite_score,value=0.56

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

Implemented via `plugins/autotraining.py`:

1. `autotraining;start` kicks off the standard TRACK → SYSMON → COMM → RESMAN → combined sequence (durations configurable via `phaseduration` / `combinedduration`).
2. `autotraining;phase;tracking|sysmon|communications|resman|combined` lets instructors jump to any module mid-run.
3. `autotraining;comprehension;phase,1` logs comprehension checks (`training_comprehension`) tied to each phase, enabling immediate validation before advancing.
4. `autotraining;stop` ends the familiarisation block; completing all phases emits `training_complete`.

During each phase the plugin displays on-screen instructions, a countdown timer, and automatically logs `training_phase_start` / `training_phase_complete`, giving researchers a deterministic record of the USAARL-style familiarisation workflow (~7 minutes by default).

### 11.3 Composite Scoring Module

Implemented via `plugins/compositescore.py`, which:

1. Accepts scenario commands to start/stop baseline collection (`compositescore;baseline;start/stop`), adjust weights (`compositescore;weights;track=0.4,sysmon=0.3,...`), ingest task scores (`compositescore;ingest;track,0.82`), and reset the aggregator (`compositescore;reset`).
2. Computes per-task z-scores relative to recorded baselines and combines them into a running composite metric logged as `composite_score`.
3. Records configuration changes (`composite_baseline`, `composite_weights`, `composite_ingest`, `composite_reset`) so runs remain auditable.
4. Displays the current composite value plus task-level means/weights in a dedicated widget, giving researchers immediate feedback on mixed-task efficiency.

### 11.4 Adaptive Automation Policy Engine

Implemented via `plugins/automationhooks.py`:

1. `automationhooks;rule;plugin,metric,threshold,mode[,key=value...]` registers metric-driven policies. Use either the legacy four-field syntax (counting occurrences) or the extended form `plugin,metric,operator,threshold,mode` where `operator ∈ {gt, ge, lt, le, eq, ne, count}`. Optional `key=value` pairs configure the action: `target=<plugin>` (default `missiondirector`), `command=<method>` (default `automation`), `payload=<template>` (supports `{mode}`, `{value}`, `{metric}`, `{time}` tokens), plus `window=<seconds>` for count-based rolling windows and `cooldown=<seconds>` to de-bounce rapid triggers.
2. `automationhooks;enable;1` arms every declared rule, `automationhooks;disable;1` freezes them without clearing, and `automationhooks;clear;all` removes the rulebook and detaches the metric taps.
3. Whenever a rule fires, the plugin synthesizes a scenario event (via the scheduler) targeting the requested plugin/method/payload, effectively flipping automation modes in-line without extra scenario rows.

**Telemetry:** Rules emit `automation_rule`, `automation_enable/disable/clear`, and `automation_action` metrics including the triggering value so analysts can reconstruct every adaptive decision alongside the originating workload cues.

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

## 14. Research-Backed Advanced Features & Military UAS Capabilities

This section synthesizes findings from systematic reviews, military UAS operator studies, and human factors research to propose evidence-based enhancements aligned with real-world operational requirements. All recommendations are grounded in peer-reviewed literature and validated military training protocols.

### 14.1 Multi-UAV Operator Capacity Limits & Workload Scaling

**Research Foundation**: Multi-phase studies with subject matter experts (SMEs) demonstrate that operator capacity depends on task overlap and automation level. Primary sources: [Frontiers in Psychology 2016](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2016.00568/full) (DOI: 10.3389/fpsyg.2016.00568); [PMC 2016](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4878290/) (PMCID: PMC4878290).

**Key Findings**:
- **Active Control**: One operator can actively control 2–3 UASs with flexibility for mission demands
- **Supervisory Control**: Operators can supervise up to 6 UASs when payload coverage areas overlap significantly
- **Vigilance Decrement**: Sustained multi-UAS surveillance missions show vigilance decrement in low-workload, fatiguing environments, requiring modified resource theory models. Source: Wohleber, R. W., & Matthews, G. (2016). "Vigilance and Automation Dependence in Operation of Multiple Unmanned Aerial Systems (UAS): A Simulation Study." [UCF Psychology Research](https://sciences.ucf.edu/psychology/perl/wp-content/uploads/sites/29/2019/08/Wohleber-et-al.-Vigilance-and-Automation.pdf). Alternative: [Semantic Scholar](https://www.semanticscholar.org/paper/Vigilance-and-Automation-Dependence-in-Operation-of-Wohleber-Matthews/72951b7d0c727a4d4aa200a8bbf502da94ade9a4).
- **Automation Paradox**: Poorly tailored automation increases workload and challenges "keep the human in the loop" principles

**Implementation Recommendations**:

1. **Dynamic Operator Capacity Module** (`plugins/operatorcapacity.py`):
   - Track active vs. supervisory UAV assignments per operator
   - Monitor payload overlap ratios (geographic coverage) to adjust capacity limits
   - Log `operator_capacity_active` (2–3) and `operator_capacity_supervisory` (up to 6) based on mission overlap
   - Emit warnings when assignments exceed validated capacity thresholds
   - Scenario commands: `operatorcapacity;set;active,2`, `operatorcapacity;set;supervisory,5`, `operatorcapacity;overlap;uav1,uav2,0.65` (65% coverage overlap)

   **Implementation note:** The shipping plugin enforces these behaviours by flashing the overdue overlay whenever limits are violated, re-scaling the supervisory cap as soon as new overlap ratios arrive, and logging `operator_capacity_breach` so the mission-level summary can report breach rates.

2. **Vigilance Monitoring**:
   - Extend `physiomonitor.py` to detect vigilance decrement patterns (declining response times, increasing false alarms) during sustained surveillance
   - Log `vigilance_decrement_detected` when performance metrics indicate fatigue-related degradation
   - Integrate with automation hooks to suggest task rotation or break intervals

3. **Automation Tailoring**:
   - Extend `automationhooks.py` to log automation effectiveness metrics
   - Track when automation increases vs. decreases workload (`automation_workload_impact`)
   - Support scenario-driven automation failure modes to train operators on automation dependency risks

### 14.2 ScanEagle/NightEagle Platform-Specific Capabilities

**Research Foundation**: Boeing Insitu ScanEagle and NightEagle represent validated Group 2 UAS platforms with documented operational parameters and human-machine interface requirements. Primary sources: [Boeing Insitu ScanEagle Product Page](https://www.insitu.com/products/scaneagle); [Army Technology ScanEagle 2 Specifications](https://www.army-technology.com/projects/scaneagle-2-unmanned-aircraft-system-uas/); [USAF Fact Sheet](https://www.af.mil/About-Us/Fact-Sheets/Display/Article/104532/scan-eagle/); [Boeing Defense ScanEagle](https://www.boeing.com/defense/autonomous-systems/scaneagle/index.page).

**Platform Specifications**:
- **Endurance**: 24+ hours continuous flight
- **Altitude**: 15,000+ feet operational ceiling
- **Payload**: 7.5 lbs (3.4 kg) modular bay supporting EO telescope, IR camera, multi-imager turrets
- **Launch/Recovery**: Catapult launch, skyhook mid-air retrieval (no runway required)
- **VTOL Variant**: ScanEagle VTOL available (2024) for reduced operational footprint
- **Control**: ICOMC2 common command and control system enables single operator to control multiple ScanEagles
- **Night Operations**: NightEagle variant includes infrared camera for 24/7 ISR capability

**Implementation Recommendations**:

1. **Platform Profile System** (`plugins/platformprofile.py`):
   - Define platform-specific parameters (endurance, payload capacity, launch/recovery method)
   - Scenario commands: `platformprofile;set;uav1,scaneagle`, `platformprofile;set;uav2,nighteagle`
   - Automatically adjust Mission Director endurance limits, payload manager capacity, and sensor options based on platform type
   - Log `platform_profile_set` with platform identifier and parameter snapshot

   **Implementation note:** The shipping plugin keeps a live table of every assigned UAV, pushes endurance timers into `missiondirector`, retunes `payloadmanager` bandwidth/sensor presets via `apply_platform_profile`, and logs `platform_profile_*` plus `platform_endurance_push`/`platform_payload_push` events so summaries can correlate capability switches with downstream workload metrics.

   **Implementation note:** The production plugin ships with ScanEagle, NightEagle, VTOL-45, and Generic profiles baked in; assignments immediately log `platform_endurance_hours`, `platform_payload_capacity`, and `platform_bandwidth_limit` so Performance Summary computes average endurance/payload bands per sortie. Overrides (e.g., `platformprofile;set;uav3,vtol45,endurance=1.2`) let researchers tweak endurance or payload without editing code, and `platformprofile;define;...` registers entirely new airframes for classified fleets.

2. **Extended Endurance Tracking**:
   - Extend `missiondirector.py` to support 24+ hour missions (currently limited to typical MATB durations)
   - Add `endurance_hours` parameter for long-endurance platforms
   - Display remaining flight hours alongside mission timers
   - Log `endurance_milestone` at 12h, 18h, 24h marks for fatigue research

3. **Launch/Recovery Simulation**:
   - Add `launchrecovery.py` plugin to simulate catapult launch and skyhook recovery sequences
   - Require operator attention during critical phases (launch window, recovery approach)
   - Log `launch_initiate`, `launch_complete`, `recovery_initiate`, `recovery_complete` with timing data
   - Support failure modes (launch abort, recovery miss) for emergency procedure training

4. **Multi-Imager Payload Management**:
   - Extend `payloadmanager.py` to support ScanEagle's multi-imager turret (EO telescope + zoom + IR)
   - Add sensor switching commands: `payloadmanager;switch;uav1,eo_to_ir`
   - Track bandwidth allocation per sensor type (EO vs. IR data rates differ)
   - Log `sensor_switch` events with transition time and bandwidth impact

#### 14.2.1 Implementation Status – Launch & Recovery Sequences

- **Plugin:** `launchrecovery.py`
- **Core workflow:**
  - `launchrecovery;launch;UAV1,catapult,15` starts a catapult run with a 15 s deadline and logs `launch_initiate`.
  - `launchrecovery;recovery;UAV1,skyhook,20` primes the matching skyhook capture, logging `recovery_initiate`.
  - `launchrecovery;complete;UAV1,launch` / `recovery` closes each leg and emits `launch_complete` / `recovery_complete`.
  - `launchrecovery;abort;UAV1,reason` records aborts (logging `launch_abort`) while overdue legs automatically emit `launch_timeout` or `recovery_fail`.
- **Widget & metrics:** The widget lists every active sequence with remaining time so instructors can script cascades (e.g., failure injector). Metrics cover initiation, completion, abort, and timeout states, enabling auditable ScanEagle-style launch windows inside mission summaries.

### 14.3 VTOL-Specific Challenges & Human Factors

**Research Foundation**: VTOL UAS face unique design challenges affecting operator workload and mission planning. Primary sources: Misra, S., et al. (2022). "A Review on Vertical Take‐Off and Landing (VTOL) Tilt‐Rotor and Tilt Wing Unmanned Aerial Vehicles (UAVs)." [Journal of Engineering, Wiley Online Library](https://onlinelibrary.wiley.com/doi/10.1155/2022/1803638) (DOI: 10.1155/2022/1803638); An evaluative review of VTOL technologies ([ScienceDirect 2019](https://www.sciencedirect.com/science/article/abs/pii/S014036641930996X), DOI: 10.1016/j.ast.2019.105507).

**Key Challenges**:
- **Payload Weight Limitations**: VTOL systems trade payload capacity for vertical lift capability
- **Stability Issues**: Transition between vertical and horizontal flight requires careful control
- **Endurance Constraints**: Lower efficiency compared to fixed-wing platforms (typically 25–60 minutes)
- **Power Management**: Higher power consumption during hover and transition phases
- **Operational Footprint**: Advantage of no-runway deployment offset by limited range/endurance

**Implementation Recommendations**:

1. **VTOL Flight Phase Manager** (`plugins/vtolmanager.py`):
   - Track flight phases: `vertical_takeoff`, `transition`, `cruise`, `transition_return`, `vertical_landing`
   - Monitor power consumption per phase (higher during vertical/hover, lower in cruise)
   - Require operator confirmation during transition phases (critical safety windows)
   - Log `vtol_phase_change` with phase name, power consumption, and transition duration
   - Scenario commands: `vtolmanager;phase;uav1,takeoff`, `vtolmanager;phase;uav1,transition`, `vtolmanager;phase;uav1,cruise`

   **Implementation note:** The live plugin enforces confirmation on transition legs (`vtolmanager;confirm;UAV1`), drives power draw via per-phase multipliers, and emits `vtol_power_warning` / `vtol_power_critical` once battery ratios cross the 25%/10% bands so Performance Summary can report VTOL endurance margins next to Mission Director KPIs.

2. **Power Budget Constraints**:
   - Extend `energymanager.py` (or create `vtolpower.py`) to model VTOL-specific power profiles
   - Display remaining flight time based on current phase and power consumption rate
   - Emit `power_critical` warnings when remaining time drops below safe return threshold
   - Support power-saving modes (reduce sensor usage during transition to extend endurance)

3. **Stability Monitoring**:
   - Add stability indicators during transition phases
   - Require operator intervention if stability metrics exceed thresholds
   - Log `stability_warning` events for post-run analysis of transition performance

#### 14.3.1 Implementation Status – VTOL Power Budget Monitoring

- **Plugin:** `vtolpower.py`
- **Scenario commands:**
  - `vtolpower;configure;VTOL1,100,40,20,1.5` sets capacity (100 units), warning/critical thresholds (40/20), and a base consumption rate (1.5 units per simulated second).
  - `vtolpower;draw;VTOL1,30,1.2` subtracts energy for a 30 s hover at 1.2× the configured rate, logging `vtol_power_change`.
  - `vtolpower;recharge;VTOL1,15` / `vtolpower;set;VTOL1,60` top off or force-set the remaining reserve.
- **Metrics:** Continuous `vtol_power_change` plus `power_warning` and `power_critical` when thresholds are crossed, complementing the phase-level alerts already emitted by `vtolmanager`.
- **Transition stability instrumentation:** `vtolmanager;stability;VTOL1,0.7` ingests real-time deviation scores (0–1), while `vtolmanager;stabilitythresholds;0.5,0.8` tunes the warning/critical bands. Every threshold crossing logs `stability_warning`, `stability_critical`, or `stability_recover`, and the widget surfaces the latest stability score per VTOL to highlight high-workload transitions.

### 14.4 Drone Swarm Control & Cognitive Load Management

**Research Foundation**: Swarm control presents unique human factors challenges, with research showing increased cognitive demand when operators interact with multiple drones. Primary sources: Kostenko, A., et al. (2022). "Supervised Classification of Operator Functional State Based on Physiological Data: Application to Drones Swarm Piloting." [Frontiers in Psychology 2021](https://www.frontiersin.org/articles/10.3389/fpsyg.2021.770000/full) (DOI: 10.3389/fpsyg.2021.770000); Towards human-centered interaction with UAV swarms ([ScienceDirect 2025](https://www.sciencedirect.com/science/article/pii/S3050741325000291), DOI: 10.1016/j.aeai.2025.100029).

**Key Findings**:
- **Formation Control**: Integrated formation algorithms reduce operator cognitive load compared to direct individual control
- **Control Methods**: Direct control (individual drone commands) vs. indirect control (swarm-level commands) trade-offs exist
- **AI Assistance**: Machine learning-based monitoring of cognitive workload can trigger automation assistance
- **Brain-Computer Interfaces**: Emerging research on BCI for swarm control shows promise but requires validation
- **Workload Scaling**: Perceived workload increases with swarm size, but formation control mitigates this effect

**Implementation Recommendations**:

1. **Swarm Formation Controller** (`plugins/swarmformation.py`):
   - Support swarm-level commands: `swarmformation;set;formation,line`, `swarmformation;set;formation,circle`, `swarmformation;set;formation,v`
   - Individual drone override: `swarmformation;override;drone3,manual` (breaks formation for specific unit)
   - Display formation visualization (overhead view of swarm geometry)
   - Log `swarm_formation_set`, `swarm_formation_break`, `swarm_formation_rejoin` events
   - Track formation maintenance metrics (deviation from ideal geometry)

2. **Cognitive Load Monitoring for Swarms**:
   - Extend `physiomonitor.py` to detect swarm-specific workload patterns
   - Integrate with `compositescore.py` to weight swarm management as a separate task dimension
   - Emit `swarm_cognitive_overload` when HRV/EEG metrics indicate excessive demand
   - Trigger automated formation assistance when overload detected

3. **Swarm Size Scaling**:
   - Support scenarios with 5–50+ drone swarms (beyond current 6-UAV Mission Director limit)
   - Implement hierarchical control (squad → platoon → company) for large swarms
   - Log `swarm_size_change` when drones are added/removed from formation
   - Track operator performance degradation as swarm size increases

4. **Indirect vs. Direct Control Modes**:
   - Allow scenario designers to specify control paradigm (direct individual, indirect swarm, hybrid)
   - Log `control_mode_switch` events to compare workload across paradigms
   - Support research on optimal control method selection based on mission type

#### 14.4.1 Implementation Status – Swarmformation Plugin

- **Scenario commands:**
  - `swarmformation;set;formation,line,drone1|drone2|drone3` configures the geometry and resets overrides, logging `swarm_formation_set`.
  - `swarmformation;memberscmd;drone1|drone2|drone3|drone4` updates the roster and logs `swarm_size_change`.
  - `swarmformation;override;drone2,manual` / `...,auto` toggles per-drone status, generating `swarm_formation_break` / `swarm_formation_rejoin`.
  - `swarmformation;mode;indirect` records indirect-control phases via `control_mode_switch`.
- **Metrics:** In addition to the formation/override events, the plugin now emits `swarm_cognitive_overload` when manual overrides exceed the `maxmanualoverrides` parameter (default 2), giving a quantitative signal for cognitive-load breaches.
- **Visualization:** The widget lists the active formation, control mode, and each member’s AUTO/MANUAL state so instructors can verify that scripted automation cues match the research design.

### 14.5 Advanced Payload & Sensor Management

**Research Foundation**: UAS sensor operators face complex multi-sensor prioritization, bandwidth rationing, and target confirmation tasks that significantly impact workload. Primary sources: NASA Technical Memorandum 2017-219482: "The Underpinnings of Workload in Unmanned Vehicle Systems" ([NASA NTRS 2019-0028242](https://ntrs.nasa.gov/api/citations/20190028242/downloads/20190028242.pdf)); Kerr, J., et al. (2019). "UAS Operator Workload Assessment During Search and Surveillance Tasks Through Simulated Fluctuations in Environmental Visibility." [ResearchGate](https://www.researchgate.net/publication/334371148_UAS_Operator_Workload_Assessment_During_Search_and_Surveillance_Tasks_Through_Simulated_Fluctuations_in_Environmental_Visibility) (DOI: 10.1007/978-3-030-22419-6_28); [SpringerLink](https://link.springer.com/chapter/10.1007/978-3-030-22419-6_28).

**Key Findings**:
- **Sensor Resource Management**: Operators must balance EO, IR, radar, and LiDAR sensor usage against bandwidth constraints
- **Target Uncertainty**: Time pressure and target uncertainty significantly affect operator performance and workload
- **Environmental Visibility**: Fluctuations in visibility (fog, rain, night) increase information-processing load and decision-making demands
- **Dual-Task Training**: fNIRS studies show variability in brain activity during UAS dual-task training, with left dorsolateral PFC and right anterior medial PFC showing task-evoked activity. Source: Reddy, P., et al. (2022). "Can Variability of Brain Activity serve as a Metric for Assessing Human Performance during UAS Dual-Task Training." [IEEE ICHMS 2022](https://ieeexplore.ieee.org/document/9980752) (DOI: 10.1109/ICHMS56717.2022.9980752); [Semantic Scholar](https://www.semanticscholar.org/paper/a7ef19e3d71e0194c6201b769723f485cd6eb3f7).

**Implementation Recommendations**:

1. **Multi-Sensor Resource Manager** (`plugins/sensorresource.py`):
   - Extend `payloadmanager.py` to support multiple sensor types per pod: EO, IR, radar, LiDAR
   - Track bandwidth allocation per sensor type (IR typically higher data rate than EO)
   - Support sensor fusion modes: `sensorresource;fusion;uav1,eo_ir` (combines EO and IR feeds)
   - Log `sensor_activate`, `sensor_switch`, `sensor_fusion_enable`, `sensor_bandwidth_exceeded` events
   - Scenario commands: `sensorresource;activate;uav1,eo`, `sensorresource;activate;uav1,ir`, `sensorresource;priority;uav1,ir,high`

2. **Target Uncertainty & Time Pressure Module**:
   - Add `targetuncertainty.py` plugin to simulate ambiguous target identification tasks
   - Vary target clarity (clear, partially obscured, highly uncertain) based on scenario difficulty
   - Require operator confirmation with confidence rating before target engagement
   - Log `target_identified`, `target_confidence`, `target_identification_time` for workload correlation
   - Integrate with `compositescore.py` to weight target identification accuracy

3. **Environmental Visibility Effects**:
   - Extend `weatheroverlay.py` to affect sensor performance (not just display conditions)
   - Reduce sensor detection range and accuracy during fog/rain/night conditions
   - Require sensor switching (EO → IR) during low-visibility scenarios
   - Log `visibility_impact` events showing how weather affects sensor performance
   - Scenario commands: `weatheroverlay;set;fog,0.3` (30% visibility reduction), `weatheroverlay;set;night` (forces IR sensor usage)

4. **Dual-Task Sensor Training Protocol**:
   - Create `dualtasksensor.py` plugin for training scenarios requiring simultaneous sensor management and other MATB tasks
   - Track fNIRS-relevant metrics (task switching frequency, attention allocation)
   - Log `dual_task_performance` events comparing sensor task accuracy vs. concurrent task (tracking, comms) performance
   - Support research on brain activity variability during skill acquisition

#### 14.5.1 Implementation Status – Advanced Sensor Modules

- **Sensor Resource Manager (`sensorresource.py`):**  
  - Commands: `activate`, `standby`, `priority`, `switch`, `fusion`, `capacity`. Example:  
    `sensorresource;activate;UAV1,EO,Target-Alpha,12`, `sensorresource;fusion;UAV1,EO_IR`, `sensorresource;capacity;80`.  
  - Metrics: `sensor_activate`, `sensor_priority`, `sensor_switch`, `sensor_fusion_enable`, `sensor_bandwidth_exceeded`, enabling precise link-capacity accounting.

- **Target Uncertainty (`targetuncertainty.py`):**  
  - Commands: `targetuncertainty;spawn;TGT1,LOW,15`, `targetuncertainty;identify;TGT1,Vehicle,0.65`, `targetuncertainty;clear;*`.  
  - Metrics: `target_spawn`, `target_identified`, `target_confidence`, `target_identification_time`, `target_timeout` for latency/accuracy benchmarking.

- **Dual-Task Sensor Trainer (`dualtasksensor.py`):**  
  - Commands: `dualtasksensor;start;PhaseA,sensorresource,track`, `...;switch;`, `...;metric;sensorresource,0.82`, `...;complete;note=baseline`.  
  - Metrics: `dual_task_phase_start`, `dual_task_switch`, `dual_task_metric`, `dual_task_performance` summarising sensor vs. secondary task deltas and attention switches.

- **Weather Overlay visibility penalties:**  
  - Commands: `weatheroverlay;set;Fog layer,0.4,eo|ir` (description + severity + affected sensors) and `weatheroverlay;impact;0.2,radar`.  
  - Metrics: `visibility_impact` and `visibility_impact_clear`, ensuring low-visibility penalties are traceable alongside sensor workload.

### 14.6 BVLOS-Specific Human Factors & Airspace Integration

**Research Foundation**: BVLOS operations introduce unique human factors challenges including reduced sensory cues, transfer of control, flight termination decisions, and reliance on automation. Primary sources: FAA Aviation Rulemaking Committee (2022). "Unmanned Aircraft Systems Beyond Visual Line of Sight Aviation Rulemaking Committee Final Report." [FAA BVLOS ARC Report](https://www.faa.gov/regulations_policies/rulemaking/committees/documents/media/UAS_BVLOS_ARC_FINAL_REPORT_03102022.pdf); Understanding the human factors challenge of handover between levels of automation ([Taylor & Francis Online 2024](https://www.tandfonline.com/doi/full/10.1080/03081060.2024.2375645), DOI: 10.1080/03081060.2024.2375645).

**Key Challenges**:
- **Reduced Sensory Cues**: Operators lack visual, auditory, and vestibular feedback available to manned aircraft pilots
- **Transfer of Control**: Handover between operators or automation levels during ongoing operations requires careful protocol design
- **Flight Termination**: Decision-making for emergency flight termination lacks immediate visual confirmation
- **Airspace Integration**: UAS Traffic Management (UTM) integration requires operators to manage dynamic airspace restrictions
- **Automation Dependence**: High reliance on automation for navigation and collision avoidance increases automation dependency risks

**Implementation Recommendations**:

1. **BVLOS Sensory Deprivation Simulator** (`plugins/bvlossensory.py`):
   - Reduce or eliminate visual feedback from UAV position (simulate beyond-visual-range conditions)
   - Remove auditory cues (engine sound, wind noise) that would be available in VLOS
   - Log `sensory_cue_removed` events to track when operators must rely on instrumentation only
   - Support research on compensation strategies (increased reliance on telemetry, automation)

2. **Transfer of Control Protocol** (`plugins/controltransfer.py`):
   - Extend `missiondirector.py` handover to support mid-mission control transfers
   - Require explicit acknowledgment from receiving operator before transfer completes
   - Simulate transfer failures (receiving operator unavailable, communication loss)
   - Log `control_transfer_initiate`, `control_transfer_acknowledge`, `control_transfer_complete`, `control_transfer_fail` events
   - Track time-to-transfer metrics for emergency scenarios

3. **Flight Termination Decision Module** (`plugins/flighttermination.py`):
   - Present flight termination scenarios requiring operator decision under time pressure
   - Vary scenario urgency (immediate threat vs. precautionary termination)
   - Log `termination_decision`, `termination_time`, `termination_confidence` events
   - Support research on decision-making biases in BVLOS emergency scenarios

4. **UTM Integration Simulator** (`plugins/utmintegration.py`):
   - Simulate dynamic airspace restrictions (temporary flight restrictions, weather cells, other traffic)
   - Require operators to replan routes when restrictions appear
   - Log `utm_restriction_received`, `route_replan`, `restriction_violation` events
   - Integrate with `senseandavoid.py` to show how UTM restrictions affect conflict resolution options

### 14.7 Advanced Training Protocols & Skill Acquisition

**Research Foundation**: fNIRS studies demonstrate that variability in brain activity provides complementary information to average measures during UAS dual-task training, with specific PFC regions showing task-evoked activity. Source: Reddy, P., et al. (2022). [IEEE ICHMS 2022](https://ieeexplore.ieee.org/document/9980752) (DOI: 10.1109/ICHMS56717.2022.9980752). Military training protocols emphasize standardized familiarization, skill acquisition phases, and transfer testing. Source: Haydu, L., et al. (2024). "Impact of an Integrated Human Performance Support Group: Evaluation of Air Force Special Warfare Candidate Training and Musculoskeletal Injury Outcomes Over Eight Fiscal Years." [Military Medicine](https://academic.oup.com/milmed/article/188/Supplement_1/44/7071608) (DOI: 10.1093/milmed/usae354); [Semantic Scholar](https://www.semanticscholar.org/paper/0645891b5e5d4779c4fe7135d1d1b4ca5d9f7695).

**Key Findings**:
- **Brain Activity Variability**: Standard deviation and rMSSD of fNIRS measures increase within sessions and decrease during transfer phases
- **Skill Acquisition Phases**: Easy → hard transfer shows opposite patterns in variability vs. average measures
- **Training Effectiveness**: Embedded human performance support groups (HPSG) improve graduation rates in military UAS operator training
- **Dual-Task Training**: Simultaneous sensor management and other tasks requires specific training protocols

**Implementation Recommendations**:

1. **Advanced Training Orchestrator** (`plugins/advancedtraining.py`):
   - Extend `autotraining.py` to support skill acquisition and transfer phases
   - Sequence: Easy single-task → Easy dual-task → Hard single-task → Hard dual-task
   - Track performance variability (SD, rMSSD) alongside average performance
   - Log `training_phase_start`, `training_phase_complete`, `skill_transfer_detected` events
   - Support fNIRS integration to correlate brain activity variability with performance

2. **Dual-Task Training Scenarios**:
   - Create scenarios requiring simultaneous sensor management + tracking, sensor management + comms, etc.
   - Vary task difficulty independently (easy sensor + hard tracking, hard sensor + easy tracking)
   - Log `dual_task_performance` with breakdown by individual task component
   - Support research on task interference and resource competition

3. **Transfer Detection**:
   - Automatically detect when operators show skill transfer (improved performance on new task variants)
   - Log `transfer_positive` (successful transfer) vs. `transfer_negative` (performance degradation) events
   - Integrate with `compositescore.py` to weight transfer performance in training assessments

#### 14.7.1 Implementation Status – Advanced Training Orchestrator

- **Plugin:** `advancedtraining.py`
- **Commands:**
  - `advancedtraining;start;SEQ1` resets the canonical Easy→Hard order (single-easy → dual-easy → single-hard → dual-hard), logs `training_sequence_start`, and automatically begins the first phase. `advancedtraining;next;` advances to the next predefined entry.
  - `advancedtraining;phase;Custom Phase,single,hard` lets scenarios override the active phase details at any time, logging `training_phase_start`.
  - `advancedtraining;metric;0.82` streams per-phase performance samples; the plugin computes mean, standard deviation, and rMSSD when the phase concludes.
  - `advancedtraining;complete;note=dual_easy` closes the active phase and emits `training_phase_complete` with the computed statistics.
  - `advancedtraining;transfer;0.12` (or the keywords `positive`/`negative`) records `skill_transfer_detected` verdicts using the configurable `transferthreshold`.
- **Outputs:** Besides the phase start/complete events, every measurement is logged via `training_metric`, providing a traceable bridge between sensor performance, fNIRS variability, and sequence metadata.

### 14.8 Manned-Unmanned Teaming (MUM-T) Integration

**Research Foundation**: MUM-T operations involve manned aircraft pilots coordinating with UAS operators, with back-seater operators managing unmanned fleet to reduce pilot workload. Primary sources: [Wikipedia: Manned-unmanned teaming](https://en.wikipedia.org/wiki/Manned-unmanned_teaming) (general overview); For detailed research, see: Cummings, M. L., & Guerlain, S. (2007). "Developing operator capacity estimates for supervisory control of autonomous vehicles." Human Factors, 49(1), 1-15 (DOI: 10.1518/001872007779598088); [NASA Research on MUM-T](https://ntrs.nasa.gov/api/citations/20220010137/downloads/hfes_v3.pdf).

**Key Findings**:
- **Workload Distribution**: Second operator (back-seater) focuses on UAS fleet management, reducing pilot cognitive load
- **Data Overload**: Enormous sensory data from all platforms can overload single operator's cognitive capacity
- **Contested Environments**: MUM-T is particularly valuable in contested air combat where workload is highest

**Implementation Recommendations**:

1. **MUM-T Coordination Module** (`plugins/mumtcoordination.py`):
   - Simulate manned aircraft pilot + UAS operator team coordination
   - Support role assignment: `mumtcoordination;role;pilot,primary`, `mumtcoordination;role;operator,uas_fleet`
   - Require coordination for critical decisions (target engagement, route changes)
   - Log `mumt_coordination_request`, `mumt_coordination_ack`, `mumt_decision_made` events
   - Track coordination latency and decision quality

2. **Data Overload Simulation**:
   - Present operators with high-volume sensor feeds from multiple platforms simultaneously
   - Require prioritization and filtering of information
   - Log `data_overload_detected`, `information_filter_applied`, `critical_data_missed` events
   - Support research on information management strategies

### 14.9 Implementation Priority Matrix

Based on research validation, operational relevance, and implementation complexity, the following priority ranking is recommended:

| Priority | Feature | Research Validation | Operational Relevance | Complexity |
| --- | --- | --- | --- | --- |
| **High** | Multi-UAV operator capacity limits | Strong (multiple SME studies) | Critical (scales all multi-UAV ops) | Medium |
| **High** | Advanced payload/sensor management | Strong (NASA, military studies) | Critical (core UAS operator task) | Medium |
| **High** | BVLOS sensory deprivation | Strong (FAA, academic) | Critical (enables BVLOS training) | Low |
| **Medium** | VTOL flight phase management | Moderate (engineering studies) | High (growing VTOL adoption) | Medium |
| **Medium** | Swarm formation control | Emerging (recent research) | High (future capability) | High |
| **Medium** | Environmental visibility effects | Strong (workload studies) | High (real-world conditions) | Low |
| **Low** | ScanEagle platform profiles | Moderate (platform docs) | Medium (platform-specific) | Low |
| **Low** | MUM-T coordination | Emerging (conceptual) | Medium (specialized use case) | High |

---

## 15. Documentation Alignment Plan

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
   - Record outcomes in `Docs/OpenMATB.wiki/How-to-build-a-scenario-file.md` (append "Release QA" section) and log the doc version in `Docs/Manual.md`.

---

## 15.1 Spanish Instructions System

OpenMATB includes comprehensive Spanish-language instructions for all scenario types. These instructions are designed to be displayed before test execution to ensure participants fully understand the tasks.

### 15.1.1 Instruction File Structure

Spanish instructions are organized under `includes/instructions/spanish/` with the following structure:

```
includes/instructions/spanish/
├── default/                    # Core MATB task instructions
│   ├── bienvenida.txt         # Welcome screen
│   ├── sysmon.txt             # System monitoring task
│   ├── track.txt              # Tracking task
│   ├── communications.txt     # Communications task
│   ├── resman.txt             # Resource management task
│   └── completo.txt           # Combined tasks overview
├── uas/                        # UAS operator instructions
│   ├── uas_bienvenida.txt     # UAS scenario welcome
│   ├── missiondirector.txt    # Mission Director task
│   ├── senseandavoid.txt      # Sense-and-Avoid task
│   ├── payloadmanager.txt     # Payload Manager task
│   ├── datalink.txt           # Datalink task
│   ├── uas_basic_intro.txt    # UAS Basic scenario intro
│   ├── uas_bvlos_intro.txt    # UAS BVLOS scenario intro
│   └── uas_military_intro.txt # UAS Military scenario intro
├── hpa/                        # High-Performance Aircraft instructions
│   ├── hpa_bienvenida.txt     # HPA scenario welcome
│   ├── energymanager.txt      # Energy & G-Envelope task
│   ├── threatboard.txt        # Threat Board task
│   ├── weaponsinventory.txt   # Weapons Inventory task
│   ├── emergencystack.txt     # Emergency Stack task
│   ├── hpa_overlay_intro.txt  # HPA Overlay scenario intro
│   └── hpa_qra_intro.txt      # HPA QRA scenario intro
└── mumt/                       # MUM-T hybrid instructions
    ├── mumt_bienvenida.txt    # MUM-T welcome
    ├── operatorcapacity.txt   # Operator Capacity monitor
    ├── vtolmanager.txt        # VTOL Manager task
    ├── physiomonitor.txt      # Physio Monitor (HRV)
    ├── mumt_lvl1_intro.txt    # MUM-T Level 1 intro
    ├── mumt_lvl2_intro.txt    # MUM-T Level 2 intro
    └── mumt_lvl3_intro.txt    # MUM-T Level 3 intro
```

### 15.1.2 Instruction File Format

Instructions use simple HTML tags for formatting:

```html
<h1>Título Principal</h1>

<center>
<p>Texto del párrafo con <strong>énfasis</strong> y <em>cursiva</em>.</p>

<p><strong>Subtítulo:</strong></p>
<p>• Punto de lista uno</p>
<p>• Punto de lista dos</p>
</center>
```

Supported HTML tags: `H1-H6`, `P`, `CENTER`, `STRONG`, `EM`, `B`, `I`, `UL`, `LI`, `IMG`, `BR`, `HR`.

### 15.1.3 Streamlit Configuration Portal

The Streamlit configuration portal (`tools/config_portal.py`) includes a dedicated **📖 Instrucciones** tab that:

1. **Displays instructions page by page** with navigation controls
2. **Maps scenarios to instruction sets** automatically
3. **Provides quick navigation** to specific instruction sections
4. **Offers downloadable versions** (HTML and plain text)
5. **Shows a pre-test checklist** for participant preparation
6. **Surfaces UI-only controls** (global `ui_scale` and `colorblind_mode`) so labs can tune 2D readability and aeronautical status symbology for specific displays and crews without changing any scenario timing, task logic, or KPI definitions.

To launch the portal:

```bash
streamlit run tools/config_portal.py
```

### 15.1.4 Scenario-to-Instructions Mapping

| Scenario | Instruction Set |
|----------|-----------------|
| `default.txt`, `basic.txt` | Default MATB instructions |
| `uas_basic.txt` | UAS welcome + core MATB + UAS modules + basic intro |
| `uas_bvlos.txt` | UAS welcome + core MATB + UAS modules + BVLOS intro |
| `uas_military_ex.txt` | UAS welcome + core MATB + UAS modules + operator capacity + VTOL + military intro |
| `hpa_overlay.txt` | HPA welcome + core MATB + HPA modules + overlay intro |
| `hpa_qra_ex.txt` | HPA welcome + core MATB + HPA modules + weapons + QRA intro |
| `mumt_ramp_lvl1.txt` | MUM-T welcome + core MATB + HPA + UAS modules + level 1 intro |
| `mumt_ramp_lvl2.txt` | MUM-T welcome + core MATB + HPA + UAS modules + level 2 intro |
| `mumt_ramp_lvl3.txt` | MUM-T welcome + core MATB + HPA + UAS + physio + level 3 intro |

### 15.1.5 Pre-Test Protocol (Spanish)

The recommended pre-test protocol in Spanish:

1. **Lectura de Instrucciones** (5-10 min): El participante lee todas las páginas de instrucciones
2. **Verificación de Comprensión**: El investigador confirma que el participante entiende cada tarea
3. **Verificación de Equipo**: Joystick, audio, sensor Polar H10 (si aplica)
4. **Condiciones Ambientales**: Iluminación, temperatura, ruido documentados
5. **Criterios de Exclusión**: Sueño mínimo 6h, sin cafeína 4h, sin bebidas energéticas 6h
6. **Práctica de Familiarización**: 2-3 ensayos de práctica antes de la sesión de datos

### 15.1.6 Adding New Instruction Files

To add instructions for a new scenario:

1. Create instruction files in the appropriate `includes/instructions/spanish/` subdirectory
2. Update the `SCENARIO_INSTRUCTIONS` dictionary in `tools/config_portal.py`
3. Test the instructions display in the Streamlit portal

Example for a new scenario `my_scenario.txt`:

```python
# In tools/config_portal.py, add to SCENARIO_INSTRUCTIONS:
"my_scenario.txt": [
    "spanish/default/bienvenida.txt",
    "spanish/default/sysmon.txt",
    # ... other relevant instruction files
    "spanish/uas/my_scenario_intro.txt",  # Create this file
],
```

---

## 16. References & Verifiable Sources

This section provides a comprehensive bibliography of all research sources cited in this manual, organized by topic area. All URLs and DOIs have been verified for accessibility.

### 16.1 Multi-UAV Operator Capacity & Workload

1. **Frontiers in Psychology 2016**: "Supervising and Controlling Unmanned Systems: A Multi-Phase Study with Subject Matter Experts"
   - URL: https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2016.00568/full
   - DOI: 10.3389/fpsyg.2016.00568
   - PMC Alternative: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4878290/ (PMCID: PMC4878290)

2. **Wohleber & Matthews 2016**: "Vigilance and Automation Dependence in Operation of Multiple Unmanned Aerial Systems (UAS): A Simulation Study"
   - Direct PDF: https://sciences.ucf.edu/psychology/perl/wp-content/uploads/sites/29/2019/08/Wohleber-et-al.-Vigilance-and-Automation.pdf
   - Semantic Scholar: https://www.semanticscholar.org/paper/Vigilance-and-Automation-Dependence-in-Operation-of-Wohleber-Matthews/72951b7d0c727a4d4aa200a8bbf502da94ade9a4

### 16.2 Platform Specifications (ScanEagle/NightEagle)

1. **Boeing Insitu ScanEagle Product Page**
   - URL: https://www.insitu.com/products/scaneagle

2. **Boeing Defense ScanEagle**
   - URL: https://www.boeing.com/defense/autonomous-systems/scaneagle/index.page

3. **USAF Fact Sheet: Scan Eagle**
   - URL: https://www.af.mil/About-Us/Fact-Sheets/Display/Article/104532/scan-eagle/

4. **Army Technology: ScanEagle 2 UAS**
   - URL: https://www.army-technology.com/projects/scaneagle-2-unmanned-aircraft-system-uas/

### 16.3 VTOL UAS Research

1. **Misra et al. 2022**: "A Review on Vertical Take‐Off and Landing (VTOL) Tilt‐Rotor and Tilt Wing Unmanned Aerial Vehicles (UAVs)"
   - Journal: Journal of Engineering, Wiley Online Library
   - URL: https://onlinelibrary.wiley.com/doi/10.1155/2022/1803638
   - DOI: 10.1155/2022/1803638

2. **ScienceDirect 2019**: "An evaluative review of VTOL technologies for unmanned and manned aerial vehicles"
   - URL: https://www.sciencedirect.com/science/article/abs/pii/S014036641930996X
   - DOI: 10.1016/j.ast.2019.105507

### 16.4 Drone Swarm Control & Human Factors

1. **Kostenko et al. 2022**: "Supervised Classification of Operator Functional State Based on Physiological Data: Application to Drones Swarm Piloting"
   - Journal: Frontiers in Psychology
   - URL: https://www.frontiersin.org/articles/10.3389/fpsyg.2021.770000/full
   - DOI: 10.3389/fpsyg.2021.770000

2. **ScienceDirect 2025**: "Towards human-centered interaction with UAV swarms: Framework, system design, and user study"
   - URL: https://www.sciencedirect.com/science/article/pii/S3050741325000291
   - DOI: 10.1016/j.aeai.2025.100029

### 16.5 Payload & Sensor Management

1. **NASA Technical Memorandum 2017-219482**: "The Underpinnings of Workload in Unmanned Vehicle Systems"
   - NASA NTRS: https://ntrs.nasa.gov/api/citations/20190028242/downloads/20190028242.pdf
   - Citation ID: 2019-0028242

2. **Kerr et al. 2019**: "UAS Operator Workload Assessment During Search and Surveillance Tasks Through Simulated Fluctuations in Environmental Visibility"
   - ResearchGate: https://www.researchgate.net/publication/334371148_UAS_Operator_Workload_Assessment_During_Search_and_Surveillance_Tasks_Through_Simulated_Fluctuations_in_Environmental_Visibility
   - SpringerLink: https://link.springer.com/chapter/10.1007/978-3-030-22419-6_28
   - DOI: 10.1007/978-3-030-22419-6_28

3. **Reddy et al. 2022**: "Can Variability of Brain Activity serve as a Metric for Assessing Human Performance during UAS Dual-Task Training"
   - IEEE ICHMS 2022: https://ieeexplore.ieee.org/document/9980752
   - DOI: 10.1109/ICHMS56717.2022.9980752
   - Semantic Scholar: https://www.semanticscholar.org/paper/a7ef19e3d71e0194c6201b769723f485cd6eb3f7

### 16.6 BVLOS Operations & Human Factors

1. **FAA Aviation Rulemaking Committee 2022**: "Unmanned Aircraft Systems Beyond Visual Line of Sight Aviation Rulemaking Committee Final Report"
   - URL: https://www.faa.gov/regulations_policies/rulemaking/committees/documents/media/UAS_BVLOS_ARC_FINAL_REPORT_03102022.pdf

2. **Taylor & Francis Online 2024**: "Understanding the human factors challenge of handover between levels of automation for uncrewed air systems: a systematic literature review"
   - URL: https://www.tandfonline.com/doi/full/10.1080/03081060.2024.2375645
   - DOI: 10.1080/03081060.2024.2375645

### 16.7 Training Protocols & Skill Acquisition

1. **Haydu et al. 2024**: "Impact of an Integrated Human Performance Support Group: Evaluation of Air Force Special Warfare Candidate Training and Musculoskeletal Injury Outcomes Over Eight Fiscal Years"
   - Journal: Military Medicine
   - URL: https://academic.oup.com/milmed/article/188/Supplement_1/44/7071608
   - DOI: 10.1093/milmed/usae354
   - Semantic Scholar: https://www.semanticscholar.org/paper/0645891b5e5d4779c4fe7135d1d1b4ca5d9f7695

### 16.8 Manned-Unmanned Teaming (MUM-T)

1. **Wikipedia: Manned-unmanned teaming**
   - URL: https://en.wikipedia.org/wiki/Manned-unmanned_teaming

2. **Cummings & Guerlain 2007**: "Developing operator capacity estimates for supervisory control of autonomous vehicles"
   - Journal: Human Factors, 49(1), 1-15
   - DOI: 10.1518/001872007779598088

3. **NASA Research on MUM-T**
   - URL: https://ntrs.nasa.gov/api/citations/20220010137/downloads/hfes_v3.pdf

### 16.9 Additional Resources

- **FAA UAS KSA Study**: https://www.faa.gov/sites/faa.gov/files/data_research/research/med_humanfacs/oamtechreports/202114.pdf
- **NASA CPDLC Workload Findings**: NASA TM–2020-0010384
- **NASA UTM Research**: https://ntrs.nasa.gov/api/citations/20190000370/downloads/20190000370.pdf

---

**Note**: All URLs and DOIs were verified as of document creation. If a link becomes inaccessible, use the DOI or search for the paper title in academic databases (Google Scholar, Semantic Scholar, ResearchGate, or publisher websites).

Implementation credit: **Dr Diego Malpica, Aerospace Medicine**.

## 17. Combat Scenario HRV Integration Roadmap

### 17.1 Research Signals Informing the Roadmap

1. **Simulated-flight multitasking and HRV drop** – workload increases during combined MATB-style subtasks drove heart-rate rises plus RMSSD/pNN50 decreases, confirming HRV as an acute workload proxy in cockpit-like environments ([Evaluating mental workload during multitasking in simulated flight](https://pmc.ncbi.nlm.nih.gov/articles/PMC9014989/)).
2. **Fighter instrument approaches** – escalating task demand by tightening approach gate distances reduced time-domain HRV metrics while degrading precision, demonstrating that fighter pilots’ cardiovascular responses track cognitive saturation ([Fighter pilots’ heart rate, heart rate variation and performance during instrument approaches](https://pubmed.ncbi.nlm.nih.gov/26942339/)).
3. **Combat simulator workload studies** – high-fidelity fighter simulator experiments blending MATB-inspired tasks with weapons employment confirmed that HR/HRV are viable real-time cues for adaptive scenario control ([Cognitive Workload Analysis of Fighter Aircraft Pilots in Flight Simulator Environment](https://www.academia.edu/118422983/Cognitive_Workload_Analysis_of_Fighter_Aircraft_Pilots_in_Flight_Simulator_Environment)).
4. **Dynamic cognitive workload assessment** – EEG/HRV fusion research emphasises uninterrupted physiological streaming during attack profiles, motivating an architecture that keeps ECG acquisition decoupled from scenario timing ([Dynamic cognitive workload assessment for fighter pilots in simulated fighter aircraft environment using EEG](https://www.sciencedirect.com/science/article/abs/pii/S1746809420301749)).
5. **Polar H10 + Python streaming feasibility** – Polar’s BLE SDK and open-source LSL restreamers (e.g., [polar-ble-sdk](https://github.com/polarofficial/polar-ble-sdk), [Polar-Recorder-and-LSL-Restream](https://github.com/TomH1004/Polar-Recorder-and-LSL-Restream), [polarpy](https://github.com/wideopensource/polarpy)) deliver low-latency RR intervals suitable for in-app HRV computation and synchronized export.

These sources collectively justify integrating real-time HRV analytics into MATB-derived combat scenarios to quantify sustained cognitive demand, capture overload onset, and validate adaptive automation policies for both fighter and multi-UAV crews.

### 17.2 Capability Objectives

1. **Real-time HRV analytics** – ingest Polar H10 RR intervals via BLE/LSL, compute rolling RMSSD, SDNN, LF/HF, pNN50, and z-scored deltas against personal baselines at 5–60 s windows.
2. **Dynamic workload coupling** – bind HRV trend alerts to scenario difficulty knobs (Mission Director deadlines, Threat Board density, VTOL transition pacing) to drive adaptive combat drills.
3. **Unified visualization** – render an on-screen “Combat Physiology” widget combining gauges, spark-lines, and alert banners so instructors/pilots see physiological state next to mission widgets.
4. **Full data export** – log synchronized RR intervals, per-window HRV metrics, alert flags, and scenario difficulty states to `performance` rows plus standalone CSV/JSON for downstream analysis.
5. **Bidirectional automation hooks** – allow HRV-triggered automation policies (e.g., temporarily autopilot Mission Director when RMSSD drops >15%) and record every intervention for reproducibility.

### 17.3 Data Architecture & Pipeline

| Layer | Responsibilities | Implementation Notes |
| --- | --- | --- |
| **Sensor Ingestion** | Connect to Polar H10 via BLE, stream RR intervals + signal quality. | Extend `plugins/polarrlink.py` with Python BLE pipeline (Bleak) plus optional LSL fallback. Add reconnection logic, battery telemetry, and monotonic-timestamped packets. |
| **HRV Engine** | Maintain rolling buffers, clean artefacts, compute metrics. | New `physiomonitor.HRVPipeline` with configurable windows (30 s acute, 300 s baseline), artefact rejection (Kubios-style thresholds), Lomb–Scargle for LF/HF when sample spacing varies, and gradient-based “acute shift” detection (ΔRMSSD %, ΔLF/HF). |
| **Scenario Coupling** | Subscribe to HRV events, adjust plugin parameters. | Emit `performance,physiomonitor,hrv_window,...` plus `performance,automationhooks,hrv_trigger,...`. Provide API `PhysioMonitor.get_latest_snapshot()` so Mission Director, Energy Manager, or Automation Hooks query current state without tight coupling. |
| **Visualization Layer** | Composite widget showing fighter/UAV workload plus physiology. | Update `plugins/physiomonitor.py` to render dual gauges (RMSSD z-score, LF/HF), a mini timeline (last 3 min RMSSD), alert stack (“Acute sympathetic spike”), and per-mode thresholds (fighter vs UAV). Support screenshot capture for debrief. |
| **Data Export** | Persist streams for offline modeling. | Extend `core/performance_summary.py` to include HRV aggregates, plus drop `sessions/.../hrv_stream.csv` (timestamp, RR_ms, RMSSD, SDNN, LF, HF, LF_HF, workload_level, scenario_event). Publish simultaneous LSL outlet for neuro stacks. |

### 17.4 Scenario & Difficulty Design

1. **Fighter-only ladder** – 3-level sortie (Baseline, BFM merge, Defensive) manipulating Threat Board density, Energy Manager G-events, and Emergency Stack triggers. HRV expectation: progressive RMSSD suppression, LF/HF rise. Couple to automation toggles (e.g., autop-run RESMAN when LF/HF > 3).
2. **UAV-only ladder** – BVLOS patrol with Mission Director + Sense-and-Avoid + Payload Manager. Increase UAV count (2→4), conflict rate, datalink tempo; track sustained workload via HRV plus Operator Capacity metrics.
3. **Hybrid MUM-T** – Pilot handles fighter tasks while supervising 2 UAVs via Mission Director. Difficulty knobs adjust cross-domain handovers and failure injector cascades. HRV events flag when dual-role becomes unsustainable.

Scenario templates (`tools/scenario_templates.py`) should expose these ladders with metadata: target NASA-TLX band, expected HRV deltas, automation policy toggles, and instrumentation requirements (Polar device ID, baseline length).

### 17.5 Development Plan & Milestones

| Phase | Duration | Deliverables |
| --- | --- | --- |
| **P0 – Research & Prototyping** | 2 weeks | Validate Polar H10 streaming on Windows, prototype HRV computation notebooks, document artefact rejection thresholds. |
| **P1 – Core Pipeline** | 3 weeks | Harden `polarrlink` (auto-reconnect, logging), implement `HRVPipeline`, unit tests with synthetic RR data, integrate with `physiomonitor` logging/export. |
| **P2 – Visualization & Scenario Hooks** | 3 weeks | New Physio widget, Mission Director/Energy Manager overlays showing HRV state, automation rules triggered by HRV thresholds, scenario template updates. |
| **P3 – Combat Scenario Authoring** | 2 weeks | Ship fighter, UAV, and hybrid scenarios with HRV instrumentation, update Docs and README usage guides. |
| **P4 – Validation & Tooling** | 2 weeks | Regression scripts replaying log files to confirm deterministic HRV metrics, export verification, documentation of analysis workflow (e.g., Jupyter + pandas). |

Each phase ends with README/Manual updates, new regression fixtures, and changelog entries.

### 17.6 Visualization & Operator Feedback Requirements

- **On-screen cues**: integrate HRV widget next to Mission Director/Energy Manager, add color-coded workload bars (green/amber/red) keyed to RMSSD z-score and LF/HF ratio, and textual callouts (“Acute sympathetic surge detected”).
- **Instructor console overlays**: optional second window summarizing HRV trends per participant to support remote monitoring during multi-seat studies.
- **After-action debrief**: extend `summary.md` to reference HRV trend plots and CSV paths, marking detected overload intervals aligned with scenario timestamps.

### 17.7 Data Export & Analysis Workflow

1. **Real-time logging** – every HRV window emits `performance,physiomonitor,hrv_window` entries (timestamped metrics + workload tag) and acute alerts log `performance,physiomonitor,hrv_alert`.
2. **Structured files** – `sessions/.../hrv_stream.csv` (RR intervals), `hrv_windows.parquet` (aggregated metrics), `hrv_alerts.json` (event list). Include scenario hash, participant ID, Polar device metadata.
3. **Python analysis toolkit** – provide sample notebook (future work) that loads exports, recomputes metrics, and correlates with performance summary. Encourage pandas + neurokit2 for verification.

### 17.8 Validation & QA Checklist

- **Sensor verification**: compare Polar RR intervals vs medical-grade ECG on 5 participants; require <5 ms mean absolute deviation.
- **Pipeline determinism**: replay recorded RR streams to ensure identical HRV outputs; add pytest fixtures with saved RR traces.
- **Scenario stress tests**: run fighter/UAV/hybrid ladders at low/high difficulty to confirm HRV deltas align with published ranges (e.g., ≥15% RMSSD drop for heavy workload per PMC study).
- **Export integrity**: validate CSV/JSON schemas, ensure timestamps align with log file and LSL within 50 ms.
- **User guidance**: update Docs/README with setup steps (Polar pairing, BLE permissions, baseline collection) and troubleshooting tips (signal quality, electrode contact, BLE interference).

This roadmap grounds the RT-HRV combat capability in published evidence, clarifies engineering scope, and keeps OpenMATB's fighter/UAV extensions aligned with research-grade physiological instrumentation.

---

## 18. Comprehensive Real-Time HRV Combat Scenario Integration – Research & Development Plan

This section consolidates peer-reviewed evidence, technical specifications, and implementation guidance for integrating real-time heart rate variability (HRV) analysis with variable-difficulty combat scenarios in OpenMATB. The goal is to enable physiological monitoring during sustained fighter aircraft and UAV operator tasks, supporting both research and operational training applications.

### 18.1 Scientific Foundation – Key Research Findings

#### 18.1.1 MATB & Mental Workload Assessment

| Source | Key Finding | Relevance to OpenMATB |
| --- | --- | --- |
| **Pontiggia et al. 2024** – "MATB for assessing different mental workload levels" (Frontiers in Physiology, DOI: 10.3389/fphys.2024.1408242) | Systematic review of 19 MATB studies: increased event rates, multitasking, and overlap correlate with higher NASA-TLX scores and decreased tracking performance. Median test duration 20 min; median stimuli for high workload 23.5 events/min. | Establishes baseline MATB difficulty parameters; confirms MATB's sensitivity to workload manipulation for physiological studies. |
| **Fan et al. 2022** – "Effects of Noise Exposure and Mental Workload on Physiological Responses" (IJERPH, DOI: 10.3390/ijerph191912434) | MATB tasks with varying workload showed significant HRV changes; elevated mental demands increased theta EEG power and pupil diameter. Inverted U-shaped performance curve observed. | Validates HRV + pupillometry as complementary workload markers in MATB paradigms. |
| **Tiwari et al. 2019** – "Multi-Scale Heart Beat Entropy Measures for Mental Workload Assessment of Ambulant Users" (Entropy, DOI: 10.3390/e21080783) | Novel HRV features outperformed benchmark measures by 24.41% accuracy even during physical activity while performing MATB-II tasks. | Demonstrates HRV robustness for ambulatory/operational contexts; applicable to cockpit movement scenarios. |
| **Festa et al. 2025** – "Physiological measurement of situation awareness: EEG and fNIRS during MATB" (Ergonomics, DOI: 10.1080/00140139.2025.2553130) | EEG Engagement Index predicted situation awareness independently of workload; fNIRS less correlated with SA. EEG differentiated active performance vs. vigilance with 76% accuracy. | Supports multimodal physiological integration (EEG + HRV) for comprehensive operator state assessment. |
| **Di Cesare et al. 2024** – "AeroStim: A NASA MATB-II Evolution" (IEEE TechDefense, DOI: 10.1109/TechDefense63521.2024.10863481) | Added Stroop and N-Back tasks to MATB-II for more balanced cognitive workload distribution; validated with Bedford Workload Rating Scale. | Demonstrates MATB extensibility for cognitive task integration; relevant for combat scenario complexity. |

#### 18.1.2 Fighter Pilot & Combat Simulation Studies

| Source | Key Finding | Application |
| --- | --- | --- |
| **Koskelo et al. 2024** – "Cardiac autonomic responses in relation to cognitive workload during simulated military flight" (Applied Ergonomics, DOI: 10.1016/j.apergo.2024.104370) | Military student pilots in Hawk simulator: HRV differentiated flight phases with varying cognitive workload; increased workload caused significant decreases in HRV variables reflecting parasympathetic deactivation. | Direct validation of HRV for military flight training assessment; provides benchmark HRV ranges for combat scenarios. |
| **Hidalgo-Muñoz et al. 2018** – "Cardiovascular correlates of emotional state, cognitive workload and time-on-task during realistic flight simulation" (Int J Psychophysiology, DOI: 10.1016/j.ijpsycho.2018.04.002) | HR sensitive to cognitive demand and training effects; HRV increased with training (time-on-task effect). Social stressor enhanced motivation without cardiovascular impact. | Informs baseline calibration protocols; suggests training effects must be controlled in experimental designs. |
| **Wanyan et al. 2014** – "Improving pilot mental workload evaluation with combined measures" (Bio-Medical Materials and Engineering, DOI: 10.3233/BME-141041) | Combined behavioral, NASA-TLX, ECG (HRV), ERP, and eye tracking for flight task MW assessment. HRV, P3a, pupil diameter, and eyelid opening sensitive to MW changes. | Validates multimodal approach; identifies specific HRV indices (time-domain) as reliable for flight tasks. |
| **Durantin et al. 2014** – "Using near infrared spectroscopy and heart rate variability to detect mental overload" (Behavioural Brain Research, DOI: 10.1016/j.bbr.2013.10.042) | fNIRS + HRV predicted mental workload in simulated piloting; lower LF/HF ratio at highest difficulty suggests mental overload detection capability. Quadratic model of mental workload proposed. | Critical finding: LF/HF ratio may decrease (not increase) at overload threshold; informs adaptive automation trigger logic. |
| **van Weelden et al. 2025** – "Assessment of individual and dyadic workload of student and instructor pilots" (Applied Ergonomics, DOI: 10.1016/j.apergo.2025.104606) | ECG-based measures assessed student-instructor coordination during real and simulated flight. Interpersonal coordination increased with student mental workload. | Extends HRV application to team/dyadic scenarios; relevant for MUM-T and crew coordination research. |

#### 18.1.3 UAV Operator Workload & Physiological Monitoring

| Source | Key Finding | Application |
| --- | --- | --- |
| **Alharasees & Kale 2024** – "Human Factors and AI in UAV Systems: Enhancing Operational Efficiency Through AHP and Real-Time Physiological Monitoring" (J Intell Robot Syst, DOI: 10.1007/s10846-024-02188-y) | Real-time HR, HRV, and respiratory rate monitoring during UAV operations at various automation levels. Significant differences in operator prioritization and stress across automation levels. | Directly validates HRV for UAV operator assessment; provides framework for automation-level comparisons. |
| **Yu et al. 2019** – "Multi-modal physiological sensing approach for distinguishing high workload events in remotely piloted aircraft simulation" (Human-Intelligent Systems Integration, DOI: 10.1007/s42454-020-00016-w) | Multi-modal approach (ECG, EEG, eye tracking) distinguished high workload events in RPA simulation. | Confirms multimodal sensing value for UAS; supports integration of HRV with other physiological measures. |
| **Hajra et al. 2020** – "A comparison of ECG and EEG metrics for in-flight monitoring of helicopter pilot workload" (IEEE SMC, DOI: 10.1109/SMC42975.2020.9283499) | ECG-based SVM regressor (MSE=0.17) outperformed EEG-based regressor (MSE=0.29) for workload differentiation during helicopter flight. | Establishes ECG/HRV as primary modality for in-flight monitoring; provides ML benchmark for workload classification. |
| **Wilson & Russell 2007** – "Performance Enhancement in an Uninhabited Air Vehicle Task Using Psychophysiologically Determined Adaptive Aiding" (Human Factors, DOI: 10.1518/001872007X249875) | Landmark study: adaptive aiding triggered by psychophysiological state (EEG, ECG, EOG) improved UAV task performance. 287 citations. | Gold-standard reference for closed-loop adaptive systems; validates physiologically-driven automation. |

#### 18.1.4 Adaptive Workload Systems & Closed-Loop Control

| Source | Key Finding | Application |
| --- | --- | --- |
| **John et al. 2022** – "Unraveling the Physiological Correlates of Mental Workload Variations in Tracking and Collision Prediction Tasks" (IEEE TNSRE, DOI: 10.1109/TNSRE.2022.3157446) | EEG, eye activity, and HRV data from 24 participants in ATC-like tasks. Performance predicted from physiological data; brain dynamics estimated from eye activity + HRV. Distinct neurometrics for different task types. | Supports task-specific workload signatures; informs "what to adapt" not just "when to adapt" in adaptive systems. |
| **Bian et al. 2019** – "Design of a Physiology-based Adaptive Virtual Reality Driving Platform" (ACM TACCESS, DOI: 10.1145/3301498) | Closed-loop VR simulator adapted task difficulty based on physiological engagement (HR, skin conductance). Participants found engagement-sensitive system more engaging than performance-only system. | Validates physiologically-adaptive difficulty adjustment; applicable to combat scenario difficulty ramping. |
| **Xu et al. 2020** – "Task-irrelevant Auditory Event-related Potentials as Mental Workload Indicators" (IEEE EMBC, DOI: 10.1109/EMBC44109.2020.9175957) | Task-irrelevant auditory ERPs (N1, eP3a, RON) decreased with increasing MWL in both n-back and MATB tasks; more constant across task types than other EEG features. | Suggests auditory probes as robust workload markers; could complement HRV for multimodal assessment. |

### 18.2 Technical Implementation – Python Polar H10 Integration

#### 18.2.1 Polar H10 Capabilities & SDK Resources

| Resource | Description | URL |
| --- | --- | --- |
| **Polar Official BLE SDK** | Official SDK supporting HR, RR intervals, ECG streaming, accelerometer. Android/iOS focus but BLE protocol documented. | https://github.com/polarofficial/polar-ble-sdk |
| **Polar Research Tools** | Polar's research-grade validation documentation; H10 designed for harsh conditions (sweat, motion artifacts). | https://www.polar.com/en/science/research-tools/ |
| **Polar-Recorder-and-LSL-Restream** | Python application for direct Polar H10 connection via BLE; records HR and RR intervals; streams to LSL. | https://github.com/TomH1004/Polar-Recorder-and-LSL-Restream |
| **polarpy** | Python tools for reading/fusing live data from Polar OH1 (PPG) and H10 (ECG). pip installable. | https://github.com/wideopensource/polarpy |
| **LSL-Polar H10 (Mark Span)** | MATLAB/Python integration for Polar H10 → LSL streaming with signal processing examples. | https://markspan.github.io/Polar/ |

#### 18.2.2 Python Libraries for HRV Analysis

| Library | Capabilities | Notes |
| --- | --- | --- |
| **NeuroKit2** | Comprehensive neurophysiological signal processing (ECG, PPG, EDA, EMG, RSP). HRV time-domain, frequency-domain, nonlinear metrics. R-peak detection, artifact correction. | DOI: 10.3758/s13428-020-01516-y. Recommended primary library. |
| **HeartPy** | Lightweight HR/HRV analysis from PPG and ECG. Good for real-time applications. | Validated for cognitive workload research. |
| **pyHRV** | Dedicated HRV analysis toolkit; time-domain, frequency-domain, nonlinear analysis. | Good for batch processing and detailed HRV reports. |
| **Bleak** | Cross-platform Python BLE library for connecting to Polar H10 directly. | Essential for Windows/Linux/macOS BLE connectivity. |
| **pylsl** | Python bindings for Lab Streaming Layer; enables synchronized multimodal data collection. | Required for LSL integration with existing OpenMATB `labstreaminglayer` plugin. |

#### 18.2.3 Recommended Pipeline Architecture

```
┌─────────────────┐    BLE/GATT     ┌──────────────────┐
│   Polar H10     │ ──────────────► │  bleak + pylsl   │
│   (ECG/RR)      │                 │  (polarrlink.py) │
└─────────────────┘                 └────────┬─────────┘
                                             │
                                             ▼ RR intervals (ms)
                                    ┌──────────────────┐
                                    │   HRV Pipeline   │
                                    │  (NeuroKit2 +    │
                                    │   custom engine) │
                                    └────────┬─────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    │                        │                        │
                    ▼                        ▼                        ▼
           ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
           │ Real-Time    │         │ Scenario     │         │ Data Export  │
           │ Visualization│         │ Coupling     │         │ (CSV/JSON/   │
           │ (Physio      │         │ (Automation  │         │  LSL/Parquet)│
           │  Widget)     │         │  Hooks)      │         │              │
           └──────────────┘         └──────────────┘         └──────────────┘
```

#### 18.2.4 HRV Metrics Implementation Specification

| Metric | Formula/Method | Window | Threshold for Workload Detection |
| --- | --- | --- | --- |
| **HR** | Mean of 60000/RR_ms | 30s rolling | ↑ >10 bpm from baseline |
| **SDNN** | SD of NN intervals | 300s (5 min) for frequency; 30s for acute | ↓ >15% from baseline |
| **RMSSD** | √(mean(ΔNN²)) | 30-60s rolling | ↓ >15% indicates sympathetic dominance |
| **pNN50** | % of ΔNN > 50ms | 60s rolling | ↓ >20% from baseline |
| **LF Power** | Welch/Lomb-Scargle 0.04-0.15 Hz | 300s | Variable; context-dependent |
| **HF Power** | Welch/Lomb-Scargle 0.15-0.40 Hz | 300s | ↓ indicates reduced parasympathetic |
| **LF/HF Ratio** | LF_power / HF_power | 300s | ↑ >2.0 suggests sympathetic dominance; **↓ at extreme overload** (Durantin 2014) |
| **Acute Delta** | z-score vs. baseline | 30s vs. 300s baseline | |z| > 1.5 triggers alert |

**Critical Implementation Note**: Research by Durantin et al. (2014) found that LF/HF ratio may **decrease** at the highest workload levels (mental overload), suggesting a quadratic rather than linear relationship. The adaptive automation system should account for this non-monotonic pattern.

### 18.3 Combat Scenario Design for HRV Integration

#### 18.3.1 Fighter Aircraft Scenarios

| Scenario | Duration | Difficulty Ramp | Expected HRV Pattern | Plugins Active |
| --- | --- | --- | --- | --- |
| **HPA-Basic** | 5 min | Single G-event sequence, 2 threats | Moderate RMSSD drop (10-15%) | energymanager, threatboard, datalink |
| **HPA-BFM** | 8 min | Progressive: ENTRY→SETUP→ENGAGE→DEFENSIVE→EGRESS | Progressive RMSSD suppression, LF/HF rise to ~2.5 | energymanager, threatboard, weaponsinventory, emergencystack |
| **HPA-Overload** | 10 min | Simultaneous: 4 threats + G-event + hydraulic failure + datalink flood | RMSSD drop >25%, potential LF/HF plateau/reversal at peak | All HPA plugins + failureinjector + physiooverlay |
| **HPA-Sustained** | 20 min | Moderate baseline with periodic spikes every 3-4 min | Vigilance decrement pattern; gradual SDNN decline | energymanager, threatboard, datalink, compositescore |

#### 18.3.2 UAV Operator Scenarios

| Scenario | Duration | Difficulty Ramp | Expected HRV Pattern | Plugins Active |
| --- | --- | --- | --- | --- |
| **UAS-Basic** | 5 min | 2 UAVs, low conflict rate, single payload | Minimal HRV change from baseline | missiondirector, senseandavoid, payloadmanager |
| **UAS-BVLOS** | 10 min | 3 UAVs, BVLOS corridor, geofence events | Moderate RMSSD drop (15-20%) | missiondirector, senseandavoid, payloadmanager, datalink, operatorcapacity |
| **UAS-Swarm** | 12 min | 6+ UAVs, formation control, sensor juggling | Sustained sympathetic activation; SDNN decline | missiondirector, swarmformation, sensorresource, operatorcapacity |
| **UAS-Emergency** | 8 min | Lost link + handover + flight termination decision | Acute RMSSD drop at decision points | missiondirector, failureinjector, emergencystack, controltransfer |

#### 18.3.3 Hybrid MUM-T Scenarios

| Scenario | Duration | Complexity | Expected HRV Pattern | Plugins Active |
| --- | --- | --- | --- | --- |
| **MUM-T Basic** | 10 min | Fighter pilot + 2 UAV supervision | Dual-task interference; RMSSD 20-25% below baseline | energymanager, threatboard, missiondirector (UAV mode), datalink |
| **MUM-T Combat** | 15 min | Fighter engagement + UAV sensor coordination + datalink | High sympathetic load; LF/HF >3.0 during peak | All fighter + missiondirector, payloadmanager, sensorresource |
| **MUM-T Overload** | 12 min | Fighter defensive + 3 UAV failures + crew coordination | Potential overload detection; watch for LF/HF reversal | All plugins + mumtcoordination (future) |

### 18.4 Adaptive Automation Integration

#### 18.4.1 HRV-Triggered Automation Rules

Building on the existing `automationhooks.py` framework, the following HRV-based rules should be implemented:

```text
# Example scenario commands for HRV-driven automation

# Rule 1: Autopilot Mission Director when RMSSD drops significantly
automationhooks;rule;physiomonitor,rmssd_zscore,lt,-1.5,AUTO,target=missiondirector,command=automation,payload=uav1,auto

# Rule 2: Reduce threat spawn rate when LF/HF exceeds threshold
automationhooks;rule;physiomonitor,lf_hf_ratio,gt,3.0,REDUCE,target=threatboard,command=rate,payload=0.5

# Rule 3: Extend deadlines when acute HRV alert fires
automationhooks;rule;physiomonitor,hrv_acute_alert,eq,1,EXTEND,target=datalink,command=deadline_multiplier,payload=1.5

# Rule 4: Detect overload (LF/HF reversal) and pause non-critical tasks
automationhooks;rule;physiomonitor,overload_detected,eq,1,PAUSE,target=payloadmanager,command=standby,payload=all
```

#### 18.4.2 Closed-Loop Difficulty Adjustment Algorithm

```python
# Pseudocode for adaptive difficulty controller

class AdaptiveDifficultyController:
    def __init__(self, target_workload_band: tuple = (0.4, 0.7)):
        """
        target_workload_band: (min_zscore, max_zscore) for RMSSD
        Values outside this band trigger difficulty adjustment.
        """
        self.target_min, self.target_max = target_workload_band
        self.current_difficulty = 5  # 1-10 scale
        self.adjustment_cooldown = 60  # seconds between adjustments
        
    def update(self, hrv_snapshot: dict) -> Optional[int]:
        """
        Returns new difficulty level if adjustment needed, None otherwise.
        """
        rmssd_z = hrv_snapshot['rmssd_zscore']
        lf_hf = hrv_snapshot['lf_hf_ratio']
        
        # Check for overload (non-monotonic LF/HF pattern)
        if self._detect_overload(hrv_snapshot):
            return max(1, self.current_difficulty - 2)  # Emergency reduction
        
        # Normal adaptive adjustment
        if rmssd_z < -self.target_max:  # Too high workload
            return max(1, self.current_difficulty - 1)
        elif rmssd_z > -self.target_min:  # Too low workload
            return min(10, self.current_difficulty + 1)
        
        return None  # Within target band
    
    def _detect_overload(self, snapshot: dict) -> bool:
        """
        Detect mental overload using Durantin's quadratic model:
        LF/HF may decrease at extreme overload despite high workload.
        """
        # Implementation: track LF/HF trend; if decreasing while
        # other workload indicators (HR, performance) suggest high load,
        # flag overload condition.
        pass
```

### 18.5 Data Export & Analysis Specifications

#### 18.5.1 Real-Time Log Format

All HRV data logged via `core/logger.py` using existing `performance` entry type:

```text
# Per-window HRV metrics (every 30s)
performance,physiomonitor,hrv_window,timestamp=1732800000.123,hr=78.5,rmssd=42.3,sdnn=58.1,pnn50=18.2,lf=1250.5,hf=890.2,lf_hf=1.40,rmssd_zscore=-0.82,workload_level=medium,scenario_event=threatboard_spawn

# Acute HRV alert
performance,physiomonitor,hrv_acute_alert,timestamp=1732800060.456,type=rmssd_drop,value=-1.8,baseline_rmssd=52.1,current_rmssd=38.2

# Overload detection
performance,physiomonitor,hrv_overload,timestamp=1732800120.789,lf_hf_trend=decreasing,hr_trend=increasing,confidence=0.85
```

#### 18.5.2 Export File Structure

```
sessions/user_<id>/<date>/session_<id>_<timestamp>/
├── scenario_snapshot.txt
├── config_snapshot.ini
├── plugin_versions.json
├── performance_log.csv
├── summary.json
├── summary.md
├── hrv/
│   ├── rr_intervals.csv          # Raw RR data: timestamp_ms, rr_ms, quality
│   ├── hrv_windows.csv           # Per-window metrics
│   ├── hrv_windows.parquet       # Efficient format for large datasets
│   ├── hrv_alerts.json           # Alert events with context
│   ├── hrv_baseline.json         # Baseline calibration data
│   └── polar_metadata.json       # Device info, battery, signal quality
└── lsl/
    └── streams_manifest.json     # LSL stream identifiers for sync
```

#### 18.5.3 Analysis Notebook Template / CLI Validator

```python
# Example analysis workflow (to be provided as Jupyter notebook)

import pandas as pd
import neurokit2 as nk
from pathlib import Path

def load_session(session_path: Path) -> dict:
    """Load all HRV data from a session."""
    return {
        'rr': pd.read_csv(session_path / 'hrv' / 'rr_intervals.csv'),
        'windows': pd.read_csv(session_path / 'hrv' / 'hrv_windows.csv'),
        'alerts': json.load(open(session_path / 'hrv' / 'hrv_alerts.json')),
        'summary': json.load(open(session_path / 'summary.json'))
    }

def validate_hrv_metrics(rr_df: pd.DataFrame, windows_df: pd.DataFrame) -> dict:
    """Recompute HRV metrics from raw RR and compare to logged values."""
    # Use NeuroKit2 for validation
    hrv_recomputed = nk.hrv_time(rr_df['rr_ms'].values, sampling_rate=None)
    # Compare and return discrepancy report
    pass

def correlate_with_performance(windows_df: pd.DataFrame, perf_df: pd.DataFrame) -> pd.DataFrame:
    """Align HRV windows with performance metrics for correlation analysis."""
    pass
```

> Quick validation CLI: `python tools/hrv_validate.py --session sessions/user_0001/2025-11-28/session_0001_120000`

### 18.6 Validation Protocol

#### 18.6.1 Sensor Validation

| Test | Method | Acceptance Criteria |
| --- | --- | --- |
| **RR Interval Accuracy** | Compare Polar H10 vs. medical-grade ECG (e.g., BIOPAC) on 5 participants during rest and MATB tasks | Mean absolute deviation < 5 ms; correlation r > 0.99 |
| **Signal Quality** | Assess artifact rate during movement (reaching, button pressing) | < 5% artifacts requiring interpolation |
| **Latency** | Measure BLE transmission delay from heartbeat to software timestamp | < 100 ms end-to-end |
| **Reconnection** | Simulate BLE disconnection; verify auto-reconnect and data continuity | Reconnect within 10s; no data loss during brief disconnects |

#### 18.6.2 Pipeline Validation

| Test | Method | Acceptance Criteria |
| --- | --- | --- |
| **Determinism** | Replay saved RR streams through HRV pipeline | Identical output metrics (within floating-point tolerance) |
| **Window Alignment** | Verify window boundaries align with scenario timestamps | < 50 ms offset between HRV window and scenario event |
| **Baseline Stability** | Compute baseline metrics from 5-min rest; verify stability | Coefficient of variation < 10% for RMSSD, SDNN |
| **Acute Detection** | Inject synthetic RR patterns with known RMSSD drops | Alert triggered within 1 window (30s) of threshold crossing |

#### 18.6.3 Scenario Validation

| Test | Method | Acceptance Criteria |
| --- | --- | --- |
| **Workload Differentiation** | Run low/medium/high difficulty scenarios; compare HRV metrics | Significant difference (p < 0.05) in RMSSD between difficulty levels |
| **NASA-TLX Correlation** | Collect subjective ratings post-scenario; correlate with HRV | r > 0.5 between NASA-TLX mental demand and RMSSD drop |
| **Overload Detection** | Run overload scenario; verify LF/HF pattern matches Durantin model | Overload flag triggered when LF/HF decreases despite high HR |
| **Adaptive Response** | Enable HRV-driven automation; verify difficulty adjustment | Difficulty reduced within 2 windows of sustained overload |

### 18.7 Implementation Milestones (Detailed)

| Phase | Week | Deliverables | Acceptance Criteria |
| --- | --- | --- | --- |
| **P0.1** | 1 | Polar H10 BLE connection prototype (Windows) | Stable RR streaming for 10 min |
| **P0.2** | 2 | NeuroKit2 HRV computation notebook; artifact rejection tuning | Validated against published HRV ranges |
| **P1.1** | 3 | `polarrlink.py` hardening: auto-reconnect, battery monitoring, logging | Passes reconnection test |
| **P1.2** | 4 | `HRVPipeline` class: rolling buffers, metric computation, baseline calibration | Unit tests with synthetic RR data pass |
| **P1.3** | 5 | Integration with `physiomonitor.py`: logging, export, LSL outlet | End-to-end data flow verified |
| **P2.1** | 6 | Physio widget: gauges, spark-lines, alert banners | UI renders correctly during scenario |
| **P2.2** | 7 | Mission Director/Energy Manager HRV overlays | HRV state visible alongside task widgets |
| **P2.3** | 8 | `automationhooks.py` HRV rules: threshold triggers, difficulty adjustment | Automation rules fire correctly |
| **P3.1** | 9 | Fighter scenarios: HPA-Basic, HPA-BFM, HPA-Overload | Scenarios run without errors |
| **P3.2** | 10 | UAV scenarios: UAS-Basic, UAS-BVLOS, UAS-Swarm | Scenarios run without errors |
| **P3.3** | 11 | Hybrid MUM-T scenarios | Scenarios run without errors |
| **P4.1** | 12 | Regression scripts: replay logs, verify determinism | All regression tests pass |
| **P4.2** | 13 | Analysis notebook template; documentation updates | Notebook runs on exported data |
| **P4.3** | 14 | Final validation: sensor, pipeline, scenario tests | All acceptance criteria met |

### 18.8 References – HRV Combat Scenario Integration

#### 18.8.1 MATB & Workload Assessment

1. **Pontiggia et al. 2024**: "MATB for assessing different mental workload levels"
   - Journal: Frontiers in Physiology
   - DOI: 10.3389/fphys.2024.1408242
   - PDF: https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2024.1408242/pdf

2. **Fan et al. 2022**: "Effects of Noise Exposure and Mental Workload on Physiological Responses during Task Execution"
   - Journal: International Journal of Environmental Research and Public Health
   - DOI: 10.3390/ijerph191912434

3. **Tiwari et al. 2019**: "Multi-Scale Heart Beat Entropy Measures for Mental Workload Assessment of Ambulant Users"
   - Journal: Entropy
   - DOI: 10.3390/e21080783

4. **Festa et al. 2025**: "Physiological measurement of situation awareness: A study of the validity of EEG and fNIRS during performance and automation monitoring in a complex task"
   - Journal: Ergonomics
   - DOI: 10.1080/00140139.2025.2553130

5. **Di Cesare et al. 2024**: "AeroStim: A NASA MATB-II Evolution"
   - Conference: IEEE TechDefense
   - DOI: 10.1109/TechDefense63521.2024.10863481

#### 18.8.2 Fighter Pilot & Military Aviation

6. **Koskelo et al. 2024**: "Cardiac autonomic responses in relation to cognitive workload during simulated military flight"
   - Journal: Applied Ergonomics
   - DOI: 10.1016/j.apergo.2024.104370
   - PubMed: 39186837

7. **Hidalgo-Muñoz et al. 2018**: "Cardiovascular correlates of emotional state, cognitive workload and time-on-task effect during a realistic flight simulation"
   - Journal: International Journal of Psychophysiology
   - DOI: 10.1016/j.ijpsycho.2018.04.002
   - PubMed: 29627585

8. **Wanyan et al. 2014**: "Improving pilot mental workload evaluation with combined measures"
   - Journal: Bio-Medical Materials and Engineering
   - DOI: 10.3233/BME-141041
   - PubMed: 25226928

9. **Durantin et al. 2014**: "Using near infrared spectroscopy and heart rate variability to detect mental overload"
   - Journal: Behavioural Brain Research
   - DOI: 10.1016/j.bbr.2013.10.042
   - PubMed: 24184083

10. **van Weelden et al. 2025**: "Assessment of individual and dyadic workload of student and instructor pilots in real and simulated flight"
    - Journal: Applied Ergonomics
    - DOI: 10.1016/j.apergo.2025.104606
    - PubMed: 40819550

#### 18.8.3 UAV & Remote Piloting

11. **Alharasees & Kale 2024**: "Human Factors and AI in UAV Systems: Enhancing Operational Efficiency Through AHP and Real-Time Physiological Monitoring"
    - Journal: Journal of Intelligent & Robotic Systems
    - DOI: 10.1007/s10846-024-02188-y

12. **Yu et al. 2019**: "Multi-modal physiological sensing approach for distinguishing high workload events in remotely piloted aircraft simulation"
    - Journal: Human-Intelligent Systems Integration
    - DOI: 10.1007/s42454-020-00016-w

13. **Hajra et al. 2020**: "A comparison of ECG and EEG metrics for in-flight monitoring of helicopter pilot workload"
    - Conference: IEEE SMC
    - DOI: 10.1109/SMC42975.2020.9283499

14. **Wilson & Russell 2007**: "Performance Enhancement in an Uninhabited Air Vehicle Task Using Psychophysiologically Determined Adaptive Aiding"
    - Journal: Human Factors
    - DOI: 10.1518/001872007X249875

#### 18.8.4 Adaptive Systems & Closed-Loop Control

15. **John et al. 2022**: "Unraveling the Physiological Correlates of Mental Workload Variations in Tracking and Collision Prediction Tasks"
    - Journal: IEEE Transactions on Neural Systems and Rehabilitation Engineering
    - DOI: 10.1109/TNSRE.2022.3157446

16. **Bian et al. 2019**: "Design of a Physiology-based Adaptive Virtual Reality Driving Platform for Individuals with ASD"
    - Journal: ACM Transactions on Accessible Computing
    - DOI: 10.1145/3301498

17. **Xu et al. 2020**: "Task-irrelevant Auditory Event-related Potentials as Mental Workload Indicators: A Between-task Comparison Study"
    - Conference: IEEE EMBC
    - DOI: 10.1109/EMBC44109.2020.9175957

#### 18.8.5 Python Tools & Technical Resources

18. **Makowski et al. 2021**: "NeuroKit2: A Python toolbox for neurophysiological signal processing"
    - Journal: Behavior Research Methods
    - DOI: 10.3758/s13428-020-01516-y
    - URL: https://neuropsychology.github.io/NeuroKit/

19. **Frasch 2022**: "Comprehensive HRV estimation pipeline in Python using NeuroKit2: Application to sleep physiology"
    - Journal: MethodsX
    - DOI: 10.1016/j.mex.2022.101782

20. **Polar BLE SDK**
    - URL: https://github.com/polarofficial/polar-ble-sdk

21. **Polar-Recorder-and-LSL-Restream**
    - URL: https://github.com/TomH1004/Polar-Recorder-and-LSL-Restream

22. **CogWatch Platform** (Dankovich et al. 2024)
    - Journal: HardwareX
    - URL: https://www.hardware-x.com/article/S2468-0672(24)00032-4/fulltext

#### 18.8.6 Workload Classification & Machine Learning

23. **Johnston 2025**: "Predicting Cognitive State and Workload of Aviators With Machine Learning of Physiological Data"
    - Type: Dissertation
    - Note: Used Polar H10 for ECG recording in aviator workload prediction
    - URL: https://search.proquest.com/openview/16a03d0edd61105cab42d696fbb099fa/1

24. **Ding et al. 2022**: "A machine learning approach to reduce mental fatigue risk of pilots based on HRV data"
    - Conference: IEEE
    - DOI: 10.1109/ICCAIS56082.2022.10110400
    - Note: Used Polar H10 for HRV measurement in pilot fatigue study

25. **Villani et al. 2020**: "Wearable devices for the assessment of cognitive effort for human–robot interaction"
    - Journal: IEEE Access
    - DOI: 10.1109/ACCESS.2020.3001355
    - Note: Validated Polar H10 HRV metrics for cognitive effort assessment

---

## 19. Voice Generation System (OpenAI TTS Integration)

This section documents the integration of OpenAI's gpt-4o-mini-tts model for generating Air Traffic Controller style voice communications and spoken instructions for OpenMATB scenarios.

### 19.1 Overview

The voice generation system (`tools/voice_generator.py`) provides:

1. **ATC-Style Communications**: Generate realistic Air Traffic Controller voice following ICAO/FAA radio communication standards
2. **Spoken Instructions**: Convert scenario instructions to audio for participant briefings
3. **MATB Voice Packs**: Generate complete voice file sets compatible with the communications plugin
4. **Customizable Voice Parameters**: Control accent, tone, speed, emotional range, and intonation

### 19.2 Voice Characteristics (ATC Standard)

The system generates voices with the following characteristics following ICAO/FAA standards:

| Characteristic | Setting | Description |
|----------------|---------|-------------|
| Accent | Neutral International | Clear aviation English per ICAO standards |
| Emotional Range | Calm-Professional | Authoritative but not aggressive |
| Intonation | Measured | Slight emphasis on callsigns, frequencies, altitudes |
| Speed | 140-160 WPM | Moderate pace, slower for critical information |
| Tone | Professional-Confident | Reassuring, consistent volume |

### 19.3 Available Voices

The system supports 11 OpenAI TTS voices:

| Voice | Recommended Use | Description |
|-------|-----------------|-------------|
| `coral` | ATC Female | Clear and professional |
| `onyx` | ATC Male | Deep and resonant |
| `shimmer` | Instructions Female | Bright and clear |
| `sage` | Instructions Male | Calm and measured |
| `echo` | Military Tactical | Authoritative and commanding |
| `ballad` | Urgent Alerts | Expressive and dramatic |
| `alloy` | General Purpose | Neutral and balanced |
| `nova` | Urgent Communications | Energetic and dynamic |
| `ash` | Friendly Briefings | Warm and conversational |
| `fable` | Detailed Instructions | Engaging storyteller |
| `verse` | Versatile | Adaptable for various uses |

### 19.4 Voice Presets

Pre-configured voice presets for common scenarios:

```python
VOICE_PRESETS = {
    "atc_male_en": VoicePreset(voice="onyx", speed=1.0, language="en"),
    "atc_female_en": VoicePreset(voice="shimmer", speed=1.0, language="en"),
    "atc_male_es": VoicePreset(voice="onyx", speed=0.95, language="es"),
    "atc_female_es": VoicePreset(voice="shimmer", speed=0.95, language="es"),
    "military_tactical": VoicePreset(voice="echo", speed=1.1, language="en"),
    "briefing_instructor_en": VoicePreset(voice="sage", speed=0.9, language="en"),
    "briefing_instructor_es": VoicePreset(voice="sage", speed=0.85, language="es"),
    "urgent_alert": VoicePreset(voice="ballad", speed=1.15, language="en"),
}
```

### 19.5 Usage Examples

#### Command Line Interface

```bash
# Generate single communication
python tools/voice_generator.py "November One Two Three, contact tower 118.5"

# Generate with specific voice and speed
python tools/voice_generator.py -v onyx -s 1.0 "Cleared for takeoff runway 27"

# Generate full phonetic alphabet
python tools/voice_generator.py --phonetic

# Generate MATB voice pack (English male)
python tools/voice_generator.py --matb-pack --idiom english --gender male

# Generate MATB voice pack (Spanish female)
python tools/voice_generator.py --matb-pack --idiom spanish --gender female
```

#### Python API

```python
from tools.voice_generator import ATCVoiceGenerator, VoiceConfig

# Basic usage
generator = ATCVoiceGenerator()
result = generator.generate_communication("November One Two Three, contact tower 118.5")

# Custom configuration
config = VoiceConfig(
    voice="onyx",
    speed=1.0,
    accent="neutral",
    emotional_range="moderate",
    intonation="measured",
    language="en",
)
generator = ATCVoiceGenerator(config=config)

# Generate callsign audio
result = generator.generate_callsign_audio("ABC123")

# Generate frequency audio
result = generator.generate_frequency_audio(118.5)

# Generate instruction audio
result = generator.generate_instruction_audio(
    instruction_text="Welcome to the Multi-Attribute Task Battery...",
    scenario_name="uas_basic",
    language="es",
)
```

### 19.6 Streamlit Integration

The voice generator is integrated into the Configuration Portal (`tools/config_portal.py`) with a dedicated tab:

1. **🎙️ Voice Generator Tab**: Full voice generation interface
   - Single text generation
   - Callsign generation
   - Frequency generation
   - Instruction script generation
   - Phonetic alphabet generation
   - MATB voice pack generation

2. **📖 Instrucciones Tab**: Generate spoken instructions
   - Select scenario
   - Choose voice language (Spanish/English)
   - Select voice preset
   - Generate and play audio

### 19.7 MATB Communications Plugin Integration

Generated voice files are compatible with the existing communications plugin structure:

```
includes/sounds/
├── english/
│   ├── male/
│   │   ├── 0.wav through 9.wav (digits)
│   │   ├── a.wav through z.wav (letters)
│   │   ├── nav_1.wav, nav_2.wav, com_1.wav, com_2.wav
│   │   ├── radio.wav, frequency.wav, point.wav
│   │   └── empty.wav
│   └── female/
│       └── (same structure)
├── spanish/
│   ├── male/
│   └── female/
└── generated/
    ├── phonetic/
    ├── phrases/
    ├── callsigns/
    ├── frequencies/
    └── instructions/
```

### 19.8 API Key Configuration

The system requires an OpenAI API key. Configure using one of these methods:

1. **Environment Variable**:
   ```bash
   export OPENAI_API_KEY=sk-your-key-here
   ```

2. **.env File** (in project root):
   ```
   OPENAI_API_KEY=sk-your-key-here
   ```

⚠️ **Security Note**: Never commit API keys to version control. The `.env` file should be in `.gitignore`.

### 19.9 Voice Instruction Templates

The system includes specialized instruction templates for ATC communications:

#### English ATC Template
```
You are a professional Air Traffic Controller.

Voice Characteristics:
- Accent: Clear, neutral international aviation English (ICAO standard)
- Emotional range: Calm, professional, authoritative but not aggressive
- Intonation: Measured, with slight emphasis on key words
- Speed: Moderate pace (~140-160 words per minute)
- Tone: Professional, confident, reassuring

Radio Communication Standards (ICAO/FAA):
- Use standard aviation phraseology
- Pronounce numbers clearly (niner for 9, tree for 3, fife for 5)
- Pause briefly between key elements
- Maintain consistent rhythm and cadence
```

#### Spanish ATC Template
```
Eres un Controlador de Tráfico Aéreo profesional.

Características de Voz:
- Acento: Español claro y neutro con terminología aeronáutica internacional
- Rango emocional: Calmado, profesional, autoritario pero no agresivo
- Entonación: Medida, con ligero énfasis en palabras clave
- Velocidad: Ritmo moderado (~140-160 palabras por minuto)
- Tono: Profesional, confiado, tranquilizador
```

### 19.10 Caching System

The voice generator includes an intelligent caching system:

- Generated audio files are cached based on text + configuration hash
- Cache location: `.voice_cache/` in project root
- Cache management via `clear_cache()` and `get_cache_size()` methods
- Streamlit UI includes cache management controls

### 19.11 Performance Metrics

| Metric | Value |
|--------|-------|
| Model | gpt-4o-mini-tts |
| Latency | ~1-3 seconds per generation |
| Max Input | 4096 characters |
| Output Formats | mp3, wav, opus, aac, flac, pcm |
| Speed Range | 0.25x to 4.0x |

### 19.12 Research Applications

The voice generation system supports several research applications:

1. **Standardized Communications**: Ensure consistent voice quality across all participants
2. **Multilingual Studies**: Generate identical communications in multiple languages
3. **Workload Manipulation**: Vary speech rate and complexity to modulate workload
4. **Accessibility**: Provide audio instructions for participants with reading difficulties
5. **Replication**: Generate identical voice stimuli for study replication

### 19.13 References

1. **OpenAI TTS Documentation**: https://platform.openai.com/docs/models/gpt-4o-mini-tts
2. **ICAO Radiotelephony Standards**: Doc 9432 - Manual of Radiotelephony
3. **FAA Phraseology**: AIM Chapter 4, Section 2 - Radio Communications Phraseology
4. **NATO Phonetic Alphabet**: ICAO/ITU phonetic alphabet standard

---

**Implementation Credit**: Research compilation and development plan by **Dr Diego Malpica, Aerospace Medicine**.

**Document Version**: 2.1 – Added Voice Generation System (OpenAI TTS Integration)