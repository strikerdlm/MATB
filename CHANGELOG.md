# Changelog

All notable changes to the MATB military aviation research platform.

## [Unreleased] — 2026-06-04

### Phase 3A — frequentist statistics engine

#### Added
- `matb_integration/analysis/stats/` — standalone frequentist library (pandas +
  statsmodels + scipy; no web imports). Implements four pre-specified research
  questions:
  - **Q1** workload-level effects: MixedLM with random intercepts per participant,
    2-df Wald omnibus, Holm-corrected pairwise contrasts gated on BH-FDR
    (q = .05) over the 6-test confirmatory family ({SYSMON d′, raw TLX, Bedford}
    × {Q1 omnibus, Q2 slope}).
  - **Q2** visit trajectories: additive MixedLM (level-adjusted common slope as
    primary; interaction model fit exploratory).
  - **Q3** repeated-measures correlation: Bakdash & Marusich (2017) ANCOVA
    rmcorr implementation, validated to 1e-9 against the published Bland-Altman
    oracle; level-adjusted sensitivity included.
  - **Q4** DEPDF parameter drift: g0/p0/tau0 ~ visit LMM.
  - First-class result statuses: `ok | insufficient_data | not_estimable` with
    pre-registered data gates.
  - Effect sizes: raw + 95% CI + standardized by √(re_var + resid_var).
  - Full provenance: input fingerprint (sha256 of sorted metric rows), library
    versions, engine version 1.0.0.
  - rmANOVA complete-case sensitivity for every Q1/Q2 outcome.
- CLI: `python3 -m matb_integration.analysis.stats.cli run --metrics-json m.json
  --fits-json f.json -o artifact.json` — accepts the JSON bodies of
  `GET /metrics/long` and `GET /fits`; writes a reproducible provenance-stamped
  JSON artifact for manuscript supplementary material.
- Backend: `POST /analysis/run` — collects rows from the DB, fingerprints input,
  runs the stats engine, caches result per (fingerprint, engine_version) in the
  new `analysis_result` table, returns the artifact with a `cached` flag.
  `GET /analysis/latest` — returns the most recent cached artifact; 404 when
  none exists.
- Frontend: `/analysis` screen — run button; confirmatory family table (p, p-FDR,
  survives); Q1 and Q2 LMM cards with status badges and pairwise contrast tables;
  Q3 rmcorr table; Q4 drift cards; rmANOVA sensitivity lines; provenance footer
  with library versions and pre-registration caveats. Sidebar item enabled.
- Tests: 36 library tests (`tests/analysis_stats/`; pandas 2.x and 3.x), 31
  backend tests, 19 frontend tests.
- Live end-to-end verified 2026-06-04: 8 participants × 2 visits × 3 levels =
  48 CSVs ingested over HTTP with a gate-crossing synthetic cohort; CLI artifact
  fingerprint matched the backend run exactly.

> Phase 3B (async Bayesian PyMC sensitivity) is pending — not marked done.

