# Phase 3B — Async Bayesian Sensitivity (PyMC) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bayesian hierarchical re-fits of Q2 (trajectories) and Q4 (DEPDF drift) as an async console job with full reproducibility diagnostics, per spec §7 (pinned 2026-06-04).

**Architecture:** Library `matb_integration/analysis/stats/bayes.py` (PyMC NUTS, pinned priors, 95% ETI, gates reused) → CLI `bayes` subcommand → backend `bayes_result` job table + `POST /analysis/bayes/run` (background thread) + `GET /analysis/bayes/status` → frontend Bayesian section on `/analysis` with polling. **Separate artifact + version (`BAYES_VERSION`)** — never extends the frequentist artifact (cache-staleness guard).

**Tech Stack:** pymc 6.0.1 + arviz 1.1.0 (verified working on the py3.14 venv 2026-06-04: sampling ~1 s/model at study size; `az.summary(..., ci_prob=0.95)` yields columns `mean, sd, eti95_lb, eti95_ub, ess_bulk, ess_tail, r_hat`; divergences via `idata.sample_stats["diverging"].sum()`; **`cores=1` mandatory** — job runs in a worker thread, no nested multiprocessing).

**Conventions:** identical to the Phase 3A plan — library tests from repo root with `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats -q`; backend from `webui/backend`; frontend `npm test -- --run` + `npm run typecheck`; commits without AI co-author lines (Diego sole author).

**File map (final state):**

```
matb_integration/analysis/stats/bayes.py      # run_bayes + per-model fits
matb_integration/analysis/stats/cli.py        # + bayes subcommand
tests/analysis_stats/test_bayes.py
tests/analysis_stats/test_cli.py              # + 1 bayes CLI test
webui/backend/requirements.txt                # + pymc
webui/backend/app/models.py                   # + BayesResult job table
webui/backend/app/routers/analysis.py         # + bayes endpoints + thread runner
webui/backend/tests/test_bayes_endpoint.py
webui/frontend/src/types/index.ts             # + Bayes types
webui/frontend/src/lib/api.ts                 # + runBayes, getBayesStatus
webui/frontend/src/lib/api.test.ts            # + 2 tests
webui/frontend/src/components/analysis/BayesSection.tsx
webui/frontend/src/app/analysis/page.tsx      # + <BayesSection />
```

---

### Task 1: Bayesian library module (`bayes.py`)

**Files:**
- Create: `matb_integration/analysis/stats/bayes.py`
- Test: `tests/analysis_stats/test_bayes.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/analysis_stats/test_bayes.py
from __future__ import annotations

import json

import pytest

from matb_integration.analysis.stats.bayes import BAYES_VERSION, run_bayes

from .conftest import simulate_metric_rows

# Small but real sampling: keep draws low so the suite stays fast (seeded).
FAST = {"draws": 300, "tune": 300, "chains": 2}


def test_bayes_q2_recovers_known_effects(sim_fits):
    rows = simulate_metric_rows("sysmon_d_prime", seed=42)
    art = run_bayes(rows, sim_fits, seed=20260604, **FAST,
                    created_utc="2026-06-04T00:00:00+00:00")
    assert art["bayes_version"] == BAYES_VERSION
    q2 = art["q2"]["sysmon_d_prime"]
    assert q2["status"] == "ok"
    # truth: visit slope -0.05, MEDIUM-LOW 0.8, HIGH-LOW 1.6 (posterior means)
    assert q2["coefs"]["b_visit"]["mean"] == pytest.approx(-0.05, abs=0.05)
    assert q2["coefs"]["b_med"]["mean"] == pytest.approx(0.8, abs=0.2)
    assert q2["coefs"]["b_high"]["mean"] == pytest.approx(1.6, abs=0.25)
    lo, hi = q2["coefs"]["b_visit"]["eti95"]
    assert lo < q2["coefs"]["b_visit"]["mean"] < hi
    d = q2["diagnostics"]
    assert set(d) == {"max_r_hat", "min_ess_bulk", "divergences"}
    assert isinstance(q2["converged"], bool)
    # Q4 on the drifting-g0 fixture
    q4 = art["q4"]["g0"]
    assert q4["status"] == "ok"
    assert q4["coefs"]["b_visit"]["mean"] == pytest.approx(0.5, abs=0.15)
    # sampler config + provenance persisted (spec section 7)
    s = art["sampler"]
    assert s["seed"] == 20260604 and s["chains"] == 2 and s["draws"] == 300 and s["tune"] == 300
    assert s["interval"] == "95% ETI"
    assert "Normal(0, 2.5*sd(y))" in s["priors"]["coefficients"]
    assert "HalfNormal(sd(y))" in s["priors"]["sds"]
    assert {"pymc", "arviz", "numpy", "pandas"} <= set(art["provenance"]["libraries"])
    assert len(art["provenance"]["fingerprint"]) == 64
    json.dumps(art)  # JSON-serializable


def test_bayes_insufficient_and_empty():
    rows = simulate_metric_rows("bedford", seed=7, n_participants=2)
    art = run_bayes(rows, [], **FAST)
    assert art["q2"]["bedford"]["status"] == "insufficient_data"
    assert all(v["status"] == "insufficient_data" for v in art["q4"].values())
    empty = run_bayes([], [], **FAST)
    assert all(v["status"] == "insufficient_data" for v in empty["q2"].values())


def test_bayes_seed_reproducibility(sim_fits):
    rows = simulate_metric_rows("nasatlx_raw_tlx", seed=43)
    a = run_bayes(rows, [], seed=11, draws=200, tune=200, chains=2)
    b = run_bayes(rows, [], seed=11, draws=200, tune=200, chains=2)
    assert a["q2"]["nasatlx_raw_tlx"]["coefs"]["b_visit"]["mean"] == \
        b["q2"]["nasatlx_raw_tlx"]["coefs"]["b_visit"]["mean"]
```

