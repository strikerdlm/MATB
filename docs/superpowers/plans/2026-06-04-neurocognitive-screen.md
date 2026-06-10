# Baseline Neurocognitive Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Browser-administered 4-subtest baseline battery (Spanish participant UI) whose Python-scored results feed per-participant HCF into the Suhir DEPDF fits, replacing F = F₀.

**Architecture:** Raw-trials-to-backend. The browser captures raw trials and POSTs them; `matb_integration/screen/` (stdlib-only, like `log_converter`) scores subtests and maps cohort z-scores → F/F₀; the backend stores `ScreenResult`, refreshes the HCF columns of ALL `DepdfFit` rows on every screen ingest, and serves F-aware P^h curves (Eq. 5.1). Spec: `docs/superpowers/specs/2026-06-04-neurocognitive-screen-design.md`.

**Tech Stack:** Python stdlib (statistics, math) + existing `log_converter._d_prime` (Hautus) + existing `suhir.hcf.HCFEstimate`/`depdf.p_bar`; FastAPI/SQLModel; Next.js + TS + vitest, seeded mulberry32 PRNG for trial sequences.

**Conventions:** identical to prior plans. Library tests from repo root: `~/.venvs/matb-webui/bin/python -m pytest tests/screen -q` AND `python3 -m pytest tests/screen -q` (stdlib-only — both must pass). Backend from `webui/backend`; frontend `npm test -- --run` + `npm run typecheck`. Commits without AI co-author lines (Diego sole author).

**Pinned details the spec leaves to the plan:**
- Cohort z per metric needs **≥ 2 valid values** (else that metric is excluded cohort-wide); sample SD (ddof=1); SD = 0 → all z = 0 for that metric.
- `p_bar` accepts f² < 1 without guards (verified) — below-baseline capacity (F/F₀ ∈ [0.85, 1)) is well-defined.
- Raw payload carries the PRNG `seed` so any administration's trial sequence is reproducible.
- e2e "fast mode" (`?fast=1`) shrinks trial counts/durations only (6/6/12 trials, 8 s tracking) — identical logic paths; production constants exported and unit-tested.

**File map (final state):**

```
matb_integration/screen/__init__.py
matb_integration/screen/scoring.py          # subtest scorers + score_screen()
matb_integration/screen/hcf_mapping.py      # SCREEN_VERSION, K, CLAMP, gates, compute_cohort_hcf()
tests/screen/{__init__.py,test_scoring.py,test_hcf_mapping.py}
webui/backend/app/models.py                 # + ScreenResult
webui/backend/app/hcf_refresh.py            # build_hcf_store() + refresh_fit_hcf()
webui/backend/app/routers/screen.py         # POST /screen, GET /screen
webui/backend/app/routers/fits.py           # F-aware _curve
webui/backend/app/ingestion.py              # pass hcf_store to fit_participant
webui/backend/app/main.py                   # include screen router
webui/backend/tests/test_screen_endpoint.py
webui/backend/tests/test_hcf_refresh.py
webui/frontend/src/lib/screen.ts            # seeded PRNG, sequence generators, payload types
webui/frontend/src/lib/screen.test.ts
webui/frontend/src/lib/api.ts               # + postScreen, getScreenSummary
webui/frontend/src/components/screen/strings_es.ts
webui/frontend/src/components/screen/{SimpleRT,ChoiceRT,NBack,Tracking,TaskRunner}.tsx
webui/frontend/src/app/screen/page.tsx
webui/frontend/src/components/layout/SidebarNav.tsx   # + Screen item
README.md / webui READMEs / CHANGELOG.md
```

---

### Task 1: Subtest scoring (`matb_integration/screen/scoring.py`)

**Files:**
- Create: `matb_integration/screen/__init__.py` (empty docstring module)
- Create: `matb_integration/screen/scoring.py`
- Create: `tests/screen/__init__.py` (empty)
- Test: `tests/screen/test_scoring.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/screen/test_scoring.py
from __future__ import annotations

import pytest

from matb_integration.screen.scoring import (
    score_choice_rt, score_nback, score_screen, score_simple_rt, score_tracking,
)


def _rt_trials(rts, responded=True):
    return [{"rt_ms": r, "responded": responded} for r in rts]


def test_simple_rt_median_and_anticipation_discard():
    rts = [300, 320, 280, 140, 310]            # 140 ms -> anticipation, unusable
    out = score_simple_rt(_rt_trials(rts))
    assert out["median_ms"] == 305.0           # median of 280,300,310,320
    assert out["n_usable"] == 4 and out["n_trials"] == 5
    assert out["valid"] is True                # 4/5 = 80% usable


def test_simple_rt_invalid_when_too_few_usable():
    trials = _rt_trials([300] * 3) + _rt_trials([100] * 2)  # 3/5 = 60% < 80%
    assert score_simple_rt(trials)["valid"] is False


def test_choice_rt_correct_median_and_accuracy_gate():
    trials = [
        {"rt_ms": 400, "responded": True, "correct": True},
        {"rt_ms": 500, "responded": True, "correct": True},
        {"rt_ms": 450, "responded": True, "correct": False},
        {"rt_ms": 420, "responded": True, "correct": True},
    ]
    out = score_choice_rt(trials)
    assert out["median_ms"] == 420.0           # correct trials only: 400,420,500
    assert out["accuracy"] == pytest.approx(0.75)
    assert out["valid"] is True
    # accuracy below 0.6 invalidates even with full usability
    bad = [{"rt_ms": 400, "responded": True, "correct": i < 2} for i in range(10)]
    assert score_choice_rt(bad)["valid"] is False


def test_nback_d_prime_matches_sysmon_helper():
    # 20 targets (15 hits / 5 misses), 40 non-targets (4 FA / 36 CR)
    trials = (
        [{"is_target": True, "responded": True, "gap": False}] * 15
        + [{"is_target": True, "responded": False, "gap": False}] * 5
        + [{"is_target": False, "responded": True, "gap": False}] * 4
        + [{"is_target": False, "responded": False, "gap": False}] * 36
    )
    out = score_nback(trials)
    from matb_integration.log_converter import _d_prime
    assert out["d_prime"] == pytest.approx(_d_prime(15, 5, 4, 36))
    assert out["valid"] is True
    # >20% gap-flagged trials -> invalid
    gappy = [dict(t, gap=i < 15) for i, t in enumerate(trials)]
    assert score_nback(gappy)["valid"] is False


def test_tracking_rms_normalized():
    # constant 30 px error against amplitude 100 -> rms_norm 0.3
    samples = [[i * 16, 30 + 0, 0, 0, 0] for i in range(100)]
    # samples are [t_ms, mouse_x, mouse_y, target_x, target_y]: mouse 30px right of target
    out = score_tracking({"samples": [[i * 16, 30, 0, 0, 0] for i in range(100)],
                          "n_expected_samples": 100, "path_amplitude_px": 100.0})
    assert out["rms_norm"] == pytest.approx(0.3)
    assert out["valid"] is True
    sparse = {"samples": [[0, 30, 0, 0, 0]] * 50, "n_expected_samples": 100,
              "path_amplitude_px": 100.0}
    assert score_tracking(sparse)["valid"] is False  # 50% < 80% of expected


def test_score_screen_assembles_all_subtests():
    payload = {
        "simple_rt": {"trials": _rt_trials([300] * 30)},
        "choice_rt": {"trials": [{"rt_ms": 400, "responded": True, "correct": True}] * 30},
        "nback": {"trials": [{"is_target": i % 3 == 0, "responded": i % 3 == 0, "gap": False}
                              for i in range(60)]},
        "tracking": {"samples": [[i * 16, 10, 0, 0, 0] for i in range(5400)],
                     "n_expected_samples": 5400, "path_amplitude_px": 120.0},
    }
    scores = score_screen(payload)
    assert set(scores) == {"simple_rt", "choice_rt", "nback", "tracking"}
    assert all("valid" in s for s in scores.values())
```

