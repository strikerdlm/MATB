# MATB Research Console — Phase 2 (Visualization) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use the **frontend-design** skill for polish on Tasks 5–6.

**Goal:** Descriptive visualization dashboards — metric trajectories, level comparisons, DEPDF curves + parameter trajectories, group overview — over the Phase 1 data, with PNG export, on the `/visualization` route.

**Architecture:** Two new backend read endpoints (`/metrics/long` tidy long-format, `/fits` with server-computed DEPDF curve points via `matb_integration.suhir.depdf`). Frontend: pure reshapers in `src/lib/viz.ts` (vitest TDD), one `EChart` wrapper (dynamic import, PNG toolbox), four tab panels on the visualization page. No inferential statistics (Phase 3).

**Tech Stack:** FastAPI + SQLModel (backend), ECharts via `echarts-for-react` (already in deps), Next.js/TS, vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-06-03-webui-phase2-visualization-design.md`
**Branch:** `feat/webui-phase1` (extends PR #6). Backend tests: `~/.venvs/matb-webui/bin/python -m pytest` from `webui/backend`. Frontend gates from `webui/frontend`.

---

## File structure

| File | Responsibility |
|---|---|
| `webui/backend/app/metrics_long.py` | Pure `extract_long_metrics(record)` + `METRIC_KEYS` registry |
| `webui/backend/app/routers/metrics.py` | `GET /metrics/long` |
| `webui/backend/app/routers/fits.py` | `GET /fits` (joins DepdfFit→Visit; computes curve via suhir.depdf) |
| `webui/backend/tests/test_metrics_long.py`, `tests/test_fits_endpoint.py` | TDD |
| `webui/frontend/src/lib/api.ts` (+`types/index.ts`) | `getMetricsLong`, `getFits`, `MetricRow`, `FitRow` |
| `webui/frontend/src/lib/viz.ts` + `viz.test.ts` | `METRICS` registry, `trajectorySeries`, `groupOverview` |
| `webui/frontend/src/components/charts/EChart.tsx` | dynamic-import wrapper, base option, `LEVEL_COLORS`, PNG toolbox |
| `webui/frontend/src/components/charts/{TrajectoryChart,LevelBarsChart,DepdfPanel,GroupChart}.tsx` | the four chart views |
| `webui/frontend/src/app/visualization/page.tsx` | real page with Tabs + controls |
| `webui/frontend/src/components/layout/SidebarNav.tsx` | enable the Visualization item |

---

### Task 1: Backend — long-format metrics endpoint (TDD)

**Files:** Create `webui/backend/app/metrics_long.py`, `webui/backend/app/routers/metrics.py`, `webui/backend/tests/test_metrics_long.py`; Modify `webui/backend/app/main.py`.

- [ ] **Step 1: Write the failing test**

Create `webui/backend/tests/test_metrics_long.py`:

```python
from __future__ import annotations

from app.metrics_long import METRIC_KEYS, extract_long_metrics


def test_extract_covers_all_metrics_and_omits_nulls():
    record = {
        "sysmon": {"d_prime": 2.5, "hit_rate": 0.9, "mean_rt_ms": None, "n_misses": 1},
        "comm": {"d_prime": 1.1},
        "nasatlx": {"raw_tlx": 55.0},
        "bedford": {"value": 4},
        "isa": {"mean": 2.5},
    }
    pairs = dict(extract_long_metrics(record))
    assert pairs["sysmon_d_prime"] == 2.5
    assert pairs["sysmon_hit_rate"] == 0.9
    assert pairs["comm_d_prime"] == 1.1
    assert pairs["nasatlx_raw_tlx"] == 55.0
    assert pairs["bedford"] == 4.0
    assert pairs["isa_mean"] == 2.5
    assert "sysmon_mean_rt_ms" not in pairs  # null omitted
    assert set(pairs) <= set(METRIC_KEYS)


def test_extract_handles_missing_sections():
    assert extract_long_metrics({}) == []


def _enroll_and_ingest(client, sample_csv_bytes):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    files = {"file": ("a.csv", sample_csv_bytes(misses=(5.0, 25.0), raw_tlx=60.0), "text/csv")}
    data = {"participant_id": "P01", "visit_ordinal": "1", "workload_level": "LOW"}
    assert client.post("/ingest", files=files, data=data).status_code == 201


def test_metrics_long_endpoint(client, sample_csv_bytes):
    _enroll_and_ingest(client, sample_csv_bytes)
    rows = client.get("/metrics/long").json()
    assert rows, "expected long rows"
    r0 = rows[0]
    assert set(r0) == {"participant_id", "visit_ordinal", "workload_level", "metric", "value"}
    tlx = [r for r in rows if r["metric"] == "nasatlx_raw_tlx"]
    assert tlx and tlx[0]["value"] == 60.0
    assert tlx[0]["participant_id"] == "P01" and tlx[0]["visit_ordinal"] == 1
    # filter works
    assert client.get("/metrics/long", params={"participant_id": "P99"}).json() == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_metrics_long.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.metrics_long'`.

