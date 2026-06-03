# MATB Research Console — Phase 3: Statistics Engine (design)

Date: 2026-06-03
Status: approved by Diego ("proceed to Phase 3")
Predecessors: `2026-06-03-webui-phase1-data-tracker-design.md` (§7 pre-specified
analysis table), `2026-06-03-webui-phase2-visualization-design.md`.

## 1. Purpose and architecture: paper-first

The statistics engine answers the four pre-specified research questions (Q1–Q4,
Phase-1 spec §7) for the 12-participant × 6-visit × 3-level study. Its primary
consumer is the **manuscript**, not the web page — so the engine is a
**standalone library** with a CLI that writes versioned, seed-pinned JSON
artifacts, and the webui is a thin wrapper around it.

- **Library:** `matb_integration/analysis/stats/` — pure functions over a tidy
  long-format DataFrame (the exact shape served by `GET /metrics/long`:
  `participant_id, visit_ordinal, scheduled_day, workload_level, metric, value`)
  plus a fits frame for Q4 (`participant_id, visit_ordinal, g0, p0, tau0`).
  No web imports. Depends on pandas + statsmodels + scipy only (Phase 3A).
- **CLI:** `python3 -m matb_integration.analysis.stats.cli run --metrics-json
  <path> --fits-json <path> -o <artifact.json>` — reproducible artifact for the
  paper; same code path the webui calls.
- **Webui wrapper:** backend `POST /analysis/run` + `GET /analysis/latest`
  persisting an `analysis_result` row keyed by an **input fingerprint**
  (sha256 of the canonicalized input rows) so unchanged data never re-runs;
  frontend `/analysis` page renders the artifact.
- **Provenance block** in every artifact: engine version, criteria/spec
  version, library versions (statsmodels/pandas/scipy), input fingerprint,
  row/participant counts, seed (where stochastic), UTC timestamp.

## 2. Models (verbatim formulas; statsmodels MixedLM)

All confirmatory models are **linear mixed models with random intercepts
only** — at n=12 participants, random slopes are not reliably estimable and
are not attempted. `visit` enters as a centered numeric covariate
(`visit_c = visit_ordinal - 3.5`); `level` as a categorical with LOW reference.

| Q | Model (statsmodels formula) | Primary test |
|---|---|---|
| Q1 Workload-level effect | `value ~ C(level, Treatment('LOW')) + visit_c`, `groups=participant` | 2-df Wald omnibus on the two level coefficients |
| Q2 Trajectory (learning/fatigue) | `value ~ visit_c + C(level, Treatment('LOW')) + visit_c:C(level, Treatment('LOW'))`, `groups=participant` | `visit_c` slope (primary); interaction reported as secondary |
| Q3 Within-subject coupling | Canonical **rmcorr** (Bakdash & Marusich 2017): ANCOVA `y ~ x + C(participant)`; r from the x coefficient's partial SS, **df = N − k − 1** (N pairs, k participants) | rmcorr r |
| Q4 Drift in DEPDF params | Per parameter θ ∈ {g0, p0, tau0}: `θ ~ visit_c`, `groups=participant` | `visit_c` slope |

- Fitting: REML for estimates; the Q1 omnibus uses a Wald chi-square on the
  REML fit (small-sample caveat stated in the artifact's `caveats` list).
- Q3 sensitivity: rmcorr re-run on level-adjusted residuals (remove `C(level)`
  from both x and y first); reported alongside, never replacing, canonical rmcorr.
- rmANOVA sensitivity (Q1): complete-case two-way (level × participant)
  repeated-measures ANOVA via `statsmodels.stats.anova.AnovaRM`, with an
  explicit `complete_case_n` field; descriptive only.

## 3. Multiplicity (exact rules)

- **Confirmatory family (6 tests):** {`sysmon_d_prime`, `nasatlx_raw_tlx`,
  `bedford`} × {Q1 omnibus, Q2 visit slope}. **Benjamini–Hochberg FDR at
  q = 0.05** over exactly these 6 p-values. This is the only family.
- **Pairwise level contrasts (Q1):** computed only for metrics whose omnibus
  survives FDR; the 3 contrasts (MED−LOW, HIGH−LOW, HIGH−MED) are
  **Holm-corrected within metric**.
- Everything else — remaining metrics (`sysmon_hit_rate`, `sysmon_mean_rt_ms`,
  `comm_d_prime`, `isa_mean`), Q2 interactions, Q3, Q4, rmANOVA — is labeled
  **exploratory** in the artifact and UI; no correction, no "significant"
  language attached.

## 4. Statuses and pre-registered data gates

Every result object carries `status: "ok" | "insufficient_data" |
"not_estimable"` as first-class values — the UI and artifact render them,
never crash or silently omit.

- `insufficient_data` (gate fails before fitting):
  - Q1/Q2: < 6 participants with ≥ 2 levels (Q1) / ≥ 2 visits (Q2), or
    < 24 total rows for that metric.
  - Q3 (rmcorr): < 4 participants with ≥ 2 complete (x, y) pairs, or error
    df = N − k − 1 < 8.
  - Q4: < 4 participants with ≥ 2 fitted visits.
- `not_estimable` (fit attempted, failed): convergence failure, singular
  covariance, boundary RE variance with non-converged Hessian. The artifact
  records the exception class + message in `detail`.

## 5. Effect sizes (always reported)

- LMM coefficients: raw coefficient + **95% Wald CI**, plus a standardized
  effect with a **named standardizer**:
  `std_effect = coef / sqrt(re_var + resid_var)` — field
  `standardizer: "sqrt(re_var + resid_var)"` so the manuscript can state it.
- rmcorr: r, df, and a **Fisher-z 95% CI** using the rmcorr error df.
- rmANOVA: partial η² (descriptive).

## 6. Verification oracle

- rmcorr is verified against the **published Bland & Altman 1995 dataset**
  values reported in Bakdash & Marusich (2017): reference r/df/p generated
  once with `pingouin.rm_corr` in a throwaway venv and **hard-coded** into the
  test file with a comment recording the pingouin version. pingouin is NOT a
  runtime dependency.
- LMM paths verified by construction: simulate data with known fixed effects +
  random intercepts (seeded numpy), assert recovery within tolerance; plus
  gate/edge tests (empty, single-participant, all-missing-metric inputs).

## 7. Bayesian sensitivity (Phase 3B, async)

PyMC hierarchical re-fit of Q2 and Q4 as an **async job** in the console
(user-triggered, runs in a background thread/process; UI polls status).
Pre-specified weakly-informative priors: `Normal(0, 2.5·sd(y))` for
coefficients, `HalfNormal` for SDs. The artifact persists seed, chains, draws,
tune, R-hat, ESS, divergences; result is labeled **"not converged"** if any
R-hat > 1.01 or divergences > 0. PyMC is a Phase-3B-only dependency.

## 8. Sequencing

- **Phase 3A (first plan):** frequentist engine (Q1–Q4 + rmcorr + rmANOVA
  sensitivity + FDR/Holm + gates + effect sizes + provenance), CLI, backend
  endpoints + `analysis_result` table, `/analysis` page.
- **Phase 3B (second plan):** async PyMC job + diagnostics UI.

## 9. Dependencies

Phase 3A adds `pandas`, `statsmodels` (scipy already present) to
`webui/backend/requirements.txt` and to the library's needs; Phase 3B adds
`pymc` behind an optional extra. No frontend dependency changes (ECharts +
existing table components suffice).

## 10. Out of scope

Per-participant HCF (needs the Phase-10 neurocognitive screen); automated
model selection; power analysis UI; any correction scheme beyond §3.
