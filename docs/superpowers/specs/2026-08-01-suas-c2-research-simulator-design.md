# sUAS Supervisory C2 Research Simulator — V1 Design

**Date:** 2026-08-01

**Status:** Approved design; pending implementation plan

**Target:** Offline Linux workstation, developed and verified in a headless Linux environment

**Scope:** V1 operator-in-the-loop, non-kinetic, multi-sUAS ISR research simulator

---

## 1. Purpose

Build a browser-based command-and-control research simulator in which one
operator supervises a configurable fleet of two to eight synthetic small
uncrewed aircraft systems (sUAS). The first mission family is a fictional
multi-sUAS intelligence, surveillance, and reconnaissance (ISR) area search.
The simulator must support repeatable workload and situation-awareness studies,
run entirely offline on Linux, and integrate with the repository's existing
participant, questionnaire, analysis, provenance, and export capabilities.

The simulator is a supervisory-control instrument, not a flight trainer. The
operator assigns tasks, manages exceptions, evaluates contacts, and maintains
mission coverage while deterministic synthetic autopilots fly the aircraft.

### 1.1 V1 success condition

A researcher can launch the platform on one offline Linux workstation, run a
guided practice block followed by counterbalanced LOW/MEDIUM/HIGH blocks,
supervise four or more aircraft through the browser UI, complete all workload
and situation-awareness instruments, inspect a debrief, export a complete
provenance bundle, and reproduce the final state from the recorded scenario,
seed, engine version, and command stream.

## 2. Locked product decisions

- **Primary use:** operator-in-the-loop C2 and human-factors research.
- **Mission:** multi-sUAS ISR/area search.
- **Control:** supervisory commands only; no manual piloting.
- **Deployment:** one fully offline Linux workstation.
- **Fleet:** configurable from 2 through 8 aircraft; the reference MEDIUM and
  default ad-hoc setup use 4 aircraft.
- **Terrain:** bundled fictional terrain in a local Cartesian coordinate system;
  no real-world map data in V1.
- **Research question:** workload and situation awareness as fleet and event
  demand change.
- **Mission effects:** strictly non-kinetic. Operators may search, detect,
  inspect, classify, prioritize, track, and report contacts. There are no
  engagement, weapon, targeting, or damage-effect controls.
- **Protocol:** five-minute guided practice followed by three counterbalanced
  10-minute LOW/MEDIUM/HIGH blocks.
- **Operational events:** sector assignment, autonomous search, contact
  detection/classification, battery and return-to-base management, lost-link
  recovery, and separation/conflict alerts.
- **Languages:** English and es-CO Spanish, selected before the session.
- **Scenario authoring:** strict, versioned YAML files; no graphical editor in
  V1.
- **Future fidelity:** define a simulator adapter boundary now, but ship only a
  deterministic synthetic backend in V1.

## 3. Relationship to the existing repository

The new simulator is a first-class subsystem. It does not depend on OpenMATB and
does not turn the legacy `aircraft_monitor` event script into an authoritative
simulation engine.

- `matb_integration` gains the reusable sUAS domain, engine, scenario, recording,
  replay, and metric libraries.
- `webui/backend` gains simulation session persistence, lifecycle orchestration,
  REST endpoints, and a WebSocket stream.
- `webui/frontend` gains mission setup, live operator console, and debrief/replay
  routes.
- Existing participant, visit, questionnaire, scenario provenance, statistics,
  and research bundle code is reused or extended through explicit adapters.
- OpenMATB remains available for classical MATB experiments.
- `aircraft_monitor` remains a legacy demo. Concepts may be ported, but its
  mutable single-aircraft model and scripted generator are not runtime
  dependencies of the new subsystem.

No existing OpenMATB CSV workflow or endpoint may be broken by this work.

## 4. Architecture

