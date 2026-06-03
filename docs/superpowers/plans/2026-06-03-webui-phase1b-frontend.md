# MATB Research Console — Phase 1B (Frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use the **frontend-design** skill during component tasks (6–9) for visual polish within the copied HRV design system.

**Goal:** Build `webui/frontend/` — a Next.js/TypeScript tracker console (completeness grid + participant management + CSV upload + nav shell) over the Phase 1A backend, visually consistent with the HRV "Mission Control" console.

**Architecture:** Next.js App Router + Tailwind + shadcn/ui (copied from HRV). Pure logic (`src/lib/api.ts`, `src/lib/tracker.ts`) is unit-tested with vitest; React components are thin and gated by `tsc --noEmit` + `next build`. State via zustand; data from the FastAPI backend on port 8000.

**Tech Stack:** Next.js, React 18, TypeScript, TailwindCSS, shadcn/ui (Radix + CVA), zustand, lucide-react, framer-motion, ECharts (deps only, used in Phase 2), vitest. Node 22 / npm 10.

**Spec:** `docs/superpowers/specs/2026-06-03-webui-phase1b-frontend-design.md`
**HRV reference (copy source):** `/root/repos/HRV/frontend/`
**Backend (consumed):** `webui/backend/` — `GET /health`, `POST/GET /participants`, `GET /participants/{id}/visits`, `POST /ingest`, `GET /tracker`. CORS already allows `http://localhost:3100`.

---

## File structure

| File | Responsibility |
|---|---|
| `webui/frontend/package.json`, `tsconfig.json`, `next.config.js`, `tailwind.config.ts`, `postcss.config.js`, `vitest.config.ts`, `.gitignore` | Project config (copied/adapted from HRV) |
| `webui/frontend/src/app/globals.css` | Theme tokens (copied from HRV) |
| `webui/frontend/src/components/ui/*` | shadcn primitives (copied from HRV) |
| `webui/frontend/src/lib/utils.ts` | `cn()` etc. (copied from HRV) |
| `webui/frontend/src/types/index.ts` | `Participant`, `Visit`, `TrackerCell`, `BlockMetrics`, `DepdfFit` |
| `webui/frontend/src/lib/api.ts` | Typed fetch client (unit-tested) |
| `webui/frontend/src/lib/tracker.ts` | Grid aggregation helpers (unit-tested) |
| `webui/frontend/src/lib/store.ts` | zustand store |
| `webui/frontend/src/app/layout.tsx` | AppShell wrapper + dark theme |
| `webui/frontend/src/components/layout/{AppShell,SidebarNav}.tsx` | Shell + nav |
| `webui/frontend/src/app/page.tsx`, `components/tracker/{CompletenessGrid,CellDetailDialog}.tsx` | Tracker |
| `webui/frontend/src/app/participants/page.tsx`, `components/participants/{ParticipantTable,AddParticipantDialog}.tsx` | Participants |
| `webui/frontend/src/app/upload/page.tsx`, `components/upload/UploadForm.tsx` | Upload |
| `webui/frontend/src/app/{visualization,analysis}/page.tsx` | Placeholders |

All commands run from `/root/repos/MATB/webui/frontend` unless noted. Git commands run from repo root `/root/repos/MATB`.

---

### Task 1: Scaffold (copy + adapt HRV setup)

**Files:** create `webui/frontend/` by copying from `/root/repos/HRV/frontend/` and adapting.

- [ ] **Step 1: Copy config + design-system files from HRV**

```bash
cd /root/repos/MATB
mkdir -p webui/frontend/src
H=/root/repos/HRV/frontend
cp "$H/package.json" "$H/tsconfig.json" "$H/next.config.js" "$H/postcss.config.js" webui/frontend/
cp "$H/tailwind.config.ts" webui/frontend/ 2>/dev/null || cp "$H/tailwind.config."* webui/frontend/
cp -r "$H/src/components" webui/frontend/src/        # brings ui/* primitives
cp -r "$H/src/lib" webui/frontend/src/ 2>/dev/null || true
mkdir -p webui/frontend/src/app
cp "$H/src/app/globals.css" webui/frontend/src/app/globals.css
ls webui/frontend && ls webui/frontend/src/components/ui | head
```

- [ ] **Step 2: Prune copied lib to only `utils.ts`**

HRV's `src/lib` carries HRV-specific modules. Keep only `utils.ts`; we author MATB lib files in later tasks.

```bash
cd /root/repos/MATB/webui/frontend
find src/lib -type f ! -name 'utils.ts' -delete
ls src/lib   # expect: utils.ts
```

Also prune any copied `src/components` subfolders that are HRV-specific (keep only `ui/`):

```bash
find src/components -mindepth 1 -maxdepth 1 -type d ! -name 'ui' -exec rm -rf {} +
ls src/components   # expect: ui
```

- [ ] **Step 3: Replace `package.json` with the MATB-adapted version**

Overwrite `webui/frontend/package.json` with EXACTLY (HRV deps preserved; renamed; vitest added; port 3100):

```json
{
  "name": "matb-research-console-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev --port 3100",
    "build": "next build",
    "start": "next start --port 3100",
    "lint": "next lint",
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "dependencies": {
    "@radix-ui/react-dialog": "^1.0.5",
    "@radix-ui/react-label": "^2.0.2",
    "@radix-ui/react-select": "^2.0.0",
    "@radix-ui/react-separator": "^1.0.3",
    "@radix-ui/react-slot": "^1.0.2",
    "@radix-ui/react-switch": "^1.2.6",
    "@radix-ui/react-tabs": "^1.0.4",
    "@radix-ui/react-tooltip": "^1.0.7",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.0",
    "echarts": "^5.5.0",
    "echarts-for-react": "^3.0.2",
    "framer-motion": "^11.0.0",
    "lucide-react": "^0.330.0",
    "next": "^14.2.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "tailwind-merge": "^2.2.0",
    "tailwindcss-animate": "^1.0.7",
    "zustand": "^4.5.0"
  },
  "devDependencies": {
    "@types/node": "^20.11.0",
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "autoprefixer": "^10.4.17",
    "postcss": "^8.4.35",
    "tailwindcss": "^3.4.1",
    "typescript": "^5.3.0",
    "vitest": "^2.1.0"
  }
}
```