- [ ] **Step 3: Implement the extractor**

Create `webui/backend/app/metrics_long.py`:

```python
"""Tidy long-format metric extraction from stored block records.

The long format (participant, visit, level, metric, value) is the shape the
Phase-2 charts and the Phase-3 statistics engine both consume. Only observed
(non-null numeric) values are emitted.
"""

from __future__ import annotations

from typing import Any

# metric key -> (section, field) inside the log_converter record
_PATHS: dict[str, tuple[str, str]] = {
    "sysmon_d_prime": ("sysmon", "d_prime"),
    "sysmon_hit_rate": ("sysmon", "hit_rate"),
    "sysmon_mean_rt_ms": ("sysmon", "mean_rt_ms"),
    "comm_d_prime": ("comm", "d_prime"),
    "nasatlx_raw_tlx": ("nasatlx", "raw_tlx"),
    "bedford": ("bedford", "value"),
    "isa_mean": ("isa", "mean"),
}

METRIC_KEYS: tuple[str, ...] = tuple(_PATHS)


def extract_long_metrics(record: dict[str, Any]) -> list[tuple[str, float]]:
    """(metric, value) pairs for observed metrics; nulls/missing omitted."""
    out: list[tuple[str, float]] = []
    for key, (section, field) in _PATHS.items():
        value = (record.get(section) or {}).get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out.append((key, float(value)))
    return out
```

- [ ] **Step 4: Implement the router and register it**

Create `webui/backend/app/routers/metrics.py`:

```python
"""Tidy long-format metrics endpoint for visualization/statistics."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.db import get_session
from app.metrics_long import extract_long_metrics
from app.models import Block, Visit

router = APIRouter(tags=["metrics"])


@router.get("/metrics/long")
def metrics_long(
    participant_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    query = select(Block, Visit).where(Block.visit_id == Visit.id)
    if participant_id is not None:
        query = query.where(Visit.participant_id == participant_id)
    rows: list[dict[str, Any]] = []
    for block, visit in session.exec(query).all():
        record = json.loads(block.metrics_json)
        for metric, value in extract_long_metrics(record):
            rows.append({
                "participant_id": visit.participant_id,
                "visit_ordinal": visit.visit_ordinal,
                "workload_level": block.workload_level,
                "metric": metric,
                "value": value,
            })
    return rows
```

In `webui/backend/app/main.py`, extend the router block to:

```python
from app.routers import ingest, metrics, participants, tracker  # noqa: E402

app.include_router(participants.router)
app.include_router(ingest.router)
app.include_router(tracker.router)
app.include_router(metrics.router)
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_metrics_long.py -q`
Expected: 3 passed. Then full suite: `~/.venvs/matb-webui/bin/python -m pytest -q` — all pass.

- [ ] **Step 6: Commit**

```bash
cd /root/repos/MATB
git add webui/backend/app/metrics_long.py webui/backend/app/routers/metrics.py webui/backend/app/main.py webui/backend/tests/test_metrics_long.py
git commit -m "feat(webui): tidy long-format metrics endpoint"
```

---

### Task 2: Backend — fits endpoint with server-computed DEPDF curves (TDD)

**Files:** Create `webui/backend/app/routers/fits.py`, `webui/backend/tests/test_fits_endpoint.py`; Modify `webui/backend/app/main.py`.

- [ ] **Step 1: Write the failing test**

Create `webui/backend/tests/test_fits_endpoint.py`:

```python
from __future__ import annotations

from datetime import date

from sqlmodel import Session

from app.models import DepdfFit, Participant, Visit


def _seed_fit(engine) -> None:
    with Session(engine) as s:
        s.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        v = Visit(participant_id="P01", visit_ordinal=2, scheduled_day=3)
        s.add(v)
        s.commit()
        s.refresh(v)
        s.add(DepdfFit(participant_id="P01", visit_id=v.id, mwl_source="raw_tlx",
                       g0=40.0, p0=0.99, tau0=12.0,
                       hcf_value=1.0, hcf_source="F0_default",
                       criteria_version=1, per_level_json="{}"))
        s.commit()


def test_fits_endpoint_returns_curve(client, engine):
    _seed_fit(engine)
    fits = client.get("/fits").json()
    assert len(fits) == 1
    f = fits[0]
    assert f["participant_id"] == "P01" and f["visit_ordinal"] == 2
    assert f["g0"] == 40.0 and f["p0"] == 0.99
    curve = f["curve"]
    assert len(curve) == 51
    assert curve[0]["r"] == 1.0
    assert abs(curve[0]["p"] - 0.99) < 1e-9        # P^h(G0) == p0
    ps = [pt["p"] for pt in curve]
    assert all(a > b for a, b in zip(ps, ps[1:]))   # strictly decreasing
    assert curve[-1]["r"] == 3.0


def test_fits_filter_by_participant(client, engine):
    _seed_fit(engine)
    assert client.get("/fits", params={"participant_id": "P01"}).json()
    assert client.get("/fits", params={"participant_id": "P99"}).json() == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_fits_endpoint.py -q`