- [ ] **Step 2: Run to verify FAIL**

`~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats/test_bayes.py -q` → ModuleNotFoundError

- [ ] **Step 3: Implement**

```python
# matb_integration/analysis/stats/bayes.py
"""Bayesian sensitivity re-fits for Q2/Q4 (spec section 7, Phase 3B).

NUTS via PyMC with pinned weakly-informative priors: coefficients
Normal(0, 2.5*sd(y)); group and residual SDs HalfNormal(sd(y)). Intervals are
95% equal-tailed (ETI; arviz 1.x). Convergence: max R-hat <= 1.01 AND zero
divergences. cores=1 always — the console runs this inside a worker thread.

This artifact is SEPARATE from the frequentist engine artifact and carries its
own BAYES_VERSION; bump it on any model/prior/schema change.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from . import gates
from .data import CONFIRMATORY_METRICS, fingerprint, fits_frame, metrics_frame

BAYES_VERSION = "1.0.0"
SPEC = "docs/superpowers/specs/2026-06-03-webui-phase3-statistics-design.md"
DEFAULT_SEED = 20260604
RHAT_MAX = 1.01
PRIORS = {
    "coefficients": "Normal(0, 2.5*sd(y))",
    "sds": "HalfNormal(sd(y)) for sigma_u (participant) and sigma_e (residual)",
}
CAVEATS = [
    "Bayesian sensitivity re-fit of Q2/Q4 only; the frequentist artifact is primary.",
    "95% intervals are equal-tailed (ETI), not HDI.",
    "'not converged' (R-hat > 1.01 or any divergence) means the posterior summary "
    "is unreliable and must not be reported.",
]


def _fit_one(df: pd.DataFrame, *, include_levels: bool, seed: int, draws: int,
             tune: int, chains: int) -> dict[str, Any]:
    """One hierarchical fit: y ~ b0 + b_visit*visit_c (+ level indicators)
    + u[participant] + eps. df needs columns participant_id, visit_c, value
    (+ workload_level when include_levels)."""
    import arviz as az
    import pymc as pm

    pid_codes, uniques = pd.factorize(df["participant_id"])
    y = df["value"].to_numpy(dtype=float)
    x = df["visit_c"].to_numpy(dtype=float)
    sd_y = float(np.std(y)) or 1.0
    var_names = ["b0", "b_visit"]
    with pm.Model():
        b0 = pm.Normal("b0", 0.0, 2.5 * sd_y)
        b_visit = pm.Normal("b_visit", 0.0, 2.5 * sd_y)
        mu = b0 + b_visit * x
        if include_levels:
            med = (df["workload_level"] == "MEDIUM").to_numpy(dtype=float)
            high = (df["workload_level"] == "HIGH").to_numpy(dtype=float)
            b_med = pm.Normal("b_med", 0.0, 2.5 * sd_y)
            b_high = pm.Normal("b_high", 0.0, 2.5 * sd_y)
            mu = mu + b_med * med + b_high * high
            var_names += ["b_med", "b_high"]
        sigma_u = pm.HalfNormal("sigma_u", sd_y)
        sigma_e = pm.HalfNormal("sigma_e", sd_y)
        u = pm.Normal("u", 0.0, sigma_u, shape=len(uniques))
        pm.Normal("y", mu + u[pid_codes], sigma_e, observed=y)
        idata = pm.sample(draws=draws, tune=tune, chains=chains, cores=1,
                          random_seed=seed, progressbar=False,
                          compute_convergence_checks=False)
    var_names += ["sigma_u", "sigma_e"]
    summ = az.summary(idata, var_names=var_names, ci_prob=0.95)
    divergences = int(idata.sample_stats["diverging"].sum())
    coefs: dict[str, Any] = {}
    for name in var_names:
        row = summ.loc[name]
        coefs[name] = {
            "mean": float(row["mean"]), "sd": float(row["sd"]),
            "eti95": [float(row["eti95_lb"]), float(row["eti95_ub"])],
            "r_hat": float(row["r_hat"]),
            "ess_bulk": float(row["ess_bulk"]), "ess_tail": float(row["ess_tail"]),
        }
    max_r_hat = float(summ["r_hat"].max())
    return {
        "status": "ok",
        "n_obs": int(len(df)), "n_participants": int(len(uniques)),
        "coefs": coefs,
        "diagnostics": {"max_r_hat": max_r_hat,
                        "min_ess_bulk": float(summ["ess_bulk"].min()),
                        "divergences": divergences},
        "converged": bool(max_r_hat <= RHAT_MAX and divergences == 0),
    }


def _guarded(df: pd.DataFrame, gate_reason: str | None, **kw) -> dict[str, Any]:
    if gate_reason:
        return {"status": "insufficient_data", "detail": gate_reason}
    try:
        return _fit_one(df, **kw)
    except Exception as e:  # noqa: BLE001 — statuses are first-class
        return {"status": "not_estimable", "detail": f"{type(e).__name__}: {e}"}


def run_bayes(metrics_rows: list[dict[str, Any]], fits_rows: list[dict[str, Any]],
              *, seed: int = DEFAULT_SEED, draws: int = 1000, tune: int = 1000,
              chains: int = 4, created_utc: str | None = None) -> dict[str, Any]:
    metrics_rows, fits_rows = list(metrics_rows), list(fits_rows)
    mdf, fdf = metrics_frame(metrics_rows), fits_frame(fits_rows)
    kw = {"seed": seed, "draws": draws, "tune": tune, "chains": chains}

    q2 = {}
    for m in CONFIRMATORY_METRICS:
        d = mdf[mdf["metric"] == m]
        q2[m] = _guarded(d, gates.gate_q2(d), include_levels=True, **kw)
    q4 = {}
    for param in ("g0", "p0", "tau0"):
        d = fdf.rename(columns={param: "value"})
        q4[param] = _guarded(d, gates.gate_q4(fdf), include_levels=False, **kw)

    fitted = [r for r in list(q2.values()) + list(q4.values()) if r["status"] == "ok"]
    return {
        "bayes_version": BAYES_VERSION, "spec": SPEC,
        "sampler": {"seed": seed, "chains": chains, "draws": draws, "tune": tune,
                    "nuts": "pymc", "cores": 1, "interval": "95% ETI",
                    "priors": dict(PRIORS)},
        "provenance": {
            "fingerprint": fingerprint(metrics_rows, fits_rows),
            "n_metric_rows": len(metrics_rows), "n_fit_rows": len(fits_rows),
            "libraries": _libraries(), "created_utc": created_utc,
        },
        "q2": q2, "q4": q4,
        "all_converged": bool(fitted) and all(r["converged"] for r in fitted),
        "caveats": list(CAVEATS),
    }


def _libraries() -> dict[str, str]:
    import arviz
    import numpy
    import pymc
    return {"pymc": pymc.__version__, "arviz": arviz.__version__,
            "numpy": numpy.__version__, "pandas": pd.__version__}
```

