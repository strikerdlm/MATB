# MATB Phase 8+ Feature Implementation Specification
# Military Human Factors Research Platform

**Author.** Diego Malpica, MD — Aerospace medicine and human factors (Bogotá, Colombia).  
**Version.** 1.0 — 2026-05-03.  
**Scope.** Concrete implementation specification for Phase 8–11 features. Companion to `docs/research/military-aviation-platform/research_evidence_review.md`. This document translates the gap analysis into Python-level specs, parameter values, scoring formulas, and acceptance criteria. It does not repeat the literature justification found in the evidence review.

---

## Part 1 — Reference Implementations

### 1.1 MATB Lineage Summary

| Variant | Year | Platform | Primary Tasks | Key Feature |
|---|---|---|---|---|
| NASA MATB (Comstock & Arnegard) | 1992 | DOS | SYSMON, TRACK, COMM, RESMAN | Original; no automation |
| AF-MATB (Miller et al., 2014) | 2014 | Windows C++ | SYSMON, TRACK, COMM, RESMAN | Scriptable event sequences; per-task automation |
| NASA MATB-II (Santiago-Espada et al., 2011) | 2011 | Windows C++ | SYSMON, TRACK, COMM, RESMAN | GUI config; 8 WAV audio files; TRACK automation |
| OpenMATB (Cegarra et al., 2020) | 2020 | Python 3 + Pygame | SYSMON, TRACK, COMM, RESMAN | Plugin architecture; LSL-ready; CSV scenario files; MIT license |
| USAARL MATB (Vogl et al., 2024) | 2024 | Windows (proprietary) | SYSMON, TRACK, COMM, RESMAN + adaptive automation | Performance-driven handoffs; dynamic demand transitions; ISA probe ingestion |

**Primary reference for Python implementation:** OpenMATB (doi:10.3758/s13428-020-01364-w). It is the only open-source Python MATB with LSL synchronisation support. Architecture decisions below are informed by OpenMATB where relevant but optimised for the military aviation domain and Rich/terminal-first UI.

---

## Part 2 — Phase 8: The Four Primary Tasks

The single most important missing piece is the **operator input loop**. The current `experiment` mode emits scenario events but never collects a response. Phase 8 adds four task objects with a common `Task` interface, an input thread, and per-task scoring.

### 2.1 Task Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

@dataclass
class TaskScore:
    task: str          # "sysmon" | "track" | "comm" | "resman"
    monotonic_sec: float
    metric: str        # e.g. "hit_rate", "rmse_px", "correct_pct", "tank_deviation_L"
    value: float
    n_events: int
    n_correct: int
    n_missed: int
    n_false_alarms: int
    extra: dict[str, Any] = field(default_factory=dict)

class Task(ABC):
    @abstractmethod
    def tick(self, dt_sec: float) -> list[dict]:
        """Advance simulation by dt_sec. Return list of task events to display."""

    @abstractmethod
    def accept_input(self, input_event: dict) -> bool:
        """Process one input event. Return True if valid response."""

    @abstractmethod
    def score(self) -> TaskScore:
        """Return current accumulated score."""

    @abstractmethod
    def reset(self) -> None:
        """Clear state for a new block."""
```

### 2.2 System Monitoring (SYSMON)

**What it does.** Operator monitors 2 lights and 4 gauges. When a fault occurs, operator must press the designated key within a response window. Faults persist until responded to or they time out.

**Display layout:**
```
[ GREEN ]  [ RED ]
 Scale-1    Scale-2    Scale-3    Scale-4
 |||||      |||||      |||||      |||||
