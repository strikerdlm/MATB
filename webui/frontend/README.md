# MATB Research Console — Frontend (Phase 1B)

Next.js + TypeScript tracker UI for the MATB longitudinal study, styled to match
the HRV "Mission Control" console. Talks to the Phase 1A FastAPI backend.

## Setup

```bash
cd webui/frontend
npm install
```

## Run (dev — backend must be running on :8000)

```bash
# backend (from repo root):
cd webui/backend && ~/.venvs/matb-webui/bin/uvicorn app.main:app --port 8000

# frontend:
cd webui/frontend && npm run dev   # http://localhost:3100
```

Override the API base with `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

## Test

```bash
npm test          # vitest unit tests (lib/: api client + tracker aggregation)
npm run typecheck # tsc --noEmit
npm run build     # production build
```

## Screens

- **Tracker** (`/`) — the 12×6×3 completeness grid; click a filled cell for that
  block's metrics (SYSMON d′, hit-rate, RT; COMM d′; NASA-TLX; Bedford; ISA) plus
  the visit's DEPDF fit (G₀/P₀/τ₀) once all three levels are ingested.
- **Participants** (`/participants`) — list + add (auto-generates the 6 visits).
- **Upload** (`/upload`) — tag + ingest an OpenMATB CSV, with guard feedback
  (duplicate / filled-cell / validation).
- **Visualization** (`/visualization`) — Trajectories / Levels / DEPDF / Group tabs
  with PNG export on every chart (descriptive only; inferential stats are Phase 3).
- **Analysis** (`/analysis`) — run the frequentist statistics engine via a
  single button; displays a confirmatory family table (p, p-FDR, survives) for
  the 6-test BH-FDR family; Q1 (MixedLM workload effects) and Q2 (visit
  trajectory) cards with `ok` / `insufficient_data` / `not_estimable` status
  badges and pairwise contrast tables; Q3 repeated-measures correlation table;
  Q4 DEPDF parameter drift cards; rmANOVA complete-case sensitivity lines; and a
  provenance footer (input fingerprint, engine version, library versions, caveats).
  **Bayesian section (Phase 3B):** dedicated run button that posts to
  `POST /analysis/bayes/run` and polls `GET /analysis/bayes/status` every 2 s
  (polling resumes automatically when mounting over an active job); posterior
  summary tables showing mean, 95% ETI, R̂, and ESS per parameter for Q2 and Q4
  re-fits; red "not converged" badge when max R̂ > 1.01 or divergences detected;
  sampler settings and pinned priors provenance footnote.

## Design system

Mirrors `HRV/frontend`: TailwindCSS + shadcn/ui (Radix + CVA), HSL CSS-variable
theme tokens, dark-mode, lucide-react icons, zustand state. Pure logic lives in
`src/lib/{api,tracker}.ts` (unit-tested); React components are thin.

Spec: `docs/superpowers/specs/2026-06-03-webui-phase1b-frontend-design.md`
Plan: `docs/superpowers/plans/2026-06-03-webui-phase1b-frontend.md`