Expected: FAIL (404 — no `/fits` route).

- [ ] **Step 3: Implement the router and register it**

Create `webui/backend/app/routers/fits.py`:

```python
"""DEPDF fits endpoint. Curve points are computed server-side via the suhir
package so the model math stays single-sourced (no Eq-5.16 duplication in TS)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.db import get_session
from app.models import DepdfFit, Visit

router = APIRouter(tags=["fits"])

N_CURVE_POINTS = 51
R_MAX = 3.0  # Suhir: effects saturate beyond G/G0 ~ 3


def _curve(p0: float) -> list[dict[str, float]]:
    from matb_integration.suhir.depdf import p_nonfailure_ordinary

    points: list[dict[str, float]] = []
    for i in range(N_CURVE_POINTS):
        r = 1.0 + (R_MAX - 1.0) * i / (N_CURVE_POINTS - 1)
        points.append({"r": round(r, 4), "p": p_nonfailure_ordinary(p0, g=r, g0=1.0)})
    return points


@router.get("/fits")
def list_fits(
    participant_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    query = select(DepdfFit, Visit).where(DepdfFit.visit_id == Visit.id)
    if participant_id is not None:
        query = query.where(DepdfFit.participant_id == participant_id)
    out: list[dict[str, Any]] = []
    for fit, visit in session.exec(query).all():
        out.append({
            "participant_id": fit.participant_id,
            "visit_ordinal": visit.visit_ordinal,
            "g0": fit.g0, "p0": fit.p0, "tau0": fit.tau0,
            "hcf_source": fit.hcf_source, "mwl_source": fit.mwl_source,
            "curve": _curve(fit.p0),
        })
    out.sort(key=lambda f: (f["participant_id"], f["visit_ordinal"]))
    return out
```

In `webui/backend/app/main.py`, extend the router block to include `fits`:

```python
from app.routers import fits, ingest, metrics, participants, tracker  # noqa: E402

app.include_router(participants.router)
app.include_router(ingest.router)
app.include_router(tracker.router)
app.include_router(metrics.router)
app.include_router(fits.router)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest tests/test_fits_endpoint.py -q`
Expected: 2 passed. Full suite: all pass.

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add webui/backend/app/routers/fits.py webui/backend/app/main.py webui/backend/tests/test_fits_endpoint.py
git commit -m "feat(webui): fits endpoint with server-computed DEPDF curves"
```

---

### Task 3: Frontend — API client additions (vitest TDD)

**Files:** Modify `webui/frontend/src/types/index.ts`, `webui/frontend/src/lib/api.ts`, `webui/frontend/src/lib/api.test.ts`.

- [ ] **Step 1: Write the failing tests** — append to `webui/frontend/src/lib/api.test.ts` (inside the existing `describe`, after the last `it`; also extend the import from `@/lib/api` to include `getMetricsLong, getFits`):

```typescript
  it("getMetricsLong hits /metrics/long with optional participant filter", async () => {
    global.fetch = mockFetch(200, []);
    await getMetricsLong();
    expect((global.fetch as any).mock.calls[0][0]).toContain("/metrics/long");
    global.fetch = mockFetch(200, []);
    await getMetricsLong("P02");
    expect((global.fetch as any).mock.calls[0][0]).toContain("participant_id=P02");
  });

  it("getFits hits /fits", async () => {
    global.fetch = mockFetch(200, []);
    await getFits("P01");
    const url = (global.fetch as any).mock.calls[0][0] as string;
    expect(url).toContain("/fits");
    expect(url).toContain("participant_id=P01");
  });
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /root/repos/MATB/webui/frontend && npx vitest run src/lib/api.test.ts` — FAIL (no export `getMetricsLong`).

- [ ] **Step 3: Add types** — append to `webui/frontend/src/types/index.ts`:

```typescript
export interface MetricRow {
  participant_id: string;
  visit_ordinal: number;
  workload_level: "LOW" | "MEDIUM" | "HIGH";
  metric: string;
  value: number;
}

export interface CurvePoint { r: number; p: number; }