- [ ] **Step 2: Run to verify FAIL**

`~/.venvs/matb-webui/bin/python -m pytest tests/screen -q` → ModuleNotFoundError

- [ ] **Step 3: Implement**

```python
# matb_integration/screen/__init__.py
"""Baseline neurocognitive screen: scoring + HCF mapping (Phase 10 #20).

Spec: docs/superpowers/specs/2026-06-04-neurocognitive-screen-design.md
"""
```

```python
# matb_integration/screen/scoring.py
"""Subtest scoring for the baseline neurocognitive screen.

Stdlib-only (like log_converter). Raw trials come from the browser; all
scoring decisions live here so they are testable and re-derivable. Validity
rules are pre-registered in the spec (>=80% usable trials; Choice RT also
needs accuracy >= 0.6).
"""
from __future__ import annotations

import math
import statistics
from typing import Any

# Reuse the Hautus log-linear d' used for SYSMON/COMM — single-sourced math.
from matb_integration.log_converter import _d_prime

MIN_RT_MS = 150.0          # below this a simple-RT response is an anticipation
USABLE_FRACTION = 0.8
MIN_CHOICE_ACCURACY = 0.6


def _base(n_trials: int, n_usable: int) -> dict[str, Any]:
    return {"n_trials": n_trials, "n_usable": n_usable,
            "valid": n_trials > 0 and (n_usable / n_trials) >= USABLE_FRACTION}


def score_simple_rt(trials: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [t["rt_ms"] for t in trials
              if t.get("responded") and float(t["rt_ms"]) >= MIN_RT_MS]
    out = _base(len(trials), len(usable))
    out["median_ms"] = float(statistics.median(usable)) if usable else None
    return out


def score_choice_rt(trials: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [t for t in trials if t.get("responded")]
    correct = [float(t["rt_ms"]) for t in usable if t.get("correct")]
    out = _base(len(trials), len(usable))
    accuracy = (len(correct) / len(usable)) if usable else None
    out["accuracy"] = accuracy
    out["median_ms"] = float(statistics.median(correct)) if correct else None
    if out["valid"] and (accuracy is None or accuracy < MIN_CHOICE_ACCURACY):
        out["valid"] = False
    return out


def score_nback(trials: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [t for t in trials if not t.get("gap")]
    hits = sum(1 for t in usable if t["is_target"] and t.get("responded"))
    misses = sum(1 for t in usable if t["is_target"] and not t.get("responded"))
    fa = sum(1 for t in usable if not t["is_target"] and t.get("responded"))
    cr = sum(1 for t in usable if not t["is_target"] and not t.get("responded"))
    out = _base(len(trials), len(usable))
    out["d_prime"] = _d_prime(hits, misses, fa, cr) if usable else None
    out.update({"hits": hits, "misses": misses, "fa": fa, "cr": cr})
    return out


def score_tracking(block: dict[str, Any]) -> dict[str, Any]:
    samples = block.get("samples", [])
    n_expected = int(block.get("n_expected_samples") or 0)
    amplitude = float(block.get("path_amplitude_px") or 0.0)
    out = {"n_samples": len(samples), "n_expected_samples": n_expected,
           "valid": n_expected > 0 and amplitude > 0
                    and (len(samples) / n_expected) >= USABLE_FRACTION}
    if samples and amplitude > 0:
        sq = [(s[1] - s[3]) ** 2 + (s[2] - s[4]) ** 2 for s in samples]
        out["rms_norm"] = math.sqrt(sum(sq) / len(sq)) / amplitude
    else:
        out["rms_norm"] = None
    return out


def score_screen(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Score all four subtests from the raw browser payload."""
    return {
        "simple_rt": score_simple_rt(payload["simple_rt"]["trials"]),
        "choice_rt": score_choice_rt(payload["choice_rt"]["trials"]),
        "nback": score_nback(payload["nback"]["trials"]),
        "tracking": score_tracking(payload["tracking"]),
    }
```

- [ ] **Step 4: Run to verify PASS**

`~/.venvs/matb-webui/bin/python -m pytest tests/screen -q` → 6 pass.
Also `python3 -m pytest tests/screen -q` → 6 pass (stdlib-only).

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/screen tests/screen
git commit -m "feat(screen): subtest scoring with pre-registered validity rules"
```

---

### Task 2: HCF mapping (`matb_integration/screen/hcf_mapping.py`)

**Files:**
- Create: `matb_integration/screen/hcf_mapping.py`
- Test: `tests/screen/test_hcf_mapping.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/screen/test_hcf_mapping.py
from __future__ import annotations

import pytest

from matb_integration.screen.hcf_mapping import (
    CLAMP, K, MIN_COHORT, SCREEN_VERSION, compute_cohort_hcf,
)


def _scores(simple=300.0, choice=420.0, nback=2.0, tracking=0.3, valid=True):
    return {
        "simple_rt": {"median_ms": simple, "valid": valid},
        "choice_rt": {"median_ms": choice, "valid": valid, "accuracy": 0.9},
        "nback": {"d_prime": nback, "valid": valid},
        "tracking": {"rms_norm": tracking, "valid": valid},
    }


def test_gate_below_min_cohort():
    assert compute_cohort_hcf({"P01": _scores(), "P02": _scores()}) == {}


def test_signs_and_direction():
    # P01 faster RT, better d', lower tracking error -> F above 1; P03 opposite
    cohort = {"P01": _scores(simple=250, choice=380, nback=2.8, tracking=0.2),
              "P02": _scores(simple=300, choice=420, nback=2.0, tracking=0.3),
              "P03": _scores(simple=350, choice=460, nback=1.2, tracking=0.4)}
    store = compute_cohort_hcf(cohort)
    assert set(store) == {"P01", "P02", "P03"}
    assert store["P01"].value > 1.0 > store["P03"].value
    assert store["P02"].value == pytest.approx(1.0, abs=1e-9)  # cohort mean
    assert store["P01"].source == "screen"
    assert "composite_z" in store["P01"].components
    assert store["P01"].components["screen_version"] == SCREEN_VERSION


def test_clamping():
    # construct an extreme outlier; z magnitudes large -> clamp at bounds
    cohort = {"P01": _scores(simple=150, nback=4.5, choice=300, tracking=0.05),
              "P02": _scores(), "P03": _scores(), "P04": _scores(),
              "P05": _scores(simple=900, nback=0.1, choice=900, tracking=0.95)}
    store = compute_cohort_hcf(cohort)
    assert store["P01"].value <= CLAMP[1] and store["P05"].value >= CLAMP[0]
    assert min(s.value for s in store.values()) >= CLAMP[0]
    assert max(s.value for s in store.values()) <= CLAMP[1]