NOTE: `next` is pinned to `^14.2.0` (stable App Router) rather than HRV's `^16`,
to avoid a bleeding-edge toolchain. If `src/components/ui/*` imports any Radix
package not listed above, add it to `dependencies` (check after Step 5's typecheck).

- [ ] **Step 4: Point the dev proxy at the backend port (8000) and create supporting files**

Overwrite `webui/frontend/next.config.js` with EXACTLY:

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: { optimizePackageImports: ["lucide-react", "echarts-for-react"] },
  async rewrites() {
    const apiUrl = process.env.API_URL || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};
module.exports = nextConfig;
```

Create `webui/frontend/.gitignore`:

```
node_modules/
.next/
out/
*.tsbuildinfo
next-env.d.ts
.env*.local
```

Create `webui/frontend/vitest.config.ts`:

```typescript
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
```

- [ ] **Step 5: Install and verify the scaffold compiles**

```bash
cd /root/repos/MATB/webui/frontend
npm install 2>&1 | tail -5
npx tsc --noEmit && echo "TYPECHECK OK"
```
Expected: install succeeds; `TYPECHECK OK`. If typecheck reports a missing Radix dep used by a copied `ui/*` file, add it to `package.json` dependencies and re-run `npm install`. (No app pages exist yet, so typecheck only covers `ui/` + `utils.ts`.)

- [ ] **Step 6: Commit**

```bash
cd /root/repos/MATB
git add -f webui/frontend/package.json webui/frontend/tsconfig.json webui/frontend/next.config.js webui/frontend/postcss.config.js webui/frontend/tailwind.config.* webui/frontend/vitest.config.ts webui/frontend/.gitignore webui/frontend/src
git commit -m "feat(webui): scaffold Next.js frontend from HRV design system"
```

---

### Task 2: Types + typed API client (vitest TDD)

**Files:** Create `src/types/index.ts`, `src/lib/api.ts`, `src/lib/api.test.ts`.

- [ ] **Step 1: Write the failing test**

Create `webui/frontend/src/lib/api.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { createParticipant, getTracker, ingestCsv, IngestError } from "@/lib/api";

beforeEach(() => { vi.restoreAllMocks(); });

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response);
}

describe("api client", () => {
  it("getTracker GETs /tracker and returns cells", async () => {
    const cells = [{ participant_id: "P01", visit_ordinal: 1, scheduled_day: 0, workload_level: "LOW", present: true }];
    global.fetch = mockFetch(200, cells);
    const out = await getTracker();
    expect(out).toEqual(cells);
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("/tracker"), expect.objectContaining({ method: "GET" }));
  });

  it("createParticipant POSTs JSON body", async () => {
    global.fetch = mockFetch(201, { id: "P01", enrollment_date: "2026-06-01" });
    const p = await createParticipant({ id: "P01", enrollment_date: "2026-06-01" });
    expect(p.id).toBe("P01");
    const [, init] = (global.fetch as any).mock.calls[0];
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toMatchObject({ id: "P01" });
  });

  it("ingestCsv sends multipart form and throws IngestError on 409", async () => {
    global.fetch = mockFetch(409, { detail: "cell already filled: P01 visit 1 LOW" });
    const file = new File([new Uint8Array([1, 2, 3])], "run.csv", { type: "text/csv" });
    await expect(
      ingestCsv(file, { participant_id: "P01", visit_ordinal: 1, workload_level: "LOW" })
    ).rejects.toThrow(IngestError);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /root/repos/MATB/webui/frontend && npx vitest run src/lib/api.test.ts`
Expected: FAIL — cannot resolve `@/lib/api`.

- [ ] **Step 3: Create the types**

Create `webui/frontend/src/types/index.ts`:

```typescript
export interface Participant {
  id: string;
  enrollment_date: string;
  sex?: string | null;
  age_band?: string | null;
  notes?: string | null;
}

export interface Visit {
  id: number;
  participant_id: string;
  visit_ordinal: number;
  scheduled_day: number;
  actual_date?: string | null;
  status: string;
}

export interface TrackerCell {
  participant_id: string;
  visit_ordinal: number;
  scheduled_day: number;
  workload_level: "LOW" | "MEDIUM" | "HIGH";
  present: boolean;
}

export interface IngestResult {
  id: number;
  workload_level: string;
  visit_id: number;
}

export interface ParticipantCreate {
  id: string;
  enrollment_date: string;
  sex?: string;
  age_band?: string;
  notes?: string;
}
```

- [ ] **Step 4: Implement the API client**

Create `webui/frontend/src/lib/api.ts`:

```typescript
import type {
  IngestResult, Participant, ParticipantCreate, TrackerCell, Visit,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}
export class IngestError extends ApiError {
  constructor(status: number, message: string) {
    super(status, message);
    this.name = "IngestError";
  }
}

async function detail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return (body && (body.detail || body.message)) || res.statusText;
  } catch {
    return res.statusText;
  }
}

export async function getTracker(): Promise<TrackerCell[]> {
  const res = await fetch(`${API_BASE}/tracker`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function listParticipants(): Promise<Participant[]> {
  const res = await fetch(`${API_BASE}/participants`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function createParticipant(body: ParticipantCreate): Promise<Participant> {
  const res = await fetch(`${API_BASE}/participants`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function listVisits(participantId: string): Promise<Visit[]> {
  const res = await fetch(`${API_BASE}/participants/${participantId}/visits`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export interface IngestTags {
  participant_id: string;
  visit_ordinal: number;
  workload_level: "LOW" | "MEDIUM" | "HIGH";
  overwrite?: boolean;
}

export async function ingestCsv(file: File, tags: IngestTags): Promise<IngestResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("participant_id", tags.participant_id);
  form.append("visit_ordinal", String(tags.visit_ordinal));
  form.append("workload_level", tags.workload_level);
  form.append("overwrite", String(tags.overwrite ?? false));
  const res = await fetch(`${API_BASE}/ingest`, { method: "POST", body: form });
  if (!res.ok) throw new IngestError(res.status, await detail(res));
  return res.json();
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd /root/repos/MATB/webui/frontend && npx vitest run src/lib/api.test.ts`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src/types webui/frontend/src/lib/api.ts webui/frontend/src/lib/api.test.ts
git commit -m "feat(webui): typed API client + domain types"
```

---

### Task 3: Tracker aggregation logic (vitest TDD)

**Files:** Create `src/lib/tracker.ts`, `src/lib/tracker.test.ts`.

- [ ] **Step 1: Write the failing test**

Create `webui/frontend/src/lib/tracker.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { summarize, byParticipant, LEVELS } from "@/lib/tracker";
import type { TrackerCell } from "@/types";

function grid(present: Array<[string, number, string]>, pids = ["P01"]): TrackerCell[] {
  const cells: TrackerCell[] = [];
  for (const pid of pids)
    for (let v = 1; v <= 6; v++)
      for (const lvl of LEVELS)
        cells.push({
          participant_id: pid, visit_ordinal: v, scheduled_day: (v - 1) * 3,
          workload_level: lvl,
          present: present.some(([p, vv, l]) => p === pid && vv === v && l === lvl),
        });
  return cells;
}

describe("tracker aggregation", () => {
  it("summarize counts filled vs total", () => {
    const s = summarize(grid([["P01", 1, "LOW"], ["P01", 1, "MEDIUM"]]));
    expect(s.total).toBe(18);
    expect(s.filled).toBe(2);
  });

  it("byParticipant groups cells and computes per-participant completeness", () => {
    const rows = byParticipant(grid([["P01", 1, "LOW"]], ["P01", "P02"]));
    expect(rows.map((r) => r.participantId)).toEqual(["P01", "P02"]);
    expect(rows[0].filled).toBe(1);
    expect(rows[0].total).toBe(18);
    expect(rows[1].filled).toBe(0);
  });

  it("byParticipant orders visit×level cells deterministically (visit then LOW/MED/HIGH)", () => {
    const rows = byParticipant(grid([["P01", 2, "HIGH"]]));
    const cell = rows[0].cells.find((c) => c.visit_ordinal === 2 && c.workload_level === "HIGH");
    expect(cell?.present).toBe(true);
    // 18 cells, ordered visit 1..6, each LOW,MEDIUM,HIGH
    expect(rows[0].cells.length).toBe(18);
    expect(rows[0].cells[0]).toMatchObject({ visit_ordinal: 1, workload_level: "LOW" });
    expect(rows[0].cells[5]).toMatchObject({ visit_ordinal: 2, workload_level: "HIGH" });
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /root/repos/MATB/webui/frontend && npx vitest run src/lib/tracker.test.ts`
Expected: FAIL — cannot resolve `@/lib/tracker`.

- [ ] **Step 3: Implement**

Create `webui/frontend/src/lib/tracker.ts`:

```typescript
import type { TrackerCell } from "@/types";

export const LEVELS = ["LOW", "MEDIUM", "HIGH"] as const;
export const N_VISITS = 6;

export interface Summary { filled: number; total: number; }

export function summarize(cells: TrackerCell[]): Summary {
  return { filled: cells.filter((c) => c.present).length, total: cells.length };
}

export interface ParticipantRow {
  participantId: string;
  cells: TrackerCell[];   // ordered: visit 1..6, each LOW/MEDIUM/HIGH
  filled: number;
  total: number;
}

const levelRank: Record<string, number> = { LOW: 0, MEDIUM: 1, HIGH: 2 };

export function byParticipant(cells: TrackerCell[]): ParticipantRow[] {
  const groups = new Map<string, TrackerCell[]>();
  for (const c of cells) {
    if (!groups.has(c.participant_id)) groups.set(c.participant_id, []);
    groups.get(c.participant_id)!.push(c);
  }
  const ids = Array.from(groups.keys()).sort();
  return ids.map((participantId) => {
    const sorted = groups.get(participantId)!.slice().sort((a, b) =>
      a.visit_ordinal - b.visit_ordinal || levelRank[a.workload_level] - levelRank[b.workload_level]
    );
    return {
      participantId,
      cells: sorted,
      filled: sorted.filter((c) => c.present).length,
      total: sorted.length,
    };
  });
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /root/repos/MATB/webui/frontend && npx vitest run src/lib/tracker.test.ts`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src/lib/tracker.ts webui/frontend/src/lib/tracker.test.ts
git commit -m "feat(webui): tracker completeness aggregation helpers"
```

---

### Task 4: zustand store

**Files:** Create `src/lib/store.ts`. (Gate: `npx tsc --noEmit`.)

- [ ] **Step 1: Implement the store**

Create `webui/frontend/src/lib/store.ts`:

```typescript
import { create } from "zustand";
import type { Participant, TrackerCell } from "@/types";
import { getTracker, listParticipants } from "@/lib/api";

interface ConsoleState {
  participants: Participant[];
  tracker: TrackerCell[];
  loading: boolean;
  error: string | null;
  refreshParticipants: () => Promise<void>;
  refreshTracker: () => Promise<void>;
  refreshAll: () => Promise<void>;
}

export const useConsole = create<ConsoleState>((set, get) => ({
  participants: [],
  tracker: [],
  loading: false,
  error: null,
  refreshParticipants: async () => {
    set({ loading: true, error: null });
    try { set({ participants: await listParticipants() }); }
    catch (e) { set({ error: (e as Error).message }); }
    finally { set({ loading: false }); }
  },
  refreshTracker: async () => {
    set({ loading: true, error: null });
    try { set({ tracker: await getTracker() }); }
    catch (e) { set({ error: (e as Error).message }); }
    finally { set({ loading: false }); }
  },
  refreshAll: async () => {
    await Promise.all([get().refreshParticipants(), get().refreshTracker()]);
  },
}));
```

- [ ] **Step 2: Typecheck**

Run: `cd /root/repos/MATB/webui/frontend && npx tsc --noEmit && echo OK`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src/lib/store.ts
git commit -m "feat(webui): zustand console store"
```

---

### Task 5: App shell, nav, layout, placeholder pages

Use the **frontend-design** skill for spacing/polish; the code below is the functional baseline. (Gate: `npx tsc --noEmit` + `npm run build`.)

**Files:** Create `src/components/layout/SidebarNav.tsx`, `src/components/layout/AppShell.tsx`, `src/app/layout.tsx`, `src/app/visualization/page.tsx`, `src/app/analysis/page.tsx`.

- [ ] **Step 1: Sidebar nav**

Create `webui/frontend/src/components/layout/SidebarNav.tsx`:

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGrid, Users, Upload, BarChart3, FlaskConical } from "lucide-react";
import { cn } from "@/lib/utils";

const ITEMS = [
  { href: "/", label: "Tracker", icon: LayoutGrid, enabled: true },
  { href: "/participants", label: "Participants", icon: Users, enabled: true },
  { href: "/upload", label: "Upload", icon: Upload, enabled: true },
  { href: "/visualization", label: "Visualization", icon: BarChart3, enabled: false },
  { href: "/analysis", label: "Analysis", icon: FlaskConical, enabled: false },
];

export function SidebarNav() {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-1 p-3">
      {ITEMS.map(({ href, label, icon: Icon, enabled }) => {
        const active = pathname === href;
        const base = "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors";
        if (!enabled)
          return (
            <span key={href} className={cn(base, "cursor-not-allowed text-muted-foreground/50")} title="Coming soon">
              <Icon className="h-4 w-4" /> {label}
              <span className="ml-auto text-[10px] uppercase tracking-wide">soon</span>
            </span>
          );
        return (
          <Link key={href} href={href}
            className={cn(base, active ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-accent hover:text-accent-foreground")}>
            <Icon className="h-4 w-4" /> {label}
          </Link>
        );
      })}
    </nav>
  );
}
```

- [ ] **Step 2: App shell**

Create `webui/frontend/src/components/layout/AppShell.tsx`:

```tsx
import { SidebarNav } from "@/components/layout/SidebarNav";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="w-60 shrink-0 border-r border-border bg-card">
        <div className="px-4 py-5 border-b border-border">
          <h1 className="text-sm font-semibold tracking-tight">MATB Research Console</h1>
          <p className="text-xs text-muted-foreground">Longitudinal study tracker</p>
        </div>
        <SidebarNav />
      </aside>
      <main className="flex-1 overflow-auto">
        <div className="mx-auto max-w-6xl px-6 py-8">{children}</div>
      </main>
    </div>
  );
}
```

- [ ] **Step 3: Root layout (dark theme + shell)**

Create `webui/frontend/src/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/layout/AppShell";

export const metadata: Metadata = {
  title: "MATB Research Console",
  description: "Longitudinal MATB study tracker",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="font-sans antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
```

- [ ] **Step 4: Placeholder pages**

Create `webui/frontend/src/app/visualization/page.tsx`:

```tsx
export default function VisualizationPage() {
  return (
    <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-border">
      <p className="text-muted-foreground">Visualization — Phase 2 (coming soon)</p>
    </div>
  );
}
```

Create `webui/frontend/src/app/analysis/page.tsx`:

```tsx
export default function AnalysisPage() {
  return (
    <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-border">
      <p className="text-muted-foreground">Analysis — Phase 3 (coming soon)</p>
    </div>
  );
}
```

- [ ] **Step 5: Add a temporary home page so the build succeeds**

Create `webui/frontend/src/app/page.tsx` (replaced in Task 6):

```tsx
export default function Home() {
  return <p className="text-muted-foreground">Tracker — loading…</p>;
}
```

- [ ] **Step 6: Typecheck + build**

Run: `cd /root/repos/MATB/webui/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -8`
Expected: typecheck clean; build succeeds (5 routes: /, /participants is missing yet — only built routes that exist; that's fine).

- [ ] **Step 7: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src/app/layout.tsx webui/frontend/src/app/page.tsx webui/frontend/src/app/visualization webui/frontend/src/app/analysis webui/frontend/src/components/layout
git commit -m "feat(webui): app shell, sidebar nav, placeholder routes"
```

---

### Task 6: Tracker page + CompletenessGrid

Use the **frontend-design** skill for the grid aesthetics (cell sizing, color, hover). (Gate: `tsc` + `build`.)

**Files:** Create `src/components/tracker/CompletenessGrid.tsx`; overwrite `src/app/page.tsx`.

- [ ] **Step 1: CompletenessGrid component**

Create `webui/frontend/src/components/tracker/CompletenessGrid.tsx`:

```tsx
"use client";

import { byParticipant, summarize, LEVELS } from "@/lib/tracker";
import type { TrackerCell } from "@/types";
import { cn } from "@/lib/utils";

export function CompletenessGrid({
  cells, onCellClick,
}: { cells: TrackerCell[]; onCellClick?: (c: TrackerCell) => void }) {
  const rows = byParticipant(cells);
  const { filled, total } = summarize(cells);

  if (cells.length === 0)
    return <p className="text-sm text-muted-foreground">No participants enrolled yet.</p>;

  return (
    <div className="space-y-4">
      <div className="text-sm text-muted-foreground">
        <span className="font-semibold text-foreground">{filled}</span> / {total} cells filled
      </div>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="bg-card">
              <th className="sticky left-0 z-10 bg-card px-3 py-2 text-left font-medium">Participant</th>
              {Array.from({ length: 6 }, (_, i) => (
                <th key={i} colSpan={3} className="border-l border-border px-2 py-2 text-center font-medium">
                  Visit {i + 1}
                </th>
              ))}
              <th className="border-l border-border px-3 py-2 text-right font-medium">Done</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.participantId} className="border-t border-border">
                <td className="sticky left-0 z-10 bg-background px-3 py-2 font-mono">{row.participantId}</td>
                {row.cells.map((c) => (
                  <td key={`${c.visit_ordinal}-${c.workload_level}`}
                      className={cn("border-l border-border/50 p-0", c.workload_level === "LOW" && "border-l-border")}>
                    <button
                      type="button"
                      disabled={!c.present}
                      onClick={() => c.present && onCellClick?.(c)}
                      title={`Visit ${c.visit_ordinal} · ${c.workload_level}${c.present ? "" : " (missing)"}`}
                      className={cn(
                        "h-7 w-full transition-colors",
                        c.present ? "bg-success/80 hover:bg-success" : "bg-muted/40",
                      )}
                    >
                      <span className="sr-only">{c.workload_level}</span>
                    </button>
                  </td>
                ))}
                <td className="border-l border-border px-3 py-2 text-right tabular-nums">
                  {row.filled}/{row.total}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1"><span className="h-3 w-3 rounded-sm bg-success/80" /> present</span>
        <span className="inline-flex items-center gap-1"><span className="h-3 w-3 rounded-sm bg-muted/40" /> expected, missing</span>
        <span>columns per visit: {LEVELS.join(" · ")}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Tracker page (client) wiring the store + grid**

Overwrite `webui/frontend/src/app/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useConsole } from "@/lib/store";
import { CompletenessGrid } from "@/components/tracker/CompletenessGrid";
import { CellDetailDialog } from "@/components/tracker/CellDetailDialog";
import type { TrackerCell } from "@/types";

export default function TrackerPage() {
  const { tracker, refreshTracker, error } = useConsole();
  const [selected, setSelected] = useState<TrackerCell | null>(null);

  useEffect(() => { void refreshTracker(); }, [refreshTracker]);

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-xl font-semibold tracking-tight">Study completeness</h2>
        <p className="text-sm text-muted-foreground">12 participants × 6 visits × 3 workload levels.</p>
      </header>
      {error && <p className="text-sm text-danger">Failed to load: {error}</p>}
      <CompletenessGrid cells={tracker} onCellClick={setSelected} />
      <CellDetailDialog cell={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
```

NOTE: `CellDetailDialog` is created in Task 7. To keep this task's build green, create a minimal stub now and replace it in Task 7:

Create `webui/frontend/src/components/tracker/CellDetailDialog.tsx` (stub):

```tsx
"use client";
import type { TrackerCell } from "@/types";
export function CellDetailDialog({ cell, onClose }: { cell: TrackerCell | null; onClose: () => void }) {
  void onClose;
  return cell ? null : null;
}
```

- [ ] **Step 3: Typecheck + build**

Run: `cd /root/repos/MATB/webui/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -8`
Expected: clean typecheck; build succeeds.

- [ ] **Step 4: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src/app/page.tsx webui/frontend/src/components/tracker
git commit -m "feat(webui): tracker page + completeness grid"
```

---

### Task 7: CellDetailDialog (block metrics + DEPDF fit)

The dialog reads the cell's block metrics. The backend `/tracker` cell does NOT include metrics; add a backend read endpoint and fetch on open. Use the **frontend-design** skill for dialog layout.

**Files:** Modify backend `webui/backend/app/routers/tracker.py` (+ test); add `getBlock` to `src/lib/api.ts`; overwrite `src/components/tracker/CellDetailDialog.tsx`.

- [ ] **Step 1 (backend): write the failing test**

Add to `webui/backend/tests/test_endpoints.py`:

```python
def test_block_detail_endpoint(client, sample_csv_bytes):
    _enroll(client)
    files = {"file": ("run1.csv", sample_csv_bytes(misses=(5.0, 25.0)), "text/csv")}
    data = {"participant_id": "P01", "visit_ordinal": "1", "workload_level": "LOW"}
    assert client.post("/ingest", files=files, data=data).status_code == 201
    r = client.get("/block", params={"participant_id": "P01", "visit_ordinal": 1, "workload_level": "LOW"})
    assert r.status_code == 200
    body = r.json()
    assert body["metrics"]["sysmon"]["n_misses"] == 2
    assert body["depdf_fit"] is None  # only LOW ingested, no full-visit fit

def test_block_detail_404_when_absent(client):
    _enroll(client)
    r = client.get("/block", params={"participant_id": "P01", "visit_ordinal": 2, "workload_level": "HIGH"})
    assert r.status_code == 404
```

- [ ] **Step 2 (backend): run to verify it fails**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_endpoints.py -q`
Expected: FAIL (404 route missing / no `/block`).

- [ ] **Step 3 (backend): add the `/block` endpoint**

Append to `webui/backend/app/routers/tracker.py`:

```python
from fastapi import HTTPException, Query, status as http_status  # add to imports at top
import json

from app.models import Block, DepdfFit, Visit  # add to imports at top


@router.get("/block")
def block_detail(
    participant_id: str = Query(...),
    visit_ordinal: int = Query(...),
    workload_level: str = Query(...),
    session: Session = Depends(get_session),
):
    visit = session.exec(
        select(Visit).where(Visit.participant_id == participant_id,
                            Visit.visit_ordinal == visit_ordinal)
    ).first()
    if visit is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "visit not found")
    block = session.exec(
        select(Block).where(Block.visit_id == visit.id,
                            Block.workload_level == workload_level)
    ).first()
    if block is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "block not ingested")
    metrics = json.loads(block.metrics_json)
    metrics.pop("_raw_sysmon_rows", None)  # internal; not for the UI
    fit = session.exec(select(DepdfFit).where(DepdfFit.visit_id == visit.id)).first()
    fit_out = None
    if fit is not None:
        fit_out = {"g0": fit.g0, "p0": fit.p0, "tau0": fit.tau0,
                   "hcf_source": fit.hcf_source, "mwl_source": fit.mwl_source}
    return {"participant_id": participant_id, "visit_ordinal": visit_ordinal,
            "workload_level": workload_level, "metrics": metrics, "depdf_fit": fit_out}
```

The existing `tracker.py` already imports `select`, `Session`, `Depends`, `get_session`, `APIRouter`. Add the new imports (`HTTPException`, `Query`, `status as http_status`, `json`, `Block`, `DepdfFit`, `Visit`) at the top; keep the existing `/tracker` route.

- [ ] **Step 4 (backend): run to verify it passes**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_endpoints.py -q`
Expected: pass (the 2 new tests + existing).

- [ ] **Step 5 (frontend): add `getBlock` + types**

Add to `webui/frontend/src/types/index.ts`:

```typescript
export interface BlockDetail {
  participant_id: string;
  visit_ordinal: number;
  workload_level: string;
  metrics: {
    sysmon?: { d_prime?: number | null; hit_rate?: number | null; n_misses?: number; mean_rt_ms?: number | null };
    comm?: { d_prime?: number | null };
    nasatlx?: { raw_tlx?: number | null };
    bedford?: { value?: number | null };
    isa?: { mean?: number | null };
  };
  depdf_fit: { g0: number; p0: number; tau0: number; hcf_source: string; mwl_source: string } | null;
}
```

Add to `webui/frontend/src/lib/api.ts`:

```typescript
import type { BlockDetail } from "@/types";  // extend the existing import line

export async function getBlock(
  participantId: string, visitOrdinal: number, level: string,
): Promise<BlockDetail> {
  const q = new URLSearchParams({
    participant_id: participantId, visit_ordinal: String(visitOrdinal), workload_level: level,
  });
  const res = await fetch(`${API_BASE}/block?${q}`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}
```

- [ ] **Step 6 (frontend): overwrite the dialog**

Overwrite `webui/frontend/src/components/tracker/CellDetailDialog.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { getBlock } from "@/lib/api";
import type { BlockDetail, TrackerCell } from "@/types";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between border-b border-border/50 py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono tabular-nums">{value ?? "—"}</span>
    </div>
  );
}

export function CellDetailDialog({ cell, onClose }: { cell: TrackerCell | null; onClose: () => void }) {
  const [data, setData] = useState<BlockDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!cell) { setData(null); setErr(null); return; }
    getBlock(cell.participant_id, cell.visit_ordinal, cell.workload_level)
      .then(setData).catch((e) => setErr((e as Error).message));
  }, [cell]);

  const fmt = (n: number | null | undefined, d = 3) =>
    n === null || n === undefined ? "—" : n.toFixed(d);

  return (
    <Dialog open={!!cell} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {cell ? `${cell.participant_id} · Visit ${cell.visit_ordinal} · ${cell.workload_level}` : ""}
          </DialogTitle>
        </DialogHeader>
        {err && <p className="text-sm text-danger">{err}</p>}
        {data && (
          <div className="space-y-3">
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Performance</h4>
              <Row label="SYSMON d′" value={fmt(data.metrics.sysmon?.d_prime)} />
              <Row label="Hit rate" value={fmt(data.metrics.sysmon?.hit_rate)} />
              <Row label="Misses" value={data.metrics.sysmon?.n_misses} />
              <Row label="Mean RT (ms)" value={fmt(data.metrics.sysmon?.mean_rt_ms, 0)} />
              <Row label="COMM d′" value={fmt(data.metrics.comm?.d_prime)} />
            </div>
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Workload</h4>
              <Row label="NASA-TLX (raw)" value={fmt(data.metrics.nasatlx?.raw_tlx, 1)} />
              <Row label="Bedford" value={data.metrics.bedford?.value} />
              <Row label="ISA (mean)" value={fmt(data.metrics.isa?.mean, 2)} />
            </div>
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">DEPDF fit (visit)</h4>
              {data.depdf_fit ? (
                <>
                  <Row label="G₀" value={fmt(data.depdf_fit.g0, 2)} />
                  <Row label="P₀" value={fmt(data.depdf_fit.p0, 4)} />
                  <Row label="τ₀" value={fmt(data.depdf_fit.tau0, 2)} />
                  <Row label="HCF source" value={data.depdf_fit.hcf_source} />
                </>
              ) : (
                <p className="text-sm text-muted-foreground">No fit yet (needs all 3 levels of this visit).</p>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 7: Typecheck + build + backend tests**

Run: `cd /root/repos/MATB/webui/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -6`
Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest -q 2>&1 | tail -2`
Expected: frontend clean; backend all pass.

- [ ] **Step 8: Commit**

```bash
cd /root/repos/MATB
git add webui/backend/app/routers/tracker.py webui/backend/tests/test_endpoints.py webui/frontend/src/types/index.ts webui/frontend/src/lib/api.ts webui/frontend/src/components/tracker/CellDetailDialog.tsx
git commit -m "feat(webui): block-detail endpoint + cell detail dialog"
```

---

### Task 8: Participants page (table + add dialog)

Use the **frontend-design** skill for table/dialog polish. (Gate: `tsc` + `build`.)

**Files:** Create `src/components/participants/AddParticipantDialog.tsx`, `src/components/participants/ParticipantTable.tsx`, `src/app/participants/page.tsx`.

- [ ] **Step 1: Add-participant dialog**

Create `webui/frontend/src/components/participants/AddParticipantDialog.tsx`:

```tsx
"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createParticipant } from "@/lib/api";

export function AddParticipantDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [id, setId] = useState("");
  const [date, setDate] = useState("");
  const [sex, setSex] = useState("");
  const [ageBand, setAgeBand] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true); setErr(null);
    try {
      await createParticipant({ id, enrollment_date: date, sex: sex || undefined, age_band: ageBand || undefined });
      setOpen(false); setId(""); setDate(""); setSex(""); setAgeBand("");
      onCreated();
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button>Add participant</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Add participant</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label htmlFor="pid">ID (e.g. P01)</Label><Input id="pid" value={id} onChange={(e) => setId(e.target.value)} /></div>
          <div><Label htmlFor="pdate">Enrollment date</Label><Input id="pdate" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>
          <div><Label htmlFor="psex">Sex (optional)</Label><Input id="psex" value={sex} onChange={(e) => setSex(e.target.value)} /></div>
          <div><Label htmlFor="page">Age band (optional)</Label><Input id="page" value={ageBand} onChange={(e) => setAgeBand(e.target.value)} /></div>
          {err && <p className="text-sm text-danger">{err}</p>}
          <Button onClick={submit} disabled={busy || !id || !date} className="w-full">
            {busy ? "Saving…" : "Create (generates 6 visits)"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Participant table**

Create `webui/frontend/src/components/participants/ParticipantTable.tsx`:

```tsx
"use client";

import type { Participant, TrackerCell } from "@/types";
import { byParticipant } from "@/lib/tracker";

export function ParticipantTable({ participants, tracker }: { participants: Participant[]; tracker: TrackerCell[] }) {
  const rows = byParticipant(tracker);
  const doneById = new Map(rows.map((r) => [r.participantId, `${r.filled}/${r.total}`]));

  if (participants.length === 0)
    return <p className="text-sm text-muted-foreground">No participants yet. Add one to generate its 6 visits.</p>;

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-card text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr><th className="px-4 py-2">ID</th><th className="px-4 py-2">Enrolled</th><th className="px-4 py-2">Sex</th><th className="px-4 py-2">Age band</th><th className="px-4 py-2 text-right">Cells done</th></tr>
        </thead>
        <tbody>
          {participants.map((p) => (
            <tr key={p.id} className="border-t border-border">
              <td className="px-4 py-2 font-mono">{p.id}</td>
              <td className="px-4 py-2">{p.enrollment_date}</td>
              <td className="px-4 py-2">{p.sex || "—"}</td>
              <td className="px-4 py-2">{p.age_band || "—"}</td>
              <td className="px-4 py-2 text-right tabular-nums">{doneById.get(p.id) ?? "0/18"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: Participants page**

Create `webui/frontend/src/app/participants/page.tsx`:

```tsx
"use client";

import { useEffect } from "react";
import { useConsole } from "@/lib/store";
import { ParticipantTable } from "@/components/participants/ParticipantTable";
import { AddParticipantDialog } from "@/components/participants/AddParticipantDialog";

export default function ParticipantsPage() {
  const { participants, tracker, refreshAll, error } = useConsole();
  useEffect(() => { void refreshAll(); }, [refreshAll]);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Participants</h2>
          <p className="text-sm text-muted-foreground">Pseudonymized IDs only. Creating one generates its 6 visits.</p>
        </div>
        <AddParticipantDialog onCreated={() => void refreshAll()} />
      </header>
      {error && <p className="text-sm text-danger">{error}</p>}
      <ParticipantTable participants={participants} tracker={tracker} />
    </div>
  );
}
```

- [ ] **Step 4: Typecheck + build**

Run: `cd /root/repos/MATB/webui/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -6`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src/app/participants webui/frontend/src/components/participants
git commit -m "feat(webui): participants page (table + add dialog)"
```

---

### Task 9: Upload page (form + guard feedback)

Use the **frontend-design** skill for the drag/drop + feedback states. (Gate: `tsc` + `build`.)

**Files:** Create `src/components/upload/UploadForm.tsx`, `src/app/upload/page.tsx`.

- [ ] **Step 1: Upload form**

Create `webui/frontend/src/components/upload/UploadForm.tsx`:

```tsx
"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { ingestCsv, IngestError } from "@/lib/api";
import type { Participant } from "@/types";

const LEVELS = ["LOW", "MEDIUM", "HIGH"] as const;
type Result = { kind: "ok"; msg: string } | { kind: "err"; msg: string } | null;

export function UploadForm({ participants, onIngested }: { participants: Participant[]; onIngested: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [pid, setPid] = useState("");
  const [ordinal, setOrdinal] = useState(1);
  const [level, setLevel] = useState<(typeof LEVELS)[number]>("LOW");
  const [overwrite, setOverwrite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result>(null);

  async function submit() {
    if (!file || !pid) return;
    setBusy(true); setResult(null);
    try {
      const r = await ingestCsv(file, { participant_id: pid, visit_ordinal: ordinal, workload_level: level, overwrite });
      setResult({ kind: "ok", msg: `Ingested block #${r.id} (${r.workload_level}).` });
      setFile(null);
      onIngested();
    } catch (e) {
      const msg = e instanceof IngestError ? `Rejected (${e.status}): ${e.message}` : (e as Error).message;
      setResult({ kind: "err", msg });
    } finally { setBusy(false); }
  }

  return (
    <div className="max-w-lg space-y-4 rounded-lg border border-border p-5">
      <div>
        <Label htmlFor="csv">Session CSV</Label>
        <Input id="csv" type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </div>
      <div>
        <Label htmlFor="up-pid">Participant</Label>
        <select id="up-pid" value={pid} onChange={(e) => setPid(e.target.value)}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm">
          <option value="">Select…</option>
          {participants.map((p) => <option key={p.id} value={p.id}>{p.id}</option>)}
        </select>
      </div>
      <div className="flex gap-3">
        <div className="flex-1">
          <Label htmlFor="up-visit">Visit</Label>
          <select id="up-visit" value={ordinal} onChange={(e) => setOrdinal(Number(e.target.value))}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm">
            {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>Visit {n}</option>)}
          </select>
        </div>
        <div className="flex-1">
          <Label htmlFor="up-level">Level</Label>
          <select id="up-level" value={level} onChange={(e) => setLevel(e.target.value as (typeof LEVELS)[number])}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm">
            {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Switch id="ow" checked={overwrite} onCheckedChange={setOverwrite} />
        <Label htmlFor="ow">Overwrite if cell already filled</Label>
      </div>
      {result && (
        <p className={result.kind === "ok" ? "text-sm text-success" : "text-sm text-danger"}>{result.msg}</p>
      )}
      <Button onClick={submit} disabled={busy || !file || !pid} className="w-full">
        {busy ? "Uploading…" : "Ingest session"}
      </Button>
    </div>
  );
}
```

- [ ] **Step 2: Upload page**

Create `webui/frontend/src/app/upload/page.tsx`:

```tsx
"use client";

import { useEffect } from "react";
import { useConsole } from "@/lib/store";
import { UploadForm } from "@/components/upload/UploadForm";

export default function UploadPage() {
  const { participants, refreshParticipants, refreshTracker } = useConsole();
  useEffect(() => { void refreshParticipants(); }, [refreshParticipants]);

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-xl font-semibold tracking-tight">Ingest a session</h2>
        <p className="text-sm text-muted-foreground">Upload an OpenMATB CSV and tag it to a participant / visit / level.</p>
      </header>
      <UploadForm participants={participants} onIngested={() => void refreshTracker()} />
    </div>
  );
}
```

- [ ] **Step 3: Typecheck + build**

Run: `cd /root/repos/MATB/webui/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -6`
Expected: clean; build lists routes `/`, `/participants`, `/upload`, `/visualization`, `/analysis`.

- [ ] **Step 4: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src/app/upload webui/frontend/src/components/upload
git commit -m "feat(webui): upload page with ingest guard feedback"
```

---

### Task 10: End-to-end verification + frontend README

**Files:** Create `webui/frontend/README.md`. No production code changes (verification task).

- [ ] **Step 1: Run the full unit + build gate**

```bash
cd /root/repos/MATB/webui/frontend
npx vitest run 2>&1 | tail -5      # lib unit tests
npx tsc --noEmit && echo TYPECHECK_OK
npm run build 2>&1 | tail -8
```
Expected: vitest passes (api + tracker tests); typecheck OK; build succeeds with 5 routes.

- [ ] **Step 2: Live end-to-end smoke (backend + frontend)**

```bash
# Terminal-equivalent: start backend, enroll, ingest, then start frontend and screenshot.
cd /root/repos/MATB/webui/backend
~/.venvs/matb-webui/bin/uvicorn app.main:app --port 8000 &   # background
sleep 2
curl -s -XPOST localhost:8000/participants -H 'Content-Type: application/json' \
  -d '{"id":"P01","enrollment_date":"2026-06-01"}' | head -c 200
# ingest one LOW block from the repo smoke CSV (any CSV with SYSMON rows)
curl -s -XPOST localhost:8000/ingest \
  -F 'file=@/root/repos/MATB/openmatb/sessions/2026-05-03/27_260503_174528.csv' \
  -F participant_id=P01 -F visit_ordinal=1 -F workload_level=LOW | head -c 200
curl -s localhost:8000/tracker | head -c 200
```
Expected: participant created (201 JSON), ingest returns 201 (or a clear 409/422 if that CSV lacks SYSMON — if so, use a CSV that has SYSMON rows), and `/tracker` shows one `present:true` cell. Use the **run** skill or `playwright-cli`/screenshot tooling to load `http://localhost:3100` (after `npm run dev`) and confirm the grid renders with one green cell and the detail dialog opens. Stop the backend when done (`kill %1`).

- [ ] **Step 3: Frontend README**

Create `webui/frontend/README.md`:

```markdown
# MATB Research Console — Frontend (Phase 1B)

Next.js + TypeScript tracker UI for the MATB longitudinal study, styled to match
the HRV "Mission Control" console. Talks to the Phase 1A FastAPI backend.

## Setup
\`\`\`bash
cd webui/frontend
npm install
\`\`\`

## Run (dev — backend must be running on :8000)
\`\`\`bash
# backend:
cd ../backend && ~/.venvs/matb-webui/bin/uvicorn app.main:app --port 8000
# frontend:
cd ../frontend && npm run dev   # http://localhost:3100
\`\`\`
Override the API base with `NEXT_PUBLIC_API_URL`.

## Test
\`\`\`bash
npm test          # vitest unit tests (lib/)
npm run typecheck # tsc --noEmit
npm run build     # production build
\`\`\`

## Screens
- **Tracker** (`/`) — 12×6×3 completeness grid; click a filled cell for metrics + DEPDF fit.
- **Participants** (`/participants`) — list + add (auto-generates 6 visits).
- **Upload** (`/upload`) — tag + ingest an OpenMATB CSV, with guard feedback.
- **Visualization / Analysis** — Phase 2 / Phase 3 placeholders.

Spec: `docs/superpowers/specs/2026-06-03-webui-phase1b-frontend-design.md`
```

(Use REAL triple-backtick fences in the file.)

- [ ] **Step 4: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/README.md
git commit -m "docs(webui): frontend README + Phase 1B verified"
```

---

## Self-review notes (completed by plan author)

- **Spec coverage:** §3 stack + §4 layout → Task 1 (copy/adapt). §5 API client → Task 2. tracker aggregation (§4 lib) → Task 3. §7 state → Task 4. §3/§6 shell + placeholders → Task 5. §6 tracker grid → Task 6; cell detail (needs a backend read endpoint) → Task 7. §6 participants → Task 8. §6 upload → Task 9. §8 testing (vitest + build gate + live smoke) → Tasks 2,3,10. §9 frontend-design polish → flagged in Tasks 5–9 headers.
- **Cross-task addition flagged, not a placeholder:** the spec's CellDetailDialog needs block metrics, which `/tracker` does not carry; Task 7 adds a `/block` backend endpoint (with tests) — a real, specified addition.
- **Type consistency:** `TrackerCell`, `Participant`, `Visit`, `IngestResult`, `BlockDetail` defined in Task 2/7 and consumed unchanged; `ingestCsv(file, IngestTags)`, `getTracker()`, `createParticipant(ParticipantCreate)`, `getBlock(...)` signatures stable across tasks; `byParticipant`/`summarize`/`LEVELS` from Task 3 used in Tasks 6 & 8.
- **Build-green discipline:** Task 6 creates a `CellDetailDialog` stub so the build stays green before Task 7 replaces it; Task 5 adds a temporary `page.tsx` replaced in Task 6.
- **Backend stays green:** Task 7 adds `/block` + tests and re-runs the full backend suite.
