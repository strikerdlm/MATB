# Implementation Roadmap for Improved 2D Visualizations (Science-Based)

## 1. Objectives and Scientific Constraints

1. Preserve the psychometric validity and timing precision of MATB / OpenMATB.
2. Stay strictly **2D** (single depth plane) – no VR/3D depth separation, per recent evidence that 3D MATB-II variants increase workload and degrade performance.
3. Improve **clarity, salience, and accessibility** of information, not realism.
4. Keep all existing **scenario syntax and logging contracts** intact; visualization upgrades must be backward compatible.

This roadmap assumes the current plugin set (baseline MATB, UAS, HPA, MUM-T extensions) and targets all scenarios by improving the shared visual primitives and per-plugin presentations.

---

## 2. Cross-Cutting 2D Design Upgrades

### 2.1 Unified Status & Color System

**Goal:** Consistent, science-based use of color and salience across all plugins and scenarios.

Actions:
- Extend `core/constants.py` with a **status palette**, e.g.:
  - `STATUS_NORMAL`, `STATUS_WARNING`, `STATUS_CRITICAL`, `STATUS_DISABLED`, `STATUS_INFO`.
  - Map these to color tuples for both normal and colorblind modes.
- Add a `colorblind_mode` boolean in `config.ini` (and expose it in tools/config_portal.py).
  - In colorblind mode, prioritize **shape, icons, and labels** over red/green distinctions.
- Refactor plugins that currently hard-code colors (e.g., overdue alerts, alarms) to use the shared status palette.

Impact:
- All scenarios gain consistent visual meaning for colors.
- Supports accessibility without altering task structure or timing.

---

### 2.2 Typography, Density, and Readability

**Goal:** Reduce visual search time and reading effort without changing task content.

Actions:
- Standardize font sizes via `FONT_SIZES` so that:
  - Headers use `MEDIUM` or `LARGE`.
  - Row content uses `SMALL`.
  - Fine-grained metrics (e.g., debug values) use `XSMALL`.
- For all `Simpletext` widgets that show multi-row tables:
  - Use **monospaced font** (configurable via `font_name`) for better column alignment.
  - Ensure `wrap_width` is set to keep lines within container bounds.
  - Avoid more than ~3–5 lines per widget; if more are needed, summarize (e.g., “+3 more threats…”).
- Add a global `ui_scale` parameter in `config.ini` to scale font sizes and margins for high-resolution displays.

Impact:
- Faster parsing of multi-column UAV, threat, and mission tables across UAS / HPA / MUM-T scenarios.

---

### 2.3 Task Layout and Grouping

**Goal:** Make related information co-located and predictable across scenarios, while staying on a single depth plane.

Actions:
- Define a **layout convention** (top row vs bottom row vs left/right) for task families:
  - Top-left: core MATB tasks (SYSMon, TRACK, COMM, RESMAN).
  - Top-right: fighter/HPA overlays (Threat Board, Energy Manager, Weapons, Weather).
  - Bottom-left: UAS fleet management (Mission Director, Operator Capacity, Platform Profiles, VTOL Manager).
  - Bottom-right: UTM/BVLOS/MUM-T overlays (Sense-and-Avoid, Datalink, UTM Integration, Control Transfer, Failure Injector).
- For scenarios that activate many plugins (e.g., `hpa_overlay`, `uas_military_ex`, `mumt_ramp_lvl*`):
  - Audit their `[taskplacement]` parameters so they respect the new convention.
  - Avoid overlapping containers; ensure each plugin’s `taskplacement` lands in a distinct rectangle.

Impact:
- Operators see similar spatial organization across all military scenarios, improving transfer and lowering search time.

---

### 2.4 Urgency & Temporal Encoding (Progress Bars and Sparklines)

**Goal:** Make time pressure (deadlines, time-to-impact, endurance) visible at a glance using 2D glyphs.

Actions:
- Implement simple **ASCII/Unicode progress bars** inside `Simpletext` rows for countdown-like quantities:
  - Threat TTI (time-to-impact).
  - Datalink message deadlines.
  - Mission Director endurance / mission timers.
  - VTOL transitions and battery warnings.
- Add a helper in `AbstractPlugin` or a small utility module:
  - `format_progress_bar(fraction: float, length: int = 20) -> str`.
- Apply progress bars consistently across plugins that already track remaining time, without changing underlying logic.

Impact:
- Earlier and more intuitive perception of urgency in all scenarios, without changing event timing or scoring.

---

### 2.5 Minimal 2D Tactical Overlays (No Depth)