def test_invalid_subtest_excluded_per_participant():
    cohort = {"P01": _scores(), "P02": _scores(simple=350),
              "P03": {**_scores(simple=250),
                      "nback": {"d_prime": None, "valid": False}}}
    store = compute_cohort_hcf(cohort)
    # P03's composite uses only its 3 valid metrics; still produces an estimate
    assert "nback" not in store["P03"].components
    assert store["P03"].source == "screen"


def test_metric_needs_two_valid_values_and_zero_sd():
    # all identical -> sd 0 -> z 0 -> F exactly 1.0 for everyone
    cohort = {f"P{i:02d}": _scores() for i in range(1, 4)}
    store = compute_cohort_hcf(cohort)
    assert all(s.value == pytest.approx(1.0) for s in store.values())
    # a metric valid for only one participant is excluded cohort-wide
    cohort["P01"]["tracking"]["valid"] = False
    cohort["P02"]["tracking"]["valid"] = False
    store = compute_cohort_hcf(cohort)
    assert all("tracking" not in s.components for s in store.values())


def test_constants_are_prereg_values():
    assert K == 0.05 and CLAMP == (0.85, 1.15) and MIN_COHORT == 3
```

- [ ] **Step 2: Run to verify FAIL** → no module `hcf_mapping`

- [ ] **Step 3: Implement**

```python
# matb_integration/screen/hcf_mapping.py
"""Cohort-z composite -> HCF ratio F/F0 (spec section 3; exploratory).

F/F0 = 1 + K*mean(z) clamped to CLAMP, where z are per-subtest cohort
z-scores sign-aligned so higher = better capacity. Pre-registered gates:
>= MIN_COHORT screened participants; a metric enters the cohort z only with
>= 2 valid values (sample SD, ddof=1; SD == 0 -> z = 0).

There is no validated external standard for this mapping (Suhir section 5.9's
FOM approach is itself heuristic) — every consumer labels the result
exploratory.
"""
from __future__ import annotations

import statistics
from typing import Any

from matb_integration.suhir.hcf import HCFEstimate

SCREEN_VERSION = 1
K = 0.05
CLAMP = (0.85, 1.15)
MIN_COHORT = 3
MIN_METRIC_N = 2

# metric key -> (subtest, score field, sign): sign +1 means higher raw = better
METRICS: dict[str, tuple[str, str, int]] = {
    "simple_rt": ("simple_rt", "median_ms", -1),
    "choice_rt": ("choice_rt", "median_ms", -1),
    "nback": ("nback", "d_prime", +1),
    "tracking": ("tracking", "rms_norm", -1),
}


def _metric_values(scores_by_pid: dict[str, dict], subtest: str, field: str
                   ) -> dict[str, float]:
    vals: dict[str, float] = {}
    for pid, scores in scores_by_pid.items():
        s = scores.get(subtest) or {}
        if s.get("valid") and s.get(field) is not None:
            vals[pid] = float(s[field])
    return vals


def compute_cohort_hcf(scores_by_pid: dict[str, dict[str, Any]]
                       ) -> dict[str, HCFEstimate]:
    """Map every screened participant's scores to an HCFEstimate.

    Returns {} when the cohort gate (>= MIN_COHORT screens) fails.
    """
    if len(scores_by_pid) < MIN_COHORT:
        return {}
    z_by_pid: dict[str, dict[str, float]] = {pid: {} for pid in scores_by_pid}
    for metric, (subtest, field, sign) in METRICS.items():
        vals = _metric_values(scores_by_pid, subtest, field)
        if len(vals) < MIN_METRIC_N:
            continue  # excluded cohort-wide
        mean = statistics.fmean(vals.values())
        sd = statistics.stdev(vals.values()) if len(vals) > 1 else 0.0
        for pid, v in vals.items():
            z_by_pid[pid][metric] = sign * ((v - mean) / sd) if sd > 0 else 0.0

    store: dict[str, HCFEstimate] = {}
    for pid, zs in z_by_pid.items():
        if not zs:
            continue  # no valid metrics survived -> no screen estimate
        composite = statistics.fmean(zs.values())
        f = min(max(1.0 + K * composite, CLAMP[0]), CLAMP[1])
        store[pid] = HCFEstimate(
            participant_id=pid, value=f, source="screen",
            components={**zs, "composite_z": composite,
                        "screen_version": SCREEN_VERSION},
        )
    return store
```

- [ ] **Step 4: Run to verify PASS**

`~/.venvs/matb-webui/bin/python -m pytest tests/screen -q` → 12 pass; same on `python3`.

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/screen/hcf_mapping.py tests/screen/test_hcf_mapping.py
git commit -m "feat(screen): cohort-z HCF mapping with pre-registered gates"
```

---

### Task 3: Backend — `ScreenResult`, `/screen` endpoints, scoring wiring

**Files:**
- Modify: `webui/backend/app/models.py` (append)
- Create: `webui/backend/app/routers/screen.py`
- Modify: `webui/backend/app/main.py` (include router)
- Test: `webui/backend/tests/test_screen_endpoint.py`

- [ ] **Step 1: Write the failing tests** (read `tests/conftest.py` first; reuse `client`)

```python
# webui/backend/tests/test_screen_endpoint.py
"""POST /screen scoring+storage+guards; GET /screen summary with gate status."""
from __future__ import annotations


def _payload(simple=300.0):
    return {
        "seed": 12345,
        "administered_at": "2026-06-04T10:00:00+00:00",
        "simple_rt": {"trials": [{"rt_ms": simple, "responded": True}] * 30},
        "choice_rt": {"trials": [{"rt_ms": 420.0, "responded": True, "correct": True}] * 30},
        "nback": {"trials": [{"is_target": i % 3 == 0, "responded": i % 3 == 0, "gap": False}
                              for i in range(60)]},
        "tracking": {"samples": [[i * 16, 10, 0, 0, 0] for i in range(200)],
                     "n_expected_samples": 200, "path_amplitude_px": 120.0},
    }


def _enroll(client, pid):
    client.post("/participants", json={"id": pid, "enrollment_date": "2026-06-01"})


def test_screen_post_scores_and_stores(client):
    _enroll(client, "P01")
    r = client.post("/screen", json={"participant_id": "P01", "payload": _payload()})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["scores"]["simple_rt"]["median_ms"] == 300.0
    assert body["scores"]["nback"]["valid"] is True
    assert body["screen_version"] == 1


def test_screen_unknown_participant_404(client):
    r = client.post("/screen", json={"participant_id": "P99", "payload": _payload()})
    assert r.status_code == 404


def test_screen_duplicate_guard_and_overwrite(client):
    _enroll(client, "P01")
    assert client.post("/screen", json={"participant_id": "P01",
                                        "payload": _payload()}).status_code == 201
    r = client.post("/screen", json={"participant_id": "P01", "payload": _payload()})
    assert r.status_code == 409
    r = client.post("/screen", json={"participant_id": "P01",
                                     "payload": _payload(simple=280.0),
                                     "overwrite": True})
    assert r.status_code == 201
    assert r.json()["scores"]["simple_rt"]["median_ms"] == 280.0


def test_screen_summary_gate_status(client):
    for i, pid in enumerate(("P01", "P02"), start=1):
        _enroll(client, pid)
        client.post("/screen", json={"participant_id": pid,
                                     "payload": _payload(simple=280.0 + i * 20)})
    s = client.get("/screen").json()
    assert s["n_screened"] == 2 and s["hcf_active"] is False  # < MIN_COHORT
    assert {e["participant_id"] for e in s["screens"]} == {"P01", "P02"}
    assert all(e["hcf_value"] is None for e in s["screens"])
    _enroll(client, "P03")
    client.post("/screen", json={"participant_id": "P03",
                                 "payload": _payload(simple=360.0)})
    s = client.get("/screen").json()
    assert s["n_screened"] == 3 and s["hcf_active"] is True
    by_pid = {e["participant_id"]: e for e in s["screens"]}
    assert by_pid["P01"]["hcf_value"] > 1.0 > by_pid["P03"]["hcf_value"]
```

