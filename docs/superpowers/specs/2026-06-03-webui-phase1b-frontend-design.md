# MATB Research Console (webui) — Phase 1B Design: Tracker Frontend

**Date:** 2026-06-03
**Status:** Approved (design); pending implementation plan
**Scope:** Phase 1B of the platform — the Next.js tracker frontend over the Phase 1A
FastAPI backend. Visualization (Phase 2) and the statistics engine (Phase 3) are
separate specs; this UI ships placeholder routes for them.
**Builds on:** `docs/superpowers/specs/2026-06-03-webui-phase1-data-tracker-design.md`
(the overall console design) and the Phase 1A backend (PR #6).

---

## 1. Purpose

A polished researcher-facing web UI that lets the operator manage the 12-participant
longitudinal study, upload OpenMATB session CSVs, and see study completeness at a
glance. It consumes the Phase 1A backend endpoints. Visual language mirrors the HRV
"Mission Control" console (`/root/repos/HRV/frontend`) so the two consoles feel like
one family.

## 2. Decisions (locked in brainstorming)

- **Scaffold:** copy/adapt HRV's frontend setup — its `package.json` deps,
  `tailwind.config`, `globals.css` HSL theme tokens, and `src/components/ui/`
  shadcn primitives — then build MATB pages on top.
- **Scope:** full tracker (completeness grid + participant management + visit list
  + CSV upload) inside an app shell with sidebar nav, plus disabled placeholder
  routes for Visualization (Phase 2) and Analysis (Phase 3).
- **Lives at:** `webui/frontend/` (same repo, same branch/PR as the backend —
  the console is one coherent deliverable).

## 3. Stack

Next.js (App Router) + React + TypeScript; TailwindCSS + shadcn/ui (Radix +
`class-variance-authority` + `clsx` + `tailwind-merge`); the HSL CSS-variable theme
tokens copied from HRV; dark-mode default; Inter / JetBrains Mono; framer-motion;
lucide-react; ECharts (`echarts-for-react`); zustand. Dev port **3100** (HRV
convention). Vitest for unit tests on pure logic.

## 4. Architecture & file layout

```
webui/frontend/
├── package.json, tsconfig.json, next.config.js, tailwind.config.ts, postcss.config.js
├── src/
│   ├── app/
│   │   ├── layout.tsx           # AppShell wrapper + dark theme
│   │   ├── globals.css          # theme tokens (copied from HRV)
│   │   ├── page.tsx             # Tracker (default route)
│   │   ├── participants/page.tsx
│   │   ├── upload/page.tsx
│   │   ├── visualization/page.tsx   # placeholder (Phase 2)
│   │   └── analysis/page.tsx        # placeholder (Phase 3)
│   ├── components/
│   │   ├── ui/                  # shadcn primitives (copied from HRV)
│   │   ├── layout/AppShell.tsx, layout/SidebarNav.tsx
│   │   ├── tracker/CompletenessGrid.tsx, tracker/CellDetailDialog.tsx
│   │   ├── participants/ParticipantTable.tsx, participants/AddParticipantDialog.tsx
│   │   └── upload/UploadForm.tsx
│   ├── lib/
│   │   ├── api.ts               # typed fetch client (pure, unit-tested)
│   │   ├── tracker.ts           # grid aggregation helpers (pure, unit-tested)
│   │   ├── store.ts             # zustand store
│   │   └── utils.ts             # cn() (copied from HRV)
│   └── types/index.ts           # Participant, Visit, TrackerCell, DepdfFit types
└── tests/                       # vitest unit tests for lib/
```

**Separation of concerns:** all non-trivial logic (request shaping, grid
aggregation, completeness math) lives in `src/lib/*` pure modules and is unit-tested;
React components are thin and validated by typecheck + build.

## 5. API client (`src/lib/api.ts`)

`API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"`. Typed
functions matching the Phase 1A backend:
- `listParticipants(): Promise<Participant[]>` — GET /participants
- `createParticipant(body): Promise<Participant>` — POST /participants (409 → typed error)
- `listVisits(id): Promise<Visit[]>` — GET /participants/{id}/visits
- `getTracker(): Promise<TrackerCell[]>` — GET /tracker
- `ingestCsv(file, {participant_id, visit_ordinal, workload_level, overwrite}): Promise<IngestResult>`
  — POST /ingest (multipart); maps 409/422 to a typed `IngestError` with the backend message.

`next.config.js` adds a `/api/:path*` rewrite to the backend for convenience; the
client uses `API_BASE` directly (matches HRV).

## 6. Screens

### Tracker (`/`) — the centerpiece
- `CompletenessGrid`: rows = participants; per participant, 6 visits × 3 levels = 18
  cells. Each cell is present (filled, accent/success) or expected-but-absent (muted).
  Per-participant completeness bar; header KPI "N / 216 cells filled".
- `CellDetailDialog`: clicking a filled cell opens a dialog with that block's metric
  summary (SYSMON d′, hit-rate, RT; COMM d′; NASA-TLX raw + subscales; Bedford; ISA
  mean) parsed from `metrics_json`, plus the visit's DEPDF fit (G₀/P₀/τ₀, hcf_source)
  if a `depdf_fit` exists.

### Participants (`/participants`)
- `ParticipantTable`: id, enrollment date, completeness (m/18 cells), visit status.
- `AddParticipantDialog`: id, enrollment_date, optional sex / age_band. On submit →
  POST /participants (which auto-creates the 6 visits); 409 surfaced inline.

### Upload (`/upload`)
- `UploadForm`: drag/drop or pick a CSV; select participant, visit_ordinal (1–6),
  workload_level (LOW/MED/HIGH); overwrite toggle. Submit → POST /ingest. Inline
  result: 201 success (with the created block summary), 409 duplicate/filled (the
  exact backend message), 422 validation. On success, invalidate the tracker store.

### Visualization (`/visualization`) and Analysis (`/analysis`)
- Placeholder pages ("Phase 2 / Phase 3 — coming soon"), reachable but disabled in nav.

## 7. State & data flow

A zustand store holds `participants` and `trackerGrid`, with actions that fetch via
`api.ts` and refetch after mutations (create participant, ingest). Pages read from the
store; mutations trigger a targeted refetch so the grid stays consistent without a
full reload.

## 8. Testing

- **Vitest unit tests** (TDD) on pure logic:
  - `lib/api.ts` — request URL/method/body shaping and error mapping (mocked `fetch`).
  - `lib/tracker.ts` — completeness aggregation (per-participant m/18, overall n/216,
    per-visit rollups) from a `TrackerCell[]` fixture.
- **Per-task build gate:** `npx tsc --noEmit` + `npm run build` must pass (no type
  errors, compiles).
- **Final verification:** run the backend (`uvicorn`) + `next dev` together, enroll a
  participant, ingest a sample CSV, confirm the grid cell flips to present and the
  detail dialog renders — captured via the run/screenshot tooling.

## 9. Build polish

The `frontend-design` skill is used during implementation for component craft
(spacing, motion, grid aesthetics, empty/loading/error states) so the result is
genuinely polished rather than generic. All output stays within the copied HRV
design system.

## 10. Out of scope (Phase 1B)

- Real charts / trajectories (Phase 2 visualization).
- The statistics engine (Phase 3 analysis).
- Editing/deleting participants or blocks (only create + ingest in Phase 1B).
- Auth / multi-user (researcher console; no login, per the overall spec).

## 11. Open items deferred to the plan

- Whether to copy HRV's exact `package.json` versions or bump to current — default:
  copy HRV's versions for guaranteed parity, then `npm install`.
- ECharts is included in deps for Phase 2 but not used by any Phase 1B screen (the
  grid is a component, not a chart) — kept in package.json to avoid a later reinstall.
- Vitest config / React Testing Library: unit tests target `src/lib` pure functions
  only in Phase 1B, so the lighter `vitest` (no jsdom component rendering) suffices.