```text
Versioned YAML scenario
          │
          ▼
 Scenario loader + validator ───────► immutable scenario manifest
          │
          ▼
 Deterministic simulation core ◄──── operator commands
          │                              ▲
          ├── versioned snapshots ───────┤ WebSocket
          ├── domain events              │
          ├── probes                     │
          ▼                              │
 Append-only session recorder       Browser C2 console
          │                              │
          ├── checkpoints                └── debrief/replay
          ├── derived metrics
          └── provenance export bundle
```

### 4.1 Package boundaries

```text
matb_integration/suas/
  domain/                 Immutable definitions and authoritative state types
    enums.py              Lifecycle, aircraft, task, contact, link, alert enums
    geometry.py           Points, polygons, routes, containment, separation
    models.py             Aircraft, contact, sector, mission and world state
    commands.py           Operator command payloads and validation results
    events.py             Ordered domain-event envelope and payloads
  scenarios/
    schema.py             Strict Pydantic YAML schema
    loader.py             Safe loading, cross-field validation, normalization
    manifest.py           Canonical representation, hashes and provenance
    profiles.py           Practice and LOW/MEDIUM/HIGH demand profiles
  engine/
    clock.py              Integer fixed-step simulation clock
    reducer.py            Commands/events applied to authoritative state
    routes.py             Transit and lawn-mower search-route generation
    vehicles.py           Synthetic vehicle state transitions and movement
    sensors.py            Coverage and deterministic contact observations
    links.py              Link degradation/loss and lost-link procedure
    separation.py         Advisory/critical proximity detection
    runtime.py            Tick orchestration and stable subsystem ordering
  adapters/
    base.py               VehicleBackend protocol
    synthetic.py          V1 deterministic backend
  recording/
    recorder.py           Append-only event/command/probe writer
    checkpoints.py        Atomic compressed state checkpoints
    replay.py             Rebuild and verify a recorded session
    artifacts.py          Metrics, manifests, checksums and bundle layout
  metrics/
    mission.py            Coverage, contact, timeliness and asset metrics
    research.py           Workload, response, command and SAGAT measures

webui/backend/app/
  simulation_models.py    SQLModel metadata tables for native sessions
  simulation_runtime.py   Single active-session manager and controller lease
  routers/simulation.py   Lifecycle, command, state, debrief and artifact API
  websocket/simulation.py Versioned real-time event/snapshot transport

webui/frontend/src/
  app/mission/setup/      Participant, protocol, scenario and language setup
  app/mission/            Full-screen live operator console
  app/mission/debrief/    Timeline, replay and component outcomes
  components/mission/     Map, fleet, alerts, contacts, commands and probes
  lib/simulation/         API client, stream client, store and translations
```

Files may be split further during implementation when a responsibility would
otherwise become difficult to understand or test, but responsibilities must not
be collapsed across the domain, transport, persistence, and presentation
boundaries above.

### 4.2 Runtime ownership

The FastAPI process owns the authoritative runtime. The browser renders state
and requests commands; it never integrates movement, resolves contacts, decrements
battery, or decides outcomes. SQLite owns session metadata, while append-only
artifacts own the high-rate experimental record. Only one session may be active
and only one browser may hold its controller lease. Additional browsers are
read-only observers.

## 5. Determinism and time

- The authoritative simulation step is exactly 100 milliseconds.
- Browser snapshots are emitted every 250 milliseconds (4 Hz).
- A complete checkpoint is written every five simulated seconds.
- Commands are assigned a server sequence number and applied at the next tick
  boundary.
- Within a tick, processing order is fixed: lifecycle changes, operator
  commands, link state, vehicle state, movement, battery, sensor observations,
  coverage, separation, alerts, probes, and block completion.
- Entities are processed in stable lexical identifier order.
- Randomness comes only from named, independent PCG32 streams seeded from the
  first 64 bits of
  `SHA-256("<scenario-seed>\0<subsystem-name>\0<entity-id>")`. Adding a new
  random consumer to one subsystem must not perturb another subsystem.