```

**Parameters:**

| Parameter | Default value | Source |
|---|---|---|
| Lights | 1 GREEN (normally ON, fault = OFF), 1 RED (normally OFF, fault = ON) | MATB-II §4.2.4.1 |
| Gauges | 4 scales; pointer moves at configurable speed; fault = pointer out of center zone | MATB-II §4.2.4.2 |
| Gauge speed lower | 2 px/cycle | AF-MATB §8.2.3.1 |
| Gauge speed upper | 6 px/cycle | AF-MATB §8.2.3.2 |
| Gauge fault timeout | 10 s (low), 6 s (med), 4 s (high) | Pontiggia et al. 2024 |
| Light fault timeout | 10 s (low), 6 s (med), 4 s (high) | Pontiggia et al. 2024 |
| Target zone (gauge) | ±15% of scale range from centre | MATB-II default |
| Fault response key | F5 (light), F1–F4 (gauges) or mouse click | MATB-II §7.1 |

**Event rates (events/min per workload level):**

| Level | SYSMON events/min | Source |
|---|---|---|
| Low | 2 | Huang et al. 2021; Pontiggia 2024 |
| Medium | 8–10 | Pontiggia 2024 meta-analysis |
| High | 16–20 | Huang et al. 2021 (hard condition) |

**Scoring:**
```
hit_rate = n_correct_detections / n_total_faults
false_alarm_rate = n_false_responses / (n_false_responses + n_correct_rejections)
mean_rt_sec = mean(response_time for each correct hit)
d_prime = Z(hit_rate) - Z(false_alarm_rate)  # signal detection metric
```

**Implementation notes:**
- Use monotonic clock for response latency; fault onset timestamp is the anchor.
- A "missed" fault is scored when the timeout expires without a valid response.
- False alarms: any response when no fault is active within the response window.
- Both lights and gauges are `SysmonFault` objects in a priority queue sorted by onset time.

---

### 2.3 Compensatory Tracking (TRACK)

**What it does.** A cursor moves randomly on a 2D plane due to a disturbance signal. Operator uses mouse/joystick to keep the cursor inside a target circle at the centre. Scoring is root-mean-square error (RMSE) in pixels.

**Parameters:**

| Parameter | Default value | Source |
|---|---|---|
| Disturbance signal | Sum of 3–5 sine waves with incommensurate frequencies; amplitude scales with workload | Standard MATB design |
| Target zone radius | 30 px (low), 20 px (med), 15 px (high) | MATB-II / AF-MATB §8.2.4.3 |
| Tracking gain | 1.0 (default); increase for higher difficulty | AF-MATB §8.2.4.1 |
| Cursor speed multiplier | 1.0 (low), 1.5 (med), 2.5 (high) | Huang et al. 2021 |
| Sample rate | 60 Hz (tick-based); RMSE computed every 30 s | AF-MATB §8.2.4.2 |
| Input device | Mouse (primary), joystick (preferred for research) | MATB-II §7.2 |

**Disturbance signal (preferred):**
```python
def disturbance(t: float, amplitude: float = 1.0) -> tuple[float, float]:
    # Sum of 5 sine waves per axis with incommensurate frequencies
    freqs_x = [0.11, 0.23, 0.37, 0.53, 0.71]  # Hz
    freqs_y = [0.13, 0.29, 0.41, 0.59, 0.79]
    x = amplitude * sum(math.sin(2 * math.pi * f * t) for f in freqs_x) / len(freqs_x)
    y = amplitude * sum(math.sin(2 * math.pi * f * t) for f in freqs_y) / len(freqs_y)
    return x, y
```

**Scoring:**
```
At each RMSE interval (default 30 s):
  samples = all (cursor_x, cursor_y) positions during interval
  rmse = sqrt(mean(cursor_x**2 + cursor_y**2))   # distance from centre
  in_zone_pct = count(dist < target_radius) / count(samples) * 100
```

**Automation:** When `automation_mode == ADVISORY` or `FORCED_HANDOFF`, the automation can reduce disturbance amplitude or auto-centre the cursor. This corresponds to MATB-II's tracking automation mode.

---

### 2.4 Communications (COMM)

**What it does.** Auditory task. An automated voice announces a callsign and a radio frequency change. Operator must respond only to messages matching their own callsign. Operator selects the correct radio (NAV1/NAV2/COM1/COM2), adjusts the frequency using increment/decrement buttons, and commits.

**Standard stimulus format:**
```
"[callsign], [callsign], turn your [radio] to [frequency]."
Example: "NASA 504, NASA 504, turn your NAV1 radio to 126.475."
```

The 8 original MATB-II WAV files cover this format. For Python, synthesise via TTS (pyttsx3, gTTS, or ElevenLabs with `sag`) or ship prerecorded WAV files.

**Parameters:**

| Parameter | Default value | Source |
|---|---|---|
| Callsigns | Own: "NASA 504"; Foils: "NASA 507", "NASA 511" | MATB-II §7.3 |
| Radios | NAV1, NAV2, COM1, COM2 | MATB-II |
| Frequency range | 108.000–135.975 MHz (COM/NAV overlap) | Standard VHF |
| Target frequencies | 8 predefined per workload script | MATB-II default script |
| Own-callsign rate | 2.5/min (low), 5/min (med), 9/min (high) | Pontiggia 2024; Huang 2021 |
| Foil ratio | ~1:1 own:foil | MATB-II default |
| Response window | 10 s (low), 7 s (med), 5 s (high) | MATB-II default timeout |

**Scoring:**
```
correct_pct = n_own_callsign_correctly_tuned / n_own_callsign_events * 100
commission_error_rate = n_responses_to_foil_callsigns / n_foil_events * 100
mean_rt_sec = mean(time from audio onset to correct commit)
```

**Implementation note:** Audio must be played on a background thread. The stimulus onset timestamp (wall clock + monotonic) must be logged when audio starts, not when it is scheduled. Use `sounddevice` or `pygame.mixer` with callback to get precise onset time.

---

### 2.5 Resource Management (RESMAN)

**What it does.** Operator manages fuel levels in a tank network by turning pumps ON/OFF. The goal is to keep Tank A and Tank B at the target level (2500 L). Tanks drain continuously; pumps transfer fuel between tanks.

**Standard tank topology (MATB-II default):**
```
Supply tanks (no operator control):
  Tank C: 6000 L max, no drain
  Tank D: 6000 L max, no drain
  
Main tanks (must be kept at target):
  Tank A: target 2500 L, drains at 800 L/min
  Tank B: target 2500 L, drains at 600 L/min
  
Side tanks (supply):
  Tank E: max 4000 L
  Tank F: max 4000 L

