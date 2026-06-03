# MATB Research Console (webui) — Phase 1 Design: Data Model, Ingestion & Study Tracker

**Date:** 2026-06-03
**Status:** Approved (design); pending implementation plan
**Scope:** Phase 1 of a 3-phase platform. Phase 1 = backend data model + ingestion
pipeline + study/session tracker UI. Phases 2 (visualization) and 3 (analysis
engine) are sketched here only enough to prove the data model carries them; each
gets its own spec.

---

## 1. Purpose

A researcher console that collects, organizes, and (later) analyzes the data the
MATB/OpenMATB platform produces, styled consistently with the HRV "Mission
Control" console (`/root/repos/HRV`). The MATB task runs separately and produces
OpenMATB session CSVs; this console **ingests** those files, converts them via
the existing `matb_integration` library, and tracks study completeness.

**Study design driving the model:** 12 participants, 6 visits each (every 3 days
over 15 days: target days 0/3/6/9/12/15), each visit administering the **same
3-block battery** (LOW/MEDIUM/HIGH, per-participant counterbalanced Latin square —
see `matb_integration/scenario_builder.py:89-108`). Longitudinal repeated-measures:
**Participant (12) → Visit (6) → Block (3) → metrics** = 72 sessions / 216 blocks.

## 2. Constraints & decisions (locked in brainstorming)

- **Ingestion:** ingest MATB output files (CSV); the task is NOT run inside this UI.
- **Users:** single researcher console; simple/no auth (HRV-style).
- **Timepoint:** `timepoint = visit ordinal 1–6` (robust to cadence slips); the
  actual calendar date is stored alongside for drift analysis.
- **Repo:** same repo — new `webui/` directory; backend imports `matb_integration`
  directly (no packaging boundary).
- **Store:** SQLite (72 sessions; matches HRV simplicity).
- **IDs:** pseudonymized only ("P01"…); no PII in the store.
- **Stats (Phase 3, structured now):** organized around pre-specified research
  questions, one primary method + sensitivity (see §7).

## 3. Architecture & repo layout

```
webui/
  backend/
    app/
      main.py            FastAPI app + CORS + router registration
      db.py              SQLite engine/session (SQLModel)
      models.py          Participant, Visit, Block, DepdfFit tables
      schemas.py         Pydantic request/response models
      ingestion.py       file -> identity mapping, guards, convert, store, fit-trigger
      completeness.py    derive the 216-cell expected-vs-actual grid
      routers/
        participants.py  CRUD
        visits.py        CRUD + schedule helpers
        ingest.py        upload + tag + ingest endpoints
        tracker.py       completeness grid endpoint
    tests/               pytest
    requirements.txt
  frontend/              Next.js + TS (mirrors HRV/frontend/src/ structure)
  README.md
```

**Reuse, not reimplement:** ingestion calls `matb_integration.log_converter`
(`convert_session`, `parse_csv`) and `matb_integration.suhir.pipeline.fit_participant`.
No metric or model logic is duplicated in the web app.

**Dependency note:** the auto-fit-on-complete-visit feature (§5) requires the
`matb_integration.suhir` package, which currently lives in PR #5
(`feat/suhir-depdf-phase1`), not yet on `main`. Phase-1 implementation should
begin after PR #5 merges (or branch from it). Ingestion + tracker (everything
except the fit trigger) do not depend on suhir and could ship independently.

## 4. Data model

SQLModel tables (SQLite). Pseudonymized; no PII.

**participant**
- `id: str` PK — "P01"…
- `enrollment_date: date`
- `sex: str | None`, `age_band: str | None` — optional covariates
- `notes: str | None`
- `created_at: datetime`

**visit**
- `id: int` PK
- `participant_id: str` FK → participant.id
- `visit_ordinal: int` — 1–6 (the timepoint)
- `scheduled_day: int` — 0/3/6/9/12/15 (target)
- `actual_date: date | None` — when it actually happened (drift analysis)
- `status: str` — "planned" | "in_progress" | "complete"
- unique (`participant_id`, `visit_ordinal`)

**block**
- `id: int` PK
- `visit_id: int` FK → visit.id
- `workload_level: str` — "LOW" | "MEDIUM" | "HIGH"
- `source_csv_filename: str`
- `source_csv_sha256: str` — unique; dedup guard
- `ingested_at: datetime`
- `metrics_json: str` — the full `log_converter.convert_session` record (JSON)
- unique (`visit_id`, `workload_level`)

**depdf_fit** (one per visit once all 3 levels present)
- `id: int` PK
- `participant_id: str`, `visit_id: int` (unique) FK
- `g0, p0, tau0: float`
- `hcf_value: float`, `hcf_source: str`, `criteria_version: int`
- `per_level_json: str`
- `fitted_at: datetime`

**Completeness is derived, not stored** (`completeness.py`): the expected grid =
enrolled participants × 6 visits × 3 levels (216 cells). Each cell is *present*
(a `block` row exists) or *expected-but-absent*. This explicit-missing
representation drives the tracker UI and is what the Phase-3 mixed/Bayesian
models consume (they use all available data; missingness is informative).