- Authoritative time uses integer milliseconds, positions and route points use
  integer millimetres, headings use integer millidegrees, and energy uses
  integer engine energy units with an integer remainder carried between ticks.
  Display conversions are never fed back into state. Keys and entity arrays are
  ordered before canonical JSON hashing.
- Replay requires the exact engine semantic version recorded in the manifest.
  A different engine version may import and view the artifacts but may not claim
  a matching deterministic replay unless the final state and event hashes match.
- Wall-clock timestamps are recorded for audit but never drive simulation truth.
- Pausing freezes simulation time. Questionnaire completion time is recorded
  separately in wall-clock and simulation-clock fields.

## 6. Scenario format and validation

YAML is parsed with `yaml.safe_load` and then validated by strict Pydantic
models. Unknown keys are errors. Scenario content may not contain executable
expressions, imports, URL references, or paths outside its scenario package.

A scenario declares:

- schema version, scenario ID, title translations, author, and description;
- seed, terrain bounds, display grid, home base, and initial view;
- polygonal search sectors and restricted zones;
- advisory and critical separation distances;
- 2–8 aircraft with initial state, performance, battery, link, and sensor
  parameters;
- static V1 contacts with hidden truth, priority, location, observation stages,
  and report requirements;
- scheduled link degradations/losses and recovery times;
- practice/LOW/MEDIUM/HIGH block profile and response windows;
- ISA schedule, SAGAT freeze window and probe bank;
- post-block questionnaire selection;
- termination conditions and metric thresholds.

Cross-field validation rejects at least:

- duplicate IDs;
- fewer than two or more than eight aircraft;
- entities outside terrain bounds;
- invalid or self-intersecting polygons;
- overlapping restricted and home-base geometry that prevents departure;
- critical separation greater than or equal to advisory separation;
- nonpositive speeds, capacities, ranges, durations, or response windows;
- probabilities outside `[0, 1]`;
- event times outside their block;
- a required SAGAT probe that cannot be answered from authoritative state;
- a mission in which an aircraft cannot reach any assigned sector and return
  under its declared nominal energy model.

The normalized scenario, questionnaire hashes, engine version, UI version,
language, participant block order, and all workload parameters are written to a
manifest before the session starts. The session uses that immutable normalized
copy even if the source YAML is later edited.

## 7. Simulation model

### 7.1 Mission space

V1 uses a fictional two-dimensional Cartesian mission area measured in metres.
It contains a home base, named search sectors, transit corridors, restricted
zones, and static contacts. Altitude is an aircraft attribute used for display
and configuration, but V1 movement and separation are planar. Terrain has no
effect on radio propagation or flight performance in V1.

Search coverage is accumulated on a deterministic grid whose cell size is
declared by the scenario. A cell becomes observed when it lies inside a healthy
sensor footprint during a scan. Coverage history is monotonic within a block.

### 7.2 Aircraft state

Each aircraft has authoritative state for:

- identifier and display label;
- position, heading, speed, and configured altitude;
- battery energy, predicted reserve at home, and sensor consumption;
- link state and last successful communication time;
- sensor state and scan schedule;
- assigned sector, active route, current route leg, and mission progress;
- autonomy mode and previous mode;
- active alerts and last accepted command.

The V1 autonomy state machine is:

```text
READY ──assignment──► TRANSIT ──arrival──► SEARCH
                          │                   │
                          └────hold──────────►HOLD
                                               │
                                  resume───────┘

TRANSIT / SEARCH / HOLD ──RTB──► RETURN_TO_BASE ──home──► RECOVERED

Any airborne state ──link loss──► LOST_LINK_PROCEDURE
Any airborne state ──energy exhausted away from home──► MISSION_FAILED
```

The default lost-link procedure holds for 10 simulated seconds and then flies a
direct return-to-base route. Operator aircraft commands are rejected while the
link is lost. If the link recovers, the aircraft retains its current safe mode
and requires an explicit operator reassignment to resume search.

### 7.3 Movement and energy

