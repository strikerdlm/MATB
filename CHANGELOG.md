# Changelog

All notable changes to the MATB military aviation research platform.

## [Unreleased] — 2026-05-03

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