Pump connections:
  P1: C → A (flow: 600 L/min)
  P2: C → B (flow: 600 L/min)
  P3: D → A (flow: 600 L/min)
  P4: D → B (flow: 600 L/min)
  P5: A → E (flow: 400 L/min, reverse flow risk)
  P6: B → F (flow: 400 L/min)
  P7: E → A (flow: 400 L/min)
  P8: F → B (flow: 400 L/min)
```

These are the MATB-II defaults from Santiago-Espada et al. (2011). The AF-MATB allows full reconfiguration.

**Parameters:**

| Parameter | Default | Source |
|---|---|---|
| Tank A target | 2500 L | MATB-II config |
| Tank B target | 2500 L | MATB-II config |
| Drain rate A | 800 L/min | MATB-II |
| Drain rate B | 600 L/min | MATB-II |
| Pump failure events/min | 1 (low), 2.5 (med), 4 (high) | Pontiggia 2024 |
| Automation RMS interval | 30 s | AF-MATB §8.2.9.7 |
| RMS target value | 2500 L | AF-MATB §8.2.9.8 |

**Scoring:**
```
At each scoring interval (default 30 s):
  deviation_A = abs(tank_A_level - 2500)
  deviation_B = abs(tank_B_level - 2500)
  rms_deviation = sqrt((deviation_A**2 + deviation_B**2) / 2)
  time_out_of_range_pct = count(out_of_±500L_range) / total_samples * 100
```

**Pump failure events:** A pump randomly fails (goes from ON→OFF or becomes unavailable). Operator must detect (RESMAN panel shows pump status) and reconfigure. Failure events are the workload manipulation knob for RESMAN.

---

## Part 3 — Phase 8: Input Thread and Event Loop

### 3.1 Architecture

The critical constraint: the 4 primary tasks must run **concurrently** with the scenario visualisation. This requires a foreground input capture thread and per-task state objects updated at a fixed tick rate.

```
Main thread:
  scenario_runner → event_generator → dashboard_render

Input thread (foreground, blocks on keyboard/mouse events):
  input_event → TaskRouter.route(event) → Task.accept_input(event)

Tick thread (50–60 Hz):
  for task in active_tasks:
      new_events = task.tick(dt)
      if new_events: task_event_queue.put(new_events)
      score_record = task.score()
      if score_interval_elapsed: logger.record_task_score(score_record)
```

### 3.2 Input Routing

```python
class TaskRouter:
    KEY_MAP = {
        "F1": "sysmon_gauge_1",
        "F2": "sysmon_gauge_2",
        "F3": "sysmon_gauge_3",
        "F4": "sysmon_gauge_4",
        "F5": "sysmon_light",
        "F6": "comm_radio_select",
        "F7": "comm_channel_up",
        "F8": "comm_channel_down",
        "F9": "comm_freq_up",
        "F10": "comm_freq_down",
        "Enter": "comm_commit",
        "mouse_motion": "track_cursor",
        "mouse_click": "resman_pump_toggle",
    }
```

Key bindings must be configurable per-study because some labs use joystick or touch input instead of keyboard.

### 3.3 Acceptance Criterion

A healthy adult participant with 10 minutes of training should produce a per-task scoring file within ±5% of MATB-II on the same event script when running both in parallel. This is the Phase 8 acceptance gate.

---

## Part 4 — Phase 8: Rating Scale Ingestion

### 4.1 ISA (Instantaneous Self-Assessment)

Inject synchronously at configured intervals. Block until response received or window expires.

```python
@dataclass
class ISARating:
    record_type: str = "isa_rating"
    block: str = ""
    scale: str = "ISA_1_5"  # or "ISA_1_10" for USAARL variant
    anchors: dict = field(default_factory=lambda: {
        1: "Underutilised",
        2: "Relaxed",
        3: "Comfortable",
        4: "High workload",
        5: "Excessive workload",
    })
    value: int | None = None      # None = timed out
    latency_sec: float = 0.0
    monotonic_sec: float = 0.0
```

**Display:** Full-screen overlay (Rich Panel), numeric key 1–5, `Escape` = skip/timeout. Log `value=None` for timeouts — do not exclude them.

**Frequency:** Every 30–60 s (USAARL MATB standard) or every N events (current platform default). Both modes should be supported.

### 4.2 NASA-TLX (Post-Block)

Use **Raw TLX** (unweighted) unless the study specifically requires weighted TLX. Raw TLX has equivalent validity and removes 15 pairwise comparisons that add ~3 min per block.

```python
NASA_TLX_SUBSCALES = [
    ("mental_demand",   "Mental Demand",   "How much mental activity was required?"),
    ("physical_demand", "Physical Demand", "How much physical activity was required?"),
    ("temporal_demand", "Temporal Demand", "How much time pressure did you feel?"),
    ("performance",     "Performance",     "How successful were you in accomplishing the task?"),
    ("effort",          "Effort",          "How hard did you have to work to accomplish your level of performance?"),
    ("frustration",     "Frustration",     "How insecure, irritated, or annoyed were you?"),
]
# Each 0–100 in steps of 5 (21 points). Performance scale is reversed: 0=perfect, 100=failure.
# Raw TLX score = mean of all 6 subscales (0–100).
```

**Post-block display:** Show immediately after `RESEARCH BLOCK COMPLETE` event. Display one subscale at a time (arrow keys to adjust, Enter to confirm). Log all 6 subscale values individually.

**Normative reference:**
- Raw TLX < 40: low workload
- Raw TLX 40–60: moderate workload  
- Raw TLX > 60: high workload
- (These are approximate; within-subject comparisons are more meaningful than absolute cutoffs.)

### 4.3 Bedford Scale (Post-Block Aviation Variant)

10-point branching workload scale designed for aviation (Roscoe & Ellis, 1990). Preferred over NASA-TLX in fast-turnaround cockpit studies because it takes <30 s.

```
Bedford Scale Structure:
  Satisfactory without reduction in work standard?
    Yes → 1-3 (spare capacity available):
      1: Spare capacity to attend to any additional task
      2: Spare capacity to attend to most additional tasks
      3: Spare capacity to attend to some additional tasks
    No → continue:
      Demanding but tolerable without reducing work standard?
        Yes → 4-6 (adequate):
          4: Spare capacity to attend to easy additional tasks
          5: No spare capacity; degradation absent but imminent
          6: Degradation in task performance likely
        No → 7-10 (inadequate):
          7: Very demanding; major degradation of task performance
          8: Catastrophic degradation; unable to cope
          9: Insufficient capacity to maintain task
          10: Abort task