The synthetic backend flies constant-speed straight route legs and changes to
the next leg heading at a waypoint. Leg advancement uses fixed-point integer
distance and carries division remainders between ticks; no floating-point
display value feeds back into movement. It is not a six-degree-of-freedom model.
Energy decreases with elapsed time using separate idle, transit, search, and
sensor loads declared per aircraft. Return reserve is recomputed from route
distance, configured return speed, and a fixed scenario margin. The engine
raises a reserve advisory before the predicted margin is consumed and a
critical alert when a safe nominal return is no longer predicted.

Commands that would create an invalid route, enter a restricted zone, exceed
mission bounds, or require energy beyond the critical reserve are rejected
without changing state.

### 7.4 Sensors and contacts

Sensors scan at a scenario-defined interval within a circular V1 footprint.
Each aircraft/contact pair has an independent deterministic observation stream.
Successful scans increase a separate `evidence_level` from `none` through
`detected` to `inspectable`. The UI exposes only that evidence and never hidden
truth. Operator actions, rather than sensor scans, advance the workflow below.

The non-kinetic contact workflow is:

```text
UNDETECTED → DETECTED → INSPECTED → CLASSIFIED → PRIORITIZED → REPORTED
```

`INSPECT_CONTACT` is accepted only when evidence is `inspectable`. Operators may
correct a classification or priority before reporting. Reports are immutable
audit events; a correction creates a new report whose `replaces_report_id`
references the earlier report. V1 contact truth uses abstract categories
(`routine`, `priority`, and `uncertain`) rather than real-world target or weapon
taxonomies.

### 7.5 Separation and conflict alerts

The engine evaluates pairwise planar distance after movement on every tick. A
crossing below the scenario's advisory threshold opens an advisory alert; a
crossing below the critical threshold records a separation violation and opens
a critical alert. Operators resolve conflicts through hold, sector
reassignment, or a valid waypoint/route command. The synthetic autopilot does
not silently resolve a research-condition conflict unless the scenario
explicitly starts that aircraft in a protected-return mode.

## 8. Operator commands

V1 accepts only these authoritative command families:

- `ASSIGN_SECTOR(aircraft_id, sector_id)`
- `SET_WAYPOINT(aircraft_id, x_m, y_m)`
- `HOLD(aircraft_id)`
- `RESUME_MISSION(aircraft_id)`
- `RETURN_TO_BASE(aircraft_id)`
- `ACKNOWLEDGE_ALERT(alert_id)`
- `INSPECT_CONTACT(contact_id)`
- `CLASSIFY_CONTACT(contact_id, classification)`
- `SET_CONTACT_PRIORITY(contact_id, priority)`
- `REPORT_CONTACT(contact_id, note_code, replaces_report_id=None)`
- `SUBMIT_ISA(probe_id, rating)`
- `SUBMIT_SAGAT(probe_id, answer)`
- `SUBMIT_POST_BLOCK_SCALE(scale_id, answers)`

Each request includes a client-generated command UUID, expected state version,
session ID, block ID, and controller lease. The backend supplies the authoritative
sequence, receive time, applied tick, result code, and state version. Duplicate
UUIDs return the first result. Stale or invalid commands are recorded but cause
no state mutation.

## 9. Research protocol

### 9.1 Session structure

1. Researcher selects participant, scenario, language, and protocol.
2. The system validates and freezes the scenario manifest.
3. The operator completes a five-minute guided practice with two aircraft.
4. The operator completes three 10-minute blocks in the participant's existing
   Latin-square LOW/MEDIUM/HIGH order.
5. Each block includes scheduled ISA probes and one seeded SAGAT freeze.
6. NASA-TLX and Bedford are administered after each block.
7. The researcher reviews block validity and completes or aborts the session.
8. The system derives outcomes, creates the debrief, and seals the export
   checksums.

### 9.2 Default demand profiles

The bundled reference protocol uses these initial, explicitly unvalidated
manipulation profiles. They are software defaults for pilot testing, not claims
of psychometric calibration:

| Profile | Aircraft | Contacts | Lost-link events | Conflict events | Required-action window | ISA interval |
|---|---:|---:|---:|---:|---:|---:|
| Practice | 2 | 2 | 0 | 0 | 30 s | 150 s |
| LOW | 2 | 3 | 0 | 1 | 30 s | 180 s |
| MEDIUM | 4 | 6 | 1 | 2 | 20 s | 120 s |
| HIGH | 8 | 12 | 2 | 3 | 12 s | 90 s |

The bundled reference profiles manipulate several factors together and therefore
estimate combined supervisory demand. A study that needs a causal estimate for
fleet size, contact rate, or failure rate must use separate YAML profiles that
vary only the factor under study. Every factor is retained in the manifest and
long-format export.

### 9.3 Probes and freezes

- ISA uses the existing 1–10 response scale.
- A SAGAT freeze pauses simulation, immediately conceals the map, fleet state,
  contacts, and alerts, and then presents only the scheduled probe set.
- SAGAT answers are scored against a state snapshot captured at the freeze tick.
- The freeze duration affects wall-clock time but not simulation time.
- A disconnected client during a probe pauses the protocol and marks the probe
  interrupted; it is not silently reissued or scored as a miss.
- NASA-TLX and Bedford reuse the repository's existing bilingual assets and
  scoring conventions.

## 10. Operator interface

The mission console is a full-screen browser UI. Development and automated QA
run in the headless server environment; the delivered UI remains intended for a
local browser on the offline workstation.

```text
┌ Session / block / timer / workload / connection / language ┐
├──────────────┬──────────────────────────────┬───────────────┤
│ Fleet status │                              │ Alert queue   │
│ UAS-01       │     Tactical mission map     │ Contacts      │
│ UAS-02       │                              │ Required acts │
│ UAS-03       │  sectors, routes, aircraft,  │ Probe status  │
│ UAS-04       │  contacts, zones, conflicts  │               │
├──────────────┴──────────────────────────────┴───────────────┤
│ Selected aircraft: assign sector · waypoint · hold · RTB   │
└─────────────────────────────────────────────────────────────┘
```

### 10.1 Mission setup

`/mission/setup` allows the researcher to choose a pseudonymized participant,
visit, scenario, protocol, and language, validate the scenario, inspect its
manifest summary, and launch practice. It does not expose arbitrary scenario
editing. A clear research-use acknowledgement states that the simulator is not
a certified operational or flight-safety system.

### 10.2 Live console

- A React SVG map renders the fictional grid, sector polygons, restricted zones,
  home base, aircraft, routes, sensor footprints, contacts, and conflict lines.
  It requires no tile server or network access.
- Map zoom, pan, reset-view, layer visibility, and keyboard selection do not
  mutate authoritative mission state.
- The fleet panel shows task, link, battery, sensor, route, reserve, and alert
  status for every aircraft.
- Selecting an aircraft reveals only commands valid for its current state;
  invalid commands remain explainable through disabled-control help text.
- The contact queue supports inspect, classify, prioritize, and report actions.
- The alert queue sorts unacknowledged critical, unacknowledged advisory,
  acknowledged critical, and acknowledged advisory items in that order, then by
  opening sequence.
- A persistent connection indicator distinguishes `live`, `reconnecting`,
  `paused`, `observer`, and `disconnected` states with text and shape as well as
  color. The language shown in the top bar is informational because the session
  language is frozen at setup.
- Research probes take focus without allowing background commands.
- The language is selected before practice, frozen for the session, and written
  to the manifest.

### 10.3 Debrief

`/mission/debrief` provides:

- time-addressable replay of aircraft, coverage, contacts, alerts, and commands;
- block and full-session timelines;
- component outcomes and protocol deviations;
- ISA series, SAGAT results, NASA-TLX, and Bedford summaries;
- command rejection and correction details;
- export and deterministic replay-verification status.

The debrief never replaces component outcomes with a single score.

### 10.4 Accessibility and display requirements

