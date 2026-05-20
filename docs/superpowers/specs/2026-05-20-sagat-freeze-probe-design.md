# SAGAT Freeze-Probe Service — Design

**Author.** Diego Malpica, MD — Aerospace medicine and human factors.
**Status.** Design approved 2026-05-20. Implementation pending.
**Scope.** Phase 8 item #9 from `docs/implementation/phase8_feature_spec.md` — operational, deterministic, EN/ES-bilingual SAGAT freeze-probe capture for the OpenMATB-integrated military aviation research platform.
**Companion docs.**
- `docs/research/military-aviation-platform/research_evidence_review.md` — gap analysis and citations.
- `docs/implementation/phase8_feature_spec.md` §5 — the requirement this design satisfies.

---

## 1. Goal

Add a Situation Awareness Global Assessment Technique (SAGAT; Endsley 1995a/2021) freeze-probe service to the platform so that mid-block, scenario time pauses, all task displays blank for a "perceptual purge", a small set of forced-choice probes covering SA Levels 1 (perception), 2 (comprehension), and 3 (projection) is administered, and the responses are scored against ground truth declared at scenario-authoring time. Output is logged to the same OpenMATB CSV stream as every other plugin and is aggregated by `matb_integration/log_converter.py` into the per-block JSONL record.

The service is the only Phase 8 deliverable that requires both new runtime code inside the vendored OpenMATB submodule and new generative code in `matb_integration/`. The four primary tasks, the rating-scale ingestion path (NASA-TLX / Bedford / ISA), and the Latin-square block ordering already exist.

---

## 2. Non-goals

- **Population-specific probe banks** (fighter / RPA / transport-MUM-T). Those are Phase 10 stressor-pack deliverables; the present design only ships a generic demo bank with EN/ES parity to prove the engine works end-to-end.
- **Runtime querying of other plugins' state to compute correct answers.** Considered and rejected — it tightly couples SAGAT to the internals of every other plugin and limits probes to states OpenMATB already models. The platform is deterministic given seed, so correct answers can be declared at authoring time.
- **Replay-mode** support. OpenMATB's `REPLAY_MODE` (which sets `can_receive_keys=False, can_execute_keys=True` for emulated input streams) is not in scope. The integration smoke test will use the existing replay key-emulation path *only* to drive automated testing; a participant-replay use case for SAGAT (re-scoring a recorded session) is deferred.
- **Mouse input.** Keyboard-only by design — removes mouse-hover SA-cuing as a confound and keeps the UX uniform with the existing genericscales path.
- **Cross-participant counterbalancing of probe order.** Each session uses a stratified random permutation, seed-deterministic from `participant_id + block_num`. Counterbalancing across participants would require a Latin-square design over the probe bank, which adds research-design complexity without obvious payoff at this stage. Documented so it can be revisited in Phase 9.

---

## 3. Architecture

### 3.1 File layout

```
openmatb/plugins/sagat.py                       NEW   ≈ 250 lines
openmatb/core/widgets/multiple_choice.py        NEW   ≈ 120 lines
openmatb/core/widgets/__init__.py               MODIFY  one-line export
openmatb/plugins/abstractplugin.py              MODIFY  add get_state_snapshot() default
openmatb/plugins/{sysmon,track,resman,communications}.py
                                                MODIFY  override get_state_snapshot()
openmatb/includes/questionnaires/
    sagat_generic_en.txt                        NEW   ≈ 9 probes
    sagat_generic_es.txt                        NEW   parallel Spanish version

matb_integration/sagat/__init__.py              NEW
matb_integration/sagat/probe_bank.py            NEW   parser + validator, pyglet-free
matb_integration/sagat/scenario_builder_ext.py  NEW   schedule + emit per-freeze files

matb_integration/scenario_builder.py            MODIFY  include_sagat flag, hook into ext
matb_integration/log_converter.py               MODIFY  _sagat_metric, freeze_details

tests/test_sagat_probe_bank.py                  NEW   ≈ 12 tests
tests/test_sagat_scenario_emission.py           NEW   ≈ 12 tests
tests/test_log_converter.py                     MODIFY  +6 SAGAT tests
tests/integration/test_sagat_smoke.py           NEW   Xvfb headless smoke

docs/research/scales/sagat_validation.md        NEW   psychometric provenance
```