**Goal:** Replace ASCII-style spatial hints with simple 2D shapes while staying in a single depth plane.

Actions:
- Introduce a lightweight **tactical overlay widget** (e.g., `TacticalDisplay`) in `core/widgets` that:
  - Draws rectangles, simple icons, and lines in a `task_container` using pyglet primitives.
  - Exposes a simple API (set geofence polygon, set UAV positions, set highlight flags).
- Use this widget **only for 2D representations** (no 3D depth cues):
  - Sense-and-Avoid geofence + normalized UAV positions.
  - Swarm formations (formation centers and offsets as simple icons).
  - VTOL pads or launch/recovery points as symbolic markers.

Impact:
- More intuitive spatial cues for UAS / MUM-T scenarios without introducing 3D, VR, or depth switching.

---

## 3. Plugin-Specific Visualization Upgrades

This section lists the primary plugins used across UAS, HPA, and MUM-T scenarios and how to upgrade each while preserving validity.

### 3.1 Mission Director (UAV Timelines)

Used in: `uas_basic`, `uas_bvlos`, `uas_military_ex`, `mumt_ramp_*`, and related templates.

Upgrades:
- Ensure column header is fixed and clear:
  - `UAV | Mission | Mode | Task | Endurance | Alert`.
- Use monospaced font so columns line up across rows.
- Add:
  - Progress bar for mission time remaining (if `duration` > 0).
  - Progress bar or numeric display for endurance remaining.
- Highlight states:
  - `Mode = AUTO` in a distinct color (e.g., cyan) to show automation.
  - Non-empty `alert` fields in WARNING/CRITICAL colors.
- Sorting / ordering:
  - Keep UAV rows in fixed order (UAV1–UAV6) to avoid cognitive re-mapping.

Validation considerations:
- Do not change how missions are scheduled or logged; only change row formatting.

---

### 3.2 Sense-and-Avoid (Intruders & Geofences)

Used in: UAS BVLOS, military UAS, MUM-T scenarios.

Upgrades:
- Keep the textual table but:
  - Sort intruders by **time-to-impact** ascending.
  - Use progress bars to show TTI.
  - Color-code `Status` (ACTIVE, RESOLVED, OVERDUE).
- Use the new tactical overlay widget to show:
  - Geofence polygon in a single 2D plane.
  - UAV icons positioned by normalized coordinates.
  - Visual highlight when a UAV is in breach (outline or flashing border).

Validation considerations:
- Maintain existing `log_performance` events (`saa_spawn`, `saa_resolve`, `geofence_breach`, etc.).
- Keep geofence purely 2D; do not add 3D depth planes.

---

### 3.3 Payload Manager / Sensor Resource / Data Overload

Used in: UAS payload-heavy and overload scenarios.

Upgrades:
- For each sensor/pod row, show:
  - Icon or short tag for sensor type (EO, IR, SAR).
  - A **horizontal bar** for bandwidth usage (Mbps / capacity).
  - Color-coded bar segments when the configured capacity is exceeded.
- For `sensorresource` and `dataoverload`:
  - Keep the existing textual logs but add a single line summary at top:
    - `Active bandwidth: 68/80 Mbps (OVER)`.
    - `Storm level: 3, Active channels: EO, IR`.

Validation considerations:
- Do not change capacity or depletion models.
- Bar visualization must be derived only from existing numeric state.

---

### 3.4 Datalink (CPDLC-Style Messaging)

Used in: UAS, BVLOS, and MUM-T scenarios.

Upgrades:
- Reformat rows to:
  - `ID | Channel | Priority | TTI(s) | Text (truncated)`.
- Use:
  - Symbol or color for priority (NORM/PRIO/CRIT).
  - Progress bar for message deadline.
- Indicate **selected row** (keyboard focus) with a visible highlight.
- Integrate optional **audio cue** for CRIT/PRIO messages via `audioalerts` or TTS.

Validation considerations:
- Keep message timing, queuing, and logging unchanged; this is purely representational.

---

### 3.5 Threat Board (Fighter / HPA)

Used in: HPA overlay, QRA, MUM-T levels.

Upgrades:
- Table remains the primary representation:
  - `ID | Sector | Range (nm) | Weapon | TTI (s) | Status`.
- Enhancements:
  - Sort threats by TTI.
  - Use progress bar for TTI per row.
  - Color-code `Status` (PENDING / ENGAGED / RESOLVED / OVERDUE).
  - Reserve a footer line for `Chaff x/x | Flare y/y` with warning colors when below thresholds.