- Supported viewport floor: 1280×720; reference viewport: 1920×1080.
- All functions are operable by keyboard and mouse.
- Focus order follows top bar, fleet, map, commands, alerts, and contacts.
- Status never relies on color alone.
- Motion respects reduced-motion preferences.
- Controls and alerts have accessible names in both languages.
- Probe overlays trap focus and restore it to the prior control on completion.
- At 1280×720 the map remains usable; secondary detail collapses into drawers
  rather than producing horizontal page scrolling.

## 11. API and real-time protocol

### 11.1 REST lifecycle

- `POST /simulation/sessions` — validate scenario and create a prepared session.
- `GET /simulation/sessions/{id}` — session metadata and lifecycle state.
- `POST /simulation/sessions/{id}/start` — start practice or the next block.
- `POST /simulation/sessions/{id}/pause` — researcher/operator pause.
- `POST /simulation/sessions/{id}/resume` — resume after an allowed pause.
- `POST /simulation/sessions/{id}/finish` — finish or explicitly abort.
- `POST /simulation/sessions/{id}/commands` — submit idempotent commands.
- `GET /simulation/sessions/{id}/state` — current authoritative snapshot.
- `GET /simulation/sessions/{id}/debrief` — derived outcomes and replay index.
- `GET /simulation/sessions/{id}/artifacts` — artifact inventory and checksums.
- `GET /simulation/scenarios` — installed, valid scenario summaries.
- `POST /simulation/scenarios/validate` — validate an allowed local YAML upload
  without installing or executing content.

Lifecycle mutations and commands require the controller lease returned when a
session is prepared. The controlling WebSocket authenticates with that same
lease; a stream without it is an observer. The controller may reconnect with
the same lease, but the simulation remains paused until an explicit resume.
The lease coordinates one local controller; it is not a replacement for user
authentication.

### 11.2 WebSocket stream

`WS /simulation/sessions/{id}/stream` carries envelopes with:

- `session_id`
- `sequence`
- `simulation_time_ms`
- `wall_time_utc`
- `state_version`
- `kind`
- `payload`

V1 message kinds are `snapshot`, `domain_event`, `alert`, `command_result`,
`probe`, `lifecycle`, `checkpoint`, and `error`. Snapshots are complete in V1;
delta compression is deferred. On reconnect, the client fetches the latest REST
snapshot and subscribes from the next sequence. A sequence gap triggers another
full snapshot fetch rather than speculative client repair.

## 12. Persistence and export

### 12.1 SQLite metadata

New SQLModel tables represent:

- `SimulationSession`: participant/visit linkage, scenario/manifest hashes,
  language, lifecycle, timestamps, validity, and artifact root;
- `SimulationBlock`: session, profile, order, lifecycle, interruption status,
  start/end times, and outcome summary;
- `SimulationArtifact`: session, kind, relative path, SHA-256, byte size, and
  creation time;
- `ProtocolDeviation`: session/block, stable code, severity, timing, and
  researcher disposition.

High-rate snapshots and events are not stored as database rows.

### 12.2 Artifact layout

```text
exports/simulation/<session-id>/
  scenario.yaml
  manifest.json
  events.jsonl
  checkpoints/
    checkpoint-000001.json.gz
  questionnaires.json
  metrics.json
  debrief.json
  replay-verification.json
  checksums.sha256
```

Every JSONL record includes the session and block IDs, ordered sequence,
simulation time, wall time, state version, record kind, and payload. Event writes
are flushed before the corresponding state is broadcast. Checkpoints and final
JSON artifacts use write-to-temporary-file followed by an atomic rename. The
final checksum file is written only after all other artifacts are sealed.

Only pseudonymized participant IDs are stored. Free-text operator input is not
accepted in V1; `REPORT_CONTACT.note_code` is selected from scenario-defined
bilingual codes.

## 13. Metrics

All component metrics are retained per block and session:

- observed search area and percentage coverage;
- duration and count of coverage gaps;
- correct, incorrect, corrected, false, late, and missed contact reports;
- detection, inspection, classification, prioritization, and reporting latency;
- commands submitted, accepted, rejected, corrected, and reversed, plus required
  operator actions that timed out;
- alert acknowledgement and resolution latency;
- time in nominal, degraded, and lost-link states;
- successful and unsuccessful lost-link recoveries;
- reserve advisories, critical reserve events, forced mission failures, and
  recovered aircraft;
- advisory conflicts, critical separation violations, duration below each
  threshold, and resolution latency;
- ISA sequence, SAGAT accuracy by perception/comprehension/projection level,
  NASA-TLX subscales/raw total, and Bedford score;
- protocol deviations and block validity.

A feedback-only composite is displayed as:

```text
mission_score = clamp(
    0.30 * coverage_score
  + 0.30 * contact_effectiveness
  + 0.20 * asset_preservation
  + 0.20 * timeliness,
  0,
  100,
)
```

Each term is normalized to `[0, 100]` using thresholds declared in the scenario
manifest. Inferential analysis uses the component outcomes, not the composite.
The UI and exports label the composite as descriptive feedback.

## 14. Failure handling and research validity

- A scenario that fails validation cannot create a session.
- Invalid, stale, unauthorized, and duplicate commands cannot silently mutate
  state. Each receives a stable result code; the UI maps that code to English or
  es-CO text.
- Loss of the controlling WebSocket immediately pauses simulation. Reconnection
  restores the last authoritative snapshot; resumption is explicit.
- A recorder flush or disk-capacity error pauses the runtime before further
  simulation ticks and opens a fatal researcher alert.
- An unhandled backend exception stops the tick loop, marks the block
  `interrupted`, flushes available records, and preserves the last completed
  checkpoint.
- Recovery from a checkpoint is a researcher decision. It creates a protocol
  deviation and never changes the original block's interruption flag.
- A participant may finish a recovered block, but analysis exports distinguish
  `valid`, `valid_with_deviation`, `interrupted`, and `aborted` blocks.
- A failed future vehicle adapter must transition affected vehicles to an
  explicit disconnected state and pause the session; it must never fall back to
  synthetic control during an active block.
- Server-side lifecycle transitions are idempotent and reject impossible
  transitions with stable error codes.
- No network service, tile endpoint, analytics endpoint, or remote font is
  required. The backend binds to `127.0.0.1` by default and development CORS is
  limited to the documented local frontend origins.

## 15. Verification strategy

### 15.1 Domain and engine tests

- Every autonomy-mode transition and rejected transition.
- Geometry containment, route clipping, restricted-zone rejection, coverage,
  and separation thresholds including boundary values.
- Battery integration, reserve prediction, critical threshold, return, recovery,
  and energy-exhaustion outcomes.
- Sensor observation staging, independent PRNG streams, and hidden-truth
  isolation.
- Link degradation/loss/recovery and the 10-second default lost-link procedure.
- Stable event order when multiple events occur on one tick.
- Same scenario, engine version, and command sequence produce byte-equivalent
  canonical events and the same final-state hash.
- Changing browser snapshot rate does not change authoritative results.

### 15.2 Backend tests

- Scenario creation and validation failures.
- Single active-session and single-controller enforcement.
- Lifecycle idempotency and impossible-transition rejection.
- Command UUID idempotency, stale state version, and observer rejection.
- WebSocket initial snapshot, ordered messages, sequence-gap recovery, and
  disconnect pause.
- Append-before-broadcast ordering.
- Checkpoint recovery, protocol deviation, abort, and final artifact sealing.
- Simulated disk-write and runtime failures.
- Existing ingestion, tracker, analysis, screen, and export endpoint regression.

### 15.3 Frontend tests

- Pure store/reducer behavior for every stream message and reconnect state.
- English and es-CO strings have identical key sets.
- Fleet sorting, alert ordering, contact progression, valid-command selection,
  metric formatting, and non-color status labels.
