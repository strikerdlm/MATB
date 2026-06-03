# Suhir DEPDF Mission-Outcome Layer for MATB — Design

**Date:** 2026-06-03
**Status:** Approved (design); pending implementation plan
**Source model:** Ephraim Suhir, *Human-in-the-Loop: Probabilistic Modeling of an
Aerospace Mission Outcome*, CRC Press / Taylor & Francis, 2018.
OCR at `docs/research/military-aviation-platform/2026-05-28_ocr_probabilistic modeling of an aerospace mission outcome(2018).md`.

---

## 1. Motivation and core insight

Suhir's book is, operationally, a **calibration recipe for a flight simulator run
as a "test-to-fail" rig** — his FOAT (failure-oriented accelerated testing). The
method: run an operator at *graded, elevated* mental-workload (MWL) levels,
measure when and how they fail, and fit a probability-of-nonfailure law (the
double-exponential probability distribution function, DEPDF). Combine that human
nonfailure probability with equipment reliability (Weibull) and environment
severity to get a **probabilistic mission-outcome** estimate.

**The MATB platform already is that rig.** The LOW / MEDIUM / HIGH OpenMATB
scenarios it generates (2.9 / 7.5 / 12.1 events·min⁻¹) *are* the graded MWL
stimulus levels Suhir's calibration equations (5.16–5.21) require. The existing
`log_converter` already emits everything the basic model needs.

This layer turns the data the app generates into the model's inputs and outputs:
calibrated per-participant DEPDFs, mission-outcome probabilities, and three
actionable products (individualized training targets, selection ranking, and an
adaptive-automation trigger signal).

## 2. The model (reference)

**Basic DEPDF of human nonfailure (Eq. 5.1 / 5.3):**

    P^h(F,G) = P0 · exp[ (1 − G²/G0²) · exp(1 − F²/F0²) ]

- `G`  = actual MWL ("demand"/"stress");  `G0` = baseline (normal) MWL
- `F`  = actual human capacity factor (HCF, "capacity"/"strength"); `F0` = baseline HCF
- `P0` = probability of nonfailure at baseline (G=G0, F=F0)

**Ordinary-capacity reduction (Eq. 5.16), used in Phase 1 when F is unknown:**

    P^h(G) = P0 · exp(1 − G²/G0²)

**Time degradation (Weibull, Eq. 5.5–5.7):**

    P^h_i(t) = P^h_i(0) · exp[ −(λ^h_i · t)^β ]      (same form for equipment P^e_i(t))

**Mission outcome over n segments (Eq. 5.10):**

    Q = 1 − Σ_i q_i · P^e_i(t_i) · P^h_i(t_i)

  where `q_i` = probability the i-th segment is fulfilled under a harsh
  environment of the anticipated severity, Σ q_i = 1.

**Extended DEPDF with time, health symptom S, human-error MTTF T\* (Eq. 9.1) — Phase 2:**

    P^h = P0 · exp[ (1 − γ_S·S·t − G²/G0²) · exp(1 − γ_T·T\* − F²/F0²) ]

**Calibration (FOAT, Eq. 5.19–5.21):** from times-to-failure τ1,τ2,τ3 at three MWL
levels G1,G2,G3, solve the transcendental Eq. 5.19 for `G0`, then Eq. 5.20 for
`P0`, Eq. 5.21 for `τ0`. Suhir's own reliability-update tool — the Beta
distribution (Ch. 2.4.10) — stabilizes `P0` at small N.

## 3. Book variable → MATB data source

| Suhir variable | Source in MATB | Status |
|---|---|---|
| `G`, `G0`, `G(t)` — MWL | NASA-TLX (raw + 6 subscales), ISA time-series, Bedford; **G0 = participant's own LOW block** | exists |
| `P^h` — nonfailure | SYSMON / COMM d′, hit-rate, TRACK/RESMAN deviation | exists |
| `λ^h`, `T\*` — failure rate / MTTF | time-to-failure from timestamped MISS / excursion events | recoverable |
| `q_i`, `T_i` — environment / segments | scenario structure (stressor-pack roadmap) | partial |
| `S`, `γ_S` — physiological symptom | LSL physio (HRV, SpO₂) | Phase 2, not wired |
| `F`, `F0` — HCF | baseline neurocognitive screen (external; simulator cannot produce F) | external input |