Run (from `webui/backend`): `~/.venvs/matb-webui/bin/python -m pytest tests/test_screen_endpoint.py -q` → FAIL.

- [ ] **Step 2: Implement**

Append to `webui/backend/app/models.py`:

```python
class ScreenResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    participant_id: str = Field(foreign_key="participant.id", unique=True, index=True)
    administered_at: str                            # ISO timestamp from the browser
    screen_version: int
    raw_trials_json: str                            # full raw payload (re-derivable)
    scores_json: str                                # score_screen() output
    created_at: datetime = Field(default_factory=_utcnow)
```

Create `webui/backend/app/routers/screen.py`:

```python
"""Baseline neurocognitive screen: raw-trial ingestion + cohort HCF summary.

Scoring and the HCF mapping live in matb_integration.screen (single-sourced);
this router stores raw + scores and triggers the fit-HCF refresh (Task 4)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models import Participant, ScreenResult

router = APIRouter(tags=["screen"])


def _score_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from matb_integration.screen.scoring import score_screen

    required = {"simple_rt", "choice_rt", "nback", "tracking"}
    missing = required - set(payload)
    if missing:
        raise HTTPException(status_code=422, detail=f"payload missing: {sorted(missing)}")
    return score_screen(payload)


@router.post("/screen", status_code=201)
def ingest_screen(
    participant_id: str = Body(...),
    payload: dict[str, Any] = Body(...),
    overwrite: bool = Body(False),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from matb_integration.screen.hcf_mapping import SCREEN_VERSION

    if session.get(Participant, participant_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown participant {participant_id}")
    existing = session.exec(
        select(ScreenResult).where(ScreenResult.participant_id == participant_id)
    ).first()
    if existing is not None and not overwrite:
        raise HTTPException(status_code=409,
                            detail=f"screen already recorded for {participant_id}")
    scores = _score_payload(payload)
    if existing is not None:
        session.delete(existing)
        session.flush()
    row = ScreenResult(
        participant_id=participant_id,
        administered_at=str(payload.get("administered_at") or ""),
        screen_version=SCREEN_VERSION,
        raw_trials_json=json.dumps(payload),
        scores_json=json.dumps(scores),
    )
    session.add(row)
    session.commit()
    # Task 4 wires refresh_fit_hcf(session) here.
    return {"participant_id": participant_id, "screen_version": SCREEN_VERSION,
            "scores": scores}


@router.get("/screen")
def screen_summary(session: Session = Depends(get_session)) -> dict[str, Any]:
    from matb_integration.screen.hcf_mapping import (MIN_COHORT, SCREEN_VERSION,
                                                     compute_cohort_hcf)

    rows = session.exec(select(ScreenResult)).all()
    scores_by_pid = {r.participant_id: json.loads(r.scores_json) for r in rows}
    store = compute_cohort_hcf(scores_by_pid)
    screens = []
    for r in sorted(rows, key=lambda x: x.participant_id):
        est = store.get(r.participant_id)
        screens.append({
            "participant_id": r.participant_id,
            "administered_at": r.administered_at,
            "screen_version": r.screen_version,
            "scores": scores_by_pid[r.participant_id],
            "hcf_value": est.value if est else None,
            "components": est.components if est else None,
        })
    return {"n_screened": len(rows), "min_cohort": MIN_COHORT,
            "hcf_active": bool(store), "screen_version": SCREEN_VERSION,
            "screens": screens}
```

In `webui/backend/app/main.py`: add `screen` to the routers import and `app.include_router(screen.router)`.

- [ ] **Step 3:** from `webui/backend`: `~/.venvs/matb-webui/bin/python -m pytest -q` → 38 pass (34 + 4).

- [ ] **Step 4: Commit**

```bash
cd /root/repos/MATB
git add webui/backend
git commit -m "feat(webui): /screen ingestion with Python scoring and cohort summary"
```

---

### Task 4: HCF refresh — store builder, fit refresh, F-aware curves, ingestion wiring

**Files:**
- Create: `webui/backend/app/hcf_refresh.py`
- Modify: `webui/backend/app/routers/screen.py` (call refresh after commit)
- Modify: `webui/backend/app/ingestion.py` (pass hcf_store into fit_participant)
- Modify: `webui/backend/app/routers/fits.py` (F-aware `_curve`)
- Test: `webui/backend/tests/test_hcf_refresh.py`

- [ ] **Step 1: Write the failing tests.** Do NOT use `ingest_one_block` here —
it posts identical CSV bytes per level (sha256 dedup rejects the second) with
equal MWL (degenerate fit). Reuse `test_fit_trigger.py`'s guaranteed-valid
pattern (varied `misses`/`raw_tlx` per level) over HTTP:

```python
# webui/backend/tests/test_hcf_refresh.py
"""Screen ingest must refresh hcf_value on ALL existing DepdfFits; new fits
must pick up the screen HCF; /fits curves switch to Eq. 5.1."""
from __future__ import annotations

from sqlmodel import Session, select

from app.models import DepdfFit

from .test_fit_trigger import LEVEL_MWL, _misses_for
from .test_screen_endpoint import _enroll, _payload


def _fill_visit(client, sample_csv_bytes, pid, visit=1):
    _enroll(client, pid)
    for level, g in LEVEL_MWL.items():
        r = client.post(
            "/ingest",
            data={"participant_id": pid, "visit_ordinal": str(visit),
                  "workload_level": level},
            files={"file": (f"{pid}_{level}.csv",
                            sample_csv_bytes(misses=_misses_for(g), raw_tlx=g),
                            "text/csv")},
        )
        assert r.status_code == 201, r.text


def test_existing_fits_refresh_when_cohort_gate_crossed(client, engine,
                                                        sample_csv_bytes):
    _fill_visit(client, sample_csv_bytes, "P01")
    with Session(engine) as s:
        fit = s.exec(select(DepdfFit)).one()
        assert fit.hcf_source == "F0_default" and fit.hcf_value == 1.0
    # screens for P01..P03 crosses the >=3 gate; P01 is fastest -> F > 1
    for pid, simple in (("P01", 260.0), ("P02", 320.0), ("P03", 380.0)):
        _enroll(client, pid)
        client.post("/screen", json={"participant_id": pid,
                                     "payload": _payload(simple=simple)})
    with Session(engine) as s:
        fit = s.exec(select(DepdfFit)).one()
        assert fit.hcf_source == "screen" and fit.hcf_value > 1.0


def test_new_fit_uses_screen_hcf(client, engine, sample_csv_bytes):
    for pid, simple in (("P01", 260.0), ("P02", 320.0), ("P03", 380.0)):
        _enroll(client, pid)
        client.post("/screen", json={"participant_id": pid,
                                     "payload": _payload(simple=simple)})
    _fill_visit(client, sample_csv_bytes, "P03")
    with Session(engine) as s:
        fit = s.exec(select(DepdfFit)).one()
        assert fit.hcf_source == "screen" and fit.hcf_value < 1.0


def test_fits_endpoint_curve_uses_f(client, sample_csv_bytes):
    for pid, simple in (("P01", 260.0), ("P02", 320.0), ("P03", 380.0)):
        _enroll(client, pid)
        client.post("/screen", json={"participant_id": pid,
                                     "payload": _payload(simple=simple)})
    _fill_visit(client, sample_csv_bytes, "P01")
    fit = client.get("/fits").json()[0]
    assert fit["hcf_source"] == "screen"
    # P01's F > 1 -> inner exponent exp(1-f^2) < 1 -> curve DECAYS SLOWER than
    # the ordinary form: at r=3, p > p0*exp(1-9)
    p0 = fit["p0"]
    import math
    ordinary_at_3 = p0 * math.exp((1 - 9) * 1.0)
    assert fit["curve"][-1]["p"] > ordinary_at_3
    assert "hcf_value" in fit
```