- SVG map projection, selection, route rendering, layer visibility, and reset.
- Probe focus trapping and restoration.
- Headless browser execution of setup, practice, all three blocks, debrief,
  export, disconnect, reconnect, observer mode, and keyboard-only workflows.
- Reference screenshots at 1280×720 and 1920×1080.

### 15.4 Soak and compatibility tests

- Accelerated complete sessions for every bundled seed and block order.
- Real-time 8-aircraft HIGH block without tick backlog on the development Linux
  host.
- Repeated pause/resume and controller reconnect cycles.
- Current root, backend, and frontend suites remain green.
- No test or production runtime requires internet access.

## 16. Linux delivery

The repository will provide a documented Linux launcher that starts the FastAPI
backend and built Next.js frontend, waits for both health checks, reports the
local URLs, and shuts both down cleanly on termination. Development remains
compatible with separate backend and frontend processes. The launcher must not
require Docker, a display server, or network access after dependencies have been
installed.

Headless development verification uses Playwright-compatible Chromium and
screenshots. A developer may reach the UI through an SSH port forward, but the
deployed workstation uses its local browser. Application fonts, icons, map
geometry, translations, and scenario assets are bundled locally.

## 17. V1 acceptance criteria

V1 is complete only when all of the following are demonstrated:

1. A strict YAML scenario with 2–8 aircraft validates and produces a stable
   manifest hash.
2. A researcher launches a pseudonymized bilingual session from the browser.
3. The operator completes practice and three counterbalanced blocks using the
   approved supervisory commands.
4. Battery, contacts, lost link, search coverage, and separation events affect
   authoritative state and appear correctly in the UI.
5. ISA, SAGAT, NASA-TLX, and Bedford are administered and scored.
6. Browser disconnect pauses the session and explicit reconnection resumes from
   authoritative state.
7. Debrief presents component outcomes, replay, validity, and protocol
   deviations.
8. Export contains the normalized scenario, manifest, records, checkpoints,
   questionnaire data, metrics, debrief, replay result, and valid checksums.
9. Replaying the recorded scenario and commands under the recorded engine
   version produces the same event and final-state hashes.
10. All new tests and all pre-existing test suites pass on Linux.

## 18. Explicitly deferred

- Manual piloting, joystick input, or six-degree-of-freedom dynamics.
- Real terrain, GPS coordinates, GeoJSON/MBTiles imports, or online maps.
- Moving contacts and detailed environmental or radio-propagation models.
- Multiple controlling operators or network-distributed experiments.
- PX4, ArduPilot, Gazebo, AirSim, or hardware-in-the-loop connectivity.
- Live physiology streams, real-time workload classification, or adaptive
  automation.
- Graphical scenario editing.
- Weapon, engagement, targeting, payload-employment, or damage simulation.
- Operational deployment, certification, or safety-critical use.

These features require separate approved specifications. The V1 adapter and
artifact boundaries must make future additions possible without weakening V1
determinism or provenance.

## 19. Implementation decomposition and repository workflow

V1 is too large to implement as one undifferentiated change. The detailed plan
must preserve these independently testable delivery gates:

1. deterministic domain, YAML scenario validation, and headless simulation;
2. recording, checkpointing, replay, and component metrics;
3. FastAPI persistence, session lifecycle, command API, and WebSocket stream;
4. playable mission setup and live operator UI;
5. research probes, questionnaires, debrief, and export integration;
6. Linux launcher, bilingual/accessibility hardening, soak testing, and complete
   regression verification.

Each gate must leave the repository in a passing, reviewable state. The
implementation plan will split these gates into small TDD tasks with exact file
paths, interfaces, commands, and expected results.

Implementation must not begin until the detailed plan has been written, reviewed,
committed, pushed, and a readiness report has been given to the user. During
implementation, each independently testable task receives its own focused commit.
After its scoped and regression tests pass, that commit is pushed to the
configured feature-branch remote before the next task begins. Existing unrelated
workspace changes are never staged or included.
