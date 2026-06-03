# Phase 3A — Frequentist Statistics Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pre-specified frequentist statistics engine (Q1–Q4: LMM, rmcorr, rmANOVA sensitivity, BH-FDR/Holm multiplicity, data gates, effect sizes, provenance) as a standalone library + CLI, wrapped by backend endpoints and an `/analysis` page.

**Architecture:** Paper-first. `matb_integration/analysis/stats/` is a pure library over tidy long-format rows (the exact `/metrics/long` and `/fits` shapes); a CLI writes versioned JSON artifacts; the webui backend persists artifacts in an `analysis_result` table keyed by input fingerprint; the frontend renders the artifact. Spec: `docs/superpowers/specs/2026-06-03-webui-phase3-statistics-design.md`.

**Tech Stack:** pandas + statsmodels + scipy (already verified importable in `~/.venvs/matb-webui` (pandas 3.0.3, statsmodels 0.14.6, py3.14) and system python (pandas 2.3.3)); FastAPI + SQLModel; Next.js + TS + vitest.

**Conventions for every task:**
- Run library tests from the **repo root**: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats -q`
- Run backend tests from `webui/backend`: `~/.venvs/matb-webui/bin/python -m pytest -q`
- Run frontend tests from `webui/frontend`: `npm test -- --run` and `npm run typecheck`
- Commits: conventional style, **no AI co-author lines, ever** (Diego is sole author).
- All new library files are plain Python ≥3.12, `from __future__ import annotations`, stdlib + pandas/statsmodels/scipy/numpy only. No FastAPI imports anywhere under `matb_integration/`.

**File map (final state):**

```
matb_integration/analysis/stats/
  __init__.py        # public API re-exports
  data.py            # frames, constants, fingerprint
  gates.py           # pre-registered data gates
  multiplicity.py    # BH-FDR + Holm wrappers
  lmm.py             # Q1/Q2/Q4 MixedLM + omnibus + contrasts + std effects
  rmcorr.py          # canonical rmcorr + level-adjusted sensitivity
  rmanova.py         # AnovaRM complete-case sensitivity
  engine.py          # run_analysis() -> artifact dict
  cli.py             # python3 -m matb_integration.analysis.stats.cli
tests/analysis_stats/
  __init__.py
  conftest.py        # simulated-study fixture
  test_data.py  test_gates.py  test_multiplicity.py
  test_lmm.py   test_rmcorr.py test_rmanova.py
  test_engine.py test_cli.py
webui/backend/app/models.py            # + AnalysisResult
webui/backend/app/routers/metrics.py   # + collect_metric_rows()
webui/backend/app/routers/fits.py      # + collect_fit_rows()
webui/backend/app/routers/analysis.py  # POST /analysis/run, GET /analysis/latest
webui/backend/app/main.py              # include analysis router
webui/backend/requirements.txt         # + pandas, statsmodels
webui/backend/tests/test_analysis_endpoint.py
webui/frontend/src/types/index.ts      # + artifact types
webui/frontend/src/lib/api.ts          # + runAnalysis, getLatestAnalysis
webui/frontend/src/lib/format.ts       # p-value/number formatting (unit-tested)
webui/frontend/src/components/analysis/{StatBadge,FamilyTable,LmmCard,RmcorrTable}.tsx
webui/frontend/src/app/analysis/page.tsx
webui/frontend/src/lib/format.test.ts
webui/frontend/src/lib/api.test.ts     # + 2 tests
```

---

### Task 1: Package skeleton, constants, frames, fingerprint (`data.py`)

**Files:**
- Create: `matb_integration/analysis/stats/__init__.py`
- Create: `matb_integration/analysis/stats/data.py`
- Create: `tests/analysis_stats/__init__.py` (empty)
- Test: `tests/analysis_stats/test_data.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/analysis_stats/test_data.py
from __future__ import annotations

import pandas as pd
import pytest

from matb_integration.analysis.stats.data import (
    ALL_METRICS, CONFIRMATORY_METRICS, VISIT_CENTER,
    fingerprint, fits_frame, metrics_frame,
)


def _mrow(p="P01", v=1, lvl="LOW", metric="sysmon_d_prime", value=2.0, **extra):
    return {"participant_id": p, "visit_ordinal": v, "workload_level": lvl,
            "metric": metric, "value": value, **extra}


def test_constants():
    assert CONFIRMATORY_METRICS == ("sysmon_d_prime", "nasatlx_raw_tlx", "bedford")
    assert len(ALL_METRICS) == 7 and set(CONFIRMATORY_METRICS) <= set(ALL_METRICS)
    assert VISIT_CENTER == 3.5


def test_metrics_frame_shape_and_centering():
    df = metrics_frame([_mrow(v=1), _mrow(v=6, lvl="HIGH", value=1.0)])
    assert list(df.columns) == ["participant_id", "visit_ordinal", "workload_level",
                                "metric", "value", "visit_c"]
    assert df["visit_c"].tolist() == [-2.5, 2.5]
    assert df["value"].dtype.kind == "f"


def test_metrics_frame_drops_extras_and_null_values():
    df = metrics_frame([_mrow(scheduled_day=0), _mrow(value=None)])
    assert "scheduled_day" not in df.columns
    assert len(df) == 1  # null value dropped


def test_metrics_frame_rejects_unknown_level_and_metric():
    with pytest.raises(ValueError, match="workload_level"):
        metrics_frame([_mrow(lvl="EXTREME")])
    with pytest.raises(ValueError, match="metric"):
        metrics_frame([_mrow(metric="made_up")])


def test_metrics_frame_empty():
    df = metrics_frame([])
    assert df.empty and "visit_c" in df.columns


def test_fits_frame():
    df = fits_frame([{"participant_id": "P01", "visit_ordinal": 2,
                      "g0": 40.0, "p0": 0.99, "tau0": 12.0, "curve": [1, 2]}])
    assert "curve" not in df.columns
    assert df["visit_c"].tolist() == [-1.5]
    assert fits_frame([]).empty


def test_fingerprint_is_order_invariant_and_value_sensitive():
    a = [_mrow(), _mrow(p="P02")]
    f1 = fingerprint(a, [])
    f2 = fingerprint(list(reversed(a)), [])
    f3 = fingerprint([_mrow(), _mrow(p="P02", value=9.9)], [])
    assert f1 == f2 != f3
    assert len(f1) == 64