### 3.2 Architectural split — why these boundaries

- Plugin + widget + questionnaire assets live inside the vendored `openmatb/` because they touch pyglet rendering and the OpenMATB scheduler runtime.
- Everything *generative* (freeze-time scheduling, probe sampling, per-participant file emission, post-hoc CSV → JSONL aggregation) lives in `matb_integration/sagat/` so it runs in plain pytest without spinning up a window. This mirrors the existing `scenario_builder.py` / `log_converter.py` split.
- The new `get_state_snapshot()` hook on `AbstractPlugin` is the *only* coupling between SAGAT and the other plugins. It is additive, defaults to `{}`, and is independently useful for replay/audit work.

### 3.3 Patch surface against upstream OpenMATB

Pulling future upstream OpenMATB will need to merge:
- **Additive (safe):** `sagat.py`, `multiple_choice.py`, two questionnaire files, `tests/` (the tests directory is gitignored upstream anyway).
- **Single-line export:** `core/widgets/__init__.py` adds one line. Trivial merge.
- **One-method-per-plugin additions:** `get_state_snapshot()` is appended to `abstractplugin.py` (default) and overridden in `sysmon.py`, `track.py`, `resman.py`, `communications.py`. Five small surfaces; document each in the diff so future merges can reapply them.

This patch surface is comparable to the three headless bug-fixes already accepted in the submodule (commit 6365d3f).

---

## 4. Probe-bank file format

### 4.1 Stanza grammar

```
PROBE_ID: gen_l1_lights
SA_LEVEL: 1
DOMAIN: perception
QUESTION: Which monitoring lights were active in the past 30 seconds?
OPTIONS: green only | red only | both | neither
CORRECT: red only
TIMEOUT_SEC: 15
```

All 7 fields are required; order is **not** enforced by the parser (a dict-keyed accumulator is used). The canonical order shown above is what the writer emits and what hand-authored banks should follow, but a reshuffled stanza parses identically as long as the semantic constraints (DOMAIN/SA_LEVEL consistency, CORRECT in OPTIONS, etc.) still hold. Rationale: a value misplaced into the wrong slot whose type happens to be valid (e.g., transposed OPTIONS and CORRECT) is already caught by the semantic checks downstream; strict order enforcement adds no bug-catching power and degrades hand-edit ergonomics. Blank lines separate stanzas. Lines starting with `#` are comments and may appear anywhere outside a stanza; they are stripped by the parser.

Header line at top of file (comment, mandatory):
```
# SAGAT freeze | participant=P03 | block=1 | freeze=2 | scenario_time=540 | seed=44
```
The parser extracts and validates this header against the scenario .txt that points to this probe file. Mismatch (e.g. probe file declares `block=1` but scenario .txt fires it at the block-2 timestamp) raises at scenario-build time, not at runtime.

### 4.2 Validation rules (enforced at parse time)

| Rule | Action on violation |
|---|---|
| All 7 fields present per stanza (order not enforced) | `ProbeBankError` naming the probe_id |
| Bank file contains at least one probe (zero-probe file is malformed) | `ProbeBankError` |
| `SA_LEVEL ∈ {1, 2, 3}` | `ProbeBankError` |
| `DOMAIN ∈ {perception, comprehension, projection}` | `ProbeBankError` |
| `SA_LEVEL` and `DOMAIN` consistent (1↔perception, 2↔comprehension, 3↔projection) | `ProbeBankError` |
| `OPTIONS` is `|`-separated, 2 ≤ count ≤ 6 | `ProbeBankError` |
| `CORRECT` appears verbatim in `OPTIONS` | `ProbeBankError` |
| `TIMEOUT_SEC` integer, 5 ≤ value ≤ 60. Mandatory; `defaulttimeoutsec=15` on the plugin is a fallback for malformed legacy banks and should never trigger in normal use. | `ProbeBankError` |
| `PROBE_ID` unique within file | `ProbeBankError` |
| `"Unknown"` (EN bank) or `"No sé"` (ES bank, detected by `_es.txt` suffix) auto-appended to `OPTIONS` if absent | Silent (documented behaviour) |