**App-generates vs. externally-supplied boundary (answers "use the data this app
generates"):** the app cleanly generates the entire demand / performance /
failure side (`G`, `P^h`, `λ^h`, `T\*`, later `S`). It **cannot** generate HCF —
Suhir states `F` "cannot typically be evaluated experimentally using accelerated
testing on a flight simulator." HCF is supplied by an external baseline
neurocognitive screen. Corollary: `F` is only estimable from MEDIUM/HIGH blocks
(it has no leverage at G=G0).

## 4. Architecture — new package `matb_integration/suhir/`

Pure-function core, thin I/O at the edges, each unit independently testable.

| Module | Responsibility | Depends on |
|---|---|---|
| `depdf.py` | Stateless model math: basic (5.1), ordinary-capacity (5.16), extended (9.1), Weibull (5.5–5.7), entropy. | numpy |
| `failure_events.py` | Apply pre-specified per-task failure criteria to JSONL/raw rows → timestamped failure series, λ^h, MTTF T\*, Weibull β per block×task. | log_converter output |
| `mwl.py` | Normalize TLX/ISA/Bedford → dimensionless G/G0 anchored to participant LOW block; G(t) from ISA series. | log_converter output |
| `hcf.py` | HCF input **contract** + neurocognitive-screen adapter; defaults to F0 when screen absent. | external screen (later) |
| `calibration.py` | FOAT fit across the 3 MWL levels (5.19→G0, 5.20→P0, 5.21→τ0); Beta-update for P0; γ_S/γ_T (9.12–9.14) in Phase 2. | depdf, failure_events, mwl |
| `mission.py` | Segment composition → overall mission Q (5.10); environment q_i config. | depdf |
| `cli.py` | `matb-suhir fit <session_dir>` → params JSON; `matb-suhir mission <config>` → Q. | all above |

## 5. Data flow

OpenMATB CSV → `log_converter` (existing JSONL) → `failure_events` + `mwl`
(feature extraction) → `calibration` (per-participant fit) → `mission` / report
→ params JSON + figures. Read-only over existing artifacts; **nothing in
OpenMATB changes.**

## 6. Failure-event specification (pre-registered)

Decision: **discrete per-task failure events** (faithful to Suhir's "error =
failure" and his testing-to-fail). A per-task criteria config
(`failure_criteria.yaml`), versioned in-repo and fixed before any fit:

- **SYSMON**: each MISS = one failure event (timestamp from raw detection row).
- **COMM**: each missed own-callsign prompt = failure.
- **TRACK**: cursor excursion beyond radius `r` sustained ≥ `t_ms` = failure (r, t_ms in config).
- **RESMAN**: tank level outside tolerance band ≥ `t_s` = failure.

Output per block×task: ordered inter-failure times → MTTF `T\*`, failure rate
`λ^h`, Weibull `β` via MLE.

## 7. HCF contract (interface now, screen later)

Decision: **HCF from an objective baseline neurocognitive screen.** The screen is
a **separate sub-project**; this design fixes only the contract:

```python
@dataclass
class HCFEstimate:
    participant_id: str
    value: float            # dimensionless, same scale as MWL
    source: str             # "screen" | "metadata_fom" | "F0_default"
    components: dict[str, float]
```

`hcf.resolve(participant_id)` returns the screen-derived estimate if present,
else `F0_default` — in which case the model runs in its Eq. 5.16 ordinary-capacity
form (mathematically exact, not a hack). Phase 1 ships in the `F0_default` form.

## 8. Calibration and the validation oracle

The model module is TDD'd against the book's **own published numbers**:

- **Table 5.1** — the P̄ = P^h/P0 ratio matrix (8×8 of F/F0 × G/G0) — exact fixtures.
- **Example 5.1** — the worked 6-segment mission giving Q = 1% — exact fixture.

These give a hard correctness anchor independent of any participant data.
Small-N `P0` stabilized via the Beta-update (Ch. 2.4.10).

## 9. Actionable outputs

1. **Individualized training target** — the MWL level at which each participant's
   `P^h` crosses a chosen threshold (operationalizes Suhir's "trained to handle
   factor-of-3 MWL" guidance).
2. **Selection ranking** — participants ordered by fitted capacity / curve shape.
3. **Automation-adequacy & live hook** — given a required mission `Q`, compute
   whether the human contribution suffices or equipment reliability must
   compensate; predicted `P^h(t)` becomes the **trigger signal for the Phase 11
   adaptive-automation engine** (engage automation when `P^h(t)` drops below
   threshold). This layer produces the signal only; the engine is separate.
4. **BIDS-derivative export** of fitted parameters (Phase 10 #18).

## 10. Testing and validity guardrails

- Unit tests against Table 5.1 / Example 5.1 fixtures (model correctness).
- Property tests: monotonicity (`P↓` as `G↑`, `P↑` as `F↑`), bounds in [0,1].
- Normalization **sensitivity analysis** as a first-class output (the ratio-scale
  validity threat: TLX/ISA/Bedford are ordinal/interval, model squares them as
  ratios; defense is Suhir's within-participant *comparative* framing).
- Every fit emits an explicit assumptions/limitations block: within-participant
  comparative only; 3-level exact-identification → zero residual df, no
  goodness-of-fit test of the functional form (Suhir advises ≥4 levels; consider
  adding an intermediate difficulty later).
- Research instrument — **not** a certified safety tool.

## 11. Scope boundaries

- **Phase 1 (this build):** §4–10 with `F = F0`, basic DEPDF + mission outcome,
  on existing JSONL. Home: `matb_integration/suhir/`.
- **Phase 2 (after LSL physio lands):** Ch. 9 symptom term `γ_S·S·t`.
- **Out of scope / separate sub-projects:** neurocognitive-screen internals; the
  adaptive-automation engine itself (this layer only emits its trigger signal);
  stressor-pack–derived `q_i` environment library (consumed, not built here).

## 12. Open items deferred to the plan

- Exact normalization function for TLX/ISA/Bedford → dimensionless `G` (and its
  sensitivity-analysis sweep set).
- Numerical solver choice for the transcendental Eq. 5.19 (and convergence guards
  when the 3 measured τ are near-degenerate).
- Weibull `β` MLE vs. Suhir's Rayleigh (β=2) simplification as a default.