```

- [ ] **Step 2: Run tests to verify they fail**

Run (repo root): `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats -q`
Expected: FAIL — `ModuleNotFoundError: matb_integration.analysis.stats`

- [ ] **Step 3: Implement**

```python
# matb_integration/analysis/stats/__init__.py
"""Pre-specified frequentist statistics engine (Phase 3A).

Spec: docs/superpowers/specs/2026-06-03-webui-phase3-statistics-design.md
"""
```

```python
# matb_integration/analysis/stats/data.py
"""Tidy long-format frames + input fingerprint for the stats engine.

Input row shapes are exactly what the console serves: /metrics/long rows
(participant_id, visit_ordinal, workload_level, metric, value) and /fits rows
(participant_id, visit_ordinal, g0, p0, tau0; extra keys ignored).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

import pandas as pd

ALL_METRICS: tuple[str, ...] = (
    "sysmon_d_prime", "sysmon_hit_rate", "sysmon_mean_rt_ms",
    "comm_d_prime", "nasatlx_raw_tlx", "bedford", "isa_mean",
)
CONFIRMATORY_METRICS: tuple[str, ...] = ("sysmon_d_prime", "nasatlx_raw_tlx", "bedford")
LEVELS: tuple[str, ...] = ("LOW", "MEDIUM", "HIGH")
VISIT_CENTER = 3.5  # mean of visit ordinals 1..6

_METRIC_COLS = ("participant_id", "visit_ordinal", "workload_level", "metric", "value")
_FIT_COLS = ("participant_id", "visit_ordinal", "g0", "p0", "tau0")


def _frame(rows: Iterable[dict[str, Any]], cols: tuple[str, ...]) -> pd.DataFrame:
    df = pd.DataFrame(list(rows), columns=list(cols))
    if df.empty:
        df = pd.DataFrame({c: pd.Series(dtype="object") for c in cols})
    return df


def metrics_frame(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    df = _frame(rows, _METRIC_COLS)
    df = df[df["value"].notna()].copy()
    if not df.empty:
        bad_lvl = set(df["workload_level"]) - set(LEVELS)
        if bad_lvl:
            raise ValueError(f"unknown workload_level values: {sorted(bad_lvl)}")
        bad_metric = set(df["metric"]) - set(ALL_METRICS)
        if bad_metric:
            raise ValueError(f"unknown metric keys: {sorted(bad_metric)}")
        df["visit_ordinal"] = df["visit_ordinal"].astype("int64")
        df["value"] = df["value"].astype("float64")
    df["visit_c"] = pd.to_numeric(df["visit_ordinal"], errors="coerce") - VISIT_CENTER
    return df.reset_index(drop=True)


def fits_frame(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    df = _frame(rows, _FIT_COLS)
    if not df.empty:
        df["visit_ordinal"] = df["visit_ordinal"].astype("int64")
        for c in ("g0", "p0", "tau0"):
            df[c] = df[c].astype("float64")
    df["visit_c"] = pd.to_numeric(df["visit_ordinal"], errors="coerce") - VISIT_CENTER
    return df.reset_index(drop=True)


def fingerprint(metrics_rows: Iterable[dict[str, Any]],
                fits_rows: Iterable[dict[str, Any]]) -> str:
    """sha256 over canonicalized (sorted, column-restricted) input rows."""
    def canon(rows: Iterable[dict[str, Any]], cols: tuple[str, ...]) -> list[list[Any]]:
        recs = [[r.get(c) for c in cols] for r in rows]
        return sorted(recs, key=lambda rec: json.dumps(rec, default=str))
    payload = json.dumps(
        {"metrics": canon(metrics_rows, _METRIC_COLS),
         "fits": canon(fits_rows, _FIT_COLS)},
        separators=(",", ":"), default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats -q`
Expected: all PASS. Also run with system python to guard the pandas-2.x path:
`python3 -m pytest tests/analysis_stats -q` → PASS.

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/analysis/stats tests/analysis_stats
git commit -m "feat(stats): data frames, constants, input fingerprint"
```

---

### Task 2: Pre-registered data gates (`gates.py`)

**Files:**
- Create: `matb_integration/analysis/stats/gates.py`
- Test: `tests/analysis_stats/test_gates.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/analysis_stats/test_gates.py
from __future__ import annotations

import pandas as pd

from matb_integration.analysis.stats.data import metrics_frame
from matb_integration.analysis.stats.gates import (
    gate_q1, gate_q2, gate_q4, gate_rmcorr,
)


def _rows(n_participants, levels=("LOW", "MEDIUM", "HIGH"), visits=(1, 2)):
    rows = []
    for p in range(n_participants):
        for v in visits:
            for lvl in levels:
                rows.append({"participant_id": f"P{p:02d}", "visit_ordinal": v,
                             "workload_level": lvl, "metric": "bedford", "value": 3.0})
    return rows


def test_gate_q1_passes_at_minimums():
    # 6 participants x 2 visits x 2 levels = 24 rows, 6 with >=2 levels
    df = metrics_frame(_rows(6, levels=("LOW", "HIGH")))
    assert gate_q1(df) is None


def test_gate_q1_fails_on_rows_and_participants():
    assert "rows" in gate_q1(metrics_frame(_rows(2)))          # 12 rows < 24
    # 8 participants but each has only one level -> 0 with >=2 levels
    df = metrics_frame(_rows(8, levels=("LOW",), visits=(1, 2, 3)))
    assert "levels" in gate_q1(df)


def test_gate_q2_needs_two_visits():
    df = metrics_frame(_rows(8, visits=(1,)))  # 24 rows but single visit
    assert "visits" in gate_q2(df)
    assert gate_q2(metrics_frame(_rows(6))) is None


def test_gate_rmcorr():
    pairs = pd.DataFrame({
        "participant_id": [f"P{p}" for p in range(4) for _ in range(4)],
        "x": list(range(16)), "y": list(range(16)),
    })
    assert gate_rmcorr(pairs) is None           # N=16, k=4 -> err df 11 >= 8
    assert "participants" in gate_rmcorr(pairs[pairs.participant_id.isin(["P0", "P1"])])
    small = pairs.groupby("participant_id").head(3)  # N=12, k=4 -> err df 7 < 8
    assert "df" in gate_rmcorr(small)


def test_gate_q4():
    fits = pd.DataFrame({
        "participant_id": ["P1", "P1", "P2", "P2", "P3", "P3", "P4", "P4"],
        "visit_ordinal": [1, 2] * 4,
    })
    assert gate_q4(fits) is None
    assert "participants" in gate_q4(fits[fits.visit_ordinal == 1])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats/test_gates.py -q`
Expected: FAIL — no module `gates`

- [ ] **Step 3: Implement**

```python
# matb_integration/analysis/stats/gates.py
"""Pre-registered data gates (spec section 4). None = pass; str = failure reason."""
from __future__ import annotations

import pandas as pd

MIN_PARTICIPANTS_LMM = 6
MIN_ROWS_LMM = 24
MIN_PARTICIPANTS_RMCORR = 4
MIN_ERROR_DF_RMCORR = 8
MIN_PARTICIPANTS_Q4 = 4


def gate_q1(df: pd.DataFrame) -> str | None:
    if len(df) < MIN_ROWS_LMM:
        return f"only {len(df)} rows (< {MIN_ROWS_LMM})"
    n = int((df.groupby("participant_id")["workload_level"].nunique() >= 2).sum())
    if n < MIN_PARTICIPANTS_LMM:
        return f"only {n} participants with >=2 levels (< {MIN_PARTICIPANTS_LMM})"
    return None


def gate_q2(df: pd.DataFrame) -> str | None:
    if len(df) < MIN_ROWS_LMM:
        return f"only {len(df)} rows (< {MIN_ROWS_LMM})"
    n = int((df.groupby("participant_id")["visit_ordinal"].nunique() >= 2).sum())
    if n < MIN_PARTICIPANTS_LMM:
        return f"only {n} participants with >=2 visits (< {MIN_PARTICIPANTS_LMM})"
    return None


def gate_rmcorr(pairs: pd.DataFrame) -> str | None:
    n_ok = int((pairs.groupby("participant_id").size() >= 2).sum())
    if n_ok < MIN_PARTICIPANTS_RMCORR:
        return f"only {n_ok} participants with >=2 pairs (< {MIN_PARTICIPANTS_RMCORR})"
    n, k = len(pairs), int(pairs["participant_id"].nunique())
    err_df = n - k - 1
    if err_df < MIN_ERROR_DF_RMCORR:
        return f"error df {err_df} (< {MIN_ERROR_DF_RMCORR})"
    return None


def gate_q4(fits: pd.DataFrame) -> str | None:
    n = int((fits.groupby("participant_id")["visit_ordinal"].nunique() >= 2).sum())
    if n < MIN_PARTICIPANTS_Q4:
        return f"only {n} participants with >=2 fitted visits (< {MIN_PARTICIPANTS_Q4})"
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/analysis/stats/gates.py tests/analysis_stats/test_gates.py
git commit -m "feat(stats): pre-registered data gates"
```

---

### Task 3: Multiplicity wrappers (`multiplicity.py`)

**Files:**
- Create: `matb_integration/analysis/stats/multiplicity.py`
- Test: `tests/analysis_stats/test_multiplicity.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/analysis_stats/test_multiplicity.py
from __future__ import annotations

import pytest

from matb_integration.analysis.stats.multiplicity import bh_fdr, holm


def test_bh_fdr_known_example():
    # classic BH worked example
    pvals = [0.01, 0.04, 0.03, 0.005]
    p_adj, reject = bh_fdr(pvals, q=0.05)
    assert reject == [True, True, True, True]
    assert p_adj[3] == pytest.approx(0.02)   # 0.005 * 4 / 1
    assert p_adj[1] == pytest.approx(0.04)   # max step-up at the largest p


def test_bh_fdr_empty():
    assert bh_fdr([]) == ([], [])


def test_holm():
    p_adj, reject = holm([0.01, 0.04, 0.03])
    assert p_adj[0] == pytest.approx(0.03)   # 0.01 * 3
    assert reject[0] is True
    assert holm([]) == ([], [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats/test_multiplicity.py -q`
Expected: FAIL — no module `multiplicity`

- [ ] **Step 3: Implement**

```python
# matb_integration/analysis/stats/multiplicity.py
"""BH-FDR (confirmatory family) and Holm (within-metric contrasts) wrappers."""
from __future__ import annotations

from statsmodels.stats.multitest import multipletests


def bh_fdr(pvals: list[float], q: float = 0.05) -> tuple[list[float], list[bool]]:
    if not pvals:
        return [], []
    reject, p_adj, _, _ = multipletests(pvals, alpha=q, method="fdr_bh")
    return [float(p) for p in p_adj], [bool(r) for r in reject]


def holm(pvals: list[float], alpha: float = 0.05) -> tuple[list[float], list[bool]]:
    if not pvals:
        return [], []
    reject, p_adj, _, _ = multipletests(pvals, alpha=alpha, method="holm")
    return [float(p) for p in p_adj], [bool(r) for r in reject]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats -q` → PASS

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/analysis/stats/multiplicity.py tests/analysis_stats/test_multiplicity.py
git commit -m "feat(stats): BH-FDR and Holm multiplicity wrappers"
```

---

### Task 4: Simulated-study fixture (`conftest.py`)

**Files:**
- Create: `tests/analysis_stats/conftest.py`

No production code; this fixture is used by Tasks 5–9. Seeded
`numpy.random.default_rng` streams are version-stable, so exact assertions are
safe.

- [ ] **Step 1: Write the fixture**

```python
# tests/analysis_stats/conftest.py
from __future__ import annotations

import numpy as np
import pytest

# Known ground truth for the simulated study (used by recovery assertions)
TRUE_LEVEL_STEP = 0.8     # per level index LOW=0, MEDIUM=1, HIGH=2
TRUE_VISIT_SLOPE = -0.05  # per centered visit
RE_SD, NOISE_SD = 0.5, 0.3


def simulate_metric_rows(metric: str, seed: int, n_participants: int = 12,
                         base: float = 2.0) -> list[dict]:
    """12x6x3 rows for one metric with known fixed effects + random intercepts."""
    rng = np.random.default_rng(seed)
    rows = []
    for p in range(n_participants):
        u = rng.normal(0, RE_SD)
        for v in range(1, 7):
            for li, lvl in enumerate(["LOW", "MEDIUM", "HIGH"]):
                y = (base + TRUE_LEVEL_STEP * li
                     + TRUE_VISIT_SLOPE * (v - 3.5) + u + rng.normal(0, NOISE_SD))
                rows.append({"participant_id": f"P{p:02d}", "visit_ordinal": v,
                             "workload_level": lvl, "metric": metric,
                             "value": float(y)})
    return rows


@pytest.fixture
def sim_study():
    """Three confirmatory metrics with the same known structure, distinct seeds."""
    rows = []
    for seed, metric in ((42, "sysmon_d_prime"), (43, "nasatlx_raw_tlx"), (44, "bedford")):
        rows.extend(simulate_metric_rows(metric, seed))
    return rows


@pytest.fixture
def sim_fits():
    """Per-visit DEPDF fits with a known g0 drift (+0.5/visit) for 6 participants."""
    rng = np.random.default_rng(99)
    rows = []
    for p in range(6):
        for v in range(1, 7):
            rows.append({"participant_id": f"P{p:02d}", "visit_ordinal": v,
                         "g0": float(40.0 + 0.5 * (v - 3.5) + rng.normal(0, 0.3)),
                         "p0": float(np.clip(0.99 + rng.normal(0, 0.002), 0, 1)),
                         "tau0": float(12.0 + rng.normal(0, 0.5))})
    return rows
```

- [ ] **Step 2: Sanity-run collection**

Run: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats -q --collect-only | tail -3`
Expected: collects existing tests, no errors.

- [ ] **Step 3: Commit**

```bash
cd /root/repos/MATB
git add tests/analysis_stats/conftest.py
git commit -m "test(stats): simulated-study fixtures with known ground truth"
```

---

### Task 5: LMM module — Q1/Q2/Q4, omnibus, contrasts, effect sizes (`lmm.py`)

**Files:**
- Create: `matb_integration/analysis/stats/lmm.py`
- Test: `tests/analysis_stats/test_lmm.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/analysis_stats/test_lmm.py
from __future__ import annotations

import pytest

from matb_integration.analysis.stats.data import fits_frame, metrics_frame
from matb_integration.analysis.stats.lmm import fit_q1, fit_q2, fit_q4

from .conftest import simulate_metric_rows


@pytest.fixture
def df42():
    return metrics_frame(simulate_metric_rows("sysmon_d_prime", seed=42))


def test_q1_recovers_level_effects_and_omnibus(df42):
    out = fit_q1(df42)
    assert out["status"] == "ok"
    coefs = {c["name"]: c for c in out["coefs"]}
    # truth: MEDIUM-LOW = 0.8, HIGH-LOW = 1.6
    assert coefs["MEDIUM-LOW"]["coef"] == pytest.approx(0.8, abs=0.15)
    assert coefs["HIGH-LOW"]["coef"] == pytest.approx(1.6, abs=0.15)
    assert out["omnibus"]["df"] == 2 and out["omnibus"]["p"] < 1e-6
    lo, hi = coefs["HIGH-LOW"]["ci95"]
    assert lo < 1.6 < hi
    assert coefs["HIGH-LOW"]["standardizer"] == "sqrt(re_var + resid_var)"
    # std effect = coef / sqrt(re_var + resid_var)
    import math
    expected = coefs["HIGH-LOW"]["coef"] / math.sqrt(out["re_var"] + out["resid_var"])
    assert coefs["HIGH-LOW"]["std_effect"] == pytest.approx(expected)


def test_q1_contrasts_include_high_vs_medium(df42):
    out = fit_q1(df42)
    names = [c["name"] for c in out["contrasts"]]
    assert names == ["MEDIUM-LOW", "HIGH-LOW", "HIGH-MEDIUM"]
    hm = out["contrasts"][2]
    assert hm["coef"] == pytest.approx(0.8, abs=0.15)
    assert 0 < hm["p"] < 1e-4
    assert hm["ci95"][0] < hm["coef"] < hm["ci95"][1]


def test_q2_recovers_visit_slope(df42):
    out = fit_q2(df42)
    assert out["status"] == "ok"
    slope = {c["name"]: c for c in out["coefs"]}["visit_c"]
    assert slope["coef"] == pytest.approx(-0.05, abs=0.04)
    assert any(":" in c["name"] for c in out["interactions"])


def test_insufficient_data_status():
    df = metrics_frame(simulate_metric_rows("bedford", seed=7, n_participants=2))
    assert fit_q1(df)["status"] == "insufficient_data"
    assert fit_q2(df)["status"] == "insufficient_data"


def test_not_estimable_on_degenerate_input():
    # constant response -> singular fit must yield a status, never raise
    rows = simulate_metric_rows("bedford", seed=7)
    for r in rows:
        r["value"] = 5.0
    out = fit_q1(metrics_frame(rows))
    assert out["status"] in ("ok", "not_estimable")  # never an exception
    if out["status"] == "not_estimable":
        assert out["detail"]


def test_q4_recovers_g0_drift(sim_fits):
    out = fit_q4(fits_frame(sim_fits), "g0")
    assert out["status"] == "ok"
    slope = {c["name"]: c for c in out["coefs"]}["visit_c"]
    assert slope["coef"] == pytest.approx(0.5, abs=0.1)


def test_q4_insufficient(sim_fits):
    one_visit = [r for r in sim_fits if r["visit_ordinal"] == 1]
    assert fit_q4(fits_frame(one_visit), "g0")["status"] == "insufficient_data"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats/test_lmm.py -q`
Expected: FAIL — no module `lmm`

- [ ] **Step 3: Implement**

```python
# matb_integration/analysis/stats/lmm.py
"""MixedLM fits for Q1 (level), Q2 (trajectory), Q4 (DEPDF drift).

