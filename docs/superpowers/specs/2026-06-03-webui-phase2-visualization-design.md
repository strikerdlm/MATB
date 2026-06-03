# MATB Research Console (webui) — Phase 2 Design: Visualization Dashboards

**Date:** 2026-06-03
**Status:** Approved (design); pending implementation plan
**Scope:** Phase 2 of the console — descriptive visualization dashboards over the
Phase 1 data (blocks + DEPDF fits). The statistics engine (inferential: LMM,
rmcorr, Bayesian, CIs, p-values) is **Phase 3** and explicitly out of scope here.
**Builds on:** Phase 1 spec (`2026-06-03-webui-phase1-data-tracker-design.md`),
Phase 1A backend, Phase 1B frontend (branch `feat/webui-phase1`, PR #6).

---

## 1. Purpose

Give the researcher immediate visual insight into the longitudinal study as data
accumulates: per-participant metric trajectories, the workload manipulation
check (level comparisons), the Suhir-model view (fitted DEPDF curves and
parameter drift), and a descriptive group overview. All charts match the HRV
design language and offer one-click PNG export.

## 2. Decisions (locked in brainstorming)

- **Chart families (all four):** metric trajectories; level comparisons; DEPDF
  curves + G₀/P₀/τ₀ trajectories; group overview (descriptive mean ± SD).
- **Export:** ECharts built-in save-as-image (PNG, 2× pixel ratio) on every
  chart. Journal-grade vector figures are Phase 3's Python pipeline.
- **DEPDF math stays server-side:** curve points are computed by the backend via
  `matb_integration.suhir.depdf.p_nonfailure_ordinary` — no model math in TS.

## 3. Backend additions (`webui/backend`)

### 3.1 `GET /metrics/long`
Tidy long-format rows for every ingested block:

```json
[{"participant_id":"P01","visit_ordinal":1,"workload_level":"LOW",
  "metric":"sysmon_d_prime","value":2.79}, ...]
```

- **Metric registry** (pure function `extract_long_metrics(record) -> list[(metric, value)]`
  in a new `app/metrics_long.py`): `sysmon_d_prime`, `sysmon_hit_rate`,
  `sysmon_mean_rt_ms`, `comm_d_prime`, `nasatlx_raw_tlx`, `bedford`, `isa_mean`.
  Null/missing values are **omitted** (long format carries only observed values).
- Optional `?participant_id=` filter.
- Long format is deliberately the same shape Phase 3's stats engine will consume.

### 3.2 `GET /fits`
All `DepdfFit` rows joined to their visit ordinal:

```json
[{"participant_id":"P01","visit_ordinal":1,"g0":40.1,"p0":0.99,"tau0":12.2,
  "hcf_source":"F0_default","mwl_source":"raw_tlx",
  "curve":[{"r":1.0,"p":0.99},{"r":1.04,"p":0.95}, ...]}]
```

- `curve` = `p_nonfailure_ordinary(p0, g=r, g0=1)` sampled at 51 evenly spaced
  `r = G/G₀ ∈ [1.0, 3.0]` (Suhir's meaningful range; saturation beyond 3).
  Computed server-side via the suhir package (single-sourced math).
- Optional `?participant_id=` filter.

## 4. Frontend additions (`webui/frontend`)

### 4.1 Pure logic (`src/lib/viz.ts`, vitest TDD)
- `METRICS` registry: key → `{label, unit?, decimals}` for the seven metrics.
- `trajectorySeries(rows, participantId, metric)` → `{visits:[1..6], series:{LOW:[...],MEDIUM:[...],HIGH:[...]}}`
  with `null` gaps for missing visits (ECharts `connectNulls: false`).
- `levelComparison(rows, participantId, metric)` → per-visit grouped values.
- `groupOverview(rows, metric)` → per visit × level `{mean, sd, n}` across
  participants (descriptive only).
- API additions in `src/lib/api.ts`: `getMetricsLong(participantId?)`,
  `getFits(participantId?)` + `MetricRow`, `FitRow` types.

### 4.2 Chart wrapper (`src/components/charts/EChart.tsx`)
One thin `echarts-for-react` wrapper applying: transparent background, theme
colors from the design tokens (LOW/MED/HIGH = info/warning/danger hues), Inter
font, and the toolbox `saveAsImage` (PNG, `pixelRatio: 2`) on every chart.

### 4.3 Visualization page (`src/app/visualization/page.tsx`)
Replaces the placeholder. shadcn **Tabs** with four panels:

| Tab | Chart(s) | Controls |
|---|---|---|
| Trajectories | line: metric vs visit 1–6, one series per level | participant select, metric select |
| Levels | grouped bars: level values per visit | participant, metric |
| DEPDF | (a) line: P^h vs G/G₀ ∈ [1,3], one curve per fitted visit; (b) small multiples: G₀, P₀, τ₀ vs visit | participant |
| Group | mean line ± SD band per level across visits | metric |

Empty states: "no data yet for this selection" / "no fits yet (a fit needs all
3 levels of a visit)". Sidebar nav: **Visualization becomes enabled**; Analysis
remains a disabled Phase-3 stub.

## 5. Out of scope (Phase 2)

- Inferential statistics of any kind (CIs from models, p-values, rmcorr, LMM,
  Bayesian) — Phase 3.
- Vector/SVG export, figure captioning, publication layouts — Phase 3 pipeline.
- Editing data; physiological signals; SAGAT visualizations (no SAGAT fields in
  the long registry yet — added when SAGAT data collection starts).

## 6. Testing & verification

- **Backend pytest:** `extract_long_metrics` covers all seven metrics + omits
  nulls; `/metrics/long` end-to-end on an ingested block; `/fits` curve has 51
  points, starts at `(1.0, ≈p0)`, and is strictly decreasing.
- **Frontend vitest:** `viz.ts` reshapers (trajectory gaps, level grouping,
  group mean/sd math).
- **Gates:** `tsc --noEmit` + `npm run build` per component task.
- **Live e2e:** seed one participant with ≥2 visits incl. one complete visit
  (real fit), screenshot all four tabs via Playwright.

## 7. Open items deferred to the plan

- Exact ECharts option shapes (axis formatting, band rendering for mean ± SD —
  two stacked transparent areas vs custom series).
- Whether `/metrics/long` should also emit the six TLX subscales (default: no —
  raw TLX only in Phase 2; subscales added with Phase 3 needs).
