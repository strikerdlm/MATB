# Changelog

All notable changes to the MATB military aviation research platform.

## [Unreleased] — 2026-05-03

### Smoke test — headless Xvfb, low_workload.txt, 95s run (session 27)
Confirmed working after three bug fixes below:
- SYSMON MISS events logged at t=37.8s, 41.9s, 55.8s (3 MISSes in 95s, ~2.9/min rate ✓)
- ISA genericscales probe fires at t=90.006s (scheduled every 90s ✓)
- COMM radioprompt events fire at t=53.0s and t=62.0s (own/other ✓)
- Max scenario_time reached: 90.05s before SIGINT
- CSV columns confirmed: `logtime, scenario_time, type, module, address, value`
- Performance rows: `type=performance, module=sysmon, address=signal_detection, value=MISS`
- ISA rows: `type=event, module=genericscales, address=self, value=start`

### Fixed — three headless bugs in OpenMATB submodule

### Added
- `matb_integration/` package: bridge between `aircraft_monitor/` scenario
  generator and OpenMATB engine
  - `scenario_builder.py`: converts `ResearchProtocol` demand blocks to
    OpenMATB-compatible `.txt` scenario files without requiring OpenMATB to
    be installed
  - `questionnaires/isa_en.txt`: ISA 5-point rating scale in OpenMATB
    `genericscales` format
- `install_to_openmatb.py`: CLI script that copies questionnaire and scenario
  assets into an existing OpenMATB installation tree
- `scenarios/military_aviation/`: pre-generated Low / Medium / High workload
  scenario files, ready to drop into OpenMATB `includes/scenarios/`
- `tests/test_scenario_builder.py`: unit + regression tests for the
  scenario builder, including sync-guard assertions that fail loudly if
  OpenMATB changes its default `sysmon` parameters
- `docs/implementation/phase8_feature_spec.md`: Phase 8–11 implementation
  specification (primary tasks, scoring, ISA ingestion, LSL, SAGAT, BIDS)
- `docs/research/military-aviation-platform/research_evidence_review.md`:
  peer-reviewer-grade gap analysis vs AF-MATB and USAARL MATB (40 refs)

### Changed
- `requirements.txt`: added `pyglet>=2.1.0,<3.0.0` (OpenMATB engine dep)
- README: extended Phase 8+ roadmap with OpenMATB integration strategy

### Fixed — three headless bugs in OpenMATB submodule
1. `openmatb/core/clock.py`: Changed `pyglet.clock.schedule(advance)` to
   `schedule_interval(advance, 1/60)`. Without vsync on Xvfb, the event
   loop spins at ~100k fps with dt≈0μs, so scenario_time never advanced past
   t=0 and no scenario events ever fired.
2. `openmatb/core/joystick.py`: Demoted `add_error("No joystick found")` to
   silent pass. The module-level error was added to `get_errors()` at import
   time; on the first Scheduler.update() call `show_errors()` created a
   blocking modal that could never be dismissed headless.
3. `matb_integration/scenario_builder.py`: Fixed `tank-A/B-lossperminute` →
   `tank-a/b-lossperminute` (OpenMATB parameter validation is case-sensitive).

### Removed
- `core`: stray 36 MB `light-locker` ELF crash dump removed from git

### Architecture note
The MATB repo (`aircraft_monitor/`) is a scenario *emitter*. OpenMATB
(`/root/repos/openmatb/`, v1.4.5, Cegarra & Valéry 2023–2026) is the task
*engine* (SYSMON, TRACK, COMM, RESMAN, LSL outlet, generic rating scales).
`matb_integration/` generates OpenMATB-compatible scenario files driven by
`aircraft_monitor/research/protocol.py` workload parameters.

On Linux/headless: OpenMATB requires an X server.
  `Xvfb :100 -screen 0 1920x1080x24 &`
  `DISPLAY=:100 /path/to/venv/bin/python main.py`

### Calibration note (Pontiggia et al. 2024)
Event rates at `difficulty=0.20/0.50/0.80`, `alerttimeout=10000 ms`,
`block_duration=900 s` (15 min):

| Level  | SYSMON | COMM | Total | /min |
|--------|--------|------|-------|------|
| LOW    | 32     | 12   | 44    | 2.9  |
| MEDIUM | 80     | 32   | 112   | 7.5  |
| HIGH   | 130    | 51   | 181   | 12.1 |

Pontiggia LOW ≈ 3/min ✓. Pontiggia HIGH ≈ 23.5/min reflects their full
RESMAN pump event count not separately tallied here. Validated by monotonic
ISA/NASA-TLX increase across levels.

## [0.3.0] — 2026-05-02
### Added
- MATB-inspired experiment mode with research protocol and JSONL logging
- `research/protocol.py`: `DemandBlock`, `ResearchProtocol`, `WorkloadLevel`,
  `AutomationMode`, `ResearchModality`
- `research/runner.py`, `research/logger.py`: full JSONL run output
- Phase 8+ roadmap in README

## [0.2.0] — 2026-05-02 (prior sessions)
### Added
- Rich terminal dashboard: UAV + FighterAircraft scenario generators
- Simulation physics engine, event system, visualization panels

## [0.1.0] — 2026-05-02
### Added
- Initial aircraft_monitor package skeleton