- [ ] **Step 4: Run to verify PASS**

`~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats/test_bayes.py -q` → 3 pass
(expect ~30–60 s: several real NUTS runs). Then the whole stats suite:
`~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats -q` → 39 pass.

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/analysis/stats/bayes.py tests/analysis_stats/test_bayes.py
git commit -m "feat(stats): Bayesian Q2/Q4 sensitivity with pinned priors and ETI diagnostics"
```

---

### Task 2: CLI `bayes` subcommand

**Files:**
- Modify: `matb_integration/analysis/stats/cli.py`
- Test: append to `tests/analysis_stats/test_cli.py`

- [ ] **Step 1: failing test** (append)

```python
def test_cli_bayes_writes_artifact(tmp_path, sim_study, sim_fits):
    m = tmp_path / "metrics.json"
    f = tmp_path / "fits.json"
    out = tmp_path / "bayes.json"
    # one confirmatory metric only -> a single sampled model keeps this fast
    rows = [r for r in sim_study if r["metric"] == "sysmon_d_prime"]
    m.write_text(json.dumps(rows))
    f.write_text(json.dumps([]))
    rc = main(["bayes", "--metrics-json", str(m), "--fits-json", str(f),
               "-o", str(out), "--draws", "200", "--tune", "200", "--chains", "2"])
    assert rc == 0
    art = json.loads(out.read_text())
    assert art["bayes_version"]
    assert art["sampler"]["draws"] == 200
    assert art["q2"]["sysmon_d_prime"]["status"] == "ok"