Run → FAIL (no refresh, curves ordinary, fits payload lacks hcf_value).

- [ ] **Step 2: Implement**

Create `webui/backend/app/hcf_refresh.py`:

```python
"""Cohort HCF store + DepdfFit refresh (spec section 4).

Calibration (g0/p0/tau0) is F-independent; only the hcf_value/hcf_source
columns change. Called on every screen ingest and used by the fit trigger."""

from __future__ import annotations

import json

from sqlmodel import Session, select

from app.models import DepdfFit, ScreenResult


def build_hcf_store(session: Session):
    """{participant_id: HCFEstimate} from stored screens; {} below the gate."""
    from matb_integration.screen.hcf_mapping import compute_cohort_hcf

    rows = session.exec(select(ScreenResult)).all()
    scores = {r.participant_id: json.loads(r.scores_json) for r in rows}
    return compute_cohort_hcf(scores)


def refresh_fit_hcf(session: Session) -> int:
    """Update hcf_value/hcf_source on every DepdfFit from the current cohort
    store. Participants without a screen estimate revert to F0. Returns the
    number of rows changed."""
    from matb_integration.suhir.hcf import F0_DEFAULT

    store = build_hcf_store(session)
    changed = 0
    for fit in session.exec(select(DepdfFit)).all():
        est = store.get(fit.participant_id)
        value = est.value if est else F0_DEFAULT
        source = "screen" if est else "F0_default"
        if fit.hcf_value != value or fit.hcf_source != source:
            fit.hcf_value, fit.hcf_source = value, source
            session.add(fit)
            changed += 1
    session.commit()
    return changed
```

In `routers/screen.py` `ingest_screen`, right after `session.commit()`:

```python
    from app.hcf_refresh import refresh_fit_hcf
    refresh_fit_hcf(session)
```

In `app/ingestion.py` `_maybe_fit_visit`, build the store and pass it (keep the
whole fit attempt inside the existing try/except isolation):

```python
        from app.hcf_refresh import build_hcf_store
        out = fit_participant(visit.participant_id, blocks_arg, source="raw_tlx",
                              hcf_store=build_hcf_store(session) or None)
```

In `routers/fits.py`: make `_curve` F-aware and expose `hcf_value` (keep
`p_nonfailure_ordinary` semantics when F = F₀ via `p_bar(r², f²)` with f = 1):

```python
def _curve(p0: float, f_ratio: float = 1.0) -> list[dict[str, float]]:
    from matb_integration.suhir.depdf import p_bar

    points: list[dict[str, float]] = []
    for i in range(N_CURVE_POINTS):
        r = 1.0 + (R_MAX - 1.0) * i / (N_CURVE_POINTS - 1)
        points.append({"r": round(r, 4), "p": p0 * p_bar(r ** 2, f_ratio ** 2)})
    return points
```

and in `list_fits` use `"curve": _curve(fit.p0, fit.hcf_value if fit.hcf_source == "screen" else 1.0)` and add `"hcf_value": fit.hcf_value` to the row dict.

- [ ] **Step 3:** from `webui/backend`: `~/.venvs/matb-webui/bin/python -m pytest -q` → 41 pass (38 + 3). The pre-existing fits tests must still pass — `p_bar(r², 1)` is numerically identical to `p_nonfailure_ordinary`.

- [ ] **Step 4: Commit**

```bash
cd /root/repos/MATB
git add webui/backend
git commit -m "feat(webui): cohort HCF refresh into DEPDF fits and F-aware curves"
```

---

### Task 5: Frontend lib — seeded generators, payload types, API client

**Files:**
- Create: `webui/frontend/src/lib/screen.ts`
- Test: `webui/frontend/src/lib/screen.test.ts`
- Modify: `webui/frontend/src/lib/api.ts` (+2 functions), `src/types/index.ts` (+ types)

- [ ] **Step 1: Write the failing tests**

```typescript
// webui/frontend/src/lib/screen.test.ts
import { describe, it, expect } from "vitest";
import {
  mulberry32, genSimpleRtIsis, genChoiceSides, genNbackSequence,
  targetPosition, SCREEN_CONFIG, FAST_CONFIG,
} from "@/lib/screen";

describe("screen lib", () => {
  it("mulberry32 is deterministic", () => {
    const a = mulberry32(42), b = mulberry32(42);
    expect([a(), a(), a()]).toEqual([b(), b(), b()]);
  });

  it("genSimpleRtIsis yields n ISIs within [1000, 3000] ms", () => {
    const isis = genSimpleRtIsis(30, mulberry32(1));
    expect(isis).toHaveLength(30);
    expect(Math.min(...isis)).toBeGreaterThanOrEqual(1000);
    expect(Math.max(...isis)).toBeLessThanOrEqual(3000);
  });

  it("genChoiceSides is balanced within 10%", () => {
    const sides = genChoiceSides(30, mulberry32(2));
    const left = sides.filter((s) => s === "left").length;
    expect(left).toBeGreaterThanOrEqual(12);
    expect(left).toBeLessThanOrEqual(18);
  });

  it("genNbackSequence has the requested target count and no 3-runs", () => {
    const { letters, isTarget } = genNbackSequence(60, 18, mulberry32(3));
    expect(letters).toHaveLength(60);
    expect(isTarget.filter(Boolean)).toHaveLength(18);
    // targets are defined as letter[i] === letter[i-2]
    isTarget.forEach((t, i) => {
      if (i >= 2) expect(t).toBe(letters[i] === letters[i - 2]);
      else expect(t).toBe(false);
    });
    // no 3 identical consecutive letters (would make 1-back == 2-back)
    for (let i = 2; i < letters.length; i++) {
      expect(letters[i] === letters[i - 1] && letters[i - 1] === letters[i - 2]).toBe(false);
    }
  });

  it("targetPosition is a bounded sum-of-sines", () => {
    for (const t of [0, 5, 30, 90]) {
      const { x, y } = targetPosition(t, 100);
      expect(Math.abs(x)).toBeLessThanOrEqual(100);
      expect(Math.abs(y)).toBeLessThanOrEqual(100);
    }
  });

  it("configs expose prereg counts and fast mode shrinks them", () => {
    expect(SCREEN_CONFIG.simpleRtTrials).toBe(30);
    expect(SCREEN_CONFIG.nbackTrials).toBe(60);
    expect(SCREEN_CONFIG.trackingSeconds).toBe(90);
    expect(FAST_CONFIG.simpleRtTrials).toBeLessThan(SCREEN_CONFIG.simpleRtTrials);
  });
});
```