export interface FitRow {
  participant_id: string;
  visit_ordinal: number;
  g0: number;
  p0: number;
  tau0: number;
  hcf_source: string;
  mwl_source: string;
  curve: CurvePoint[];
}
```

- [ ] **Step 4: Add client functions** — in `webui/frontend/src/lib/api.ts`, extend the type import to include `FitRow, MetricRow` and append:

```typescript
export async function getMetricsLong(participantId?: string): Promise<MetricRow[]> {
  const q = participantId ? `?${new URLSearchParams({ participant_id: participantId })}` : "";
  const res = await fetch(`${API_BASE}/metrics/long${q}`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getFits(participantId?: string): Promise<FitRow[]> {
  const q = participantId ? `?${new URLSearchParams({ participant_id: participantId })}` : "";
  const res = await fetch(`${API_BASE}/fits${q}`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}
```

- [ ] **Step 5: Run to verify it passes** — `npx vitest run src/lib/api.test.ts` (6 tests) then `npx tsc --noEmit`.

- [ ] **Step 6: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src/types/index.ts webui/frontend/src/lib/api.ts webui/frontend/src/lib/api.test.ts
git commit -m "feat(webui): metrics-long + fits API client"
```

---

### Task 4: Frontend — viz reshapers (vitest TDD)

**Files:** Create `webui/frontend/src/lib/viz.ts`, `webui/frontend/src/lib/viz.test.ts`.

- [ ] **Step 1: Write the failing test**

Create `webui/frontend/src/lib/viz.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { METRICS, trajectorySeries, groupOverview } from "@/lib/viz";
import type { MetricRow } from "@/types";

const row = (p: string, v: number, l: MetricRow["workload_level"], value: number): MetricRow => ({
  participant_id: p, visit_ordinal: v, workload_level: l, metric: "nasatlx_raw_tlx", value,
});

describe("viz reshapers", () => {
  it("METRICS registry covers the seven backend metrics", () => {
    expect(Object.keys(METRICS)).toEqual([
      "sysmon_d_prime", "sysmon_hit_rate", "sysmon_mean_rt_ms",
      "comm_d_prime", "nasatlx_raw_tlx", "bedford", "isa_mean",
    ]);
    expect(METRICS.nasatlx_raw_tlx.label).toBeTruthy();
  });

  it("trajectorySeries fills 6 visits per level with null gaps", () => {
    const rows = [row("P01", 1, "LOW", 40), row("P01", 3, "LOW", 44), row("P01", 1, "HIGH", 80)];
    const t = trajectorySeries(rows, "P01", "nasatlx_raw_tlx");
    expect(t.visits).toEqual([1, 2, 3, 4, 5, 6]);
    expect(t.series.LOW).toEqual([40, null, 44, null, null, null]);
    expect(t.series.HIGH).toEqual([80, null, null, null, null, null]);
    expect(t.series.MEDIUM).toEqual([null, null, null, null, null, null]);
  });

  it("trajectorySeries ignores other participants and metrics", () => {
    const rows = [row("P02", 1, "LOW", 99), { ...row("P01", 1, "LOW", 40), metric: "bedford" }];
    const t = trajectorySeries(rows, "P01", "nasatlx_raw_tlx");
    expect(t.series.LOW).toEqual([null, null, null, null, null, null]);
  });

  it("groupOverview computes mean/sd/n across participants", () => {
    const rows = [row("P01", 1, "LOW", 40), row("P02", 1, "LOW", 60), row("P03", 1, "LOW", 50)];
    const g = groupOverview(rows, "nasatlx_raw_tlx");
    expect(g.stats.LOW.n[0]).toBe(3);
    expect(g.stats.LOW.mean[0]).toBeCloseTo(50, 6);
    expect(g.stats.LOW.sd[0]).toBeCloseTo(10, 6);        // sample SD of 40/50/60
    expect(g.stats.LOW.mean[1]).toBeNull();              // visit 2: no data
    expect(g.stats.MEDIUM.n.every((n) => n === 0)).toBe(true);
  });

  it("groupOverview sd is null when n < 2", () => {
    const g = groupOverview([row("P01", 2, "HIGH", 80)], "nasatlx_raw_tlx");
    expect(g.stats.HIGH.mean[1]).toBe(80);
    expect(g.stats.HIGH.sd[1]).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify it fails** — `npx vitest run src/lib/viz.test.ts` — FAIL (cannot resolve `@/lib/viz`).

- [ ] **Step 3: Implement**

Create `webui/frontend/src/lib/viz.ts`:

```typescript
import type { MetricRow } from "@/types";
import { LEVELS } from "@/lib/tracker";

export const VISITS = [1, 2, 3, 4, 5, 6] as const;

export const METRICS: Record<string, { label: string; decimals: number; unit?: string }> = {
  sysmon_d_prime: { label: "SYSMON d′", decimals: 3 },
  sysmon_hit_rate: { label: "SYSMON hit rate", decimals: 3 },
  sysmon_mean_rt_ms: { label: "SYSMON mean RT", decimals: 0, unit: "ms" },
  comm_d_prime: { label: "COMM d′", decimals: 3 },
  nasatlx_raw_tlx: { label: "NASA-TLX (raw)", decimals: 1 },
  bedford: { label: "Bedford", decimals: 0 },
  isa_mean: { label: "ISA (mean)", decimals: 2 },
};

export interface Trajectory {
  visits: number[];
  series: Record<string, (number | null)[]>;   // keyed by workload level
}

export function trajectorySeries(rows: MetricRow[], participantId: string, metric: string): Trajectory {
  const visits = [...VISITS];
  const series: Record<string, (number | null)[]> = {};
  for (const level of LEVELS) {
    series[level] = visits.map((v) => {
      const hit = rows.find(
        (r) => r.participant_id === participantId && r.metric === metric &&
               r.workload_level === level && r.visit_ordinal === v,
      );
      return hit ? hit.value : null;
    });
  }
  return { visits, series };
}

export interface GroupStats {
  visits: number[];
  stats: Record<string, { mean: (number | null)[]; sd: (number | null)[]; n: number[] }>;
}

export function groupOverview(rows: MetricRow[], metric: string): GroupStats {
  const visits = [...VISITS];
  const stats: GroupStats["stats"] = {};
  for (const level of LEVELS) {
    const mean: (number | null)[] = [];
    const sd: (number | null)[] = [];
    const n: number[] = [];
    for (const v of visits) {
      const values = rows
        .filter((r) => r.metric === metric && r.workload_level === level && r.visit_ordinal === v)
        .map((r) => r.value);
      n.push(values.length);
      if (values.length === 0) { mean.push(null); sd.push(null); continue; }
      const m = values.reduce((a, b) => a + b, 0) / values.length;
      mean.push(m);
      if (values.length < 2) { sd.push(null); continue; }
      const variance = values.reduce((a, b) => a + (b - m) ** 2, 0) / (values.length - 1);
      sd.push(Math.sqrt(variance));
    }
    stats[level] = { mean, sd, n };
  }
  return { visits, stats };
}
```

- [ ] **Step 4: Run to verify it passes** — `npx vitest run` (all files) + `npx tsc --noEmit`.

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src/lib/viz.ts webui/frontend/src/lib/viz.test.ts
git commit -m "feat(webui): viz reshapers (trajectory, group mean/sd) + metric registry"
```

---

### Task 5: Frontend — EChart wrapper (gate: tsc + build)

**Files:** Create `webui/frontend/src/components/charts/EChart.tsx`.

- [ ] **Step 1: Implement the wrapper**

Create `webui/frontend/src/components/charts/EChart.tsx`:

```tsx
"use client";

import dynamic from "next/dynamic";

// echarts-for-react touches `window`; load client-side only.
const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

// Canvas charts cannot consume CSS variables; these literals track the theme's
// info / warning / danger hues for LOW / MEDIUM / HIGH.
export const LEVEL_COLORS: Record<string, string> = {
  LOW: "#38bdf8",
  MEDIUM: "#f59e0b",
  HIGH: "#ef4444",
};

export const AXIS_STYLE = {
  axisLine: { lineStyle: { color: "#475569" } },
  axisLabel: { color: "#94a3b8" },
  splitLine: { lineStyle: { color: "#1e293b" } },
} as const;

const BASE_OPTION = {
  backgroundColor: "transparent",
  textStyle: { fontFamily: "Inter, system-ui, sans-serif" },
  toolbox: {
    feature: { saveAsImage: { pixelRatio: 2, name: "matb-chart", title: "PNG" } },
    iconStyle: { borderColor: "#94a3b8" },
    right: 8,
  },
  tooltip: { trigger: "axis" },
  legend: { textStyle: { color: "#94a3b8" } },
  grid: { left: 48, right: 24, top: 40, bottom: 32, containLabel: true },
};

export function EChart({ option, height = 360 }: { option: Record<string, unknown>; height?: number }) {
  return (
    <ReactECharts
      option={{ ...BASE_OPTION, ...option }}
      style={{ height, width: "100%" }}
      notMerge
      lazyUpdate
    />
  );
}
```

- [ ] **Step 2: Gate** — `cd /root/repos/MATB/webui/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -4` (the wrapper is unused yet; build must stay green).

- [ ] **Step 3: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src/components/charts/EChart.tsx
git commit -m "feat(webui): EChart wrapper (dynamic import, PNG toolbox, level colors)"
```

---

### Task 6: Frontend — visualization page with four tabs (gate: tsc + build)

Use the **frontend-design** skill for layout polish. The code below is the functional baseline.

**Files:** Create `webui/frontend/src/components/charts/TrajectoryChart.tsx`, `LevelBarsChart.tsx`, `DepdfPanel.tsx`, `GroupChart.tsx`; Overwrite `webui/frontend/src/app/visualization/page.tsx`; Modify `webui/frontend/src/components/layout/SidebarNav.tsx` (enable Visualization).

- [ ] **Step 1: TrajectoryChart**

Create `webui/frontend/src/components/charts/TrajectoryChart.tsx`:

```tsx
"use client";

import { EChart, LEVEL_COLORS, AXIS_STYLE } from "@/components/charts/EChart";
import { METRICS, type Trajectory } from "@/lib/viz";
import { LEVELS } from "@/lib/tracker";

export function TrajectoryChart({ data, metric, kind = "line" }: {
  data: Trajectory; metric: string; kind?: "line" | "bar";
}) {
  const meta = METRICS[metric];
  const option = {
    xAxis: { type: "category", data: data.visits.map((v) => `Visit ${v}`), ...AXIS_STYLE },
    yAxis: { type: "value", name: meta?.unit ?? "", ...AXIS_STYLE },
    series: LEVELS.map((level) => ({
      name: level,
      type: kind,
      data: data.series[level],
      connectNulls: false,
      color: LEVEL_COLORS[level],
      symbolSize: 7,
    })),
  };
  return <EChart option={option} />;
}
```

- [ ] **Step 2: LevelBarsChart** (thin alias over the same data, bar form)

Create `webui/frontend/src/components/charts/LevelBarsChart.tsx`:

```tsx
"use client";

import { TrajectoryChart } from "@/components/charts/TrajectoryChart";
import type { Trajectory } from "@/lib/viz";

export function LevelBarsChart({ data, metric }: { data: Trajectory; metric: string }) {
  return <TrajectoryChart data={data} metric={metric} kind="bar" />;
}
```

- [ ] **Step 3: DepdfPanel** (curves + parameter small multiples)

Create `webui/frontend/src/components/charts/DepdfPanel.tsx`:

```tsx
"use client";

import { EChart, AXIS_STYLE } from "@/components/charts/EChart";
import type { FitRow } from "@/types";

const VISIT_COLORS = ["#38bdf8", "#34d399", "#f59e0b", "#f472b6", "#a78bfa", "#ef4444"];

function ParamChart({ fits, param, label }: { fits: FitRow[]; param: "g0" | "p0" | "tau0"; label: string }) {
  const option = {
    title: { text: label, textStyle: { color: "#94a3b8", fontSize: 12 } },
    xAxis: { type: "category", data: fits.map((f) => `V${f.visit_ordinal}`), ...AXIS_STYLE },
    yAxis: { type: "value", scale: true, ...AXIS_STYLE },
    series: [{ type: "line", data: fits.map((f) => f[param]), color: "#38bdf8", symbolSize: 7 }],
    legend: { show: false },
  };
  return <EChart option={option} height={200} />;
}

export function DepdfPanel({ fits }: { fits: FitRow[] }) {
  if (fits.length === 0)
    return <p className="text-sm text-muted-foreground">No fits yet — a fit needs all 3 levels of a visit ingested.</p>;
  const sorted = [...fits].sort((a, b) => a.visit_ordinal - b.visit_ordinal);
  const curveOption = {
    xAxis: { type: "value", name: "G / G₀", min: 1, max: 3, ...AXIS_STYLE },
    yAxis: { type: "value", name: "P˾structure", min: 0, max: 1, ...AXIS_STYLE },
    tooltip: { trigger: "axis" },
    series: sorted.map((f, i) => ({
      name: `Visit ${f.visit_ordinal}`,
      type: "line",
      showSymbol: false,
      data: f.curve.map((pt) => [pt.r, pt.p]),
      color: VISIT_COLORS[(f.visit_ordinal - 1) % VISIT_COLORS.length],
    })),
  };
  return (
    <div className="space-y-6">
      <div>
        <h3 className="mb-2 text-sm font-medium">Human-nonfailure curve P^h(G/G₀) per fitted visit</h3>
        <EChart option={curveOption} height={380} />
      </div>
      <div>
        <h3 className="mb-2 text-sm font-medium">Fitted parameters across visits</h3>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <ParamChart fits={sorted} param="g0" label="G₀ (baseline MWL)" />
          <ParamChart fits={sorted} param="p0" label="P₀ (baseline nonfailure)" />
          <ParamChart fits={sorted} param="tau0" label="τ₀ (baseline MTTF)" />
        </div>
      </div>
    </div>
  );
}
```

NOTE: the y-axis name string `"P˾structure"` above is WRONG — it must be the plain label `P^h`. Use `name: "P^h"`. (Implementer: use `P^h`, not the escaped string.)

- [ ] **Step 4: GroupChart** (mean line ± SD band via stacked transparent areas)

Create `webui/frontend/src/components/charts/GroupChart.tsx`:

```tsx
"use client";

import { EChart, LEVEL_COLORS, AXIS_STYLE } from "@/components/charts/EChart";
import { METRICS, type GroupStats } from "@/lib/viz";
import { LEVELS } from "@/lib/tracker";

export function GroupChart({ data, metric }: { data: GroupStats; metric: string }) {
  const meta = METRICS[metric];
  const series: Record<string, unknown>[] = [];
  for (const level of LEVELS) {
    const { mean, sd } = data.stats[level];
    const lower = mean.map((m, i) => (m !== null && sd[i] !== null ? m - (sd[i] as number) : null));
    const band = mean.map((m, i) => (m !== null && sd[i] !== null ? 2 * (sd[i] as number) : null));
    // invisible base + band (stacked) render the ±SD envelope
    series.push({
      name: `${level} −SD`, type: "line", stack: `band-${level}`, data: lower,
      lineStyle: { opacity: 0 }, symbol: "none", tooltip: { show: false }, legendHoverLink: false,
    });
    series.push({
      name: `${level} ±SD`, type: "line", stack: `band-${level}`, data: band,
      lineStyle: { opacity: 0 }, symbol: "none",
      areaStyle: { color: LEVEL_COLORS[level], opacity: 0.12 },
      tooltip: { show: false }, legendHoverLink: false,
    });
    series.push({
      name: level, type: "line", data: mean, color: LEVEL_COLORS[level],
      connectNulls: false, symbolSize: 7,
    });
  }
  const option = {
    xAxis: { type: "category", data: data.visits.map((v) => `Visit ${v}`), ...AXIS_STYLE },
    yAxis: { type: "value", name: meta?.unit ?? "", scale: true, ...AXIS_STYLE },
    legend: { data: [...LEVELS], textStyle: { color: "#94a3b8" } },
    series,
  };
  return <EChart option={option} height={400} />;
}
```

- [ ] **Step 5: The visualization page**

Overwrite `webui/frontend/src/app/visualization/page.tsx`:

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getFits, getMetricsLong, listParticipants } from "@/lib/api";
import { METRICS, groupOverview, trajectorySeries } from "@/lib/viz";
import { TrajectoryChart } from "@/components/charts/TrajectoryChart";
import { LevelBarsChart } from "@/components/charts/LevelBarsChart";
import { DepdfPanel } from "@/components/charts/DepdfPanel";
import { GroupChart } from "@/components/charts/GroupChart";
import type { FitRow, MetricRow, Participant } from "@/types";

const SELECT_CLS = "flex h-10 rounded-md border border-input bg-background px-3 text-sm";

export default function VisualizationPage() {
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [rows, setRows] = useState<MetricRow[]>([]);
  const [fits, setFits] = useState<FitRow[]>([]);
  const [pid, setPid] = useState("");
  const [metric, setMetric] = useState("sysmon_d_prime");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listParticipants(), getMetricsLong(), getFits()])
      .then(([ps, ms, fs]) => {
        setParticipants(ps);
        setRows(ms);
        setFits(fs);
        if (ps.length && !pid) setPid(ps[0].id);
      })
      .catch((e) => setError((e as Error).message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const trajectory = useMemo(() => trajectorySeries(rows, pid, metric), [rows, pid, metric]);
  const group = useMemo(() => groupOverview(rows, metric), [rows, metric]);
  const participantFits = useMemo(() => fits.filter((f) => f.participant_id === pid), [fits, pid]);
  const hasData = rows.length > 0;

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-xl font-semibold tracking-tight">Visualization</h2>
        <p className="text-sm text-muted-foreground">Descriptive views. Inferential statistics arrive with the Analysis module (Phase 3).</p>
      </header>
      {error && <p className="text-sm text-danger">{error}</p>}

      <div className="flex flex-wrap gap-3">
        <label className="flex items-center gap-2 text-sm">
          Participant
          <select className={SELECT_CLS} value={pid} onChange={(e) => setPid(e.target.value)}>
            {participants.map((p) => <option key={p.id} value={p.id}>{p.id}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          Metric
          <select className={SELECT_CLS} value={metric} onChange={(e) => setMetric(e.target.value)}>
            {Object.entries(METRICS).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}
          </select>
        </label>
      </div>

      {!hasData ? (
        <p className="text-sm text-muted-foreground">No data yet — ingest sessions first.</p>
      ) : (
        <Tabs defaultValue="trajectories">
          <TabsList>
            <TabsTrigger value="trajectories">Trajectories</TabsTrigger>
            <TabsTrigger value="levels">Levels</TabsTrigger>
            <TabsTrigger value="depdf">DEPDF</TabsTrigger>
            <TabsTrigger value="group">Group</TabsTrigger>
          </TabsList>
          <TabsContent value="trajectories" className="pt-4">
            <TrajectoryChart data={trajectory} metric={metric} />
          </TabsContent>
          <TabsContent value="levels" className="pt-4">
            <LevelBarsChart data={trajectory} metric={metric} />
          </TabsContent>
          <TabsContent value="depdf" className="pt-4">
            <DepdfPanel fits={participantFits} />
          </TabsContent>
          <TabsContent value="group" className="pt-4">
            <GroupChart data={group} metric={metric} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Enable the nav item** — in `webui/frontend/src/components/layout/SidebarNav.tsx`, change the Visualization entry to `enabled: true` (leave Analysis disabled).

- [ ] **Step 7: Gate** — `cd /root/repos/MATB/webui/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -8`. Expected: clean; `/visualization` builds.

- [ ] **Step 8: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src/components/charts webui/frontend/src/app/visualization/page.tsx webui/frontend/src/components/layout/SidebarNav.tsx
git commit -m "feat(webui): visualization page — trajectories, levels, DEPDF, group tabs"
```

---

### Task 7: Live e2e verification + docs

**Files:** Modify `webui/frontend/README.md`, `webui/backend/README.md` (endpoint lists); verification has no production code.

- [ ] **Step 1: Full gates**

```bash
cd /root/repos/MATB/webui/frontend && npx vitest run && npx tsc --noEmit && npm run build 2>&1 | tail -4
cd /root/repos/MATB/webui/backend && ~/.venvs/matb-webui/bin/python -m pytest -q | tail -1
```
Expected: all green.

- [ ] **Step 2: Seed + live check**

Start the backend fresh (`rm -f webui/backend/matb_webui.db`, uvicorn :8000) and seed via curl: enroll P01 and P02; ingest synthetic CSVs (SYSMON misses + a `Mental demand` TLX row, format per `webui/backend/tests/conftest.py`) so that: P01 visit 1 has ALL THREE levels (→ a real DEPDF fit; vary raw_tlx 44/60/80 and miss spacing per level), and P01 visits 2–3 plus P02 visit 1 have partial data. Confirm `curl localhost:8000/fits` returns one fit with a 51-point curve. Start `next dev` (:3100), open `/visualization` with Playwright, and verify each tab renders: Trajectories (lines with gaps), Levels (bars), DEPDF (curve + 3 param charts), Group (mean lines + bands). Screenshot each tab. Stop servers; delete the seeded DB.

- [ ] **Step 3: Update READMEs**

In `webui/backend/README.md`, extend the Endpoints list with:

```markdown
- `GET  /metrics/long` — tidy long-format metric rows (optional `participant_id`)
- `GET  /fits` — DEPDF fits incl. server-computed P^h(G/G₀) curves
- `GET  /block` — one block's metrics + the visit's fit
```

In `webui/frontend/README.md`, change the Screens bullet for Visualization to:

```markdown
- **Visualization** (`/visualization`) — Trajectories / Levels / DEPDF / Group tabs
  with PNG export on every chart (descriptive only; inferential stats are Phase 3).
- **Analysis** — Phase 3 placeholder.
```

- [ ] **Step 4: Commit**

```bash
cd /root/repos/MATB
git add webui/backend/README.md webui/frontend/README.md
git commit -m "docs(webui): Phase 2 visualization verified + endpoint docs"
```

---

## Self-review notes (completed by plan author)

- **Spec coverage:** §3.1 → Task 1; §3.2 → Task 2; §4.1 → Tasks 3–4; §4.2 → Task 5; §4.3 (page, tabs, nav enable, empty states) → Task 6; §6 verification → Tasks 1–4 tests + Task 7 live e2e. §5 boundaries respected (no inferential stats anywhere).
- **Type consistency:** `MetricRow`/`FitRow` (Task 3) consumed by `viz.ts` (Task 4) and the chart components (Task 6); `Trajectory`/`GroupStats` defined in Task 4 and imported in Task 6; `LEVEL_COLORS`/`AXIS_STYLE` from Task 5 used in Task 6; `LEVELS` reused from the existing `lib/tracker`.
- **Inline correction (not a placeholder):** Task 6 Step 3 flags that the y-axis label must be `P^h` (the example string contains an encoding artifact); the implementer instruction is explicit.
- **Backend math single-sourcing:** `/fits` curve calls `suhir.depdf.p_nonfailure_ordinary`; the only numeric literals in TS are display colors/axes.