The `"Unknown" / "No sé"` auto-append is a deliberate forced-choice safeguard. Endsley (2021, *Human Factors* 63(1)) shows that SAGAT's 94% sensitivity vs SPAM's 64% depends on participants being given an explicit "I don't know" anchor; omitting it inflates scores by inducing guessing.

### 4.3 Bilingual support

`sagat_generic_en.txt` and `sagat_generic_es.txt` carry identical `PROBE_ID` values across languages — only `QUESTION`, `OPTIONS`, `CORRECT`, and the auto-appended uncertainty anchor differ. This guarantees that data from EN and ES participants can be pooled by `probe_id`. The log_converter preserves the language of the bank used in the session's JSONL output (Spanish text in for ES sessions, English for EN).

The Spanish translation is functional-equivalence, not psychometrically validated (consistent with the documented status of `isa_es.txt` and `bedford_es.txt`). Caveat is captured in `docs/research/scales/sagat_validation.md`.

---

## 5. Runtime: `Sagat` plugin

### 5.1 Class

```python
class Sagat(BlockingPlugin):
    """Freeze-probe SA assessment. One file = one freeze = N probes."""
    def __init__(self):
        super().__init__()
        self.folder = P["QUESTIONNAIRES"]
        self.parameters.update({
            "filename": None,
            "purgeblanksec": 5,           # blank "perceptual purge"
            "defaulttimeoutsec": 15,      # per-probe; bank value wins if present
            "logfreezestate": True,       # snapshot active plugins at freeze onset
            "response": dict(text=_("UP/DOWN select, ENTER confirm"), key="ENTER"),
            "allowkeypress": True,
        })
        self.keys.update({"UP", "DOWN", "ENTER", "RETURN"})
        self.probes: list[Probe] = []
        self.current_probe_idx: int = 0
        self.selected_option_idx: int = 0
        self._purge_until_monotonic: float = 0.0
        self._probe_started_monotonic: float = 0.0
        self.freeze_id: str = ""
```

### 5.2 Lifecycle per freeze

1. Scenario fires `HH:MM:SS;sagat;filename;<probe_file.txt>` then `HH:MM:SS;sagat;start`.
2. `start()` is called. `BlockingPlugin` sets `alive=True, blocking=True`. OpenMATB's `core/scheduler.py` (verified at lines 145–160 of that file) observes the blocking plugin and:
   - calls `self.pause_scenario()` → `scenario_time` stops advancing,
   - stores `self.paused_plugins = get_active_non_blocking_plugins()` and calls `.pause()` on each.
3. **`create_widgets()` is overridden end-to-end.** SAGAT does NOT use the `BlockingPlugin` `<newpage>`/`#` slide-loading path because the per-probe stanza format would be flattened into a single mega-slide. Instead:
   - Read the probe file directly via `matb_integration.sagat.probe_bank.load_probes(self.input_path)`.
   - If parse fails (file missing, malformed, header mismatch) → log `sagat;parse_error;<reason>` and call `self.stop()` immediately. No silent recovery: better to lose this freeze than to score the wrong answer against a partial bank.
   - Optionally snapshot every alive non-blocking plugin: for each `plugin` in `Window.MainWindow.scenario.plugins` where `plugin.alive and not plugin.blocking`, call `plugin.get_state_snapshot()` and log each returned `{key: value}` as `sagat;snapshot_<alias>_<key>;<value>`. A plugin without an override returns `{}` and contributes nothing.
   - Compute `_purge_until_monotonic = time.monotonic() + purgeblanksec`.
   - Create the multiple-choice widget for the first probe (hidden) and a blank-frame widget for the purge.