```

- [ ] **Step 2:** run → FAIL (argparse: invalid choice 'bayes')

- [ ] **Step 3: Implement.** In `cli.py`, after the `run` subparser block, add:

```python
    bayes = sub.add_parser("bayes", help="run the Bayesian Q2/Q4 sensitivity")
    bayes.add_argument("--metrics-json", required=True, type=Path)
    bayes.add_argument("--fits-json", required=True, type=Path)
    bayes.add_argument("-o", "--output", required=True, type=Path)
    bayes.add_argument("--seed", type=int, default=20260604)
    bayes.add_argument("--draws", type=int, default=1000)
    bayes.add_argument("--tune", type=int, default=1000)
    bayes.add_argument("--chains", type=int, default=4)
```

and branch on the command (refactor the existing body minimally):

```python
    metrics = json.loads(args.metrics_json.read_text())
    fits = json.loads(args.fits_json.read_text())
    now = datetime.now(timezone.utc).isoformat()
    if args.cmd == "run":
        artifact = run_analysis(metrics, fits, created_utc=now)
    else:
        from .bayes import run_bayes
        artifact = run_bayes(metrics, fits, seed=args.seed, draws=args.draws,
                             tune=args.tune, chains=args.chains, created_utc=now)
    args.output.write_text(json.dumps(artifact, indent=2))
    print(f"wrote {args.output}")
    return 0
```

- [ ] **Step 4:** `~/.venvs/matb-webui/bin/python -m pytest tests/analysis_stats -q` → 40 pass

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/analysis/stats/cli.py tests/analysis_stats/test_cli.py
git commit -m "feat(stats): bayes CLI subcommand"
```

---

### Task 3: Backend — `BayesResult` job table + async endpoints

**Files:**
- Modify: `webui/backend/requirements.txt` (append `pymc>=6` under the stats block)
- Modify: `webui/backend/app/models.py` (append)
- Modify: `webui/backend/app/routers/analysis.py` (append)
- Test: `webui/backend/tests/test_bayes_endpoint.py`

- [ ] **Step 1: failing tests**