```

### 4.4 Logging Schema for Ratings

```json
{
  "record_type": "rating",
  "participant_id": "P001",
  "session_id": "S01",
  "block": "high_demand",
  "scale": "NASA_TLX_RAW",
  "subscale": "mental_demand",
  "value": 75,
  "latency_sec": 4.2,
  "monotonic_sec": 1834.55,
  "wall_time_utc": "2026-05-03T14:22:11Z"
}
```

---

## Part 5 — Phase 8: SAGAT Freeze-Probe Service

### 5.1 Design

SAGAT (Situation Awareness Global Assessment Technique) is the highest-sensitivity objective SA measure (94% sensitivity vs 64% for SPAM; Endsley 2021, doi:10.1177/0018720819875376).

**Freeze procedure:**
1. At a scripted or random point within a block, emit `SAGAT_FREEZE_BEGIN` event.
2. Pause all scenario ticks and event generation.
3. Blank all task displays for 5 s (cognitive "purge" of perceptual content).
4. Present one query at a time (keyboard response), time-limited to 15 s each.
5. Log ground-truth scenario state at freeze onset (this is the scoring anchor).
6. Emit `SAGAT_FREEZE_END` event; resume scenario.

**Minimum viable probe set per freeze (3-level structure):**

| SA Level | Example probe (UAS scenario) |
|---|---|
| Level 1 (Perception) | "What is the current datalink quality? [Good / Degraded / Lost / Unknown]" |
| Level 1 (Perception) | "How many sensor targets are currently detected? [0 / 1 / 2 / 3+]" |
| Level 2 (Comprehension) | "Is the mission currently on track? [Yes / No / Uncertain]" |
| Level 2 (Comprehension) | "What is the primary threat to mission success right now? [Fuel / Link / Airspace / None / Unknown]" |
| Level 3 (Projection) | "In the next 2 minutes, what is most likely to happen? [Nothing critical / Link loss / Airspace conflict / Fuel critical / Unknown]" |

Probes must be scenario-specific and written from a Goal-Directed Task Analysis (GDTA). The above are illustrative; each modality (UAS, fighter, transport) needs its own probe bank.

**Scoring:**
```python
@dataclass
class SAGATProbeResult:
    probe_id: str
    sa_level: int      # 1, 2, or 3
    domain: str        # perception / comprehension / projection
    question: str
    correct_answer: str   # ground truth at freeze time
    given_answer: str | None
    is_correct: bool
    latency_sec: float
    monotonic_sec: float

# Session-level SA score per level:
sa_score_level_n = sum(correct_level_n) / sum(total_level_n) * 100
```

**Freeze timing:** Endsley (2000) recommends 30–60 probes per session. For a 20-min session with 3 blocks of 10 events each, target 6–10 freeze points total (2–3 per block), randomly placed within blocks.

### 5.2 Integration with Protocol

Add `sagat_probe_interval_events` to `DemandBlock` alongside `workload_probe_interval_events`. SAGAT probes should be staggered from ISA probes (do not fire both within 60 s of each other).

---

## Part 6 — Phase 9: LSL Gateway

### 6.1 Outlet (Scenario Markers)

```python
from pylsl import StreamInfo, StreamOutlet

def create_matb_marker_outlet() -> StreamOutlet:
    info = StreamInfo(
        name="MATB-Markers",
        type="Markers",
        channel_count=1,
        nominal_srate=0,        # irregular (event-driven)
        channel_format="string",
        source_id="matb-aircraft-monitor",
    )
    return StreamOutlet(info)

# Push marker on every loggable event:
outlet.push_sample([f"{event.category.value}:{event.title}"])
```

**Standard marker format:** `"CATEGORY:TITLE:BLOCK:WORKLOAD"` — e.g. `"RESEARCH:ISA_WORKLOAD_PROBE:high_demand:high"`

### 6.2 Inlet (Physiological Streams)

```python
from pylsl import StreamInlet, resolve_byprop