---

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
- SAGAT freeze-probe service (Phase 8 #9):
  - `openmatb/plugins/sagat.py`: new `Sagat(BlockingPlugin)`. Pauses scenario
    time and other plugins via OpenMATB's existing blocking semantics; renders
    5-s blank purge then forced-choice probes via new `MultipleChoice` widget;
    logs per-probe `probe_id, sa_level, domain, question_text, options_text,
    given_answer, correct_answer, is_correct, latency_sec, freeze_id` rows
    plus snapshot of every alive non-blocking plugin's `get_state_snapshot()`
    at freeze onset. All freeze-internal timing uses `time.monotonic()`
    because scenario_time is paused.
  - `openmatb/core/widgets/multiple_choice.py`: new `MultipleChoice` widget —
    keyboard-only, UP/DOWN/ENTER.
  - `openmatb/plugins/abstractplugin.py`: additive default
    `get_state_snapshot() -> {}`. Overridden in `sysmon.py`, `track.py`,
    `resman.py`, `communications.py` to expose failure flags, cursor position,
    tank tolerance, and callsign seed respectively.
  - `openmatb/includes/questionnaires/sagat_generic_en.txt`,
    `sagat_generic_es.txt`: generic 9-probe bank (3 per SA level) in EN and ES.
    Spanish is functional-equivalence (no formal psychometric validation);
    rationale documented in `docs/research/scales/sagat_validation.md`.
  - `matb_integration/sagat/probe_bank.py`: pyglet-free `Probe` dataclass +
    parser + validator + writer. `PROBE_BANK_FORMAT_VERSION = 1.0`.
  - `matb_integration/sagat/scenario_builder_ext.py`: `FreezeEvent`,
    `emit_freezes_for_block(...)` — schedules freezes with **asymmetric** ISA
    stagger (≥ 30 s after any ISA only, since cognitive contamination flows
    ISA→SAGAT not the reverse) and symmetric inter-freeze stagger (≥ 120 s);
    samples probes stratified 1×L1/1×L2/1×L3 per freeze; writes per-participant
    per-freeze probe files and per-block manifest JSON. Deterministic from
    seed.
  - `matb_integration/scenario_builder.py`: `include_sagat`, `sagat_bank`,
    `sagat_output_dir`, `sagat_n_freezes`, `participant_id`, `block_num`
    parameters on `build_block_scenario`.
  - `matb_integration/log_converter.py`: `_sagat_metric` aggregator producing
    per-block `sa_score_level_{1,2,3}_pct`, `sa_score_overall_pct`,
    `mean_latency_sec`, `n_probes_*` counters, plus `freeze_details` array.
    Cross-checks the per-block manifest to distinguish missing freezes
    (executed=False) from missing data.
  - Tests: 23 in `tests/test_sagat_probe_bank.py`, 13 in
    `tests/test_sagat_scenario_emission.py`, 6 SAGAT additions to
    `tests/test_log_converter.py`, plus `tests/integration/test_sagat_smoke.py`
    for build-pipeline integration. Full Xvfb-runtime smoke is skip-marked
    pending a recorded participant CSV fixture — OpenMATB replay is
    session-replay, not live key-injection.
  - Upstream-divergence note: edits the vendored OpenMATB submodule. Additive
    surface area: `plugins/sagat.py`, `core/widgets/multiple_choice.py`,
    two questionnaire files, plus one method per `abstractplugin.py /
    sysmon.py / track.py / resman.py / communications.py`. One-line export
    edits in `plugins/__init__.py` and `core/widgets/__init__.py`. No
    semantics of existing OpenMATB code changed.
- Spanish questionnaire files for OpenMATB genericscales:
  - `matb_integration/questionnaires/nasatlx_es.txt`: 6-subscale NASA-TLX in Spanish
    (Demanda mental, Demanda física, Demanda temporal, Rendimiento, Esfuerzo, Frustración)
    using the validated translation of Sebastián García & del Hoyo Delgado (2010,
    *Rev. Psicol. Trabajo Org.* 26(3); N=398) and INSST NTP-544.
  - `matb_integration/questionnaires/isa_es.txt`: ISA 5-point workload probe in Spanish
    (title: "Carga de trabajo", anchors: Muy baja — Excesiva). Note: functional-equivalence
    translation; no formal Spanish psychometric validation exists.
  - `matb_integration/questionnaires/bedford_es.txt`: Bedford 10-point scale in Spanish
    (anchors: Capacidad sobrante — Abandonar tarea). Same caveat: no formal validation.
  - `docs/research/scales/scale_validation_es.md`: peer-reviewer-grade summary of
    validation evidence for all three scales, recommended Methods-section language, and
    full APA7 references.
- `matb_integration/scenario_builder.py`: Spanish questionnaire filename constants
  (`ISA_QUESTIONNAIRE_ES`, `NASATLX_QUESTIONNAIRE_ES`, `BEDFORD_QUESTIONNAIRE_ES`).
- `matb_integration/log_converter.py`: bilingual support — Spanish subscale titles
  (`NASA_TLX_SUBSCALES_ES`, `ISA_TITLE_ES`) are recognised and normalised to English
  keys in the output dict; Bedford title unchanged ("Bedford" is a proper name).
- `tests/test_log_converter.py`: 4 new tests for Spanish-title parsing
  (95 pass, 3 skip total suite).
- `matb_integration/` package: bridge between `aircraft_monitor/` scenario
  generator and OpenMATB engine
  - `scenario_builder.py`: converts `ResearchProtocol` demand blocks to
    OpenMATB-compatible `.txt` scenario files without requiring OpenMATB to
    be installed
  - `questionnaires/isa_en.txt`: ISA 5-point rating scale in OpenMATB
    `genericscales` format
  - `log_converter.py`: parses OpenMATB session CSV → structured JSONL record
    per block. Extracts SYSMON (n_hits/misses/FA, hit_rate, d' via Hautus
    log-linear correction, mean RT), ISA probes (per-probe Workload ratings,
    mean, SD), NASA-TLX (6 subscales + raw_tlx), and COMM (HIT/MISS/FA/CR
    from `sdt_value` rows, hit_rate, FA_rate, d', RT). Probit implemented
    with Acklam rational approximation (error < 1.15e-9, stdlib-only,
    Python 3.12+ compatible). CLI: `python -m matb_integration.log_converter
    <session.csv> --participant P01 --block low_workload --level LOW -o
    output.jsonl`
- `install_to_openmatb.py`: CLI script that copies questionnaire and scenario
  assets into an existing OpenMATB installation tree
- `scenarios/military_aviation/`: pre-generated Low / Medium / High workload
  scenario files, ready to drop into OpenMATB `includes/scenarios/`
- `tests/test_scenario_builder.py`: unit + regression tests for the
  scenario builder, including sync-guard assertions that fail loudly if
  OpenMATB changes its default `sysmon` parameters
- `tests/test_log_converter.py`: 23 tests covering probit accuracy, d-prime
  edge cases, all four metric functions, and regression against session-27
  smoke-test CSV (64 pass, 3 skip)
- `matb_integration/questionnaires/bedford_en.txt`: Bedford 10-point workload
  scale in OpenMATB `genericscales` format (1=spare capacity, 10=abort task);
  slider value rounded to nearest integer by the log converter
- `matb_integration/scenario_builder.py` additions:
  - `BEDFORD_QUESTIONNAIRE` constant; `include_bedford` flag on
    `build_block_scenario()` to emit Bedford at block end
  - `LATIN_SQUARE_3`: all 6 permutations of LOW/MEDIUM/HIGH; groups of 6
    consecutive participants are fully counterbalanced
  - `block_order_for_participant(participant_id)`: deterministic Latin-square
    row from participant numeric suffix
  - `build_session_files(participant_id, output_dir, ...)`: generates 3
    named scenario files in counterbalanced order for one participant
    (`P03_block1_MEDIUM.txt`, `P03_block2_LOW.txt`, `P03_block3_HIGH.txt`)
- `matb_integration/log_converter.py`: added `_bedford_metric()` and
  `bedford` key to `convert_session()` output
- `matb_integration/analysis/descriptive.py`: non-parametric analysis pipeline
  - Reads JSONL files (file or directory), groups by participant × workload level
  - Descriptives (n, median, mean, SD) per level per metric
  - Friedman χ² + Kendall W (within-subject, 3 conditions, N≥3)
  - Spearman ρ per participant (condition rank vs metric) + sign-test across N
  - Console summary + optional TSV output
  - CLI: `python -m matb_integration.analysis.descriptive <source> -o results.tsv`
- `tests/test_latin_square_and_bedford.py`: 27 tests for Latin-square
  properties, `build_session_files`, Bedford questionnaire format, Bedford
  metric parsing, and analysis pipeline (91 pass, 3 skip total suite)
- `docs/implementation/phase8_feature_spec.md`: Phase 8–11 implementation
  specification (primary tasks, scoring, ISA ingestion, LSL, SAGAT, BIDS)
- `docs/research/military-aviation-platform/research_evidence_review.md`:
  peer-reviewer-grade gap analysis vs AF-MATB and USAARL MATB (40 refs)

- **Suhir DEPDF mission-outcome layer** (`matb_integration/suhir/`): implements
  Suhir (2018) probabilistic human-nonfailure (Eq. 5.1/5.16), FOAT calibration
  (Eq. 5.19–5.21), and mission-outcome composition (Eq. 5.10) on existing
  log_converter output. Model core validated against book Table 5.1 and
  Example 5.1. Phase 1 (F = F0); HCF via external neurocognitive screen.

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