```python
# webui/backend/tests/test_bayes_endpoint.py
"""Async Bayesian job lifecycle: queued -> running -> done; caching; status."""
from __future__ import annotations

import time


def _wait_done(client, timeout_s: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        body = client.get("/analysis/bayes/status").json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.2)
    raise AssertionError(f"job not finished in {timeout_s}s: {body}")


def test_bayes_status_404_before_any_job(client):
    assert client.get("/analysis/bayes/status").status_code == 404


def test_bayes_job_on_empty_db_completes(client):
    r = client.post("/analysis/bayes/run?draws=50&tune=50&chains=2")
    assert r.status_code == 202
    assert r.json()["status"] in ("queued", "running")
    body = _wait_done(client)
    assert body["status"] == "done"
    art = body["artifact"]
    assert art["bayes_version"]
    # empty DB -> every model gated out; nothing sampled
    assert all(v["status"] == "insufficient_data" for v in art["q2"].values())
    assert all(v["status"] == "insufficient_data" for v in art["q4"].values())


def test_bayes_cached_by_fingerprint(client):
    client.post("/analysis/bayes/run?draws=50&tune=50&chains=2")
    _wait_done(client)
    r = client.post("/analysis/bayes/run?draws=50&tune=50&chains=2")
    assert r.status_code == 200          # cached completed artifact, no new job
    assert r.json()["cached"] is True and r.json()["status"] == "done"
```

Run (from `webui/backend`): `~/.venvs/matb-webui/bin/python -m pytest tests/test_bayes_endpoint.py -q` → FAIL (404 on POST).

- [ ] **Step 2: Implement.** Append to `webui/backend/app/models.py`:

```python
class BayesResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    fingerprint: str = Field(index=True)            # input rows at job creation
    bayes_version: str
    status: str = "queued"                          # queued|running|done|failed
    artifact_json: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None
```