Random intercepts only (n=12 participants; spec section 2). REML estimates;
Wald inference (small-sample caveat carried in the artifact).
"""
from __future__ import annotations

import math
import warnings
from typing import Any

import pandas as pd
from scipy.stats import norm

from . import gates

LEVEL_TERM = "C(workload_level, Treatment('LOW'))"
MED = f"{LEVEL_TERM}[T.MEDIUM]"
HIGH = f"{LEVEL_TERM}[T.HIGH]"
STANDARDIZER = "sqrt(re_var + resid_var)"
_Z = float(norm.ppf(0.975))


def _fit(formula: str, df: pd.DataFrame):
    import statsmodels.formula.api as smf

    model = smf.mixedlm(formula, df, groups=df["participant_id"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return model.fit(reml=True)


def _coef(res, name: str, label: str, denom: float) -> dict[str, Any]:
    ci = res.conf_int().loc[name]
    coef = float(res.params[name])
    return {
        "name": label, "coef": coef,
        "ci95": [float(ci.iloc[0]), float(ci.iloc[1])],
        "p": float(res.pvalues[name]),
        "std_effect": coef / denom, "standardizer": STANDARDIZER,
    }


def _variances(res) -> tuple[float, float]:
    re_var = float(res.cov_re.iloc[0, 0])
    resid_var = float(res.scale)
    return re_var, resid_var


def _contrasts(res, denom: float) -> list[dict[str, Any]]:
    out = [_coef(res, MED, "MEDIUM-LOW", denom), _coef(res, HIGH, "HIGH-LOW", denom)]
    est = float(res.params[HIGH] - res.params[MED])
    V = res.cov_params()
    se = math.sqrt(float(V.loc[HIGH, HIGH] + V.loc[MED, MED] - 2 * V.loc[HIGH, MED]))
    w = res.wald_test(f"{HIGH} - {MED} = 0", scalar=True)
    out.append({
        "name": "HIGH-MEDIUM", "coef": est,
        "ci95": [est - _Z * se, est + _Z * se], "p": float(w.pvalue),
        "std_effect": est / denom, "standardizer": STANDARDIZER,
    })
    return out


def _meta(res, df: pd.DataFrame) -> dict[str, Any]:
    re_var, resid_var = _variances(res)
    return {"n_obs": int(res.nobs),
            "n_participants": int(df["participant_id"].nunique()),
            "re_var": re_var, "resid_var": resid_var}


def fit_q1(df: pd.DataFrame) -> dict[str, Any]:
    reason = gates.gate_q1(df)
    if reason:
        return {"status": "insufficient_data", "detail": reason}
    try:
        res = _fit(f"value ~ {LEVEL_TERM} + visit_c", df)
        if not res.converged:
            return {"status": "not_estimable", "detail": "MixedLM did not converge"}
        re_var, resid_var = _variances(res)
        denom = math.sqrt(re_var + resid_var)
        w = res.wald_test(f"{MED} = 0, {HIGH} = 0", scalar=True)
        return {
            "status": "ok", **_meta(res, df),
            "formula": f"value ~ {LEVEL_TERM} + visit_c",
            "omnibus": {"statistic": float(w.statistic), "df": 2,
                        "p": float(w.pvalue), "test": "Wald chi2 (REML)"},
            "coefs": [_coef(res, MED, "MEDIUM-LOW", denom),
                      _coef(res, HIGH, "HIGH-LOW", denom),
                      _coef(res, "visit_c", "visit_c", denom)],
            "contrasts": _contrasts(res, denom),
        }
    except Exception as e:  # noqa: BLE001 — statuses are first-class (spec section 4)
        return {"status": "not_estimable", "detail": f"{type(e).__name__}: {e}"}


def fit_q2(df: pd.DataFrame) -> dict[str, Any]:
    reason = gates.gate_q2(df)
    if reason:
        return {"status": "insufficient_data", "detail": reason}
    formula = f"value ~ visit_c + {LEVEL_TERM} + visit_c:{LEVEL_TERM}"
    try:
        res = _fit(formula, df)
        if not res.converged:
            return {"status": "not_estimable", "detail": "MixedLM did not converge"}
        re_var, resid_var = _variances(res)
        denom = math.sqrt(re_var + resid_var)
        inter = [n for n in res.params.index if n.startswith("visit_c:")]
        return {
            "status": "ok", **_meta(res, df), "formula": formula,
            "coefs": [_coef(res, "visit_c", "visit_c", denom),
                      _coef(res, MED, "MEDIUM-LOW", denom),
                      _coef(res, HIGH, "HIGH-LOW", denom)],
            "interactions": [_coef(res, n, n, denom) for n in inter],
        }
    except Exception as e:  # noqa: BLE001
        return {"status": "not_estimable", "detail": f"{type(e).__name__}: {e}"}


def fit_q4(fits: pd.DataFrame, param: str) -> dict[str, Any]:
    reason = gates.gate_q4(fits)
    if reason:
        return {"status": "insufficient_data", "detail": reason}
    df = fits.rename(columns={param: "value"})
    try:
        res = _fit("value ~ visit_c", df)
        if not res.converged:
            return {"status": "not_estimable", "detail": "MixedLM did not converge"}
        re_var, resid_var = _variances(res)
        denom = math.sqrt(re_var + resid_var)
        return {"status": "ok", **_meta(res, df), "formula": f"{param} ~ visit_c",
                "coefs": [_coef(res, "visit_c", "visit_c", denom)]}
    except Exception as e:  # noqa: BLE001
        return {"status": "not_estimable", "detail": f"{type(e).__name__}: {e}"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats -q` → PASS
(Verified interactively 2026-06-03 on this venv: seed-42 fit recovers
MEDIUM-LOW 0.789, HIGH-LOW 1.653, visit_c −0.057; omnibus p ≈ 7.7e-293.)

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/analysis/stats/lmm.py tests/analysis_stats/test_lmm.py
git commit -m "feat(stats): MixedLM Q1/Q2/Q4 with omnibus, contrasts, std effects"
```

---

### Task 6: rmcorr with published oracle (`rmcorr.py`)

**Files:**
- Create: `matb_integration/analysis/stats/rmcorr.py`
- Test: `tests/analysis_stats/test_rmcorr.py`

- [ ] **Step 1: Write the failing tests** (oracle values below were generated
once with `pingouin 0.6.1` in a throwaway venv on 2026-06-03 and are
hard-coded; pingouin is NOT a dependency. They match Bakdash & Marusich 2017's
published r_rm = −0.507 for the Bland & Altman 1995 pH/PaCO2 data.)

```python
# tests/analysis_stats/test_rmcorr.py
from __future__ import annotations

import pandas as pd
import pytest

from matb_integration.analysis.stats.rmcorr import rm_corr, rm_corr_level_adjusted

# Bland & Altman (1995) intra-subject pH/PaCO2 data, 8 subjects, 47 obs —
# the canonical rmcorr example in Bakdash & Marusich (2017), Front. Psychol.
_SUBJ = [1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4,
         5, 5, 5, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 7, 7, 7, 8, 8, 8, 8, 8, 8, 8, 8]
_PH = [6.68, 6.53, 6.43, 6.33, 6.85, 7.06, 7.13, 7.17, 7.4, 7.42, 7.41, 7.37,
       7.34, 7.35, 7.28, 7.3, 7.34, 7.36, 7.33, 7.29, 7.3, 7.35, 7.35, 7.3,
       7.3, 7.37, 7.27, 7.28, 7.32, 7.32, 7.38, 7.3, 7.29, 7.33, 7.31, 7.33,
       6.86, 6.94, 6.92, 7.19, 7.29, 7.21, 7.25, 7.2, 7.19, 6.77, 6.82]
_PACO2 = [3.97, 4.12, 4.09, 3.97, 5.27, 5.37, 5.41, 5.44, 5.67, 3.64, 4.32,
          4.73, 4.96, 5.04, 5.22, 4.82, 5.07, 5.67, 5.1, 5.53, 4.75, 5.51,
          4.28, 4.44, 4.32, 3.23, 4.46, 4.72, 4.75, 4.99, 4.78, 4.73, 5.12,
          4.93, 5.03, 4.93, 6.85, 6.44, 6.52, 5.28, 4.56, 4.34, 4.32, 4.41,
          3.69, 6.09, 5.58]


def _bland_altman_pairs() -> pd.DataFrame:
    return pd.DataFrame({"participant_id": [str(s) for s in _SUBJ],
                         "x": _PH, "y": _PACO2})


def test_rm_corr_matches_pingouin_oracle():
    out = rm_corr(_bland_altman_pairs())
    assert out["status"] == "ok"
    # pingouin 0.6.1: r=-0.5067697422, dof=38, p=0.0008471081091, CI95 [-0.71, -0.23]
    assert out["r"] == pytest.approx(-0.5067697422, abs=1e-9)
    assert out["dof"] == 38
    assert out["p"] == pytest.approx(0.0008471081091, rel=1e-6)
    assert out["ci95"][0] == pytest.approx(-0.71, abs=0.02)
    assert out["ci95"][1] == pytest.approx(-0.23, abs=0.02)
    assert out["n_pairs"] == 47 and out["n_participants"] == 8


def test_rm_corr_insufficient_data():
    pairs = _bland_altman_pairs().head(6)  # 2 subjects
    assert rm_corr(pairs)["status"] == "insufficient_data"


def test_rm_corr_level_adjusted_runs():
    pairs = _bland_altman_pairs()
    # synthetic level labels purely to exercise the residualization path
    pairs["workload_level"] = (["LOW", "MEDIUM", "HIGH"] * 16)[: len(pairs)]
    out = rm_corr_level_adjusted(pairs)
    assert out["status"] == "ok"
    assert "sensitivity" in out["method"]
    assert -1.0 <= out["r"] <= 0.0  # same direction as canonical
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats/test_rmcorr.py -q`
Expected: FAIL — no module `rmcorr`

- [ ] **Step 3: Implement**

```python
# matb_integration/analysis/stats/rmcorr.py
"""Canonical repeated-measures correlation (Bakdash & Marusich 2017).