Validation considerations:
- Do not change threat scheduling logic or scoring.

---

### 3.6 Energy Manager (G-Envelope)

Used in: HPA overlay, QRA scenarios.

Upgrades:
- Enhance the existing ASCII G-meter:
  - Show markers for **warning threshold**, **target G**, and **limit** with a consistent glyph set.
- Add a compact bar for energy reserve (0–100%).
- Show the **current active event** with name, target G, remaining seconds.

Validation considerations:
- Do not alter event timing or cumulative G-seconds computation.

---

### 3.7 VTOL Manager / VTOL Power / Launch & Recovery

Used in: UAS VTOL and mixed scenarios.

Upgrades:
- Present VTOL state as a small table per aircraft:
  - `ID | Phase | Time in Phase | Battery % | Alerts`.
- Use status colors for phase transitions that are pending confirmation or overdue.
- Keep power and stability metrics visible but not cluttered (single summary row + optional details).

Validation considerations:
- All transitions and power changes remain logged identically.

---

### 3.8 Operator Capacity, Platform Profiles, Automation Hooks

Used broadly in UAS and MUM-T scenarios.

Upgrades:
- Operator Capacity:
  - Show **current active/supervisory counts** and highlighted when exceeding validated limits (e.g., 2–3 active, up to 6 supervisory).
- Platform Profiles:
  - Use one-line summaries per UAV (`ScanEagle | 20h | EO/IR | Skyhook`) instead of verbose multi-line text.
- Automation Hooks:
  - Provide a compact list of enabled rules; highlight those that have recently fired.

Validation considerations:
- Only formatting and summarization; no change in rule semantics.

---

## 4. Scenario-Level Integration

### 4.1 Scenario Families and Visual Consistency

Families:
- **Baseline MATB**: classic 4 tasks + scheduling.
- **UAS**: `uas_basic`, `uas_bvlos`, `uas_military_ex`, UAS templates.
- **HPA**: `hpa_overlay`, `hpa_qra_ex`, and derived templates.
- **MUM-T Ladder**: `mumt_ramp_lvl1/2/3`.

Actions:
- For each scenario family, verify that:
  - Task placements follow the common layout convention.
  - Visual enhancements (progress bars, color coding, tactical overlays) are applied consistently to the same plugins.
- Maintain a **small JSON/YAML mapping** (internal or documented) from scenario file → active plugins → expected visual components for QA.

---

## 5. Implementation Phases

### Phase 0 – Baseline Audit

1. List all plugins and which scenarios use them.
2. Capture current screenshots for reference runs (one per key scenario).
3. Confirm no timing or logging regressions will be tolerated; all changes must be visual only.

### Phase 1 – Core Infrastructure

1. Implement unified status/color system and `colorblind_mode`.
2. Implement `format_progress_bar()` utility.
3. Implement optional `ui_scale` in `config.ini` and wire into font size selection.
4. Introduce `TacticalDisplay` widget (if warranted) for 2D spatial overlays.

### Phase 2 – High-Impact Plugin Upgrades

1. Mission Director, Sense-and-Avoid, Datalink.
2. Threat Board, Energy Manager, Operator Capacity.
3. VTOL Manager and Payload/Sensor Resource.

For each plugin:
- Refactor drawing code to use new utilities.
- Add unit/integration tests where feasible (e.g., expected ASCII output for known states).
- Re-run key scenarios and visually verify behavior.

### Phase 3 – Scenario Alignment and QA

1. Normalize `[taskplacement]` across scenarios to the new layout convention.
2. Re-run baseline and military scenarios with test subjects (or lab pilots) to:
   - Confirm no unintended increase in workload from clutter.
   - Gather subjective feedback on clarity.
3. Optionally collect NASA-TLX / HRV on old vs new visualizations in a small A/B study to confirm that changes **do not increase workload** and may reduce error rates.

---

## 6. Guardrails and Non-Goals

- **No 3D/VR, no multiple depth planes**: all tasks remain on a single 2D surface.
- **No changes to scenario syntax**, timing, or scoring logic.
- **No new tasks or subtasks** introduced through visualization-only work.
- All enhancements must be:
  - Configurable (e.g., visual extras can be disabled if needed).
  - Backward compatible with existing logs and analysis pipelines.

By following this roadmap, OpenMATB’s 2D visualizations can become more intuitive and user-friendly across all baseline, UAS, HPA, and MUM-T scenarios while preserving the scientific validity established by decades of MATB research.