def subscribe_physio(stream_type: str) -> StreamInlet:
    # Types: "EEG", "ECG", "GSR", "Gaze", "Pupil"
    streams = resolve_byprop("type", stream_type, minimum=1, timeout=5.0)
    if not streams:
        raise RuntimeError(f"No LSL stream of type '{stream_type}' found.")
    return StreamInlet(streams[0])
```

**physiology.jsonl schema (one file per inlet stream):**
```json
{
  "record_type": "physio_sample",
  "stream_type": "ECG",
  "lsl_timestamp": 12345.678,
  "matb_monotonic_sec": 834.22,
  "channels": [0.0034, 0.0021]
}
```

### 6.3 Dependencies

```
pylsl >= 1.16          # core LSL Python bindings
mne-lsl >= 1.5         # optional: real-time MNE integration (Scheltienne et al. 2025, JOSS 8088)
```

Sub-millisecond jitter is achievable on consumer hardware when `HandleJitter=true` (LSL default); Kothe et al. 2025 (doi:10.1162/imag.a.136) demonstrate ≤0.5 ms SD between EEG and EMG streams.

---

## Part 7 — Phase 9: Counterbalanced Block Ordering

### 7.1 Complete-Permutation Assignment

Replace the fixed `low → medium → high` order with participant-ID-driven assignment.

```python
from itertools import permutations

# All 6 permutations for 3 workload levels (low=L, medium=M, high=H).
# This is complete counterbalancing, not a three-row Latin square.
COMPLETE_COUNTERBALANCE_3 = [
    ("L", "M", "H"),
    ("L", "H", "M"),
    ("M", "L", "H"),
    ("M", "H", "L"),
    ("H", "L", "M"),
    ("H", "M", "L"),
]

def block_order_for_participant(participant_id: str) -> tuple[str, ...]:
    # Deterministic assignment based on participant number
    n = int("".join(filter(str.isdigit, participant_id)) or "0")
    return LATIN_SQUARE_3[n % len(LATIN_SQUARE_3)]
```

### 7.2 Practice Block

Add a mandatory practice block before counterbalanced experimental blocks:
- Fixed order: low demand only, 5 events maximum
- Performance criterion: SYSMON hit rate ≥ 0.80 AND TRACK in-zone ≥ 50%
- If criterion not met: repeat practice (max 3 attempts); log `practice_pass: bool`
- Block is excluded from analysis but logged for compliance reporting

---

## Part 8 — Phase 10: Population-Specific Stressor Packs

### 8.1 Fighter Pack

Add the following discrete scenario states to the `FighterAircraft` model:

| State | Fields | Trigger | Recovery |
|---|---|---|---|
| `G_LOC_RISK` | `g_force: float`, `agsm_quality: str` | g_force > 7.5 | Reduce g or AGSM input |
| `G_LOC_ONSET` | `consciousness_level: float [0-1]` | AGSM_FAIL + high G | Auto-reduce g; SA rebuild required |
| `HYPOXIA_ONSET` | `o2_pct: float`, `symptoms: list[str]` | O2 < 12% or mask fail | Return to O2 or descend |
| `HYPOXIA_HANGOVER` | `cognitive_degradation: float` | Post-hypoxia 5 min | Spontaneous recovery |
| `SD_EVENT` | `sd_type: str` (graveyard, leans, vertigo) | Low IMC + maneuver | Trust instruments |
| `ROE_AMBIGUITY` | `contact_classification: str`, `certainty: float` | Hostile/unknown contact | Engage or hold |

**SA rebuild probe sequence (from Militello et al. 2024, doi:10.1177/15553434241234105):**
After G-LOC_ONSET, inject 4-stage SA probe sequence: (1) impairment recognition, (2) current state, (3) threat status, (4) priority action. Score each vs ground truth.

### 8.2 RPA Pack

Add to `UAV` model:

| Feature | Parameter | Reference |
|---|---|---|
| Shift-work timeline | `shift_hour: int [0-23]`, `circadian_phase: str` | Chappelle et al. 2014 |
| Kill-chain annotations | `civilian_present: bool`, `civilian_harm: bool`, `operator_responsibility_belief: float` | Chappelle et al. 2019 |
| NtoM multi-aircraft | `n_aircraft: int`, `active_aircraft_id: str` | Fas-Millán & Pastor 2019 |
| Audio-visual feedback | `av_feedback_condition: str` (visual-only / audio-only / av) | Dunn 2023 |
| Lost-link procedure | `link_state: str`, `contingency_route_active: bool` | FAA JO 7110.724 |

### 8.3 Transport / MUM-T Pack

| Feature | Parameter | Reference |
|---|---|---|
| Sustained-ops fatigue | `hours_on_duty: float`, `sleep_deprivation_hrs: float` | Serres et al. 2015 |
| AAR receiver state | `contact_distance_m: float`, `contact_type: str` (probe/drogue) | Ament et al. 2024 |
| AAR boomer/RVS | `rvs_condition: str` (nominal / degraded-stereo / monocular) | Winterbottom et al. 2016 |
| MUM-T UAV link | `num_uavs_supervised: int`, `uav_status: list[str]` | Levulis et al. 2018 |
| Crew-coordination channel | `crew_message_queue: list[str]` | Verdière et al. 2019 |

---

## Part 9 — Phase 10: BIDS-Derivative Data Export

### 9.1 Directory Layout

```
sub-P001/
  ses-S01/
    beh/
      sub-P001_ses-S01_task-matb_events.tsv
      sub-P001_ses-S01_task-matb_events.json    # column descriptions
      sub-P001_ses-S01_task-matb_scores.tsv
      sub-P001_ses-S01_task-matb_ratings.tsv
      sub-P001_ses-S01_task-matb_sagat.tsv
    eeg/     (if LSL EEG was captured)
      sub-P001_ses-S01_task-matb_eeg.xdf
    physio/  (if LSL ECG/GSR/eye was captured)
      sub-P001_ses-S01_task-matb_physio.xdf