ANCOVA y ~ x + C(participant); r from the covariate partial SS with
df = N - k - 1 (N pairs, k participants). Fisher-z 95% CI on the error df.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import gates

METHOD = "Bakdash & Marusich (2017) ANCOVA rmcorr"
_Z = float(norm.ppf(0.975))


def rm_corr(pairs: pd.DataFrame) -> dict[str, Any]:
    """pairs: columns participant_id, x, y (complete pairs only)."""
    reason = gates.gate_rmcorr(pairs)
    if reason:
        return {"status": "insufficient_data", "detail": reason}
    try:
        import statsmodels.api as sm
        from statsmodels.formula.api import ols

        model = ols("y ~ x + C(participant_id)", data=pairs).fit()
        table = sm.stats.anova_lm(model, typ=3)
        ss_x = float(table.loc["x", "sum_sq"])
        ss_err = float(table.loc["Residual", "sum_sq"])
        dof = int(table.loc["Residual", "df"])
        r = float(np.sign(model.params["x"]) * np.sqrt(ss_x / (ss_x + ss_err)))
        z, se = np.arctanh(r), 1.0 / np.sqrt(dof - 1)
        return {
            "status": "ok", "r": r, "dof": dof,
            "p": float(table.loc["x", "PR(>F)"]),
            "ci95": [float(np.tanh(z - _Z * se)), float(np.tanh(z + _Z * se))],
            "ci_method": "Fisher z, se = 1/sqrt(dof - 1)",
            "n_pairs": int(len(pairs)),
            "n_participants": int(pairs["participant_id"].nunique()),
            "method": METHOD,
        }
    except Exception as e:  # noqa: BLE001 — statuses are first-class
        return {"status": "not_estimable", "detail": f"{type(e).__name__}: {e}"}


def rm_corr_level_adjusted(pairs: pd.DataFrame) -> dict[str, Any]:
    """Sensitivity: residualize x and y on workload level first (spec section 2)."""
    try:
        from statsmodels.formula.api import ols

        adj = pairs.copy()
        for col in ("x", "y"):
            adj[col] = ols(f"{col} ~ C(workload_level)", data=adj).fit().resid
    except Exception as e:  # noqa: BLE001
        return {"status": "not_estimable", "detail": f"{type(e).__name__}: {e}"}
    out = rm_corr(adj[["participant_id", "x", "y"]])
    out["method"] = "rmcorr on level-adjusted residuals (sensitivity)"
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats -q` → PASS.
If the oracle assertion fails on `r` beyond 1e-9: check `anova_lm` typ — it
must be `typ=3` to match pingouin. Do NOT loosen the tolerance.

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/analysis/stats/rmcorr.py tests/analysis_stats/test_rmcorr.py
git commit -m "feat(stats): canonical rmcorr with Bland-Altman published oracle"
```

---

### Task 7: rmANOVA sensitivity (`rmanova.py`)

**Files:**
- Create: `matb_integration/analysis/stats/rmanova.py`
- Test: `tests/analysis_stats/test_rmanova.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/analysis_stats/test_rmanova.py
from __future__ import annotations

from matb_integration.analysis.stats.data import metrics_frame
from matb_integration.analysis.stats.rmanova import rm_anova_q1

from .conftest import simulate_metric_rows


def test_rm_anova_detects_level_effect():
    df = metrics_frame(simulate_metric_rows("bedford", seed=42))
    out = rm_anova_q1(df)
    assert out["status"] == "ok"
    assert out["p"] < 1e-6
    assert 0.5 < out["partial_eta_sq"] <= 1.0
    assert out["complete_case_n"] == 12
    assert "sensitivity" in out["note"]


def test_rm_anova_complete_case_only():
    rows = simulate_metric_rows("bedford", seed=42)
    # drop ALL HIGH rows for P00/P01 -> those participants are not complete-case
    rows = [r for r in rows
            if not (r["participant_id"] in ("P00", "P01")
                    and r["workload_level"] == "HIGH")]
    out = rm_anova_q1(metrics_frame(rows))
    assert out["status"] == "ok" and out["complete_case_n"] == 10


def test_rm_anova_insufficient():
    rows = simulate_metric_rows("bedford", seed=42, n_participants=2)
    assert rm_anova_q1(metrics_frame(rows))["status"] == "insufficient_data"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats/test_rmanova.py -q`
Expected: FAIL — no module `rmanova`

- [ ] **Step 3: Implement**

```python
# matb_integration/analysis/stats/rmanova.py
"""Complete-case repeated-measures ANOVA — descriptive Q1 sensitivity only."""
from __future__ import annotations

from typing import Any

import pandas as pd

MIN_COMPLETE_CASE = 3


def rm_anova_q1(df: pd.DataFrame) -> dict[str, Any]:
    have = df.groupby("participant_id")["workload_level"].nunique()
    keep = have[have == 3].index
    cc = df[df["participant_id"].isin(keep)]
    n_cc = int(cc["participant_id"].nunique())
    if n_cc < MIN_COMPLETE_CASE:
        return {"status": "insufficient_data",
                "detail": f"only {n_cc} complete-case participants (< {MIN_COMPLETE_CASE})"}
    try:
        from statsmodels.stats.anova import AnovaRM

        res = AnovaRM(cc, depvar="value", subject="participant_id",
                      within=["workload_level"], aggregate_func="mean").fit()
        row = res.anova_table.iloc[0]
        f, df1, df2 = float(row["F Value"]), float(row["Num DF"]), float(row["Den DF"])
        return {"status": "ok", "F": f, "df": [df1, df2],
                "p": float(row["Pr > F"]),
                "partial_eta_sq": f * df1 / (f * df1 + df2),
                "complete_case_n": n_cc,
                "note": "complete-case, visit-averaged; descriptive sensitivity only"}
    except Exception as e:  # noqa: BLE001 — statuses are first-class
        return {"status": "not_estimable", "detail": f"{type(e).__name__}: {e}"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats -q` → PASS

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/analysis/stats/rmanova.py tests/analysis_stats/test_rmanova.py
git commit -m "feat(stats): complete-case rmANOVA sensitivity with partial eta-squared"
```

---

### Task 8: Engine orchestration (`engine.py`)

**Files:**
- Create: `matb_integration/analysis/stats/engine.py`
- Modify: `matb_integration/analysis/stats/__init__.py`
- Test: `tests/analysis_stats/test_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/analysis_stats/test_engine.py
from __future__ import annotations

from matb_integration.analysis.stats.engine import ENGINE_VERSION, Q3_PAIRS, run_analysis