4. **Purge phase** (`_purge_until_monotonic` not yet elapsed): show only the blank frame, ignore all key events.
5. **Probe phase** (one probe at a time):
   - Show the question text and option list with the current selection highlighted.
   - On UP/DOWN: move `selected_option_idx` modulo `len(probe.options)`.
   - On ENTER/RETURN: commit. Log:
     ```
     sagat;probe_id;<id>
     sagat;sa_level;<1|2|3>
     sagat;domain;<perception|comprehension|projection>
     sagat;question_text;<verbatim from probe>
     sagat;options_text;<pipe-separated verbatim>
     sagat;given_answer;<selected option text>
     sagat;correct_answer;<correct from probe>
     sagat;is_correct;<True|False>
     sagat;latency_sec;<time.monotonic() - _probe_started_monotonic>
     sagat;freeze_id;<freeze_id>
     ```
     Advance to next probe and reset `_probe_started_monotonic = time.monotonic()`.
   - **Timeout**: if `time.monotonic() - _probe_started_monotonic > probe.timeout_sec`, log `given_answer=TIMEOUT`, `is_correct=False`, `latency_sec=probe.timeout_sec`. Advance.
6. After the last probe, call `self.stop()`. The OpenMATB scheduler observes no blocking plugin remains, calls `self.unpause_scenario()`, and resumes all `self.paused_plugins`. Scenario time continues from where it left off.

### 5.3 Monotonic-time rule (global)

**Every duration measurement inside SAGAT — the purge clock, the per-probe timeout, the response latency — uses `time.monotonic()`, never `scenario_time`.** Reason: while the freeze is active, `scenario_time` is paused by the OpenMATB scheduler. Using `scenario_time` for latency would record zero for every probe and break the analysis.

`scenario_time` is still used for *scheduling* (when the freeze fires); only durations *during* the freeze use `monotonic`.

### 5.4 Failure modes

| Failure | Behaviour |
|---|---|
| `filename` parameter not set | Plugin logs `sagat;file_missing;no_filename_set` and stops immediately. |
| File path doesn't exist | Same: `sagat;file_missing;<path>` + stop. |
| Malformed probe stanza | `sagat;parse_error;<probe_id_or_line>` + stop. |
| `CORRECT` not in `OPTIONS` (caught at parse time) | Same parse error. |
| Header mismatch with scenario context | Caught at scenario-build time by `scenario_builder_ext.py`, not at runtime. |
| Per-probe timeout | Logged as `given_answer=TIMEOUT`, `is_correct=False`, `latency_sec=timeout_value`. Advance. |
| Participant hits ENTER with default selection | The default is option index 0; ENTER always commits whatever is highlighted. No "no answer" state during the response window. |
| `get_state_snapshot()` raises | Logged as `sagat;snapshot_<alias>;_error;<exception_type>` and skipped. Freeze proceeds. |
| OpenMATB window closes mid-freeze | OpenMATB shutdown path handles this; partial freeze CSV rows survive and are detected by `log_converter` as an incomplete freeze (`executed: false`). |

### 5.5 Multiple-choice widget (`core/widgets/multiple_choice.py`)

- Renders question text (top), then vertical list of options. A pyglet `Frame` highlights the selected row.
- `set_selected(i: int)` / `get_selected_value() -> str` / `set_question(text: str)` / `set_options(opts: list[str])`.
- Keyboard-only. No mouse hover or click bindings. Removes hover-as-cue confound.
- Implemented from pyglet primitives (`Simpletext`, `Frame`) already used by `Slider`; no new dependency.

---

## 6. Generation: `matb_integration/sagat/`

### 6.1 `probe_bank.py`

```python
@dataclass(frozen=True)
class Probe:
    probe_id: str
    sa_level: int                # 1 | 2 | 3
    domain: str                  # "perception" | "comprehension" | "projection"
    question: str
    options: tuple[str, ...]
    correct: str
    timeout_sec: int

def load_probes(path: Path) -> list[Probe]: ...
def validate_bank(probes: list[Probe]) -> None: ...   # raises ProbeBankError
def write_freeze_file(path: Path, probes: list[Probe], header: dict) -> None: ...
```

Pyglet-free; used by both tests and `scenario_builder_ext.py`. `write_freeze_file` is the inverse of `load_probes` and is used to emit per-freeze files from an in-memory probe selection.

### 6.2 `scenario_builder_ext.py`