dataset_description.json
participants.tsv
```

### 9.2 events.tsv Schema

```
onset   duration   trial_type   event_category   block   workload   automation_mode   stim_file   response   response_time   correct
```

Follows BIDS-Behavioral specification (column names match BIDS where possible; custom columns documented in sidecar JSON).

### 9.3 scores.tsv Schema

```
onset   block   workload   task   metric   value   n_events   n_correct   n_missed   n_false_alarms
```

### 9.4 ratings.tsv Schema

```
onset   block   scale   subscale   value   latency
```

---

## Part 10 — Event Rate Reference Table

From Pontiggia et al. (2024, doi:10.3389/fphys.2024.1408242) meta-analysis of 36 studies. Use this to calibrate `max_events` and `workload_probe_interval_events` in `DemandBlock`.

| Task | Low workload (events/min) | High workload (events/min) | Median session (min) |
|---|---|---|---|
| SYSMON | 2 | 16–20 | 20 |
| TRACK | continuous (gain varies) | continuous (higher gain) | 20 |
| COMM | 2.5 | 9 | 20 |
| RESMAN | 1 | 4 | 20 |
| Overall | ~3 total | ~23.5 total | 20 |

**Current `DemandBlock` defaults vs recommended calibration:**

| Parameter | Current default | Recommended Phase 8 |
|---|---|---|
| Low block max_events | 10 | 30 (≈3/min × 10 min) |
| Medium block max_events | 18 | 60 |
| High block max_events | 28 | 235 (≈23.5/min × 10 min) |
| Block duration | event-count limited | time-limited (10 min each) |
| ISA probe interval | every 5 events | every 60 s (USAARL standard) |

---

## Part 11 — OpenMATB Architecture Patterns to Adopt

OpenMATB (Cegarra et al. 2020, doi:10.3758/s13428-020-01364-w) is the only open-source Python MATB with psychophysiological synchronisation support. Key architectural patterns to adopt:

1. **Plugin system for tasks.** Each task (SYSMON, TRACK, COMM, RESMAN) is a plugin that can be enabled/disabled in a scenario config file. Implement this as Python protocol classes, not inheritance.

2. **CSV/YAML scenario files.** Event timing is specified externally, not hardcoded. The scenario file specifies event type, onset time (or distribution), and parameters. This enables experiment replication without code changes.

3. **Cross-platform audio.** OpenMATB uses pygame.mixer. For the Python 3 / Rich-first architecture here, use `sounddevice` with `soundfile` for WAV playback with precise onset timestamps.

4. **Psychophysiological synchronisation via LSL.** OpenMATB outputs LSL markers on every task event. Adopt this directly.

5. **Scenario replicability.** Every scenario file is hashed and stored with the data. Already partially implemented (seed stored in run_start record); extend to store the full scenario config hash.

---

## Part 12 — Implementation Priority Order

| Priority | Feature | Phase | Effort | Acceptance gate |
|---|---|---|---|---|
| 1 | SYSMON task object with fault detection | 8 | Medium | Hit rate within ±5% of MATB-II |
| 2 | TRACK task object with RMSE scoring | 8 | Medium | RMSE within ±5% of MATB-II |
| 3 | Input thread and TaskRouter | 8 | Low | All 4 tasks receive input concurrently without frame drops |
| 4 | ISA probe ingestion (blocking dialog) | 8 | Low | Rating logged with latency; timeout handled |
| 5 | COMM task (audio + radio tuning) | 8 | High | Audio onset logged within ±50 ms |
| 6 | RESMAN task (tank network + scoring) | 8 | Medium | Tank deviation within ±5% of MATB-II |
| 7 | NASA-TLX post-block ingestion | 8 | Low | 6 subscales logged |
| 8 | Bedford scale post-block ingestion | 8 | Low | 10-point scale logged |
| 9 | SAGAT freeze-probe service | 8 | Medium | Ground-truth state captured at freeze; 3 levels scored |
| 10 | LSL outlet (scenario markers) | 9 | Low | Markers visible in LabRecorder with <5 ms jitter |
| 11 | LSL inlet (physio streams) | 9 | Medium | EEG and ECG streams logged to physio.jsonl |
| 12 | Counterbalanced block ordering | 9 | Low | Complete six-order counterbalancing verified for N=24 |
| 13 | Practice block with criterion | 9 | Low | practice_pass flag logged |
| 14 | Time-based block duration | 9 | Low | Blocks run exactly N minutes regardless of event count |
| 15 | Fighter stressor pack | 10 | High | G-LOC, hypoxia, SD states with SA rebuild probes |
| 16 | RPA stressor pack | 10 | High | Shift-work timeline, kill-chain annotations |
| 17 | Transport/MUM-T stressor pack | 10 | High | AAR state machine, MUM-T link layer |
| 18 | BIDS-derivative export | 10 | Medium | events.tsv passes BIDS-Behavioral validator |
| 19 | Adaptive automation engine | 11 | High | Performance-threshold-driven handoffs |
| 20 | Aeromedical baseline neurocognitive screen | 10 | Medium | RT, WM, tracking baseline before experimental blocks |

---

## Part 13 — Critical Implementation Notes from 2025 Literature

These are findings that change or refine implementation decisions; they come from the 2025 search and are not captured in the evidence review.

### 13.1 Asymmetric Adaptive Automation Thresholds

Temme, Vogl, & O'Brien (2025, doi:10.21203/rs.3.rs-6263878/v1) — from the same USAARL group — found that the minimum detectable workload change (psychophysical JND) is **asymmetric**: high-to-low demand transitions are detected significantly faster than low-to-high transitions. 

**Implication for Phase 11 adaptive automation engine:** Use a hysteresis band rather than a single threshold:
```python
# Automation onset: performance below onset_threshold → trigger cue
AUTOMATION_ONSET_THRESHOLD  = 0.65   # conservative — operator degrades further before automation helps
# Automation cessation: performance above cessation_threshold → return to manual
AUTOMATION_CESSATION_THRESHOLD = 0.80  # higher than onset to prevent oscillation
```
This prevents the automation from thrashing between on/off states near the boundary.

### 13.2 Event-Locked Physiological Capture (not Block-Averaged)

Gugerell, Gollan, & Stolte (2024, doi:10.3390/app14083158) — pupil dilation at task onset was significantly smaller than at response time (M=34.29 vs 37.45, t=19.02, p<0.001) within a single SYSMON event. Block-averaged physiological measures wash out this within-event signal.

**Implication for LSL inlet design:** Each physiology.jsonl record should log `event_onset_monotonic_sec` and `event_response_monotonic_sec`, not just wall time. This allows ±2 s event-locked epochs to be reconstructed from the physiological stream for every task event.

### 13.3 SAGAT Instrument Licensing

The SAGAT instrument is commercially licensed through **SA Technologies** (Marietta, GA). The freeze-probe *mechanism* (pause simulation, blank displays, query operator) can be implemented freely; the specific SAGAT questionnaire items for aviation domains are proprietary. The Python platform should implement the freeze-probe mechanism and allow researchers to supply their own probe bank via a YAML config file.

### 13.4 Video Gaming as Participant Confound

Hilla, Stasch, & Mack (2025, doi:10.1038/s41598-025-25260-5) — 60 participants; gaming experience predicted MATB performance independent of cognitive capacity (SEM model). Add these columns to `participants.tsv`:
```
gaming_hrs_per_week   gaming_experience_level (none/casual/regular/competitive)
```

### 13.5 COMM Task Minimum Block Length

Prasetyo (2024, doi:10.1051/shsconf/202418901043) confirms: at 2 events/min with 25% own-callsign rate, a minimum of **10 minutes** is required to see at least 2 target stimuli per block. Blocks shorter than 10 minutes produce floor/ceiling effects in the COMM task. The current `DemandBlock.max_events = 28` (high demand) terminates too quickly at high rates; Phase 8 should switch to **time-limited blocks (10 min default)** rather than event-count-limited blocks.

### 13.6 MQTT/InfluxDB as Parallel Output Path

Rouser, Kyle, & Jurewicz (2025, doi:10.1177/10711813251367735) demonstrate that MQTT + InfluxDB + Grafana supports real-time Bayesian workload estimation and cloud-deployable multi-station research. Add an optional MQTT publisher that forwards every LSL marker to an InfluxDB topic. This is a thin bridge (`paho-mqtt` + `influxdb-client`) and adds no LSL dependency risk.

### 13.7 USAARL MATB 2025 Update

Vogl, Atchley, & Bommer (2025, doi:10.1109/rapid64712.2025.11151324) — IEEE RAPID conference, August 2025 — presents recent developments to the USAARL MATB after the 2024 Frontiers paper. Full text is behind paywall. Monitor for open access; if accessible, it is the single most important document for platform parity claims.

---

## Part 14 — New References (not in evidence_review.md)

1. Behradfar, M., & Nuamah, J. (2025). Mental Workload Classification Using Electrocardiogram Data. *HFES Annual Meeting*, 69(1), 1515–1519. https://doi.org/10.1177/10711813251358786

2. Cegarra, J., Valéry, B., & Avril, E. (2020). OpenMATB: A Multi-Attribute Task Battery promoting task customization, software extensibility and experiment replicability. *Behavior Research Methods*, 53(2), 755–765. https://doi.org/10.3758/s13428-020-01364-w

3. Gugerell, D., Gollan, B., & Stolte, M. (2024). Studying the Role of Visuospatial Attention in the Multi-Attribute Task Battery II. *Applied Sciences*, 14(8), 3158. https://doi.org/10.3390/app14083158

4. Hilla, Y., Stasch, S.-M., & Mack, W. (2025). Habitual video gaming predicts multitasking performance while the role of cognitive capacity remains inconclusive. *Scientific Reports*, 15(1). https://doi.org/10.1038/s41598-025-25260-5

5. Huang, S., et al. (2021). Cited in Pontiggia et al. 2024: AF-MATB workload parameters (TRACK: 8/40 events/min low/high; SYSMON: 2/16; RESMAN: 2.5/9).

6. Kothe, C., Shirazi, S. Y., Stenner, T., et al. (2025). The Lab Streaming Layer for synchronized multimodal recording. *Imaging Neuroscience*, 3. https://doi.org/10.1162/imag.a.136

7. Li, Y. (2024). Examining mental workload based on multiple physiological signals: Review of the multi-attribute task battery (MATB) technique. *Medicine in Novel Technology and Devices*, 24, 100340. https://doi.org/10.1016/j.medntd.2024.100340

8. Pontiggia, A., Gomez-Merino, D., & Quiquempoix, M. (2024). MATB for assessing different mental workload levels. *Frontiers in Physiology*, 15, 1408242. https://doi.org/10.3389/fphys.2024.1408242

9. Prasetyo, R. A. B. (2024). The use of multi-attribute task battery in mental workload studies: A scoping review. *SHS Web of Conferences*, 189, 01043. https://doi.org/10.1051/shsconf/202418901043

10. Roscoe, A. H., & Ellis, G. A. (1990). *A subjective rating scale for assessing pilot workload in flight: A decade of practical use* (Technical Report TR90019). Royal Aerospace Establishment.

11. Rouser, B., Kyle, A., & Jurewicz, K. (2025). Development of a Scalable Data Acquisition System for Multimodal Physiological Data for Human Factors Research. *HFES Annual Meeting*, 69(1), 1902–1904. https://doi.org/10.1177/10711813251367735

12. Rowan, C. P. (2024). Verification and Validation of Cognitive Workload Models for Adaptive Automation Tasks. *HFES Annual Meeting*, 68(1), 572–578. https://doi.org/10.1177/10711813241272121

13. Roy, S., & Nuamah, J. (2025). Relationship Between Subjective Stress Resilience and Performance Under Task-Induced Stress. *HFES Annual Meeting*, 69(1), 1967–1973. https://doi.org/10.1177/10711813251364795

14. Santiago-Espada, Y., Myer, R. R., Latorella, K. A., & Comstock, J. R. Jr. (2011). *The Multi-Attribute Task Battery II (MATB-II) Software for Human Performance and Workload Research: A User's Guide*. NASA Technical Memorandum TM-2011-217164. https://ntrs.nasa.gov/api/citations/20110014456

15. Scheltienne, M., Larson, E., Desvachez, A., & Lee, K. (2025). MNE-LSL: Real-time framework integrated with MNE-Python for online neuroscience research through LSL-compatible devices. *Journal of Open Source Software*, 10(111), 8088. https://doi.org/10.21105/joss.08088

16. Schindler, H., Onnasch, L., & Schuhmann, D. (2025). Psychophysiological Markers of Mental Workload in the Multi-Attribute Task Battery — Exp 1. OSF Registries. https://doi.org/10.17605/osf.io/8q9gm

17. Schindler, H., Kaltenstadler, Y., & Onnasch, L. (2025). Psychophysiological Markers of Mental Workload in the Multi-Attribute Task Battery — Exp 2. OSF Registries. https://doi.org/10.17605/osf.io/5pvh2

18. Smith, K., Clark, T. K., & Endsley, T. (2024). Multimodal Physiological Models of Situation Awareness. *HFES Annual Meeting*, 68(1), 367–372. https://doi.org/10.1177/10711813241261387

19. Stasch, S.-M., Ernst, F., & von Mankowski, J. (2025). Beyond Traditional Radio: Exploring Spatial-audio Systems for Enhanced Communication in Multitasking Flight Environments. Preprint. https://doi.org/10.21203/rs.3.rs-6219019/v1

20. Temme, L. A., Vogl, J., & O'Brien, K. (2025). The Psychophysics of Cognitive Workload: A Novel Methodology for the Continuous Assessment of Cognitive Demand. Preprint (Research Square). https://doi.org/10.21203/rs.3.rs-6263878/v1

21. USAARL Technical Report (2026). *Real-Time Multi-Sensor Data Collection and Processing*. US Army Aeromedical Research Laboratory. https://usaarl.health.mil/assets/docs/techReports/2026-07.pdf

22. Vogl, J., Atchley, J. A., & Bommer, S. (2025). The United States Army Aeromedical Research Laboratory Multi-Attribute Task Battery: Recent Developments. *IEEE RAPID*, 1–2. https://doi.org/10.1109/rapid64712.2025.11151324

23. Vogl, J., McCurry, C. D., Bommer, S., & Atchley, J. A. (2024). The United States Army Aeromedical Research Laboratory Multi-Attribute Task Battery. *Frontiers in Neuroergonomics*, 5, 1435588. https://doi.org/10.3389/fnrgo.2024.1435588

---

*Document maintained at `docs/implementation/phase8_feature_spec.md`. Companion: `docs/research/military-aviation-platform/research_evidence_review.md`.*