def test_full_artifact_on_simulated_study(sim_study, sim_fits):
    art = run_analysis(sim_study, sim_fits, created_utc="2026-06-03T00:00:00+00:00")
    assert art["engine_version"] == ENGINE_VERSION
    prov = art["provenance"]
    assert len(prov["fingerprint"]) == 64
    assert prov["n_metric_rows"] == 12 * 6 * 3 * 3 and prov["n_fit_rows"] == 36
    assert set(prov["libraries"]) == {"pandas", "statsmodels", "scipy", "numpy"}
    # confirmatory family: 3 metrics x {Q1 omnibus, Q2 slope} = 6, all estimable here
    fam = art["confirmatory"]
    assert fam["family_size_planned"] == 6 and fam["family_size_actual"] == 6
    assert len(fam["tests"]) == 6
    assert all(t["reject"] in (True, False) and 0 <= t["p_fdr"] <= 1 for t in fam["tests"])
    # strong simulated effects -> Q1 omnibus tests all survive -> Holm contrasts attached
    q1_dprime = art["q1"]["sysmon_d_prime"]
    assert q1_dprime["status"] == "ok"
    assert q1_dprime["contrasts"] is not None
    assert all("p_holm" in c for c in q1_dprime["contrasts"])
    # exploratory metrics carry no contrasts and are flagged
    assert art["q1"]["isa_mean"]["exploratory"] is True
    assert art["q1"]["isa_mean"].get("contrasts") is None
    # Q3: one entry per pre-specified pair, each with canonical + sensitivity
    assert len(art["q3"]) == len(Q3_PAIRS)
    ok_pairs = [e for e in art["q3"] if e["canonical"]["status"] == "ok"]
    assert all("sensitivity" in e for e in ok_pairs)
    # Q4 over the three DEPDF params
    assert set(art["q4"]) == {"g0", "p0", "tau0"}
    assert art["q4"]["g0"]["status"] == "ok"
    # rmANOVA sensitivity for the three confirmatory metrics
    assert set(art["rmanova"]) == {"sysmon_d_prime", "nasatlx_raw_tlx", "bedford"}
    assert isinstance(art["caveats"], list) and art["caveats"]


def test_empty_inputs_never_crash():
    art = run_analysis([], [])
    assert art["confirmatory"]["family_size_actual"] == 0
    assert all(v["status"] == "insufficient_data" for v in art["q1"].values())
    assert all(v["status"] == "insufficient_data" for v in art["q4"].values())
    assert all(e["canonical"]["status"] == "insufficient_data" for e in art["q3"])


def test_artifact_is_json_serializable(sim_study, sim_fits):
    import json
    json.dumps(run_analysis(sim_study, sim_fits))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats/test_engine.py -q`
Expected: FAIL — no module `engine`

- [ ] **Step 3: Implement**

```python
# matb_integration/analysis/stats/engine.py
"""Engine orchestration: Q1-Q4 + multiplicity -> one JSON-serializable artifact.

Multiplicity (spec section 3): BH-FDR at q=.05 over exactly the 6-test
confirmatory family ({d', raw TLX, Bedford} x {Q1 omnibus, Q2 visit slope});
pairwise Q1 contrasts only for FDR survivors, Holm-corrected within metric.
Everything else is exploratory.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .data import (ALL_METRICS, CONFIRMATORY_METRICS, fingerprint,
                   fits_frame, metrics_frame)
from .lmm import fit_q1, fit_q2, fit_q4
from .multiplicity import bh_fdr, holm
from .rmanova import rm_anova_q1
from .rmcorr import rm_corr, rm_corr_level_adjusted

ENGINE_VERSION = "1.0.0"
SPEC = "docs/superpowers/specs/2026-06-03-webui-phase3-statistics-design.md"
FDR_Q = 0.05
# Pre-specified exploratory coupling pairs (x = subjective workload, y = performance)
Q3_PAIRS: tuple[tuple[str, str], ...] = tuple(
    (x, y)
    for x in ("nasatlx_raw_tlx", "bedford", "isa_mean")
    for y in ("sysmon_d_prime", "sysmon_mean_rt_ms", "comm_d_prime")
)
CAVEATS = [
    "Wald inference on REML fits; small-sample (n=12) p-values are approximate.",
    "Random intercepts only; random slopes not estimable at this n.",
    "rmANOVA is complete-case and visit-averaged; descriptive sensitivity only.",
    "Q3/Q4 and non-confirmatory metrics are exploratory (no error-rate control).",
]


def _pairs_frame(mdf: pd.DataFrame, x_metric: str, y_metric: str) -> pd.DataFrame:
    cols = ["participant_id", "visit_ordinal", "workload_level"]
    empty = pd.DataFrame(columns=cols + ["x", "y"])
    if mdf.empty:
        return empty
    wide = mdf.pivot_table(index=cols, columns="metric", values="value",
                           aggfunc="first").reset_index()
    if x_metric not in wide.columns or y_metric not in wide.columns:
        return empty
    out = wide[cols + [x_metric, y_metric]].dropna()
    return out.rename(columns={x_metric: "x", y_metric: "y"})


def _libraries() -> dict[str, str]:
    import numpy
    import scipy
    import statsmodels
    return {"pandas": pd.__version__, "statsmodels": statsmodels.__version__,
            "scipy": scipy.__version__, "numpy": numpy.__version__}


def run_analysis(metrics_rows: list[dict[str, Any]], fits_rows: list[dict[str, Any]],
                 created_utc: str | None = None) -> dict[str, Any]:
    metrics_rows, fits_rows = list(metrics_rows), list(fits_rows)
    mdf, fdf = metrics_frame(metrics_rows), fits_frame(fits_rows)

    per_metric = {m: mdf[mdf["metric"] == m] for m in ALL_METRICS}
    q1 = {m: fit_q1(d) for m, d in per_metric.items()}
    q2 = {m: fit_q2(d) for m, d in per_metric.items()}

    # --- confirmatory family: BH-FDR over the available planned tests ---
    planned: list[tuple[str, str, float | None]] = []
    for m in CONFIRMATORY_METRICS:
        p1 = q1[m]["omnibus"]["p"] if q1[m]["status"] == "ok" else None
        slope = next((c for c in q2[m].get("coefs", []) if c["name"] == "visit_c"), None)
        p2 = slope["p"] if q2[m]["status"] == "ok" and slope else None
        planned.append((m, "Q1_omnibus", p1))
        planned.append((m, "Q2_visit_slope", p2))
    avail = [(m, q, p) for m, q, p in planned if p is not None]
    p_adj, reject = bh_fdr([p for _, _, p in avail], q=FDR_Q)
    adj_map = {(m, q): (pa, rj) for (m, q, _), pa, rj in zip(avail, p_adj, reject)}
    tests = []
    for m, qname, p in planned:
        pa, rj = adj_map.get((m, qname), (None, None))
        tests.append({"metric": m, "test": qname, "p": p, "p_fdr": pa, "reject": rj})
    confirmatory = {"family_size_planned": len(planned),
                    "family_size_actual": len(avail),
                    "fdr_q": FDR_Q, "tests": tests}

    # --- Q1 contrasts: only for FDR-surviving confirmatory omnibus tests ---
    survivors = {m for m, qname, _ in planned
                 if qname == "Q1_omnibus" and adj_map.get((m, qname), (None, False))[1]}
    for m, res in q1.items():
        res["exploratory"] = m not in CONFIRMATORY_METRICS
        contrasts = res.pop("contrasts", None)
        if m in survivors and contrasts:
            p_holm, rej = holm([c["p"] for c in contrasts])
            for c, ph, rj in zip(contrasts, p_holm, rej):
                c["p_holm"], c["reject_holm"] = ph, rj
            res["contrasts"] = contrasts
        else:
            res["contrasts"] = None  # suppressed: gated on the FDR family (spec section 3)
    for m, res in q2.items():
        res["exploratory"] = m not in CONFIRMATORY_METRICS

    # --- Q3 (exploratory): canonical rmcorr + level-adjusted sensitivity ---
    q3 = []
    for x_metric, y_metric in Q3_PAIRS:
        pairs = _pairs_frame(mdf, x_metric, y_metric)
        entry: dict[str, Any] = {"x": x_metric, "y": y_metric,
                                 "canonical": rm_corr(pairs[["participant_id", "x", "y"]])}
        if entry["canonical"]["status"] == "ok":
            entry["sensitivity"] = rm_corr_level_adjusted(pairs)
        q3.append(entry)

    # --- Q4 (exploratory): DEPDF parameter drift ---
    q4 = {param: fit_q4(fdf, param) for param in ("g0", "p0", "tau0")}

    rmanova = {m: rm_anova_q1(per_metric[m]) for m in CONFIRMATORY_METRICS}

    return {
        "engine_version": ENGINE_VERSION, "spec": SPEC,
        "provenance": {
            "fingerprint": fingerprint(metrics_rows, fits_rows),
            "n_metric_rows": len(metrics_rows), "n_fit_rows": len(fits_rows),
            "n_participants": int(mdf["participant_id"].nunique()) if not mdf.empty else 0,
            "libraries": _libraries(), "created_utc": created_utc,
        },
        "confirmatory": confirmatory,
        "q1": q1, "q2": q2, "q3": q3, "q4": q4, "rmanova": rmanova,
        "caveats": list(CAVEATS),
    }
```

Update the package `__init__.py`:

```python
# matb_integration/analysis/stats/__init__.py
"""Pre-specified frequentist statistics engine (Phase 3A).

Spec: docs/superpowers/specs/2026-06-03-webui-phase3-statistics-design.md
"""
from .data import fingerprint  # noqa: F401
from .engine import ENGINE_VERSION, run_analysis  # noqa: F401
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats -q` → PASS
Also: `python3 -m pytest tests/analysis_stats -q` (system python / pandas 2.x) → PASS

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/analysis/stats tests/analysis_stats/test_engine.py
git commit -m "feat(stats): engine orchestration with FDR family and gated Holm contrasts"
```

---

### Task 9: CLI (`cli.py`)

**Files:**
- Create: `matb_integration/analysis/stats/cli.py`
- Test: `tests/analysis_stats/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/analysis_stats/test_cli.py
from __future__ import annotations

import json

from matb_integration.analysis.stats.cli import main


def test_cli_run_writes_artifact(tmp_path, sim_study, sim_fits):
    m = tmp_path / "metrics.json"
    f = tmp_path / "fits.json"
    out = tmp_path / "artifact.json"
    m.write_text(json.dumps(sim_study))
    f.write_text(json.dumps(sim_fits))
    rc = main(["run", "--metrics-json", str(m), "--fits-json", str(f), "-o", str(out)])
    assert rc == 0
    art = json.loads(out.read_text())
    assert art["engine_version"]
    assert art["provenance"]["created_utc"]  # CLI stamps the timestamp
    assert art["confirmatory"]["family_size_actual"] == 6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats/test_cli.py -q`
Expected: FAIL — no module `cli`

- [ ] **Step 3: Implement**

```python
# matb_integration/analysis/stats/cli.py
"""CLI: write a reproducible analysis artifact for the manuscript.

