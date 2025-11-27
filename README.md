
# OpenMATB: An open-source version of the Multi-Attribute Task Battery (MATB)

First presented at a NASA Technical memorandum (Comstock & Arnegard, 1992), the Multi-Attribute Task Battery (MATB) contained a set of interactive tasks that were representative of those performed in aircraft piloting. The MATB requires participants to engage in four tasks presented simultaneously on a computer screen. They consist of (1) a monitoring task, (2) a tracking task, (3) an auditory communication task, and (4) a resources management task. The display screen also encompasses a scheduling view (5) for displaying a chart of incoming task events


<img src=".img/capture.png" alt="OpenMATB screen capture" width="600" />

Almost thirty years have passed since the first iteration of the MATB implementation (Comstock & Arnegard, 1992), different requirements for up to date research are no longer satisfied.

OpenMATB aims to provide an open-source re-implementation of the multi-attribute task battery. It promotes three aspects:
1. tasks customization for full adaptation of the battery,
2. software extendability to easily add new features, 
3. experiment replicability to provide significant results.

Those aspects are detailed in: 

Cegarra, J., Valéry, B., Avril, E., Calmettes, C., & Navarro, J. (2020) OpenMATB: A Multi-Attribute Task Battery promoting task customization, software extensibility and experiment replicability. *Behavior Research Methods*, 52, 1980–1990. https://doi.org/10.3758/s13428-020-01364-w


Contact : <a href="mailto:julien.cegarra@univ-jfc.fr">julien.cegarra AT univ-jfc.fr</a>; <a href="mailto:benoit.valery@univ-jfc.fr">benoit.valery AT univ-jfc.fr</a> 


## Requirements

The last version requires Python 3.9 and only depends on the following third-part libraries:

- [pyglet](https://github.com/pyglet/pyglet)
- [pyparallel](https://github.com/pyserial/pyparallel)
- [rstr](https://github.com/leapfrogonline/rstr)
- [pylsl](https://github.com/chkothe/pylsl)

The program is compatible with Windows, Mac and Linux systems. To run perfectly, the software requires only a personal computer and a joystick for the tracking task.

## Cross-platform installation

The first thing to do is to [install python 3.9](https://www.python.org/downloads/) on your computer.

To execute OpenMATB on most platforms, simply clone the current repository to a given local folder. Then, make sure you installed the correct python libraries with pip. The correct library versions are written in `requirements.txt`. You can use the `-r` flag of `pip` to install everything at once.

(In the commands below, replace `python` with `py`, under Windows)

```bash
python -m pip install -r requirements.txt
```

You can now launch OpenMATB by executing the `main.py` file with python 3.9.

```bash
python main.py
```

### Virtual environment

If you want to create a dedicated python installation (so various python projects won’t overlap), you might want to install a virtual environment in your local repository. To do so, follow the instructions detailed on this [related page](https://docs.python.org/3.9/tutorial/venv.html).

**Warning:** be sure to create the virtual environment into a directory named `.venv`. If you want to use an other name, make sure to change the `main.py` [shebang](https://docs.python.org/3.9/tutorial/appendix.html#tut-scripts) (`#! .venv/bin/python3.9`) that allows its direct execution with the distribution installed in the virtual environment.

Once the virtual environment is set, you must activate it to install the required dependencies into it:

- **Under Linux**: `source .venv/bin/activate`
- **Under Windows**: `.venv\Scripts\activate.bat` (see [this page](https://docs.python.org/3.9/tutorial/venv.html) for more information).

Now that your virtual environment is activated, just install the dependencies as you would do for a "global" python distribtion.

```bash
python -m pip install -r requirements.txt
```

Finally, you can simply execute the `main.py`. Two possibilities here :

1. You can activate the OpenMATB virtual environment and type `python main.py` in the shell;
2. Or you can execute `main.py` and let the shebang finds the virtual distribution for you. In that case, (a) no need to activate the virtual environment, (b) be sure that you made the `main.py` file executable.


### Use of compiled source (coming soon)

If you don't mind not seeing all the source files, you might want to use compiled versions of the software. The good thing here is that you don't have to install neither python nor its dependencies to make OpenMATB working.

- **For Linux**: [COMING SOON]()
- **For Windows**: [COMING SOON]()


## Basic example of OpenMATB usage

*More detailed instructions are available in the Tutorials (wiki) section below.*

When executed, the main file basically inspects the `config.ini` variables, that are `language`**, `screen_index`, `fullscreen`, `scenario_path` and `clock_speed`. The most important is the `scenario_path` variable because it defines what scenario textfile should be used for the sequencing and the setting of the protocol. 

(**For now, french (fr_FR) and english (en_EN) locales are available, but feel free to [develop your own translation](https://github.com/juliencegarra/OpenMATB/wiki/Internationalization), it's fast and easy.)

A scenario is a text file which specifies, for each module of the program (for instance the system monitoring task), all the events that it must execute, as well as their onset time. For instance, try this basic scenario, which starts the four main tasks of the MATB, and stop them after 2 minutes and a half. (Note how each command — `start` and `stop` in this example — is associated with an alias: for instance `sysmon` for the system monitoring task.)

*Content of `includes/scenarios/basic.txt`*:
```
0:00:00;sysmon;start
0:00:00;track;start
0:00:00;scheduling;start
0:00:00;resman;start
0:00:00;communications;start
0:02:30;sysmon;stop
0:02:30;track;stop
0:02:30;communications;stop
0:02:30;resman;stop
0:02:30;scheduling;stop
```

Through the scenario file, you can command the various tasks or modules, modify their own parameters, and trigger interesting events. The more you know about the scenario file syntax and modules options, the more you will be able to customize your OpenMATB scenario. See [this tutorial](https://github.com/juliencegarra/OpenMATB/wiki/How-to-build-a-scenario-file) for more information.

Once the scenario has ended, information about what happended is stored as comma-separated values (.csv) into the `sessions` directory. This log file contains all that is needed to understand what happened during the scenario and undertake performance calculations. It has the following form:

```
logtime,totaltime,scenario_time,type,module,address,value
13869.194646,0,0,input,keyboard,ENTER,release
13869.210557,0.018296,0,state,sysmon,"task_title, text",SURVEILLANCE
13869.210933,0.018296,0,state,sysmon,"automode, text",
13869.232539,0.018296,0,event,sysmon,self,start
13869.238017,0.058883,0.018296,state,track,"task_title, text",POURSUITE
13869.238209,0.058883,0.018296,state,track,"automode, text",
13869.24057,0.058883,0.018296,event,track,self,start
13869.240641,0.058883,0.018296,performance,track,cursor_in_target,1
13869.240664,0.058883,0.018296,performance,track,center_deviation,0.0
...
14307.553591,150.022335,150.008259,state,track,"reticle, cursor_relative","(-98.86763793277942, 149.15892483599305)"
14307.553667,150.022335,150.008259,state,track,"reticle, cursor_color","(241, 100, 100, 255)"
14307.566581,150.038228,150.022335,event,track,self,stop
14307.586672,150.054776,150.038228,event,communications,self,stop
14307.610734,150.071739,150.054776,event,resman,self,stop
14307.620835,150.088269,150.071739,event,scheduling,self,stop
14307.620911,150.088269,150.071739,manual,,,end
```

Details about how each module log information are available [here](the log file).

### Mission-level KPI summaries

To align with the reliability guidance from [Docs/Manual.md](Docs/Manual.md) and the USAARL/USAF research corpus (e.g., [Multi Attribute Task Battery for Military Aircrew Assessment A Comprehensive Research Report](research/Multi Attribute Task Battery for Military Aircrew Assessment A Comprehensive Research Report.md)), OpenMATB now emits an automatic mission-level summary alongside the raw CSV logs. After every run, a JSON file named like `sessions/YYYY-MM-DD/<session>_summary.json` lists:

- Count/mean/max/min snapshots for every metric recorded via `log_performance`.
- Derived KPIs for new science-driven plugins (`missiondirector`, `senseandavoid`, `payloadmanager`, `datalink`, `threatboard`, `energymanager`) such as mission completion rate, conflict resolution rate, datalink acknowledgement rate, and over-G incidence.
- Scenario metadata (session id, scenario file, run duration) so researchers can trace summaries back to raw logs or physiological streams.

These summaries make it easier to reproduce the standardized workload bands described in the military MATB literature while keeping the raw CSV pipeline unchanged.

### Operator capacity monitor

Section 14.1 of [Docs/Manual.md](Docs/Manual.md) is now backed by an `operatorcapacity` plugin that enforces the validated “2–3 active / up to 6 supervisory” crew bands from the multi-UAV workload studies. Scenario designers can inject commands such as `operatorcapacity;set;active,2` or `operatorcapacity;set;supervisory,uav1|uav2|uav3|uav4|uav5` to log the live portfolio, while `operatorcapacity;overlap;uav1,uav2,0.65` feeds the overlap-driven supervisory limit described in the manual. The plugin widget flashes when limits are exceeded and the logger emits `operator_capacity_*` metrics so the mission summary can quantify average load, breach rate, and overlap trends alongside the rest of the MATB instrumentation.

### Platform profile orchestration

To satisfy the Section 14.2 ScanEagle/NightEagle requirements, the new `platformprofile` plugin keeps a per-UAV capability table (endurance, payload, launch/recovery method, datalink capacity, and sensor presets). Commands like `platformprofile;set;uav1,scaneagle,endurance=20h|sensors=EO/IR` instantly update the on-screen profile sheet, push endurance timers into `missiondirector`, and retune `payloadmanager` capacity/sensor lists via the shared plugin bridge. Key events (`platform_profile_set`, `platform_endurance_push`, `platform_payload_push`) are logged so performance summaries can trace when a scenario switched platforms or triggered custom overrides.

### VTOL flight manager

The new `vtolmanager` plugin implements the VTOL phase tracker described in §14.3 of [Docs/Manual.md](Docs/Manual.md). Scenario commands such as `vtolmanager;phase;vtol1,takeoff` and `vtolmanager;phase;vtol1,transition` update a live status table, drain the scripted power budget using per-phase multipliers, and require `vtolmanager;confirm;vtol1` acknowledgements whenever a transition phase starts. The logger emits `vtol_phase_change`, `vtol_transition_pending/confirm/overdue`, and `vtol_power_warning/critical` so the performance summary can quantify how often trainees respected confirmation windows and how close each sortie ran to the VTOL endurance margins.

### Scenario coverage & metrics

- **Reference scenarios**: `includes/scenarios/uas_basic.txt` and `uas_bvlos.txt` cover foundational UAS workloads, `uas_military_ex.txt` adds ScanEagle/NightEagle patrols with platform/VTOL/automation hooks, and `hpa_overlay.txt` plus `hpa_qra_ex.txt` layer the fighter/Quick Reaction Alert toolchain (Energy Manager, Threat Board, Weapons Inventory, Emergency Stack). The `tools/scenario_templates.py` CLI can regenerate these studies with custom durations/difficulty codes so labs can hand out consistent workloads.
- **Mission metrics**: Every plugin writes structured `performance,<module>,<metric>` rows which the post-run summary converts into KPIs (mission completion rate, conflict resolution rate, payload over-bandwidth exposure, datalink acknowledgement rate, VTOL power warnings, etc.). Reviewing `sessions/.../*_summary.json` gives a concise single-file overview, whereas the CSV log retains the raw timeline for deeper analytics.
- **Physio/automation alignment**: Because Mission Director, Operator Capacity, Platform Profile, and VTOL Manager all log derived metrics, researchers can correlate them with HRV/LSL streams, automation hook toggles, or adaptive scenarios without reverse-engineering ad-hoc strings.

### BVLOS / UTM / MUM-T extensions

Section 14.6–14.8 of [Docs/Manual.md](Docs/Manual.md) is now fully implemented through six dedicated plugins designed for BVLOS certification studies and manned–unmanned teaming drills:

- `bvlossensory` — Uses `bvlossensory;apply;visual,0.7,15` or `...;both,1.0,10` to dim the interface and mute cues, plus `...;clear;visual` to restore. Every event logs `sensory_cue_removed` / `sensory_cue_restore` so researchers can align workload spikes with the cue deprivation windows documented by the FAA BVLOS ARC.
- `controltransfer` — Tracks custody swaps via `controltransfer;initiate;TX1,UAV1,GCS-A,GCS-B,Lost link,30`, `...;acknowledge;TX1,GCS-B`, `...;complete;TX1`, or `...;fail;TX1,radio`. It emits `control_transfer_*` metrics and flags timeouts automatically when acknowledgements miss the scripted deadline.
- `flighttermination` — Injects termination decisions with `flighttermination;prompt;FT1,Engine fire,CRITICAL,5` and captures operator intent through `flighttermination;decide;FT1,TERMINATE,0.9`. Timeouts and responses are logged as `termination_*` rows for replay against mission outcomes or subjective data.
- `utmintegration` — Simulates UTM/TFR updates (`utmintegration;restriction;R1,TFR Sector 3,HIGH,90`), reroutes (`...;replan;R1`), and violations (`...;violation;R1,late turn`). Each state change logs `utm_restriction_received`, `route_replan`, `restriction_violation`, `restriction_clear`, and automatic expirations so BVLOS corridor experiments can quantify compliance.
- `mumtcoordination` — Represents manned pilot vs. UAS operator coordination: `mumtcoordination;role;pilot,Lead`, `...;request;REQ1,Engage bandit,20,pilot,operator`, `...;ack;REQ1,operator`, `...;decision;REQ1,APPROVED`. Logged metrics (`mumt_coordination_request/ack`, `mumt_decision_made`, timeouts) make it easy to evaluate latency and agreement quality during teaming drills.
- `dataoverload` — Recreates high-volume sensor storms through `dataoverload;storm;3,20,EO|IR`, with operator responses captured via `dataoverload;filter;EO` and `dataoverload;miss;IR,priority target lost`. The plugin renders a lightweight HUD overlay and raises `data_overload_detected`, `information_filter_applied`, and `critical_data_missed` markers for dual-task interference studies.

All six plugins inherit the standard MATB scenario syntax, respect the deterministic logging contract, and are covered by the regression tests in `tests/test_military_plugins.py`.

### Swarm formations, sensor resource manager, and target uncertainty

- `swarmformation` keeps swarm-level context visible: `swarmformation;set;formation,line,drone1|drone2|drone3` establishes the active geometry, while `swarmformation;override;drone2,manual` / `...,auto` toggles per-vehicle overrides. The widget lists each member plus its AUTO/MANUAL state, and the logger emits `swarm_formation_set`, `swarm_formation_break`, and `swarm_formation_rejoin` so analysts can quantify when crews depart from doctrinal formations.
- `sensorresource` extends payload management with multi-sensor bandwidth tracking. Use `sensorresource;activate;UAV1,EO,Target-Alpha,12`, `sensorresource;switch;UAV1,EO_to_IR`, `sensorresource;fusion;UAV1,EO_IR`, and `sensorresource;capacity;80` to model simultaneous feeds, priorities, and link capacity. The plugin continuously sums active Mbps, flashes overdue overlays when the configured limit is exceeded, and logs `sensor_activate`, `sensor_switch`, `sensor_fusion_enable`, `sensor_priority`, and `sensor_bandwidth_exceeded`.
- `targetuncertainty` provides the ambiguous identification drills from §14.5. Scenario commands such as `targetuncertainty;spawn;TGT1,LOW,15` start a timed window, and operators answer through `targetuncertainty;identify;TGT1,Vehicle,0.65`. Metrics (`target_spawn`, `target_identified`, `target_confidence`, `target_identification_time`, `target_timeout`) capture both accuracy and latency so scenario designers can correlate them with workload or trust scores.
- `weatheroverlay` now accepts visibility penalties: `weatheroverlay;set;Fog band,0.4,eo|ir` or `weatheroverlay;impact;0.2,radar` attaches %-basis detection penalties to specific sensors and logs `visibility_impact` / `visibility_impact_clear`, making it easy to correlate degraded sensor performance with the meteorological cues described in §14.5.
- `dualtasksensor` orchestrates the dual-task training protocol from §14.5. Use `dualtasksensor;start;PhaseA,sensorresource,track`, sprinkle `dualtasksensor;switch;` and `dualtasksensor;metric;sensorresource,0.8` events during the phase, then finish with `dualtasksensor;complete;note=baseline` to emit `dual_task_performance` metrics (sensor vs. secondary task accuracy, attention switches, delta/ratio).
- `launchrecovery` fulfills the ScanEagle/NightEagle workflow: `launchrecovery;launch;UAV1,catapult,15`, `launchrecovery;recovery;UAV1,skyhook,20`, `launchrecovery;complete;UAV1,launch`, and `launchrecovery;abort;UAV1,reason` track the full timeline and emit `launch_*` / `recovery_*` metrics plus automatic timeouts.
- `vtolpower` models VTOL battery reserves independently of the flight-phase manager. Configure with `vtolpower;configure;VTOL1,100,40,20,1.5`, subtract draw with `vtolpower;draw;VTOL1,30,1.2`, recharge/reset via `vtolpower;recharge;VTOL1,10` or `vtolpower;set;VTOL1,50`, and consume the resulting `vtol_power_change`, `power_warning`, and `power_critical` logs for endurance studies. `vtolmanager` now also tracks transition stability through `vtolmanager;stability;VTOL1,0.7` and tunable thresholds via `vtolmanager;stabilitythresholds;0.5,0.8`, emitting `stability_warning`, `stability_critical`, and `stability_recover` events whenever pilots exceed or recover from scripted limits.
- `datalink` adds optional TTS playback for high-priority messages: `datalink;voice;True,PRIO|CRIT` enables audible callouts (gracefully disabling itself if `pyttsx3` is unavailable) and logs `datalink_voice_*` events so crews can correlate audio cueing with acknowledgement latency.
- `advancedtraining` automates the Easy→Hard skill-transfer playbook: `advancedtraining;start;SEQ1` kicks off the default phase order, `advancedtraining;phase;Name,mode,difficulty` overrides phases manually, `advancedtraining;metric;0.82` streams performance samples, `advancedtraining;complete;note=...` logs per-phase mean/SD/RMSSD, and `advancedtraining;transfer;0.12` records `skill_transfer_detected` verdicts for training studies.
- `autotraining` delivers the USAARL-style familiarisation block: `autotraining;start` runs tracking → sysmon → comms → resman → combined phases with on-screen instructions, `autotraining;phase;resman` forces a specific module, `autotraining;comprehension;phase,1` records checks, and `autotraining;stop` ends the run. Metrics include `training_phase_start`, `training_phase_complete`, `training_comprehension`, and `training_complete`.

These additions round out the research backlog in Docs/Manual.md §14.4–14.5, and like the other modules they are documented by regression tests for deterministic behavior.

## Tutorials

For more information about how to use OpenMATB, please refers to [our wiki](https://github.com/juliencegarra/OpenMATB/wiki).


## Major changes

Since the first release of OpenMATB, there has been a lot of changes, the main one of which are listed below.

### Version 1.2

**New plugins/features:**

- Each task (system monitoring, tracking, communications, resources management) can now be taken over by an automation, with the `automaticsolver` parameter;
- Accordingly, in the `scheduling` module, it is now possible to display up to four timelines (one per task);
- In the `scheduling` module, it is now possible to hide (no time) or reverse (remaining time) the chronometer;
- All the task plugins can now display their own feedback:
    * The `resman` plugin can now feedback the participant if the tanks are out of their tolerance area, by turning tolerance indicators to red (default) ;
    * The `communications` plugin can feedback the participant on response by displaying a green/red rectangle around the responded radio.
- Each task can now also display an overdue alarm, when a response is needed since too long (new parameters);
- A new plugin (labstreaminglayer) now allows the MATB to stream its log through the LSL communication protocol so has to synchronize it with various neurophysiological recordings.
- A `performance` plugin has ben added, which allows to display a general performance level to the participant. The rules that underly performance computation is described in…
- - A new `instructions` module is available, which allows the user to present static instructions in an HTML format, to the participant, at desired time. This includes the possibility to present images thanks to the `<img>` html tag;
- The `track` plugin now allows to reverse joystick axis;
- The tracking reticule path now sticks to the algorithm described in the initial MATB version by Comstock & Arnegard (1992);
- To avoid aberrant calculations of performance in the tracking task, due to the (potential) unequal proportions of height and width, the `equalproportions` parameters has been removed. Proportions in the tracking are now necessarily equals;
- The `pumpstatus` module (showing pump flows of the resources management task) has been removed. It has been integrated to the resources management module (`resman`), as an option (`displaystatus` parameter);
- Resources management pump states can now be either `on`, `off` or `failure` (instead of `1`, `0` or `-1`): more transparent;
- According to the original MATB version, scale arrows of the `sysmon` plugin now freezes during 1.5 second if a correct detection is made.

**Other changes:**

- Each scenario value is now finely controlled against a set of type verification methods. For instance, a `taskplacement` value must be a correct value (being in location_list = ['fullscreen', 'topmid', 'topright', 'topleft', 'bottomleft', 'bottommid', 'bottomright']), and so on, which greatly facilitates scenario debugging.
- Each scenario error is now logged into a `last_scenario_errors.log` file.
- The scenario does not need a final ending line anymore (e.g., `0:05:00;end`). Program now exits if there is no event to execute anymore and all the modules have been stopped.
- Added a `config.ini` file where to modify the main OpenMATB parameters, such as the scenario to use, the locale, the fullscreen mode...
- Switch from PySide/PyQt to the pyglet graphical library, which has the major advantage to be a pure python library.
- Can now exit OpenMATB with the Escape key + confirmation.
- OpenMATB can now be paused with the P key.
- The user can now define a global font into `config.ini`, given it is availale on his/her computer
- Areas of interest (AOI) of each task are now automatically logged at start, for further (oculometric) computations. AOIs can be displayed for debugging purpose, with the `highlight_aoi` parameter of the `config.ini` file.
- To comply with anonymity constraints, the `participantinfo` was removed and replace with a session ID, displayed at startup. This session ID (e.g., 52) is used as a suffix for session logging files.
- A particular scenario generator was added, so as to help conceiving scenario of progressive difficulty.
- Each task module now logs a serie of performance metrics as soon as their are available, to facilitate further calculations.