- [ ] **Step 2: Run to verify FAIL** → module missing.

- [ ] **Step 3: Implement**

```typescript
// webui/frontend/src/lib/screen.ts
// Pure, seeded, timing-independent logic for the neurocognitive screen.
// All participant-visible STRINGS live in components/screen/strings_es.ts;
// all SCORING lives in matb_integration/screen (Python). This module only
// generates reproducible trial sequences and assembles the raw payload.

export interface ScreenConfig {
  simpleRtTrials: number;
  choiceRtTrials: number;
  nbackTrials: number;
  nbackTargets: number;
  nbackSoaMs: number;
  trackingSeconds: number;
  practiceTrials: number;
}

export const SCREEN_CONFIG: ScreenConfig = {
  simpleRtTrials: 30, choiceRtTrials: 30,
  nbackTrials: 60, nbackTargets: 18, nbackSoaMs: 2500,
  trackingSeconds: 90, practiceTrials: 5,
};

// e2e/dev only: same logic, fewer trials (enabled via /screen?fast=1)
export const FAST_CONFIG: ScreenConfig = {
  simpleRtTrials: 6, choiceRtTrials: 6,
  nbackTrials: 12, nbackTargets: 4, nbackSoaMs: 1200,
  trackingSeconds: 8, practiceTrials: 2,
};

export const NBACK_LETTERS = ["B", "C", "D", "F", "G", "H", "J", "K", "L", "M"];

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function genSimpleRtIsis(n: number, rng: () => number): number[] {
  return Array.from({ length: n }, () => 1000 + Math.floor(rng() * 2001));
}

export function genChoiceSides(n: number, rng: () => number): ("left" | "right")[] {
  // balanced half/half, shuffled (Fisher-Yates with the seeded rng)
  const sides: ("left" | "right")[] = Array.from(
    { length: n }, (_, i) => (i < Math.ceil(n / 2) ? "left" : "right"));
  for (let i = sides.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [sides[i], sides[j]] = [sides[j], sides[i]];
  }
  return sides;
}

export function genNbackSequence(
  n: number, targets: number, rng: () => number,
): { letters: string[]; isTarget: boolean[] } {
  // choose target indices (>= 2, non-adjacent to keep runs controllable)
  const candidates = Array.from({ length: n - 2 }, (_, i) => i + 2);
  const targetIdx = new Set<number>();
  while (targetIdx.size < targets && candidates.length > 0) {
    const k = candidates.splice(Math.floor(rng() * candidates.length), 1)[0];
    if (!targetIdx.has(k - 1) && !targetIdx.has(k + 1)) targetIdx.add(k);
  }
  const letters: string[] = [];
  for (let i = 0; i < n; i++) {
    if (targetIdx.has(i)) {
      letters.push(letters[i - 2]);
    } else {
      let pick: string;
      do {
        pick = NBACK_LETTERS[Math.floor(rng() * NBACK_LETTERS.length)];
        // avoid accidental targets and 3-letter runs
      } while ((i >= 2 && pick === letters[i - 2]) || (i >= 1 && pick === letters[i - 1]));
      letters.push(pick);
    }
  }
  const isTarget = letters.map((l, i) => i >= 2 && l === letters[i - 2]);
  return { letters, isTarget };
}

// Sum-of-sines pursuit path, bounded by |amplitude| on each axis.
export function targetPosition(tSeconds: number, amplitude: number): { x: number; y: number } {
  const x = amplitude * (0.5 * Math.sin(2 * Math.PI * 0.07 * tSeconds)
    + 0.35 * Math.sin(2 * Math.PI * 0.15 * tSeconds + 1.3)
    + 0.15 * Math.sin(2 * Math.PI * 0.31 * tSeconds + 2.1));
  const y = amplitude * (0.5 * Math.sin(2 * Math.PI * 0.09 * tSeconds + 0.7)
    + 0.35 * Math.sin(2 * Math.PI * 0.19 * tSeconds + 2.6)
    + 0.15 * Math.sin(2 * Math.PI * 0.27 * tSeconds + 4.0));
  return { x, y };
}

// --- raw payload types (mirror matb_integration/screen/scoring.py inputs) ---
export interface RtTrial { rt_ms: number | null; responded: boolean; }
export interface ChoiceTrial extends RtTrial { correct: boolean; }
export interface NbackTrial { is_target: boolean; responded: boolean; gap: boolean; }

export interface ScreenPayload {
  seed: number;
  administered_at: string;
  fast_mode: boolean;
  simple_rt: { trials: RtTrial[] };
  choice_rt: { trials: ChoiceTrial[] };
  nback: { trials: NbackTrial[] };
  tracking: {
    samples: number[][];           // [t_ms, mouse_x, mouse_y, target_x, target_y]
    n_expected_samples: number;
    path_amplitude_px: number;
  };
}
```

Append to `src/types/index.ts`:

```typescript
// --- neurocognitive screen (matb_integration/screen) ---

export interface SubtestScore {
  valid: boolean;
  n_trials?: number;
  n_usable?: number;
  median_ms?: number | null;
  accuracy?: number | null;
  d_prime?: number | null;
  rms_norm?: number | null;
  [k: string]: unknown;
}

export interface ScreenEntry {
  participant_id: string;
  administered_at: string;
  screen_version: number;
  scores: Record<string, SubtestScore>;
  hcf_value: number | null;
  components: Record<string, number> | null;
}

export interface ScreenSummary {
  n_screened: number;
  min_cohort: number;
  hcf_active: boolean;
  screen_version: number;
  screens: ScreenEntry[];
}

export interface ScreenIngestResult {
  participant_id: string;
  screen_version: number;
  scores: Record<string, SubtestScore>;
}
```

Append to `src/lib/api.ts` (extend the type import with `ScreenSummary, ScreenIngestResult`; `ScreenPayload` imported from `@/lib/screen`):

```typescript
export async function postScreen(
  participantId: string, payload: import("@/lib/screen").ScreenPayload,
  overwrite = false,
): Promise<ScreenIngestResult> {
  const res = await fetch(`${API_BASE}/screen`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ participant_id: participantId, payload, overwrite }),
  });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getScreenSummary(): Promise<ScreenSummary> {
  const res = await fetch(`${API_BASE}/screen`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}
```

Add 2 tests to `src/lib/api.test.ts` (same pattern as previous phases — POST body field names `participant_id`/`payload`/`overwrite`; GET hits `/screen`).

- [ ] **Step 4:** `npm test -- --run` → 29 pass (21 + 6 screen lib + 2 api); `npm run typecheck` clean.

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src
git commit -m "feat(webui): screen trial generators, payload types, API client"
```

---

### Task 6: Frontend — Spanish strings + four subtest components

**Files:**
- Create: `webui/frontend/src/components/screen/strings_es.ts`
- Create: `webui/frontend/src/components/screen/{SimpleRT,ChoiceRT,NBack,Tracking}.tsx`

Presentation/timing components — no unit tests (logic was tested in Task 5); gates are typecheck + build + Task 8 live e2e.

- [ ] **Step 1: Spanish strings (complete file — Diego reviews wording here)**

```typescript
// webui/frontend/src/components/screen/strings_es.ts
// Todo el contenido visible para el participante, en español (es-CO).
// El registro sigue el de los instrumentos validados (nasatlx_es).