```python
@dataclass(frozen=True)
class FreezeEvent:
    scenario_time_sec: float
    freeze_id: str               # e.g. "P03_b1_f2"
    probe_file_path: Path

def emit_freezes_for_block(
    *,
    participant_id: str,
    block_num: int,                 # 1-based
    block_duration_sec: int,
    isa_probe_times_sec: list[float],
    bank_path: Path,
    output_dir: Path,
    n_freezes: int = 3,
    probes_per_freeze: int = 3,     # 1 per SA level
    min_post_isa_stagger_sec: float = 30.0,
    min_inter_freeze_sec: float = 120.0,
    seed: int,
) -> list[FreezeEvent]: ...
```

**Scheduling algorithm:**

1. Reject the first 60 s and last 60 s of the block (warm-up + block-stop window).
2. Use `random.Random(seed)` to sample `n_freezes` times uniformly from the remaining window.
3. Reject the sample if any freeze time falls within `min_post_isa_stagger_sec` AFTER any ISA probe (asymmetric — ISA→SAGAT direction only, see rationale below), within `min_inter_freeze_sec` of another freeze time (symmetric), or within `BLOCK_EDGE_BUFFER_SEC` of a block-end event.
4. Retry up to `MAX_SAMPLER_RETRIES = 200`. If no valid schedule is found → raise `FreezeSchedulingError` (signals: probe budget exceeds block capacity; caller must reduce `n_freezes` or lengthen the block).

**Stagger asymmetry rationale.** The original spec specified a single symmetric ±60 s stagger from every ISA probe. This is infeasible at the workload densities the platform actually targets (ISA every 90 s for LOW, 60 s for MEDIUM, 45 s for HIGH) because symmetric ±60 s exclusion zones overlap entirely. The fix uses an asymmetric rule: cognitive contamination flows ISA→SAGAT (the ISA probe primes workload self-reflection, which can bleed into SAGAT projection answers), not the reverse. SAGAT's own 60–90 s of probes already serves as a purge before any subsequent ISA. A 30 s post-ISA buffer is enough for the operator to re-engage with the primary task before the next freeze.

**Probe sampling (stratified random permutation, not Latin square):**

- For each freeze, sample 1 probe per SA level (1, 2, 3) → `probes_per_freeze = 3` exact.
- Sampling is done **without replacement within a block** to avoid a probe appearing twice in the same block.
- A new permutation is drawn per block, seeded by `(participant_id, block_num, seed)`. The bank has ≈ 9 probes (3 per level), 3 freezes × 3 probes = 9 slots per block, so each probe appears exactly once per block by construction.
- "Latin square" was *not* used — that would require a counterbalanced design across participants, which the present design does not commit to (see §2 non-goals).

**Per-freeze probe-file emission:**
- File name: `{participant_id}_block{N}_freeze{M}.txt` placed in `output_dir`.
- Header carries `participant_id, block_num, freeze_id, scenario_time, seed`.
- File contents are exactly the stanzas selected for that freeze, in presentation order (deterministic from seed).

**Manifest emission:**
- One JSON file per block: `{participant_id}_block{N}_sagat_manifest.json`.
- Schema:
  ```json
  {
    "participant_id": "P03",
    "block_num": 1,
    "seed": 142,
    "bank": "sagat_generic_en.txt",
    "freezes": [
      {
        "freeze_id": "P03_b1_f1",
        "scenario_time_sec": 240.0,
        "probe_file": "P03_block1_freeze1.txt",
        "probe_ids": ["gen_l1_lights", "gen_l2_ontrack", "gen_l3_next"]
      }
    ]
  }
  ```
- Purpose: `log_converter.py` cross-checks the manifest against the CSV to detect freezes that never fired (participant aborted, OpenMATB crashed). Missing freezes appear in `freeze_details` with `executed: false` rather than being silently dropped.

**Independence of RNG streams:**
SAGAT uses `seed = protocol.seed + block_num * 100 + 7`. The `+ 7` and `* 100` keep SAGAT's stream independent of SYSMON / COMM / TRACK / ISA streams while still being fully reproducible. Convention documented in the module docstring.

### 6.3 Integration with `scenario_builder.build_block_scenario`

Two new parameters:
```python
include_sagat: bool = False,
sagat_bank: str | Path | None = None,   # None → auto by language
```