Usage:
  python3 -m matb_integration.analysis.stats.cli run \
      --metrics-json metrics.json --fits-json fits.json -o artifact.json

metrics.json: JSON array of /metrics/long rows; fits.json: array of /fits rows.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .engine import run_analysis


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="matb-stats", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run the pre-specified analysis")
    run.add_argument("--metrics-json", required=True, type=Path)
    run.add_argument("--fits-json", required=True, type=Path)
    run.add_argument("-o", "--output", required=True, type=Path)
    args = parser.parse_args(argv)

    metrics = json.loads(args.metrics_json.read_text())
    fits = json.loads(args.fits_json.read_text())
    artifact = run_analysis(
        metrics, fits, created_utc=datetime.now(timezone.utc).isoformat())
    args.output.write_text(json.dumps(artifact, indent=2))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats -q` → PASS
Then run the **whole repo suite** to confirm nothing regressed:
`~/.venvs/matb-webui/bin/python -m pytest tests -q` → all pass (95+ previous + new).

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/analysis/stats/cli.py tests/analysis_stats/test_cli.py
git commit -m "feat(stats): artifact CLI (matb_integration.analysis.stats.cli run)"
```

---

### Task 10: Backend — `AnalysisResult` table, row collectors, `/analysis` endpoints

**Files:**
- Modify: `webui/backend/app/models.py` (append table)
- Modify: `webui/backend/app/routers/metrics.py` (extract `collect_metric_rows`)
- Modify: `webui/backend/app/routers/fits.py` (add `collect_fit_rows`)
- Create: `webui/backend/app/routers/analysis.py`
- Modify: `webui/backend/app/main.py` (router include)
- Modify: `webui/backend/requirements.txt`
- Test: `webui/backend/tests/test_analysis_endpoint.py`

- [ ] **Step 1: Add deps to `webui/backend/requirements.txt`** (append after the
existing suhir block):

```
# Required by the Phase 3A statistics engine (matb_integration.analysis.stats)
pandas>=2.3
statsmodels>=0.14.6
```

(Already installed in `~/.venvs/matb-webui`: pandas 3.0.3, statsmodels 0.14.6.)

- [ ] **Step 2: Write the failing tests**

The existing `webui/backend/tests/conftest.py` provides `client` (TestClient on
a temp SQLite DB) and `make_csv(...)`-style helpers — read it first and reuse
its existing fixtures/builders exactly as `test_fit_trigger.py` does (it
ingests all 3 levels of a visit). Test file:

```python
# webui/backend/tests/test_analysis_endpoint.py
"""POST /analysis/run + GET /analysis/latest: caching by fingerprint, statuses."""
from __future__ import annotations


def test_analysis_run_on_empty_db(client):
    r = client.post("/analysis/run")
    assert r.status_code == 200
    art = r.json()
    assert art["cached"] is False
    assert art["confirmatory"]["family_size_actual"] == 0
    assert all(v["status"] == "insufficient_data" for v in art["q1"].values())


def test_analysis_run_caches_by_fingerprint(client):
    first = client.post("/analysis/run").json()
    second = client.post("/analysis/run").json()
    assert first["cached"] is False and second["cached"] is True
    assert first["provenance"]["fingerprint"] == second["provenance"]["fingerprint"]


def test_analysis_latest(client):
    assert client.get("/analysis/latest").status_code == 404
    client.post("/analysis/run")
    r = client.get("/analysis/latest")
    assert r.status_code == 200
    assert r.json()["engine_version"]


def test_analysis_reruns_after_new_ingest(client, ingest_one_block):
    """Ingesting data changes the fingerprint -> a fresh (non-cached) run."""
    before = client.post("/analysis/run").json()
    ingest_one_block(participant_id="P01", visit_ordinal=1, workload_level="LOW")
    after = client.post("/analysis/run").json()
    assert after["cached"] is False
    assert after["provenance"]["fingerprint"] != before["provenance"]["fingerprint"]
```

`ingest_one_block`: add this fixture to `webui/backend/tests/conftest.py`. It
reuses the existing `sample_csv_bytes` builder fixture (already defined there —
`_build(misses=(5.0, 25.0), raw_tlx=60.0) -> bytes`) and the HTTP routes:

```python
@pytest.fixture
def ingest_one_block(client, sample_csv_bytes):
    def _ingest(participant_id="P01", visit_ordinal=1, workload_level="LOW"):
        client.post("/participants",
                    json={"id": participant_id, "enrollment_date": "2026-06-01"})
        r = client.post(
            "/ingest",
            data={"participant_id": participant_id,
                  "visit_ordinal": str(visit_ordinal),
                  "workload_level": workload_level},
            files={"file": ("run.csv", sample_csv_bytes(), "text/csv")},
        )
        assert r.status_code == 201, r.text
        return r
    return _ingest
```

- [ ] **Step 3: Run tests to verify they fail**

Run (from `webui/backend`): `~/.venvs/matb-webui/bin/python -m pytest tests/test_analysis_endpoint.py -q`
Expected: FAIL — 404 on `/analysis/run`

- [ ] **Step 4: Implement**

Append to `webui/backend/app/models.py`:

```python
class AnalysisResult(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("fingerprint", "engine_version"),)
    id: int | None = Field(default=None, primary_key=True)
    fingerprint: str = Field(index=True)            # sha256 of canonical input rows
    engine_version: str
    artifact_json: str                              # full engine artifact
    created_at: datetime = Field(default_factory=_utcnow)
```

In `webui/backend/app/routers/metrics.py`, extract the row-collection loop into
a reusable function and have the endpoint call it (keep the endpoint's output
identical — `scheduled_day` is not in these rows today; do not add it):

```python
def collect_metric_rows(session: Session, participant_id: str | None = None) -> list[dict[str, Any]]:
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


@router.get("/metrics/long")
def metrics_long(
    participant_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return collect_metric_rows(session, participant_id)
```

In `webui/backend/app/routers/fits.py`, add (below `_curve`) a slim collector —
note it deliberately omits curves (the engine needs only the parameters):

```python
def collect_fit_rows(session: Session) -> list[dict[str, Any]]:
    query = select(DepdfFit, Visit).where(DepdfFit.visit_id == Visit.id)
    return [
        {"participant_id": fit.participant_id, "visit_ordinal": visit.visit_ordinal,
         "g0": fit.g0, "p0": fit.p0, "tau0": fit.tau0}
        for fit, visit in session.exec(query).all()
    ]
```

Create `webui/backend/app/routers/analysis.py`:

```python
"""Statistics-engine endpoints. The engine itself lives in
matb_integration.analysis.stats (paper-first); this router only collects rows,
caches by input fingerprint, and persists artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models import AnalysisResult
from app.routers.fits import collect_fit_rows
from app.routers.metrics import collect_metric_rows

router = APIRouter(tags=["analysis"])


@router.post("/analysis/run")
def run_analysis_endpoint(session: Session = Depends(get_session)) -> dict[str, Any]:
    from matb_integration.analysis.stats import ENGINE_VERSION, fingerprint, run_analysis

    metric_rows = collect_metric_rows(session)
    fit_rows = collect_fit_rows(session)
    fp = fingerprint(metric_rows, fit_rows)
    existing = session.exec(
        select(AnalysisResult)
        .where(AnalysisResult.fingerprint == fp,
               AnalysisResult.engine_version == ENGINE_VERSION)
    ).first()
    if existing is not None:
        return {"cached": True, **json.loads(existing.artifact_json)}
    artifact = run_analysis(
        metric_rows, fit_rows,
        created_utc=datetime.now(timezone.utc).isoformat())
    session.add(AnalysisResult(fingerprint=fp, engine_version=ENGINE_VERSION,
                               artifact_json=json.dumps(artifact)))
    session.commit()
    return {"cached": False, **artifact}


@router.get("/analysis/latest")
def latest_analysis(session: Session = Depends(get_session)) -> dict[str, Any]:
    row = session.exec(
        select(AnalysisResult).order_by(AnalysisResult.created_at.desc(),
                                        AnalysisResult.id.desc())
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="no analysis has been run yet")
    return {"cached": True, **json.loads(row.artifact_json)}
```

In `webui/backend/app/main.py`, extend the import line and add the include:

```python
from app.routers import analysis, fits, ingest, metrics, participants, tracker  # noqa: E402
...
app.include_router(analysis.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run (from `webui/backend`): `~/.venvs/matb-webui/bin/python -m pytest -q`
Expected: ALL backend tests pass (27 previous + 4 new). The pre-existing
`/metrics/long` tests must still pass unchanged — if they fail, the
`collect_metric_rows` extraction changed behavior; fix the extraction, not the tests.

- [ ] **Step 6: Commit**

```bash
cd /root/repos/MATB
git add webui/backend
git commit -m "feat(webui): /analysis/run and /analysis/latest with fingerprint caching"
```

---

### Task 11: Frontend — types, API client, formatting helpers

**Files:**
- Modify: `webui/frontend/src/types/index.ts` (append)
- Modify: `webui/frontend/src/lib/api.ts` (append)
- Create: `webui/frontend/src/lib/format.ts`
- Test: `webui/frontend/src/lib/format.test.ts`, append to `webui/frontend/src/lib/api.test.ts`

- [ ] **Step 1: Write the failing tests**

Append to `webui/frontend/src/lib/api.test.ts` (inside the existing
`describe("api client", ...)` block, using the existing `mockFetch` helper):

```typescript
  it("runAnalysis POSTs /analysis/run", async () => {
    global.fetch = mockFetch(200, { cached: false, engine_version: "1.0.0" });
    const art = await runAnalysis();
    expect(art.cached).toBe(false);
    const [url, init] = (global.fetch as any).mock.calls[0];
    expect(url).toContain("/analysis/run");
    expect(init.method).toBe("POST");
  });

  it("getLatestAnalysis returns null on 404", async () => {
    global.fetch = mockFetch(404, { detail: "no analysis has been run yet" });
    expect(await getLatestAnalysis()).toBeNull();
  });
```

and extend the import at the top of the file:

```typescript
import { createParticipant, getTracker, ingestCsv, IngestError, getMetricsLong, getFits, runAnalysis, getLatestAnalysis } from "@/lib/api";
```

Create `webui/frontend/src/lib/format.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { fmtP, fmtNum, fmtCi } from "@/lib/format";