export const ES = {
  common: {
    practice: "Práctica",
    practiceDone: "Fin de la práctica. Ahora comienza la prueba real.",
    ready: "Prepárese…",
    continue: "Continuar",
    start: "Comenzar",
    subtestOf: (i: number, n: number) => `Prueba ${i} de ${n}`,
    done: "Ha completado todas las pruebas. Gracias.",
    saving: "Guardando resultados…",
  },
  simpleRt: {
    title: "Tiempo de reacción simple",
    instructions:
      "Cuando aparezca el círculo verde, presione la BARRA ESPACIADORA lo más rápido posible. " +
      "No presione antes de que aparezca.",
  },
  choiceRt: {
    title: "Tiempo de reacción de elección",
    instructions:
      "Aparecerá una flecha apuntando a la IZQUIERDA o a la DERECHA. " +
      "Presione la tecla de flecha correspondiente (← o →) lo más rápido posible.",
  },
  nback: {
    title: "Memoria de trabajo (2-atrás)",
    instructions:
      "Verá letras una por una. Presione la BARRA ESPACIADORA cuando la letra " +
      "actual sea IGUAL a la que apareció DOS posiciones antes. " +
      "Ejemplo: en la secuencia C…G…C, la segunda C es un acierto.",
  },
  tracking: {
    title: "Seguimiento con el ratón",
    instructions:
      "Un punto se moverá por la pantalla. Mantenga el cursor del ratón " +
      "lo más cerca posible del punto en todo momento, hasta que termine el tiempo.",
  },
} as const;
```

- [ ] **Step 2: Components.** Each component receives `{ config, rng, onDone }`
and returns its raw trials via `onDone`. Common pattern: instruction screen
(Spanish) → practice (config.practiceTrials, discarded) → scored block →
`onDone(trials)`. Implementation notes the implementer must follow exactly:

`SimpleRT.tsx` — state machine `instructions | waiting | stimulus | done` per
trial; ISIs from `genSimpleRtIsis(config.simpleRtTrials + config.practiceTrials, rng)`;
on stimulus show a green disc; `performance.now()` at show; keydown space →
`rt_ms = now - shownAt`, `responded: true`; auto-advance after 1500 ms with
`responded: false, rt_ms: null`; a keydown during `waiting` counts as an
anticipation: record `{rt_ms: 0, responded: true}` for that trial (scoring
discards it via the 150 ms rule) and move on.

`ChoiceRT.tsx` — same skeleton; sides from `genChoiceSides`; stimulus is a
large ← or → arrow (lucide `ArrowLeft`/`ArrowRight`); only ArrowLeft/ArrowRight
keys accepted; `correct = key side === stimulus side`; response window 2000 ms.

`NBack.tsx` — letters via `genNbackSequence(config.nbackTrials, config.nbackTargets, rng)`
(practice uses a separate short sequence `genNbackSequence(config.practiceTrials + 2, 1, rng)`);
each trial: letter visible 500 ms, blank until SOA (`config.nbackSoaMs`);
space during the SOA window marks `responded: true`; `gap = true` when the
measured SOA drift exceeds 250 ms (compare `performance.now()` deltas);
practice trials excluded from the returned array.

`Tracking.tsx` — fullscreen-ish dark canvas area; target dot follows
`targetPosition(elapsedSeconds, amplitude)` centered in the container with
`amplitude = 0.35 * min(width, height) / 2 … actually amplitude = 0.35 * min(width, height)`;
requestAnimationFrame loop samples every frame the tuple
`[Math.round(tMs), mouseX, mouseY, targetX, targetY]` (container-relative px);
`n_expected_samples = trackingSeconds * 60`; `path_amplitude_px = amplitude`;
10 s practice (not sampled), then the scored run; mouse position from a
`mousemove` listener on the container.

All four: Spanish text exclusively from `strings_es.ts`; no analytic numbers
shown to the participant; `useEffect` cleanup removes listeners/RAF.

- [ ] **Step 3:** `npm run typecheck` clean; `npm test -- --run` still 29; `npm run build` succeeds (revert tsconfig if rewritten).

- [ ] **Step 4: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src
git commit -m "feat(webui): four Spanish-language screen subtest components"
```

---

### Task 7: Frontend — TaskRunner + `/screen` page + nav/tracker indicators

**Files:**
- Create: `webui/frontend/src/components/screen/TaskRunner.tsx`
- Create: `webui/frontend/src/app/screen/page.tsx`
- Modify: `webui/frontend/src/components/layout/SidebarNav.tsx` (add Screen item, lucide `Brain` icon, enabled — mirror existing items)

- [ ] **Step 1: TaskRunner** — orchestrates the four subtests sequentially:

```tsx
// webui/frontend/src/components/screen/TaskRunner.tsx
"use client";

import { useMemo, useRef, useState } from "react";

import { ChoiceRT } from "@/components/screen/ChoiceRT";
import { NBack } from "@/components/screen/NBack";
import { SimpleRT } from "@/components/screen/SimpleRT";
import { Tracking } from "@/components/screen/Tracking";
import { ES } from "@/components/screen/strings_es";
import {
  FAST_CONFIG, SCREEN_CONFIG, mulberry32,
  type ChoiceTrial, type NbackTrial, type RtTrial, type ScreenPayload,
} from "@/lib/screen";

const SUBTEST_COUNT = 4;

export function TaskRunner({ fast, onComplete }: {
  fast: boolean;
  onComplete: (payload: ScreenPayload) => void;
}) {
  const config = fast ? FAST_CONFIG : SCREEN_CONFIG;
  const seed = useMemo(() => Math.floor(Math.random() * 2 ** 31), []);
  const rng = useMemo(() => mulberry32(seed), [seed]);
  const [step, setStep] = useState(0);
  const acc = useRef<Partial<ScreenPayload>>({});

  function advance() { setStep((s) => s + 1); }

  return (
    <div className="flex min-h-[70vh] flex-col">
      <p className="mb-4 text-center text-xs text-muted-foreground">
        {ES.common.subtestOf(Math.min(step + 1, SUBTEST_COUNT), SUBTEST_COUNT)}
      </p>
      {step === 0 && (
        <SimpleRT config={config} rng={rng} onDone={(trials: RtTrial[]) => {
          acc.current.simple_rt = { trials }; advance();
        }} />
      )}
      {step === 1 && (
        <ChoiceRT config={config} rng={rng} onDone={(trials: ChoiceTrial[]) => {
          acc.current.choice_rt = { trials }; advance();
        }} />
      )}
      {step === 2 && (
        <NBack config={config} rng={rng} onDone={(trials: NbackTrial[]) => {
          acc.current.nback = { trials }; advance();
        }} />
      )}
      {step === 3 && (
        <Tracking config={config} onDone={(tracking) => {
          acc.current.tracking = tracking;
          onComplete({
            seed,
            administered_at: new Date().toISOString(),
            fast_mode: fast,
            simple_rt: acc.current.simple_rt!,
            choice_rt: acc.current.choice_rt!,
            nback: acc.current.nback!,
            tracking,
          });
        }} />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Page** — researcher picks an unscreened participant, runs the
battery, sees the backend-scored summary:

```tsx
// webui/frontend/src/app/screen/page.tsx
"use client";