Append to `webui/backend/app/routers/analysis.py` (note: the worker thread must
use the SAME engine as the request session — derive it via `session.get_bind()`
so tests' in-memory StaticPool engine is honored):

```python
import threading


def _bayes_worker(engine, job_id: int, metric_rows, fit_rows,
                  seed: int, draws: int, tune: int, chains: int) -> None:
    from matb_integration.analysis.stats.bayes import run_bayes

    from app.models import BayesResult as BR

    def _update(**fields) -> None:
        with Session(engine) as s:
            row = s.get(BR, job_id)
            for k, v in fields.items():
                setattr(row, k, v)
            s.add(row)
            s.commit()

    _update(status="running")
    try:
        artifact = run_bayes(metric_rows, fit_rows, seed=seed, draws=draws,
                             tune=tune, chains=chains,
                             created_utc=datetime.now(timezone.utc).isoformat())
        _update(status="done", artifact_json=json.dumps(artifact),
                finished_at=datetime.now(timezone.utc))
    except Exception as e:  # noqa: BLE001 — job must record its own failure
        _update(status="failed", error=f"{type(e).__name__}: {e}",
                finished_at=datetime.now(timezone.utc))


@router.post("/analysis/bayes/run", status_code=202)
def run_bayes_endpoint(
    response: Response,
    seed: int = 20260604, draws: int = 1000, tune: int = 1000, chains: int = 4,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from matb_integration.analysis.stats import fingerprint
    from matb_integration.analysis.stats.bayes import BAYES_VERSION

    from app.models import BayesResult

    metric_rows = collect_metric_rows(session)
    fit_rows = collect_fit_rows(session)
    fp = fingerprint(metric_rows, fit_rows)
    done = session.exec(
        select(BayesResult).where(BayesResult.fingerprint == fp,
                                  BayesResult.bayes_version == BAYES_VERSION,
                                  BayesResult.status == "done")
        .order_by(BayesResult.id.desc())
    ).first()
    if done is not None:
        response.status_code = 200
        return {"job_id": done.id, "status": "done", "cached": True,
                "artifact": json.loads(done.artifact_json)}
    active = session.exec(
        select(BayesResult).where(BayesResult.fingerprint == fp,
                                  BayesResult.bayes_version == BAYES_VERSION,
                                  BayesResult.status.in_(("queued", "running")))  # type: ignore[attr-defined]
    ).first()
    if active is not None:
        response.status_code = 200
        return {"job_id": active.id, "status": active.status, "cached": False}
    row = BayesResult(fingerprint=fp, bayes_version=BAYES_VERSION)
    session.add(row)
    session.commit()
    session.refresh(row)
    engine = session.get_bind()
    threading.Thread(
        target=_bayes_worker,
        args=(engine, row.id, metric_rows, fit_rows, seed, draws, tune, chains),
        daemon=True,
    ).start()
    return {"job_id": row.id, "status": "queued", "cached": False}


@router.get("/analysis/bayes/status")
def bayes_status(session: Session = Depends(get_session)) -> dict[str, Any]:
    from app.models import BayesResult

    row = session.exec(
        select(BayesResult).order_by(BayesResult.id.desc())
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="no Bayesian job yet")
    out: dict[str, Any] = {
        "job_id": row.id, "status": row.status, "error": row.error,
        "created_at": row.created_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }
    if row.status == "done" and row.artifact_json:
        out["artifact"] = json.loads(row.artifact_json)
    return out
```

Required import changes at the top of `analysis.py`: add `Response` to the
fastapi import (`from fastapi import APIRouter, Depends, HTTPException, Response`).
Append to `webui/backend/requirements.txt` under the stats block:

```
pymc>=6
```

- [ ] **Step 3:** from `webui/backend`: `~/.venvs/matb-webui/bin/python -m pytest -q` → 34 pass (31 + 3 new). If the lifecycle test hangs, the worker thread isn't sharing the test engine — verify `session.get_bind()` is passed, not `get_engine()`.

- [ ] **Step 4: Commit**

```bash
cd /root/repos/MATB
git add webui/backend
git commit -m "feat(webui): async Bayesian job endpoints with BayesResult lifecycle"
```

---

### Task 4: Frontend — types + API client

**Files:**
- Modify: `webui/frontend/src/types/index.ts` (append)
- Modify: `webui/frontend/src/lib/api.ts` (append; extend type import)
- Modify: `webui/frontend/src/lib/api.test.ts` (+2 tests)

- [ ] **Step 1: failing tests** (append inside `describe("api client")`; extend the import with `runBayes, getBayesStatus`):

```typescript
  it("runBayes POSTs /analysis/bayes/run", async () => {
    global.fetch = mockFetch(202, { job_id: 1, status: "queued", cached: false });
    const job = await runBayes();
    expect(job.status).toBe("queued");
    const [url, init] = (global.fetch as any).mock.calls[0];
    expect(url).toContain("/analysis/bayes/run");
    expect(init.method).toBe("POST");
  });

  it("getBayesStatus returns null on 404", async () => {
    global.fetch = mockFetch(404, { detail: "no Bayesian job yet" });
    expect(await getBayesStatus()).toBeNull();
  });
```

- [ ] **Step 2: Implement.** Append to `types/index.ts`:

```typescript
// --- Phase 3B Bayesian sensitivity (matb_integration.analysis.stats.bayes) ---

export interface BayesCoef {
  mean: number;
  sd: number;
  eti95: [number, number];
  r_hat: number;
  ess_bulk: number;
  ess_tail: number;
}

export interface BayesModelResult {
  status: AnalysisStatus;
  detail?: string;
  n_obs?: number;
  n_participants?: number;
  coefs?: Record<string, BayesCoef>;
  diagnostics?: { max_r_hat: number; min_ess_bulk: number; divergences: number };
  converged?: boolean;
}

export interface BayesArtifact {
  bayes_version: string;
  spec: string;
  sampler: {
    seed: number; chains: number; draws: number; tune: number;
    nuts: string; cores: number; interval: string;
    priors: Record<string, string>;
  };
  provenance: {
    fingerprint: string;
    n_metric_rows: number;
    n_fit_rows: number;
    libraries: Record<string, string>;
    created_utc: string | null;
  };
  q2: Record<string, BayesModelResult>;
  q4: Record<string, BayesModelResult>;
  all_converged: boolean;
  caveats: string[];
}

export interface BayesJob {
  job_id: number;
  status: "queued" | "running" | "done" | "failed";
  cached?: boolean;
  error?: string | null;
  created_at?: string;
  finished_at?: string | null;
  artifact?: BayesArtifact;
}
```

Append to `lib/api.ts` (add `BayesJob` to the type import):

```typescript
export async function runBayes(): Promise<BayesJob> {
  const res = await fetch(`${API_BASE}/analysis/bayes/run`, { method: "POST" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getBayesStatus(): Promise<BayesJob | null> {
  const res = await fetch(`${API_BASE}/analysis/bayes/status`, { method: "GET" });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}
```

- [ ] **Step 3:** `npm test -- --run` → 21 pass; `npm run typecheck` → clean

- [ ] **Step 4: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src
git commit -m "feat(webui): Bayesian job API client and types"
```

---

### Task 5: Frontend — `BayesSection` + page integration

**Files:**
- Create: `webui/frontend/src/components/analysis/BayesSection.tsx`
- Modify: `webui/frontend/src/app/analysis/page.tsx`

Presentation only — gates are typecheck + tests + build (and Task 6 live e2e).

- [ ] **Step 1: Implement the component**

```tsx
// webui/frontend/src/components/analysis/BayesSection.tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FlaskConical } from "lucide-react";

import { StatBadge } from "@/components/analysis/StatBadge";
import { getBayesStatus, runBayes } from "@/lib/api";
import { fmtNum } from "@/lib/format";
import type { BayesJob, BayesModelResult } from "@/types";

const POLL_MS = 2000;

function BayesCard({ title, result }: { title: string; result: BayesModelResult }) {
  return (
    <div className="space-y-2 rounded-lg border border-border p-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium">{title}</h4>
        <div className="flex items-center gap-2">
          {result.status === "ok" && result.converged === false && (
            <span className="rounded-full border border-red-500/30 bg-red-500/15 px-2 py-0.5 text-xs font-medium text-red-400">
              not converged
            </span>
          )}
          <StatBadge status={result.status} detail={result.detail} />
        </div>
      </div>
      {result.status === "ok" && result.coefs && (
        <>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="py-1 pr-2">Param</th>
                <th className="py-1 pr-2">mean</th>
                <th className="py-1 pr-2">95% ETI</th>
                <th className="py-1 pr-2">R̂</th>
                <th className="py-1">ESS</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(result.coefs).map(([name, c]) => (
                <tr key={name} className="border-t border-border/40">
                  <td className="py-1 pr-2 font-mono text-xs">{name}</td>
                  <td className="py-1 pr-2">{fmtNum(c.mean)}</td>
                  <td className="py-1 pr-2">
                    [{fmtNum(c.eti95[0])}, {fmtNum(c.eti95[1])}]
                  </td>
                  <td className="py-1 pr-2">{c.r_hat.toFixed(3)}</td>
                  <td className="py-1">{Math.round(c.ess_bulk)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {result.diagnostics && (
            <p className="text-xs text-muted-foreground">
              max R̂ {result.diagnostics.max_r_hat.toFixed(3)} · min ESS{" "}
              {Math.round(result.diagnostics.min_ess_bulk)} · divergences{" "}
              {result.diagnostics.divergences}
            </p>
          )}
        </>
      )}
    </div>
  );
}

const METRIC_LABELS: Record<string, string> = {
  sysmon_d_prime: "SYSMON d′",
  nasatlx_raw_tlx: "NASA-TLX (raw)",
  bedford: "Bedford",
  g0: "G₀", p0: "P₀", tau0: "τ₀",
};

export function BayesSection() {
  const [job, setJob] = useState<BayesJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (timer.current) { clearInterval(timer.current); timer.current = null; }
  }, []);

  const poll = useCallback(async () => {
    try {
      const s = await getBayesStatus();
      setJob(s);
      if (!s || s.status === "done" || s.status === "failed") stopPolling();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      stopPolling();
    }
  }, [stopPolling]);

  useEffect(() => {
    poll();
    return stopPolling;
  }, [poll, stopPolling]);

  async function onRun() {
    setError(null);
    try {
      const j = await runBayes();
      setJob(j);
      if (j.status === "queued" || j.status === "running") {
        stopPolling();
        timer.current = setInterval(poll, POLL_MS);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const running = job?.status === "queued" || job?.status === "running";
  const art = job?.status === "done" ? job.artifact : undefined;

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">
            Bayesian sensitivity (Q2/Q4 — PyMC, async)
          </h3>
          <p className="text-xs text-muted-foreground">
            Hierarchical NUTS re-fit with pre-specified priors; separate artifact.
          </p>
        </div>
        <button
          onClick={onRun}
          disabled={running}
          className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50"
        >
          <FlaskConical className="h-4 w-4" />
          {running ? `Job ${job?.status}…` : "Run Bayesian sensitivity"}
        </button>
      </div>

      {error && (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-400">
          {error}
        </p>
      )}
      {job?.status === "failed" && (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-400">
          Job failed: {job.error}
        </p>
      )}
      {!job && !error && (
        <p className="text-sm text-muted-foreground">No Bayesian job yet.</p>
      )}

      {art && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            {Object.entries(art.q2).map(([m, r]) => (
              <BayesCard key={m} title={`Q2 · ${METRIC_LABELS[m] ?? m}`} result={r} />
            ))}
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {Object.entries(art.q4).map(([p, r]) => (
              <BayesCard key={p} title={`Q4 · ${METRIC_LABELS[p] ?? p}`} result={r} />
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            Sampler: seed {art.sampler.seed} · {art.sampler.chains} chains ·{" "}
            {art.sampler.draws} draws / {art.sampler.tune} tune · priors:{" "}
            {art.sampler.priors.coefficients}; {art.sampler.priors.sds} ·{" "}
            {Object.entries(art.provenance.libraries).map(([k, v]) => `${k} ${v}`).join(" · ")}
          </p>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Integrate.** In `src/app/analysis/page.tsx`: import
`{ BayesSection } from "@/components/analysis/BayesSection";` and render
`<BayesSection />` directly after the rmANOVA `</section>` (before the
provenance `<footer>`), inside the `{artifact && (...)}` block — Bayesian
sensitivity is meaningless before a frequentist run, so it only shows once an
artifact exists.

- [ ] **Step 3:** `npm run typecheck` → clean; `npm test -- --run` → 21 pass;
`npm run build` → succeeds (then `git checkout -- tsconfig.json` if Next rewrote it; never commit `.next/`).

- [ ] **Step 4: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src
git commit -m "feat(webui): Bayesian sensitivity section with async job polling"
```

---

### Task 6: Live e2e + docs (controller-run)

**Files:**
- Modify: `README.md`, `webui/backend/README.md`, `webui/frontend/README.md`, `CHANGELOG.md`

- [ ] **Step 1: Live backend e2e** — restore the Phase 3A gate-crossing cohort DB
(`/root/repos/exports/2026-06-04_db_phase3a-e2e-cohort.db` → copy to
`webui/backend/matb_webui.db` after backing up the current one), start uvicorn,
then: `POST /analysis/bayes/run?draws=300&tune=300&chains=2` → poll
`GET /analysis/bayes/status` until `done`; assert q2.sysmon_d_prime ok +
converged with b_visit posterior consistent with the frequentist slope (+0.127);
q4 all ok; re-POST returns 200 cached. Run the CLI `bayes` subcommand on the
same `/metrics/long`//`fits` dumps and confirm fingerprint parity.

- [ ] **Step 2: Live frontend** — `npm run dev`, Playwright on `/analysis`:
click "Run Bayesian sensitivity", watch status transition to done, verify Q2/Q4
Bayesian cards render posterior mean/ETI/R̂/ESS and the sampler footnote;
console error-free (favicon 404 excepted). Restore the original DB afterwards
and stop both servers.

- [ ] **Step 3: Docs** — README (Phase 3B done in roadmap; bayes CLI line;
two endpoints), backend README (endpoints + job lifecycle note), frontend
README (Bayesian section bullet), CHANGELOG ([Unreleased] entry). Commit:
`docs: Phase 3B Bayesian sensitivity status, endpoints, CLI usage`.

- [ ] **Step 4: Full sweep** — all four suites green; final code review
(whole 3B diff); push; PR.

---

## Self-review notes

- Spec §7 coverage: priors/ETI/diagnostics/converged (Task 1), persisted
  sampler config (Task 1), async job + lifecycle (Task 3), diagnostics UI
  (Task 5), separate artifact + BAYES_VERSION cache key (Tasks 1, 3 — closes
  the staleness trap flagged in memory).
- pymc/arviz API calls (`ci_prob`, `eti95_lb/ub`, `sample_stats["diverging"]`,
  `cores=1` sequential) were verified live on the target venv before writing.
- The worker thread uses `session.get_bind()` so the test suite's in-memory
  StaticPool engine is honored — this is the one integration detail most
  likely to be silently broken; Task 3 Step 3 calls it out.