When `include_sagat=True`:
1. Compute the ISA probe times (already done elsewhere in `build_block_scenario`).
2. Call `emit_freezes_for_block(...)`. This validates the bank, schedules freezes, writes per-freeze files and the manifest, and returns the `FreezeEvent` list.
3. For each `FreezeEvent`, append two lines to the scenario `.txt`:
   ```
   {ts};sagat;filename;{probe_file_basename}
   {ts};sagat;start
   ```

The `build_session_files()` function gains:
```python
include_sagat: bool = False,
lang: str = "en",         # "en" → sagat_generic_en.txt, "es" → sagat_generic_es.txt
```

### 6.4 `log_converter.py` additions

A new `_sagat_metric(rows, manifest_path: Path | None)` function. Produces per-block:

```python
"sagat": {
    "n_freezes_planned": 3,
    "n_freezes_executed": 3,
    "n_probes_total": 9,
    "n_probes_answered": 8,
    "n_probes_timeout": 1,
    "sa_score_level_1_pct": 100.0,
    "sa_score_level_2_pct": 66.7,
    "sa_score_level_3_pct": 33.3,
    "sa_score_overall_pct": 66.7,
    "mean_latency_sec": 4.8,
    "freeze_details": [
        {
            "freeze_id": "P03_b1_f1",
            "scenario_time_sec": 240.0,
            "executed": true,
            "snapshot": { "track_cursor_position": [0.45, 0.51], ... },
            "probes": [
                {
                    "probe_id": "gen_l1_lights",
                    "sa_level": 1,
                    "domain": "perception",
                    "question": "¿Qué luces de monitoreo estaban activas en los últimos 30 segundos?",
                    "options": ["solo verde", "solo roja", "ambas", "ninguna", "No sé"],
                    "given_answer": "solo roja",
                    "correct_answer": "solo roja",
                    "is_correct": true,
                    "latency_sec": 3.2
                }
            ]
        }
    ]
}
```

- Per-level score: `100 * sum(is_correct where sa_level==N) / sum(1 where sa_level==N)`.
- Overall score: `100 * sum(is_correct) / n_probes_total`. (Pre-registration option: equal-weight average across levels — defer to analysis stage, log raw counts so either can be computed.)
- `mean_latency_sec` is computed over **all** probes, including timeouts (where latency = timeout value), to avoid an n-bias if a participant times out frequently.
- `freeze_details[*].executed: false` is emitted for any freeze in the manifest that has no matching `sagat;start` row in the CSV (participant aborted, plugin crashed, etc.). Counts toward `n_freezes_planned` but not `n_freezes_executed`.
- Spanish question/option text passes through unchanged — the converter does not translate.

---

## 7. Testing

### 7.1 Unit tests (no pyglet)

**`tests/test_sagat_probe_bank.py`** — 12 tests:

1. Well-formed bank loads and returns `Probe` objects with correct types.
2. Missing field in a stanza → `ProbeBankError` naming the offending probe.
3. `OPTIONS` count < 2 → raises.
4. `OPTIONS` count > 6 → raises.
5. `CORRECT` not in `OPTIONS` → raises.
6. `SA_LEVEL=1, DOMAIN=comprehension` mismatch → raises.
7. Duplicate `probe_id` within file → raises.
8. EN bank auto-appends `"Unknown"` to `OPTIONS` when absent.
9. ES bank (filename ends `_es.txt`) auto-appends `"No sé"`.
10. Bank where the anchor is already present does not double-append.
11. Round-trip: `load_probes(write_freeze_file(probes, header)) == probes`, EN and ES.
12. Header field mismatch (file declares `block=1`, build context says `block=2`) raises at scenario-build time.

**`tests/test_sagat_scenario_emission.py`** — 12 tests:

1. `emit_freezes_for_block` with `seed=42` is deterministic across two calls.
2. Two adjacent participant IDs (P03, P04) yield distinct schedules (no seed-collision).
3. ISA stagger with `min_stagger_sec=60`: ISA at 90 s → no freeze in the range 30 s ≤ t ≤ 150 s.
4. Inter-freeze stagger: no two freezes within `min_stagger_sec`.
5. Stratification: every freeze has exactly 1 perception + 1 comprehension + 1 projection.
6. No-collision within block: no `probe_id` appears twice in the same block's freezes.
7. Block-budget overflow: 8 freezes in a 900 s block with ISA every 90 s → `FreezeSchedulingError`.
8. Block-edge respect: no freeze in first or last 60 s.
9. Manifest JSON round-trips and matches the scenario `.txt` content.
10. `lang="es"` → freeze files contain Spanish QUESTION text from `sagat_generic_es.txt`.
11. Same-participant call twice with the same seed produces byte-identical output files.
12. Sync-guard: if `Probe` adds a required field without bumping `PROBE_BANK_FORMAT_VERSION`, test fails.

**`tests/test_log_converter.py`** — 6 additions:

13. Single-freeze CSV → `sagat` dict with correct counts and percentages.
14. Mixed-completeness CSV (1 full freeze, 1 with 1 timeout, 1 missing entirely) → `n_freezes_executed=2`, `n_probes_timeout=1`, missing freeze has `executed: false`.
15. Per-level aggregation: 3 L1 (2 correct), 3 L2 (1 correct), 3 L3 (0 correct) → `level_1_pct=66.7, level_2_pct=33.3, level_3_pct=0.0, overall_pct=33.3`.
16. ES CSV → `freeze_details[*].question` is Spanish, `options` is the Spanish list.
17. All-timeout block → `mean_latency_sec == timeout_value` (not NaN), `n_probes_answered == 0`.
18. Snapshot rows round-trip into `freeze_details[*].snapshot` for audit.

### 7.2 Headless integration test (Xvfb)

`tests/integration/test_sagat_smoke.py`:

- Generate a 120 s low-workload scenario with `include_sagat=True, n_freezes=1, probes_per_freeze=2`.
- Run OpenMATB headless under Xvfb (same pattern as session-27 smoke test).
- Use OpenMATB's existing replay-mode key-emulation to feed a deterministic input script: answer probe 1 correctly, probe 2 incorrectly.
- Assertions on the resulting CSV:
  - Exactly 1 `sagat;start` and 1 `sagat;stop` row.
  - 2 `sagat;is_correct` rows: one `True`, one `False`.
  - ≥ 1 `sagat;snapshot_track_cursor_position` row (track is alive at freeze onset).
- Assertion on `log_converter.convert_session()` output:
  - `sagat.n_probes_total == 2`, `sa_score_overall_pct == 50.0`, `n_freezes_executed == 1`.

### 7.3 Explicit non-coverage

- Visual layout of the multi-choice widget (pyglet rendering is hard to unit-test; manual run covers it).
- Purge-blank timing under heavy CPU load (sub-100 ms drift on a 5 s window is acceptable; not worth a fragile timing test).
- The psychometric validity of the *generic* probe bank — that is a Phase-10 stressor-pack research question, not a Phase-8 engineering question.

### 7.4 Acceptance gates

- [ ] 30+ new unit tests pass alongside existing 95.
- [ ] Headless integration smoke passes.
- [ ] One human-in-the-loop session start-to-finish: all freezes fire, JSONL output validates, scoring matches manual ground-truth audit.
- [ ] Cross-language: ES bank loads, ES smoke test passes, ES JSONL contains Spanish text.
- [ ] CHANGELOG entry under `[Unreleased]` describing the new plugin, the four-plugin `get_state_snapshot` hook, and the patch surface against upstream OpenMATB.

---

## 8. References

- Endsley, M. R. (1995a). Measurement of situation awareness in dynamic systems. *Human Factors*, 37(1), 65–84. https://doi.org/10.1518/001872095779049499
- Endsley, M. R. (2021). A Systematic Review and Meta-Analysis of Direct Objective Measures of Situation Awareness: A Comparison of SAGAT and SPAM. *Human Factors*, 63(1), 124–150. https://doi.org/10.1177/0018720819875376
- Cegarra, J., & Valéry, B. (2020). OpenMATB: A Multi-Attribute Task Battery promoting task customization, software extensibility and experiment replicability. *Behavior Research Methods*, 52, 1980–1992. https://doi.org/10.3758/s13428-020-01364-w