import { useEffect, useState } from "react";

import { TaskRunner } from "@/components/screen/TaskRunner";
import { ES } from "@/components/screen/strings_es";
import {
  getScreenSummary, listParticipants, postScreen,
} from "@/lib/api";
import type { ScreenPayload } from "@/lib/screen";
import type { Participant, ScreenIngestResult, ScreenSummary } from "@/types";

export default function ScreenPage() {
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [summary, setSummary] = useState<ScreenSummary | null>(null);
  const [activePid, setActivePid] = useState<string | null>(null);
  const [result, setResult] = useState<ScreenIngestResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fast = typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("fast") === "1";

  async function refresh() {
    const [ps, s] = await Promise.all([listParticipants(), getScreenSummary()]);
    setParticipants(ps);
    setSummary(s);
  }
  useEffect(() => { refresh().catch((e) => setError(String(e))); }, []);

  async function onComplete(payload: ScreenPayload) {
    if (!activePid) return;
    setSaving(true);
    try {
      setResult(await postScreen(activePid, payload));
      setActivePid(null);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setActivePid(null);
    } finally {
      setSaving(false);
    }
  }

  if (activePid) {
    return <TaskRunner fast={fast} onComplete={onComplete} />;
  }

  const screened = new Set(summary?.screens.map((s) => s.participant_id));
  const unscreened = participants.filter((p) => !screened.has(p.id));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Baseline neurocognitive screen</h2>
        <p className="text-sm text-muted-foreground">
          One administration per participant at enrollment. HCF mapping is
          exploratory; active once ≥ {summary?.min_cohort ?? 3} participants are
          screened ({summary?.n_screened ?? 0} so far
          {summary?.hcf_active ? ", active" : ", inactive"}).
        </p>
      </div>

      {error && (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-400">
          {error}
        </p>
      )}
      {saving && <p className="text-sm text-muted-foreground">{ES.common.saving}</p>}

      {result && (
        <div className="rounded-lg border border-border p-4 text-sm">
          <h3 className="mb-2 font-medium">Scored: {result.participant_id}</h3>
          <pre className="overflow-x-auto text-xs text-muted-foreground">
            {JSON.stringify(result.scores, null, 2)}
          </pre>
        </div>
      )}

      <section className="space-y-2">
        <h3 className="text-sm font-semibold">Start a screen</h3>
        {unscreened.length === 0 && (
          <p className="text-sm text-muted-foreground">All participants screened.</p>
        )}
        <div className="flex flex-wrap gap-2">
          {unscreened.map((p) => (
            <button
              key={p.id}
              onClick={() => { setResult(null); setActivePid(p.id); }}
              className="rounded-md border border-border px-4 py-2 text-sm hover:bg-accent"
            >
              {p.id}
            </button>
          ))}
        </div>
      </section>

      {summary && summary.screens.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-semibold">Completed screens</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="py-1 pr-2">Participant</th>
                <th className="py-1 pr-2">Simple RT (ms)</th>
                <th className="py-1 pr-2">Choice RT (ms)</th>
                <th className="py-1 pr-2">2-back d′</th>
                <th className="py-1 pr-2">Tracking RMS</th>
                <th className="py-1">F/F₀ (exploratory)</th>
              </tr>
            </thead>
            <tbody>
              {summary.screens.map((s) => (
                <tr key={s.participant_id} className="border-t border-border/50">
                  <td className="py-1 pr-2 font-mono text-xs">{s.participant_id}</td>
                  <td className="py-1 pr-2">{s.scores.simple_rt?.median_ms ?? "—"}</td>
                  <td className="py-1 pr-2">{s.scores.choice_rt?.median_ms ?? "—"}</td>
                  <td className="py-1 pr-2">{s.scores.nback?.d_prime?.toFixed(2) ?? "—"}</td>
                  <td className="py-1 pr-2">{s.scores.tracking?.rms_norm?.toFixed(3) ?? "—"}</td>
                  <td className="py-1">{s.hcf_value?.toFixed(3) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
```

- [ ] **Step 3:** SidebarNav: add the Screen item (enabled, `/screen`, `Brain` icon) following the existing entries exactly.

- [ ] **Step 4:** `npm run typecheck` clean; `npm test -- --run` 29; `npm run build` succeeds.

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add webui/frontend/src
git commit -m "feat(webui): /screen page with Spanish task runner and cohort summary"
```

---

### Task 8: Live e2e + docs (controller-run)

- [ ] **Step 1: Backend live** — fresh scratch DB, uvicorn :8000. POST two
synthetic screens via the API (payloads as in the backend tests, different
speeds), confirm `GET /screen` shows `hcf_active: false`; POST the third →
`hcf_active: true` with ordered F values.
- [ ] **Step 2: Cohort propagation live** — restore the 48-CSV cohort DB
(exports copy), screen P01–P03 via API with distinct speeds, then assert via
`GET /fits` that all 16 existing fits now carry `hcf_source: "screen"` and
P01's curve at r=3 differs from the pre-screen value (capture before/after).
- [ ] **Step 3: Frontend live** — `npm run dev`, Playwright on `/screen?fast=1`:
pick a participant, complete all four subtests with real key presses/mouse
moves (fast mode ≈ 60 s), verify Spanish instruction text renders, the
completion POST succeeds, and the scored summary row appears. Console
error-free.
- [ ] **Step 4: Docs** — README (roadmap #20 done; screen description + HCF
note), backend README (2 endpoints + refresh note), frontend README (Screen
page bullet), CHANGELOG ([Unreleased] entry). Update
`docs/research/scales/scale_validation_es.md` with one line: screen
instructions are operational text in es-CO, not a psychometric scale.
- [ ] **Step 5: Full sweep** — library (both interpreters), backend, frontend
suites + typecheck; restore original DB; stop servers; commit docs:
`docs: baseline neurocognitive screen status, endpoints, HCF integration`.

### Task 9: Final review + PR (controller-run)

- [ ] Final code-review subagent over `git diff origin/main..HEAD` (cross-cutting seams: payload schema browser↔scorer, refresh propagation, F-aware curve consumers — DepdfPanel reads `curve` as-is so no frontend change needed there; docs accuracy; no stray artifacts).
- [ ] Push; `gh pr create` (Phase 10 #20). No AI attribution anywhere.

---

## Self-review notes

- Spec §2 battery params → Tasks 5/6 configs (30/30/60·18·2.5 s/90 s, practice 5).
- Spec §3 mapping (K/CLAMP/MIN_COHORT, validity defs incl. the per-subtest
  "usable" definitions) → Tasks 1/2 with the ≥2-valid-values pin.
- Spec §4 (calibration untouched; refresh-on-ingest of ALL fits; Eq. 5.1
  curves) → Task 4; `p_bar(r², 1)` ≡ ordinary form keeps old tests green.
- Spec §5 endpoints/uniqueness/overwrite → Task 3. Spec §6 Spanish-only
  participant strings → Task 6 (`strings_es.ts` complete in-plan for review).
- Spec §7 testing → Tasks 1–5 unit suites + Task 8 e2e; the fit-refresh
  propagation test (second participant's screen changes the first's
  `hcf_value`) is Task 4's first test.
- Type-consistency check: `score_screen` keys = `METRICS` subtest keys =
  payload sections = TS `ScreenPayload` fields; `HCFEstimate.components`
  carries floats plus `screen_version` (int) — JSON-safe.