## 5. Ingestion & file→identity mapping (Phase-1 critical path)

OpenMATB output CSVs are timestamp-named (e.g. `27_260503_174528.csv`) and carry
no participant/level/visit, so mapping is **explicit at upload**:

1. Operator uploads one or more CSVs and tags each with (participant_id,
   visit_ordinal, workload_level). The filename timestamp is shown as a hint.
2. Backend computes `sha256`, then runs `log_converter.convert_session`.
3. **Guards (never silently mislabel):**
   - reject if `sha256` already ingested (duplicate file);
   - if (visit, level) cell already filled → require explicit `overwrite=true`;
   - reject if `convert_session` yields no usable metrics (e.g. no SYSMON rows)
     — return a clear validation error, do not store.
4. Store the `block` row (metrics_json).
5. **Fit trigger:** if all 3 levels of that visit are now present, run
   `suhir.pipeline.fit_participant` over the visit's three blocks and upsert the
   `depdf_fit` row. Fit failures are logged and surfaced, not fatal to ingestion.

## 6. Study/session tracker UI (Phase-1 deliverable)

- **Completeness grid:** participants (rows) × 6 visits × 3 levels, each cell
  present/absent/overwrite-flagged; click a cell to see its block metrics summary
  and source file. This is the heart of Phase 1.
- **Participant management:** add/edit pseudonymized participants + enrollment date.
- **Visit management:** auto-generate the 6 planned visits on enrollment; record
  actual_date; status badges.
- **Upload flow:** drag/drop CSV(s) → tag (participant/visit/level) → ingest with
  inline guard feedback (duplicate, overwrite, validation).
- Working software at end of Phase 1: ingest all 72 sessions and see completeness.

## 7. Pre-specified analysis plan (structured now; built in Phase 3)

Engine is organized around **research questions**, each with one primary method +
sensitivity — the academic standard and the guard against garden-of-forking-paths
at n=12. Always report **effect sizes + CIs/credible intervals**, apply **FDR
across the question family**, and let LMM/Bayesian handle missingness natively.

| Question | Primary | Sensitivity |
|---|---|---|
| Q1 Workload-level effect on d′/TLX/Bedford | LMM (level fixed, participant random intercept) | rmANOVA |
| Q2 Trajectory across 6 visits (learning vs fatigue) | LMM (visit ± visit×level) | Bayesian hierarchical (PyMC) |
| Q3 Within-subject coupling (e.g. TLX↔d′) | rmcorr (within/between decomposition) | — |
| Q4 Drift in Suhir G0/P0/τ₀ over visits | Bayesian hierarchical / LMM on per-visit fits | LMM |

rmANOVA + OLS are **sensitivity/descriptive only**, with explicit complete-case
caveats. This table is design intent; the engine is a later spec.

## 8. Visualization (Phase 2 sketch)

Per-participant trajectory views (metric vs visit, faceted by level); per-visit
3-level comparisons; completeness heatmap; Suhir DEPDF curves + G0/P0 trajectories.
ECharts via `echarts-for-react`, journal-grade export. The §4 data model carries
all of these (block.metrics_json + depdf_fit per visit).

## 9. Frontend design system (visual consistency with HRV)

Replicate HRV (`/root/repos/HRV/frontend`) exactly so the consoles feel like one
family: Next.js App Router + React + TypeScript; **TailwindCSS + shadcn/ui**
(Radix primitives + `class-variance-authority` + `clsx` + `tailwind-merge`); the
same **HSL CSS-variable theme tokens** (copied from HRV `globals.css`), dark-mode
via `class`; **Inter** + **JetBrains Mono**; **framer-motion**; **lucide-react**;
**ECharts** (`echarts-for-react`); **zustand** state. The `frontend-design` skill
is used for polish during the build.

## 10. Testing

- **Backend (pytest):** ingestion file→identity mapping; dedup + overwrite +
  validation guards; auto-fit trigger when a visit completes; completeness-grid
  derivation; CRUD round-trips. Use a temp SQLite DB per test.
- **Frontend:** `tsc --noEmit` typecheck + minimal component tests for the upload
  flow and grid.
- The existing `matb_integration` + `suhir` suites remain green (reused as a lib).

## 11. Phase boundaries

- **Phase 1 (this spec → next plan):** §3–6, §10. Backend data core + ingestion +
  tracker UI.
- **Phase 2 (separate spec):** visualization dashboards (§8).
- **Phase 3 (separate spec):** the statistics engine (§7).
- **Out of scope (all phases):** running OpenMATB sessions in-app; participant
  self-service logins; PII storage; the neurocognitive-screen HCF source
  (external, per the suhir spec — Phase-1 fits run F=F0).

## 12. Open items deferred to the plan

- SQLModel vs SQLAlchemy-core choice (recommend SQLModel for brevity).
- Exact FastAPI ↔ Next.js dev wiring (ports, CORS, proxy) — mirror HRV's setup.
- Whether to vendor HRV's `ui/` component primitives or re-generate via shadcn CLI.