describe("format", () => {
  it("fmtP clamps tiny p-values and rounds", () => {
    expect(fmtP(0.0000004)).toBe("<0.001");
    expect(fmtP(0.0432)).toBe("0.043");
    expect(fmtP(null)).toBe("—");
  });
  it("fmtNum rounds to 3 significant-ish decimals", () => {
    expect(fmtNum(1.65321)).toBe("1.653");
    expect(fmtNum(null)).toBe("—");
  });
  it("fmtCi renders an interval", () => {
    expect(fmtCi([1.2345, 2.3456])).toBe("[1.234, 2.346]");
    expect(fmtCi(null)).toBe("—");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `webui/frontend`): `npm test -- --run`
Expected: FAIL — `runAnalysis` not exported; `@/lib/format` missing

- [ ] **Step 3: Implement**

Append to `webui/frontend/src/types/index.ts`:

```typescript
// --- Phase 3A analysis artifact (matches matb_integration.analysis.stats) ---

export type AnalysisStatus = "ok" | "insufficient_data" | "not_estimable";

export interface CoefRow {
  name: string;
  coef: number;
  ci95: [number, number];
  p: number;
  std_effect: number;
  standardizer: string;
  p_holm?: number;
  reject_holm?: boolean;
}

export interface LmmResult {
  status: AnalysisStatus;
  detail?: string;
  formula?: string;
  n_obs?: number;
  n_participants?: number;
  re_var?: number;
  resid_var?: number;
  omnibus?: { statistic: number; df: number; p: number; test: string };
  coefs?: CoefRow[];
  interactions?: CoefRow[];
  contrasts?: CoefRow[] | null;
  exploratory?: boolean;
}

export interface RmcorrResult {
  status: AnalysisStatus;
  detail?: string;
  r?: number;
  dof?: number;
  p?: number;
  ci95?: [number, number];
  n_pairs?: number;
  n_participants?: number;
  method?: string;
}

export interface FamilyTest {
  metric: string;
  test: "Q1_omnibus" | "Q2_visit_slope";
  p: number | null;
  p_fdr: number | null;
  reject: boolean | null;
}

export interface RmanovaResult {
  status: AnalysisStatus;
  detail?: string;
  F?: number;
  df?: [number, number];
  p?: number;
  partial_eta_sq?: number;
  complete_case_n?: number;
  note?: string;
}

export interface AnalysisArtifact {
  cached: boolean;
  engine_version: string;
  spec: string;
  provenance: {
    fingerprint: string;
    n_metric_rows: number;
    n_fit_rows: number;
    n_participants: number;
    libraries: Record<string, string>;
    created_utc: string | null;
  };
  confirmatory: {
    family_size_planned: number;
    family_size_actual: number;
    fdr_q: number;
    tests: FamilyTest[];
  };
  q1: Record<string, LmmResult>;
  q2: Record<string, LmmResult>;
  q3: { x: string; y: string; canonical: RmcorrResult; sensitivity?: RmcorrResult }[];
  q4: Record<string, LmmResult>;
  rmanova: Record<string, RmanovaResult>;
  caveats: string[];
}
```

Append to `webui/frontend/src/lib/api.ts` (and add `AnalysisArtifact` to the
type import at the top of the file):

```typescript
export async function runAnalysis(): Promise<AnalysisArtifact> {
  const res = await fetch(`${API_BASE}/analysis/run`, { method: "POST" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getLatestAnalysis(): Promise<AnalysisArtifact | null> {
  const res = await fetch(`${API_BASE}/analysis/latest`, { method: "GET" });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}
```

Create `webui/frontend/src/lib/format.ts`:

```typescript
// Numeric formatting for statistical output (manuscript-style).

export function fmtP(p: number | null | undefined): string {
  if (p == null) return "—";
  if (p < 0.001) return "<0.001";
  return p.toFixed(3);
}

export function fmtNum(x: number | null | undefined): string {
  if (x == null) return "—";
  return x.toFixed(3);
}

export function fmtCi(ci: [number, number] | null | undefined): string {
  if (!ci) return "—";
  return `[${ci[0].toFixed(3)}, ${ci[1].toFixed(3)}]`;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `webui/frontend`): `npm test -- --run` → all PASS (14 previous + 5 new)
Then: `npm run typecheck` → clean

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src/types webui/frontend/src/lib
git commit -m "feat(webui): analysis API client, artifact types, stat formatting"
```

---

### Task 12: Frontend — `/analysis` page + components

**Files:**
- Create: `webui/frontend/src/components/analysis/StatBadge.tsx`
- Create: `webui/frontend/src/components/analysis/FamilyTable.tsx`
- Create: `webui/frontend/src/components/analysis/LmmCard.tsx`
- Create: `webui/frontend/src/components/analysis/RmcorrTable.tsx`
- Modify: `webui/frontend/src/app/analysis/page.tsx` (replace placeholder)
- Modify: `webui/frontend/src/components/layout/SidebarNav.tsx` (enable the
  Analysis item — mirror exactly how the Visualization item was enabled in
  Phase 2; remove any "soon" badge)

No new unit tests in this task (presentation only; logic was tested in Task 11).
`npm run typecheck` + `npm run build` are the gates, plus live verification in Task 13.

- [ ] **Step 1: Implement components**

```tsx
// webui/frontend/src/components/analysis/StatBadge.tsx
import { cn } from "@/lib/utils";
import type { AnalysisStatus } from "@/types";

const STYLES: Record<AnalysisStatus, string> = {
  ok: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  insufficient_data: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  not_estimable: "bg-red-500/15 text-red-400 border-red-500/30",
};
const LABELS: Record<AnalysisStatus, string> = {
  ok: "ok",
  insufficient_data: "insufficient data",
  not_estimable: "not estimable",
};

export function StatBadge({ status, detail }: { status: AnalysisStatus; detail?: string }) {
  return (
    <span
      title={detail}
      className={cn("inline-block rounded-full border px-2 py-0.5 text-xs font-medium", STYLES[status])}
    >
      {LABELS[status]}
    </span>
  );
}
```

```tsx
// webui/frontend/src/components/analysis/FamilyTable.tsx
import { fmtP } from "@/lib/format";
import type { AnalysisArtifact } from "@/types";

const TEST_LABEL: Record<string, string> = {
  Q1_omnibus: "Q1 level omnibus",
  Q2_visit_slope: "Q2 visit slope",
};

export function FamilyTable({ confirmatory }: { confirmatory: AnalysisArtifact["confirmatory"] }) {
  return (
    <div className="rounded-lg border border-border">
      <div className="border-b border-border px-4 py-2 text-sm text-muted-foreground">
        Confirmatory family — BH-FDR at q = {confirmatory.fdr_q} over{" "}
        {confirmatory.family_size_actual}/{confirmatory.family_size_planned} planned tests
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="px-4 py-2">Metric</th>
            <th className="px-4 py-2">Test</th>
            <th className="px-4 py-2">p</th>
            <th className="px-4 py-2">p (FDR)</th>
            <th className="px-4 py-2">Survives</th>
          </tr>
        </thead>
        <tbody>
          {confirmatory.tests.map((t) => (
            <tr key={`${t.metric}-${t.test}`} className="border-t border-border/50">
              <td className="px-4 py-2 font-mono text-xs">{t.metric}</td>
              <td className="px-4 py-2">{TEST_LABEL[t.test] ?? t.test}</td>
              <td className="px-4 py-2">{fmtP(t.p)}</td>
              <td className="px-4 py-2">{fmtP(t.p_fdr)}</td>
              <td className="px-4 py-2">
                {t.reject == null ? "—" : t.reject ? "✓" : "✗"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

```tsx
// webui/frontend/src/components/analysis/LmmCard.tsx
import { StatBadge } from "@/components/analysis/StatBadge";
import { fmtCi, fmtNum, fmtP } from "@/lib/format";
import type { CoefRow, LmmResult } from "@/types";

function CoefTable({ rows, showHolm }: { rows: CoefRow[]; showHolm?: boolean }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-muted-foreground">
          <th className="py-1 pr-2">Term</th>
          <th className="py-1 pr-2">b</th>
          <th className="py-1 pr-2">95% CI</th>
          <th className="py-1 pr-2">std</th>
          <th className="py-1 pr-2">p</th>
          {showHolm && <th className="py-1">p (Holm)</th>}
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => (
          <tr key={c.name} className="border-t border-border/40">
            <td className="py-1 pr-2 font-mono text-xs">{c.name}</td>
            <td className="py-1 pr-2">{fmtNum(c.coef)}</td>
            <td className="py-1 pr-2">{fmtCi(c.ci95)}</td>
            <td className="py-1 pr-2">{fmtNum(c.std_effect)}</td>
            <td className="py-1 pr-2">{fmtP(c.p)}</td>
            {showHolm && <td className="py-1">{fmtP(c.p_holm)}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function LmmCard({ title, result }: { title: string; result: LmmResult }) {
  return (
    <div className="space-y-3 rounded-lg border border-border p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">
          {title}
          {result.exploratory && (
            <span className="ml-2 text-xs text-muted-foreground">(exploratory)</span>
          )}
        </h3>
        <StatBadge status={result.status} detail={result.detail} />
      </div>
      {result.status === "ok" && (
        <>
          {result.omnibus && (
            <p className="text-xs text-muted-foreground">
              Omnibus {result.omnibus.test}: χ²({result.omnibus.df}) ={" "}
              {fmtNum(result.omnibus.statistic)}, p = {fmtP(result.omnibus.p)} · n ={" "}
              {result.n_obs} obs / {result.n_participants} participants
            </p>
          )}
          {result.coefs && <CoefTable rows={result.coefs} />}
          {result.interactions && result.interactions.length > 0 && (
            <details className="text-xs text-muted-foreground">
              <summary>Interactions (secondary)</summary>
              <CoefTable rows={result.interactions} />
            </details>
          )}
          {result.contrasts && (
            <div>
              <p className="mb-1 text-xs text-muted-foreground">
                Pairwise contrasts (Holm within metric; shown because the omnibus survived FDR)
              </p>
              <CoefTable rows={result.contrasts} showHolm />
            </div>
          )}
        </>
      )}
    </div>
  );
}
```

```tsx
// webui/frontend/src/components/analysis/RmcorrTable.tsx
import { StatBadge } from "@/components/analysis/StatBadge";
import { fmtCi, fmtNum, fmtP } from "@/lib/format";
import type { AnalysisArtifact } from "@/types";

export function RmcorrTable({ q3 }: { q3: AnalysisArtifact["q3"] }) {
  return (
    <div className="rounded-lg border border-border">
      <div className="border-b border-border px-4 py-2 text-sm text-muted-foreground">
        Q3 — repeated-measures correlation (exploratory; canonical + level-adjusted sensitivity)
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="px-4 py-2">x</th>
            <th className="px-4 py-2">y</th>
            <th className="px-4 py-2">r</th>
            <th className="px-4 py-2">df</th>
            <th className="px-4 py-2">95% CI</th>
            <th className="px-4 py-2">p</th>
            <th className="px-4 py-2">r (level-adj)</th>
            <th className="px-4 py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {q3.map((e) => (
            <tr key={`${e.x}-${e.y}`} className="border-t border-border/50">
              <td className="px-4 py-2 font-mono text-xs">{e.x}</td>
              <td className="px-4 py-2 font-mono text-xs">{e.y}</td>
              <td className="px-4 py-2">{fmtNum(e.canonical.r)}</td>
              <td className="px-4 py-2">{e.canonical.dof ?? "—"}</td>
              <td className="px-4 py-2">{fmtCi(e.canonical.ci95)}</td>
              <td className="px-4 py-2">{fmtP(e.canonical.p)}</td>
              <td className="px-4 py-2">{fmtNum(e.sensitivity?.r)}</td>
              <td className="px-4 py-2">
                <StatBadge status={e.canonical.status} detail={e.canonical.detail} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Implement the page** (replace
`webui/frontend/src/app/analysis/page.tsx` entirely):

```tsx
"use client";

import { useEffect, useState } from "react";
import { Play } from "lucide-react";

import { FamilyTable } from "@/components/analysis/FamilyTable";
import { LmmCard } from "@/components/analysis/LmmCard";
import { RmcorrTable } from "@/components/analysis/RmcorrTable";
import { getLatestAnalysis, runAnalysis } from "@/lib/api";
import type { AnalysisArtifact } from "@/types";

const METRIC_LABELS: Record<string, string> = {
  sysmon_d_prime: "SYSMON d′",
  sysmon_hit_rate: "SYSMON hit rate",
  sysmon_mean_rt_ms: "SYSMON mean RT (ms)",
  comm_d_prime: "COMM d′",
  nasatlx_raw_tlx: "NASA-TLX (raw)",
  bedford: "Bedford",
  isa_mean: "ISA (mean)",
};
const Q4_LABELS: Record<string, string> = {
  g0: "G₀ (baseline MWL)", p0: "P₀ (baseline nonfailure)", tau0: "τ₀ (baseline MTTF)",
};

export default function AnalysisPage() {
  const [artifact, setArtifact] = useState<AnalysisArtifact | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getLatestAnalysis().then(setArtifact).catch((e) => setError(String(e)));
  }, []);

  async function onRun() {
    setRunning(true);
    setError(null);
    try {
      setArtifact(await runAnalysis());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Statistical analysis</h2>
          <p className="text-sm text-muted-foreground">
            Pre-specified engine (Q1–Q4) — LMM, rmcorr, rmANOVA sensitivity, BH-FDR.
          </p>
        </div>
        <button
          onClick={onRun}
          disabled={running}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          <Play className="h-4 w-4" />
          {running ? "Running…" : "Run analysis"}
        </button>
      </div>

      {error && (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-400">
          {error}
        </p>
      )}

      {!artifact && !error && (
        <div className="flex h-48 items-center justify-center rounded-lg border border-dashed border-border">
          <p className="text-muted-foreground">No analysis yet — ingest data, then run.</p>
        </div>
      )}

      {artifact && (
        <div className="space-y-8">
          <FamilyTable confirmatory={artifact.confirmatory} />

          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Q1 — workload-level effects (LMM)</h3>
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {Object.entries(artifact.q1).map(([m, r]) => (
                <LmmCard key={m} title={METRIC_LABELS[m] ?? m} result={r} />
              ))}
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Q2 — trajectories across visits (LMM)</h3>
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {Object.entries(artifact.q2).map(([m, r]) => (
                <LmmCard key={m} title={METRIC_LABELS[m] ?? m} result={r} />
              ))}
            </div>
          </section>

          <RmcorrTable q3={artifact.q3} />

          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Q4 — DEPDF parameter drift (exploratory)</h3>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {Object.entries(artifact.q4).map(([param, r]) => (
                <LmmCard key={param} title={Q4_LABELS[param] ?? param} result={r} />
              ))}
            </div>
          </section>

          <section className="space-y-2">
            <h3 className="text-sm font-semibold">rmANOVA sensitivity (descriptive)</h3>
            {Object.entries(artifact.rmanova).map(([m, r]) => (
              <p key={m} className="text-sm text-muted-foreground">
                <span className="font-mono text-xs">{METRIC_LABELS[m] ?? m}</span>{" "}
                {r.status === "ok"
                  ? `F(${r.df?.[0]}, ${r.df?.[1]}) = ${r.F?.toFixed(2)}, p = ${
                      r.p != null && r.p < 0.001 ? "<0.001" : r.p?.toFixed(3)
                    }, partial η² = ${r.partial_eta_sq?.toFixed(3)} (n=${r.complete_case_n})`
                  : `${r.status}${r.detail ? ` — ${r.detail}` : ""}`}
              </p>
            ))}
          </section>

          <footer className="space-y-1 rounded-lg border border-border p-4 text-xs text-muted-foreground">
            <p>
              Engine v{artifact.engine_version} · fingerprint{" "}
              <span className="font-mono">{artifact.provenance.fingerprint.slice(0, 12)}…</span> ·{" "}
              {artifact.provenance.n_metric_rows} metric rows · {artifact.provenance.n_fit_rows}{" "}
              fits · {artifact.provenance.n_participants} participants ·{" "}
              {Object.entries(artifact.provenance.libraries)
                .map(([k, v]) => `${k} ${v}`)
                .join(" · ")}
            </p>
            <ul className="list-inside list-disc">
              {artifact.caveats.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </footer>
        </div>
      )}
    </div>
  );
}
```

Then enable the sidebar item in `SidebarNav.tsx` (mirror the Visualization
enabling from Phase 2 — flip the Analysis entry from disabled/"soon" to a live
link to `/analysis`).

- [ ] **Step 3: Typecheck + build + unit tests**

Run (from `webui/frontend`):
- `npm run typecheck` → clean
- `npm test -- --run` → all pass
- `npm run build` → succeeds (after the build, `git checkout -- tsconfig.json`
  if Next.js rewrote `jsx` to `preserve`)

- [ ] **Step 4: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src
git commit -m "feat(webui): /analysis page rendering the Phase 3A artifact"
```

---

### Task 13: Live end-to-end verification + docs

**Files:**
- Modify: `README.md` (Phase 3A status + CLI usage)
- Modify: `webui/backend/README.md` (new endpoints)
- Modify: `webui/frontend/README.md` (Analysis screen)
- Modify: `CHANGELOG.md` ([Unreleased] entry)

- [ ] **Step 1: Live backend verification** (controller does this, not a subagent)

Start the backend on a scratch DB, ingest a synthetic full participant (reuse
the Phase 2 e2e CSV generation approach from session history), then:

```bash
curl -s -X POST localhost:8000/analysis/run | python3 -m json.tool | head -40
curl -s -X POST localhost:8000/analysis/run | python3 -c "import json,sys; print(json.load(sys.stdin)['cached'])"   # True
curl -s localhost:8000/analysis/latest | python3 -c "import json,sys; a=json.load(sys.stdin); print(a['engine_version'], a['provenance']['fingerprint'][:12])"
```

Expected: first run `cached: false` with statuses populated (small ingests will
legitimately show `insufficient_data` — that is correct gate behavior, not a bug);
second run `cached: true`; latest returns the artifact.

- [ ] **Step 2: Live CLI verification**

```bash
cd /root/repos/MATB
curl -s localhost:8000/metrics/long > /tmp/m.json
curl -s localhost:8000/fits > /tmp/f.json
~/.venvs/matb-webui/bin/python -m matb_integration.analysis.stats.cli run \
  --metrics-json /tmp/m.json --fits-json /tmp/f.json -o /root/repos/exports/2026-06-03_analysis_phase3a-smoke.json
```

Expected: artifact written; its fingerprint equals the backend run's fingerprint.

- [ ] **Step 3: Live frontend verification**

`npm run dev` (port 3100) → Playwright: open `/analysis`, click **Run analysis**,
verify the family table + Q1–Q4 sections render with status badges; check the
console for errors.

- [ ] **Step 4: Update docs**

- `README.md`: mark Phase 3A done in the roadmap/status table; add the CLI
  one-liner and the two endpoints to the run instructions.
- `webui/backend/README.md`: add `POST /analysis/run` and `GET /analysis/latest`
  to the endpoint list; mention fingerprint caching.
- `webui/frontend/README.md`: replace the "Analysis — Phase 3 placeholder"
  bullet with the real screen description.
- `CHANGELOG.md`: add a Phase 3A entry under `[Unreleased]`.

- [ ] **Step 5: Full test sweep + commit**

```bash
cd /root/repos/MATB && ~/.venvs/matb-webui/bin/python -m pytest tests -q
cd webui/backend && ~/.venvs/matb-webui/bin/python -m pytest -q
cd ../frontend && npm test -- --run && npm run typecheck
cd /root/repos/MATB
git add README.md CHANGELOG.md webui/backend/README.md webui/frontend/README.md
git commit -m "docs: Phase 3A statistics engine status, endpoints, CLI usage"
```

---

## Self-review notes

- Spec coverage: §1 (Tasks 1, 9, 10), §2 (Tasks 5–7), §3 (Tasks 3, 8), §4
  (Tasks 2, 5–8), §5 (Tasks 5, 6), §6 (Tasks 4–6 oracles), §8/§9 (Tasks 10–13).
  §7 (Bayesian) is Phase 3B — explicitly out of this plan.
- Oracle values in Task 6 were generated and verified on this machine
  (pingouin 0.6.1, 2026-06-03) before the plan was written; the MixedLM
  recovery values in Task 5 were verified interactively on the target venv.
- The engine treats a shrunken FDR family (some tests un-estimable) by
  correcting over the available tests and recording planned vs actual sizes —
  this is the documented pre-specified behavior (Task 8 docstring).
