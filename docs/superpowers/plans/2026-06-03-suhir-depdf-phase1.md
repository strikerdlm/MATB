# Suhir DEPDF Mission-Outcome Layer (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `matb_integration/suhir/`, a read-only analysis layer that fits Suhir's (2018) double-exponential probability distribution function (DEPDF) and mission-outcome model from existing OpenMATB `log_converter` output, producing per-participant calibrated parameters and three actionable products.

**Architecture:** Pure-function model core (`depdf.py`) validated against the book's own published numbers (Table 5.1, Example 5.1); feature extractors (`failure_events.py`, `mwl.py`) that consume `log_converter` output; an HCF input contract (`hcf.py`); a FOAT calibrator (`calibration.py`) using `scipy.optimize`; a mission composer (`mission.py`); a reporting module (`report.py`); and a CLI (`cli.py`). Phase 1 runs with `F = F0` (Suhir Eq. 5.16 ordinary-capacity reduction).

**Tech Stack:** Python 3.12, numpy 2.4, scipy 1.17, PyYAML, pytest 9. Tests run from the repo root (`/root/repos/MATB`) as `from matb_integration.suhir.<mod> import ...`.

**Design spec:** `docs/superpowers/specs/2026-06-03-suhir-depdf-mission-outcome-design.md`

---

## File structure

| File | Responsibility |
|---|---|
| `matb_integration/suhir/__init__.py` | Package marker + version. |
| `matb_integration/suhir/depdf.py` | Stateless model math (Eq. 5.1, 5.2, 5.16, Weibull 5.5, entropy). |
| `matb_integration/suhir/failure_events.py` | Discrete failure extraction from raw rows + Weibull/MTTF metrics. |
| `matb_integration/suhir/failure_criteria.yaml` | Pre-registered per-task failure criteria. |
| `matb_integration/suhir/mwl.py` | Normalize TLX/ISA/Bedford → absolute MWL + dimensionless `G/G0`; ISA timeseries. |
| `matb_integration/suhir/hcf.py` | `HCFEstimate` dataclass + `resolve()` (defaults to `F0_default`). |
| `matb_integration/suhir/calibration.py` | FOAT fit (5.19→G0, 5.20→P0, 5.21→τ0); Beta-update for P0. |
| `matb_integration/suhir/mission.py` | Segment composition → mission failure `Q` (Eq. 5.10). |
| `matb_integration/suhir/report.py` | Training target, participant ranking. |
| `matb_integration/suhir/cli.py` | `matb-suhir fit` / `matb-suhir mission`. |
| `tests/suhir/test_*.py` | One test module per source module. |

**Out of scope for this plan (separate sub-projects, see spec §11):** neurocognitive-screen internals, the adaptive-automation engine, the Ch. 9 symptom term (`γ_S·S·t`), BIDS-derivative file naming (the substance — a params JSON — is produced by `cli fit`; BIDS naming is a thin downstream wrapper).

---

### Task 1: Package scaffold + DEPDF model core

The model core is validated against the book's exact published numbers. In Table 5.1 the row/column indices are the **squared** ratios `f2 = F²/F0²` and `g2 = G²/G0²`. Verified cells: `p_bar(g2=1, f2=any) = 1`; `p_bar(g2=2, f2=1) = 0.3679`; `p_bar(g2=3, f2=1) = 0.1353`; `p_bar(g2=2, f2=2) = 0.6922`; `p_bar(g2=2, f2=3) = 0.8734`.

**Files:**
- Create: `matb_integration/suhir/__init__.py`
- Create: `matb_integration/suhir/depdf.py`
- Test: `tests/suhir/__init__.py`, `tests/suhir/test_depdf.py`

- [ ] **Step 1: Create the test package marker**

Create `tests/suhir/__init__.py` (empty file):

```python
```

- [ ] **Step 2: Write the failing test against Table 5.1 / Example 5.1**

Create `tests/suhir/test_depdf.py`:

```python
from __future__ import annotations

import math

import pytest

from matb_integration.suhir.depdf import (
    p_bar,
    p_nonfailure_basic,
    p_nonfailure_ordinary,
    weibull_nonfailure,
    entropy,
)

# Table 5.1 cells, indexed by squared ratios (g2 = G^2/G0^2, f2 = F^2/F0^2).
@pytest.mark.parametrize(
    "g2, f2, expected",
    [
        (1, 1, 1.0),
        (1, 5, 1.0),       # g2 = 1 (normal MWL) -> P_bar = 1 for any HCF
        (2, 1, 0.3679),
        (3, 1, 0.1353),
        (4, 1, 0.0498),
        (10, 1, 1.234e-4),
        (2, 2, 0.6922),
        (2, 3, 0.8734),
        (4, 3, 0.6663),
    ],
)
def test_p_bar_matches_table_5_1(g2, f2, expected):
    assert p_bar(g2, f2) == pytest.approx(expected, rel=1e-3)


def test_p_bar_monotonic_in_mwl():
    # Higher MWL -> lower nonfailure probability (fixed HCF).
    assert p_bar(2, 2) > p_bar(4, 2) > p_bar(8, 2)


def test_p_bar_monotonic_in_hcf():
    # Higher HCF -> higher nonfailure probability (fixed MWL).
    assert p_bar(4, 1) < p_bar(4, 3) < p_bar(4, 5)


def test_p_nonfailure_basic_scales_by_p0():
    # P^h = P0 * p_bar((G/G0)^2, (F/F0)^2). G/G0=sqrt(2), F/F0=1 -> g2=2,f2=1.
    p0 = 0.99
    got = p_nonfailure_basic(p0=p0, g=math.sqrt(2.0), g0=1.0, f=1.0, f0=1.0)
    assert got == pytest.approx(0.99 * 0.3679, rel=1e-3)


def test_ordinary_is_basic_with_f_equal_f0():
    # Eq 5.16 must equal Eq 5.1 when F = F0.
    basic = p_nonfailure_basic(p0=0.99, g=2.0, g0=1.0, f=1.0, f0=1.0)
    ordinary = p_nonfailure_ordinary(p0=0.99, g=2.0, g0=1.0)
    assert ordinary == pytest.approx(basic, rel=1e-9)


def test_weibull_nonfailure_example_5_1():
    # Example 5.1: lam=8e-4 /h, t=4 h, beta=2 -> ~0.99999.
    assert weibull_nonfailure(lam=8e-4, t=4.0, beta=2.0) == pytest.approx(0.99999, abs=1e-5)


def test_entropy_zero_at_bounds_max_at_1_over_e():
    assert entropy(0.0) == pytest.approx(0.0)
    assert entropy(1.0) == pytest.approx(0.0)
    assert entropy(1.0 / math.e) == pytest.approx(1.0 / math.e, rel=1e-6)
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/test_depdf.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'matb_integration.suhir'`.

- [ ] **Step 4: Create the package marker**

Create `matb_integration/suhir/__init__.py`:

```python
"""matb_integration.suhir — Suhir (2018) DEPDF mission-outcome analysis layer.

Read-only over log_converter output. Phase 1 implements the basic DEPDF
(Eq. 5.1 / 5.16) and mission-outcome composition (Eq. 5.10).
"""

from __future__ import annotations

__version__ = "0.1.0"
```

- [ ] **Step 5: Implement the model core**

Create `matb_integration/suhir/depdf.py`:

```python
"""Stateless Suhir DEPDF model math.

All references are to Suhir, *Human-in-the-Loop: Probabilistic Modeling of an
Aerospace Mission Outcome*, CRC Press, 2018. Equation numbers cited inline.
"""

from __future__ import annotations

import math


def p_bar(g2: float, f2: float) -> float:
    """Relative human-nonfailure probability P^h/P0 (Eq. 5.2).

    Args:
        g2: squared MWL ratio G^2/G0^2 (>= 1 in off-normal conditions).
        f2: squared HCF ratio F^2/F0^2 (>= 1).

    Returns:
        Dimensionless ratio in (0, 1]. Validated against book Table 5.1.
    """
    return math.exp((1.0 - g2) * math.exp(1.0 - f2))


def p_nonfailure_basic(p0: float, g: float, g0: float, f: float, f0: float) -> float:
    """Human-nonfailure probability with HCF (Eq. 5.1)."""
    return p0 * p_bar((g / g0) ** 2, (f / f0) ** 2)


def p_nonfailure_ordinary(p0: float, g: float, g0: float) -> float:
    """Ordinary-capacity reduction F = F0 (Eq. 5.16)."""
    return p0 * math.exp(1.0 - (g / g0) ** 2)


def weibull_nonfailure(lam: float, t: float, beta: float) -> float:
    """Time-degraded nonfailure probability, Weibull form (Eq. 5.5 / 5.24)."""
    return math.exp(-((lam * t) ** beta))


def entropy(p: float) -> float:
    """Distribution entropy H = -P ln P (used in Eq. 5.3); H(0)=H(1)=0."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -p * math.log(p)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/test_depdf.py -q`
Expected: PASS (10 passed).

- [ ] **Step 7: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/suhir/__init__.py matb_integration/suhir/depdf.py tests/suhir/__init__.py tests/suhir/test_depdf.py
git commit -m "feat(suhir): DEPDF model core validated vs book Table 5.1"
```

---

### Task 2: Discrete failure-event extraction

Raw OpenMATB rows are dicts with keys `type`, `module`, `address`, `value`, `scenario_time` (see `matb_integration/log_converter.py:126-167`). A SYSMON miss is `type=="performance"`, `module=="sysmon"`, `address=="signal_detection"`, `value=="MISS"`. We also provide a generic threshold-excursion extractor for TRACK/RESMAN continuous signals.

**Files:**
- Create: `matb_integration/suhir/failure_criteria.yaml`
- Create: `matb_integration/suhir/failure_events.py`
- Test: `tests/suhir/test_failure_events.py`

- [ ] **Step 1: Write the failing test**

Create `tests/suhir/test_failure_events.py`:

```python
from __future__ import annotations

import math

import pytest

from matb_integration.suhir.failure_events import (
    sysmon_failure_times,
    threshold_excursions,
    failure_metrics,
)


def _row(t, value, module="sysmon", address="signal_detection"):
    return {
        "scenario_time": str(t),
        "type": "performance",
        "module": module,
        "address": address,
        "value": value,
    }


def test_sysmon_failure_times_picks_misses_in_order():
    rows = [
        _row(10.0, "HIT"),
        _row(25.0, "MISS"),
        _row(5.0, "MISS"),
        _row(40.0, "FA"),
        _row(60.0, "MISS"),
    ]
    assert sysmon_failure_times(rows) == [5.0, 25.0, 60.0]


def test_threshold_excursions_requires_min_duration():
    # values outside [lo, hi]; only sustained breaches >= min_dur count.
    samples = [
        (0.0, 0.0), (1.0, 0.0),   # in band
        (2.0, 5.0), (2.5, 5.0),   # breach lasting 0.5 s
        (3.0, 0.0),               # back in band
        (4.0, 9.0),               # single-sample breach (0 s)
        (5.0, 0.0),
    ]
    out = threshold_excursions(samples, lo=-1.0, hi=1.0, min_dur=0.4)
    assert out == [2.0]  # only the 0.5 s breach; start time reported


def test_failure_metrics_mttf_and_rate():
    # failures at t = 10, 30, 60 over a 90 s block -> 3 failures.
    m = failure_metrics([10.0, 30.0, 60.0], duration_s=90.0)
    assert m["n_failures"] == 3
    # MTTF = mean inter-failure interval incl. time-to-first from t=0.
    # intervals: 10, 20, 30 -> mean 20.0
    assert m["mttf_s"] == pytest.approx(20.0)
    assert m["lambda_per_s"] == pytest.approx(1.0 / 20.0)


def test_failure_metrics_no_failures_is_censored():
    m = failure_metrics([], duration_s=90.0)
    assert m["n_failures"] == 0
    assert m["mttf_s"] is None
    assert m["lambda_per_s"] == pytest.approx(0.0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/test_failure_events.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'matb_integration.suhir.failure_events'`.

- [ ] **Step 3: Write the pre-registered criteria config**

Create `matb_integration/suhir/failure_criteria.yaml`:

```yaml
# Pre-registered discrete failure criteria (Suhir Phase 1). Fixed before any fit.
# version is bumped on any change; recorded in fit output for provenance.
version: 1
sysmon:
  kind: discrete_event
  match: {type: performance, module: sysmon, address: signal_detection, value: MISS}
comm:
  kind: discrete_event
  match: {type: performance, module: communications, address: sdt_value, value: MISS}
track:
  kind: threshold_excursion
  signal: {type: performance, module: track, address: cursor_radius}
  lo: -150.0          # px from centre; tune per scenario
  hi: 150.0
  min_dur: 0.5        # seconds sustained outside band
resman:
  kind: threshold_excursion
  signal: {type: performance, module: resman, address: tank_level_deviation}
  lo: -500.0
  hi: 500.0
  min_dur: 2.0
```

- [ ] **Step 4: Implement the extractor**

Create `matb_integration/suhir/failure_events.py`:

```python
"""Discrete failure-event extraction from raw OpenMATB rows.

A "failure" is a discrete per-task error event (Suhir's "error = failure").
Raw rows are dicts as produced by matb_integration.log_converter.parse_csv.
"""

from __future__ import annotations

import statistics
from typing import Any


def _to_float(s: Any) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def sysmon_failure_times(rows: list[dict[str, str]]) -> list[float]:
    """Sorted scenario times of SYSMON MISS events."""
    times = [
        t
        for r in rows
        if r.get("type") == "performance"
        and r.get("module") == "sysmon"
        and r.get("address") == "signal_detection"
        and r.get("value", "").upper() == "MISS"
        and (t := _to_float(r.get("scenario_time"))) is not None
    ]
    return sorted(times)


def threshold_excursions(
    samples: list[tuple[float, float]], lo: float, hi: float, min_dur: float
) -> list[float]:
    """Start times of breaches outside [lo, hi] sustained for >= min_dur seconds.

    Args:
        samples: (time, value) pairs, assumed time-ordered.
        lo, hi: inclusive in-band limits.
        min_dur: minimum sustained breach duration to count as one failure.
    """
    samples = sorted(samples, key=lambda s: s[0])
    out: list[float] = []
    breach_start: float | None = None
    last_t = None
    for t, v in samples:
        outside = v < lo or v > hi
        if outside and breach_start is None:
            breach_start = t
        elif not outside and breach_start is not None:
            if last_t is not None and (last_t - breach_start) >= min_dur:
                out.append(breach_start)
            breach_start = None
        last_t = t
    if breach_start is not None and last_t is not None and (last_t - breach_start) >= min_dur:
        out.append(breach_start)
    return out


def failure_metrics(failure_times: list[float], duration_s: float) -> dict[str, Any]:
    """MTTF, failure rate, and count from discrete failure times.

    MTTF is the mean inter-failure interval, counting time-to-first-failure
    from t=0. With no failures the block is right-censored: mttf undefined,
    rate 0.
    """
    times = sorted(failure_times)
    n = len(times)
    if n == 0:
        return {"n_failures": 0, "mttf_s": None, "lambda_per_s": 0.0}
    intervals = [times[0]] + [times[i] - times[i - 1] for i in range(1, n)]
    mttf = statistics.mean(intervals)
    return {
        "n_failures": n,
        "mttf_s": mttf,
        "lambda_per_s": (1.0 / mttf) if mttf > 0 else 0.0,
    }
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/test_failure_events.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/suhir/failure_events.py matb_integration/suhir/failure_criteria.yaml tests/suhir/test_failure_events.py
git commit -m "feat(suhir): discrete failure-event extraction + MTTF metrics"
```

---

### Task 3: MWL normalization

`log_converter.convert_session` returns a record dict with `nasatlx["raw_tlx"]`, `isa["mean"]`, `isa["probes"]` (list of `{scenario_time, value}`), and `bedford["value"]`. MWL `G` is the chosen scalar; `G0` is the participant's own LOW-block value; the dimensionless ratio is `G/G0`. Multiple `source` choices feed the spec's normalization sensitivity analysis.

**Files:**
- Create: `matb_integration/suhir/mwl.py`
- Test: `tests/suhir/test_mwl.py`

- [ ] **Step 1: Write the failing test**

Create `tests/suhir/test_mwl.py`:

```python
from __future__ import annotations

import pytest

from matb_integration.suhir.mwl import absolute_mwl, mwl_ratio, isa_timeseries

LOW = {
    "nasatlx": {"raw_tlx": 40.0},
    "isa": {"mean": 2.0, "probes": [{"scenario_time": 0.0, "value": 2.0}]},
    "bedford": {"value": 3},
}
HIGH = {
    "nasatlx": {"raw_tlx": 80.0},
    "isa": {"mean": 4.0, "probes": [
        {"scenario_time": 0.0, "value": 3.0},
        {"scenario_time": 90.0, "value": 5.0},
    ]},
    "bedford": {"value": 7},
}


def test_absolute_mwl_sources():
    assert absolute_mwl(HIGH, source="raw_tlx") == 80.0
    assert absolute_mwl(HIGH, source="isa_mean") == 4.0
    assert absolute_mwl(HIGH, source="bedford") == 7.0


def test_mwl_ratio_anchored_to_low_block():
    assert mwl_ratio(HIGH, LOW, source="raw_tlx") == pytest.approx(2.0)
    assert mwl_ratio(HIGH, LOW, source="isa_mean") == pytest.approx(2.0)


def test_mwl_ratio_unknown_source_raises():
    with pytest.raises(ValueError):
        absolute_mwl(HIGH, source="nonsense")


def test_isa_timeseries_returns_sorted_pairs():
    assert isa_timeseries(HIGH) == [(0.0, 3.0), (90.0, 5.0)]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/test_mwl.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'matb_integration.suhir.mwl'`.

- [ ] **Step 3: Implement the normalizer**

Create `matb_integration/suhir/mwl.py`:

```python
"""MWL normalization from log_converter records.

G0 is anchored within-participant to their LOW block (Suhir's comparative,
not absolute, framing). `source` selects which workload instrument supplies G,
enabling the normalization sensitivity analysis (spec §10).
"""

from __future__ import annotations

from typing import Any

_SOURCES = {
    "raw_tlx": lambda rec: rec["nasatlx"]["raw_tlx"],
    "isa_mean": lambda rec: rec["isa"]["mean"],
    "bedford": lambda rec: rec["bedford"]["value"],
}


def absolute_mwl(record: dict[str, Any], source: str = "raw_tlx") -> float:
    """Scalar absolute MWL G from one block record for the chosen instrument."""
    if source not in _SOURCES:
        raise ValueError(f"unknown MWL source {source!r}; choose from {sorted(_SOURCES)}")
    value = _SOURCES[source](record)
    if value is None:
        raise ValueError(f"MWL source {source!r} is missing/None in record")
    return float(value)


def mwl_ratio(record: dict[str, Any], baseline: dict[str, Any], source: str = "raw_tlx") -> float:
    """Dimensionless G/G0, anchored to the participant's baseline (LOW) block."""
    g = absolute_mwl(record, source)
    g0 = absolute_mwl(baseline, source)
    if g0 <= 0:
        raise ValueError("baseline MWL must be positive to form a ratio")
    return g / g0


def isa_timeseries(record: dict[str, Any]) -> list[tuple[float, float]]:
    """Time-resolved MWL G(t) from ISA probes, sorted by scenario time."""
    probes = record.get("isa", {}).get("probes", []) or []
    pairs = [
        (float(p["scenario_time"]), float(p["value"]))
        for p in probes
        if p.get("scenario_time") is not None and p.get("value") is not None
    ]
    return sorted(pairs, key=lambda x: x[0])
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/test_mwl.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/suhir/mwl.py tests/suhir/test_mwl.py
git commit -m "feat(suhir): MWL normalization (within-participant G/G0) + ISA timeseries"
```

---

### Task 4: HCF input contract

Suhir states HCF cannot be measured on the simulator; it is supplied externally (neurocognitive screen, a separate sub-project). This task fixes the contract and the `F0_default` fallback that lets Phase 1 run in the Eq. 5.16 form.

**Files:**
- Create: `matb_integration/suhir/hcf.py`
- Test: `tests/suhir/test_hcf.py`

- [ ] **Step 1: Write the failing test**

Create `tests/suhir/test_hcf.py`:

```python
from __future__ import annotations

from matb_integration.suhir.hcf import HCFEstimate, resolve, F0_DEFAULT


def test_resolve_defaults_to_f0_when_absent():
    est = resolve("P01", store=None)
    assert isinstance(est, HCFEstimate)
    assert est.source == "F0_default"
    assert est.value == F0_DEFAULT


def test_resolve_uses_store_when_present():
    store = {"P02": HCFEstimate("P02", value=2.5, source="screen", components={"wm": 2.5})}
    est = resolve("P02", store=store)
    assert est.value == 2.5
    assert est.source == "screen"


def test_resolve_missing_id_in_store_falls_back():
    store = {"P02": HCFEstimate("P02", 2.5, "screen", {})}
    est = resolve("P99", store=store)
    assert est.source == "F0_default"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/test_hcf.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'matb_integration.suhir.hcf'`.

- [ ] **Step 3: Implement the contract**

Create `matb_integration/suhir/hcf.py`:

```python
"""HCF (human capacity factor) input contract.

HCF cannot be produced by the simulator (Suhir §5.9, §9.5); it is supplied by
an external baseline neurocognitive screen (separate sub-project). When no
estimate exists, the model runs in the Eq. 5.16 ordinary-capacity form, i.e.
F = F0 (ratio 1.0), which is mathematically exact, not a placeholder.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Dimensionless baseline HCF: F = F0 -> F/F0 = 1.0.
F0_DEFAULT = 1.0


@dataclass
class HCFEstimate:
    participant_id: str
    value: float                                   # dimensionless, MWL-scale
    source: str = "F0_default"                     # "screen" | "metadata_fom" | "F0_default"
    components: dict[str, float] = field(default_factory=dict)


def resolve(participant_id: str, store: dict[str, HCFEstimate] | None = None) -> HCFEstimate:
    """Return the screen-derived HCF if present, else the F0 default."""
    if store is not None and participant_id in store:
        return store[participant_id]
    return HCFEstimate(participant_id=participant_id, value=F0_DEFAULT, source="F0_default")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/test_hcf.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/suhir/hcf.py tests/suhir/test_hcf.py
git commit -m "feat(suhir): HCF input contract with F0 default (Eq 5.16 form)"
```

---

### Task 5: FOAT calibration (G0, P0, τ0)

Suhir's calibration (Eq. 5.18–5.21): from three MWL levels `G1<G2<G3` with measured times-to-failure `τ1,τ2,τ3`, solve the transcendental Eq. 5.19 for `G0`, then Eq. 5.20 for `P0`, Eq. 5.21 for `τ0`. The round-trip test is the oracle: pick known `G0,P0,τ0`, synthesize `τ_i` via `τ_i = τ0 / (1 - P0·exp(1 - G_i²/G0²))`, and assert recovery.

**Files:**
- Create: `matb_integration/suhir/calibration.py`
- Test: `tests/suhir/test_calibration.py`

- [ ] **Step 1: Write the failing test**

Create `tests/suhir/test_calibration.py`:

```python
from __future__ import annotations

import math

import pytest

from matb_integration.suhir.calibration import (
    synth_tau,
    solve_g0,
    estimate_p0,
    estimate_tau0,
    beta_update_p0,
)

# Ground truth for the round-trip recovery test.
G0_TRUE, P0_TRUE, TAU0_TRUE = 40.0, 0.99, 12.0
G1, G2, G3 = 44.0, 60.0, 80.0


def _taus():
    return [synth_tau(g, G0_TRUE, P0_TRUE, TAU0_TRUE) for g in (G1, G2, G3)]


def test_synth_tau_increases_with_mwl_severity():
    t1, t2, t3 = _taus()
    # Higher MWL -> higher failure probability -> shorter time-to-failure.
    assert t1 > t2 > t3


def test_solve_g0_recovers_ground_truth():
    t1, t2, t3 = _taus()
    g0 = solve_g0([(G1, t1), (G2, t2), (G3, t3)])
    assert g0 == pytest.approx(G0_TRUE, rel=1e-3)


def test_estimate_p0_recovers_ground_truth():
    t1, t2, t3 = _taus()
    p0 = estimate_p0(G1, G2, t1, t2, g0=G0_TRUE)
    assert p0 == pytest.approx(P0_TRUE, rel=1e-3)


def test_estimate_tau0_recovers_ground_truth():
    t1, _, _ = _taus()
    tau0 = estimate_tau0(G1, t1, g0=G0_TRUE, p0=P0_TRUE)
    assert tau0 == pytest.approx(TAU0_TRUE, rel=1e-3)


def test_beta_update_pulls_toward_observed():
    # 98 nonfailures / 100 trials, weak prior Beta(1,1) -> ~0.9706.
    post = beta_update_p0(n_nonfail=98, n_total=100, prior_a=1.0, prior_b=1.0)
    assert post == pytest.approx(99.0 / 102.0, rel=1e-6)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/test_calibration.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'matb_integration.suhir.calibration'`.

- [ ] **Step 3: Implement the calibrator**

Create `matb_integration/suhir/calibration.py`:

```python
"""FOAT calibration of the steady-state DEPDF (Suhir Eq. 5.18-5.21).

Given three MWL levels with measured times-to-failure, recover the baseline
parameters G0, P0, tau0. P0 may instead be stabilized at small N via the
Beta-distribution reliability update (Suhir Ch. 2.4.10).
"""

from __future__ import annotations

import math

from scipy.optimize import brentq


def _qh(g: float, g0: float, p0: float) -> float:
    """Failure probability Q_h(G) = 1 - P0*exp(1 - G^2/G0^2) (Eq. 5.17)."""
    return 1.0 - p0 * math.exp(1.0 - (g / g0) ** 2)


def synth_tau(g: float, g0: float, p0: float, tau0: float) -> float:
    """Time-to-failure at MWL g (Eq. 5.18). Used as the round-trip oracle."""
    return tau0 / _qh(g, g0, p0)


def _eq_5_19(g0: float, g1: float, g2: float, g3: float, r12: float, r23: float) -> float:
    """LHS of Eq. 5.19; root in g0. r12 = tau1/tau2, r23 = tau2/tau3."""
    e1 = math.exp(1.0 - (g1 / g0) ** 2)
    e2 = math.exp(1.0 - (g2 / g0) ** 2)
    e3 = math.exp(1.0 - (g3 / g0) ** 2)
    return (1.0 - r12) * (e3 - r23 * e2) - (1.0 - r23) * (e2 - r12 * e1)


def solve_g0(levels: list[tuple[float, float]]) -> float:
    """Solve Eq. 5.19 for G0 from three (MWL, time-to-failure) pairs.

    Brackets the root by scanning (0, min(G)] for a sign change, then brentq.
    """
    levels = sorted(levels, key=lambda x: x[0])
    (g1, t1), (g2, t2), (g3, t3) = levels
    r12, r23 = t1 / t2, t2 / t3

    def f(g0: float) -> float:
        return _eq_5_19(g0, g1, g2, g3, r12, r23)

    hi = g1 * 0.999
    lo = g1 * 1e-3
    n = 2000
    step = (hi - lo) / n
    prev_x = lo
    prev_y = f(prev_x)
    for i in range(1, n + 1):
        x = lo + i * step
        y = f(x)
        if prev_y == 0.0:
            return prev_x
        if prev_y * y < 0.0:
            return brentq(f, prev_x, x, xtol=1e-9)
        prev_x, prev_y = x, y
    raise ValueError("no G0 root found in (0, min(G)); check input times-to-failure")


def estimate_p0(g1: float, g2: float, t1: float, t2: float, g0: float) -> float:
    """P0 from two levels and the solved G0 (Eq. 5.20, first form)."""
    r12 = t1 / t2
    e2 = math.exp(1.0 - (g2 / g0) ** 2)
    e1 = math.exp(1.0 - (g1 / g0) ** 2)
    return (1.0 - r12) / (e2 - r12 * e1)


def estimate_tau0(g1: float, t1: float, g0: float, p0: float) -> float:
    """tau0 from one level and solved G0, P0 (Eq. 5.21)."""
    return t1 * (1.0 - p0 * math.exp(1.0 - (g1 / g0) ** 2))


def beta_update_p0(n_nonfail: int, n_total: int, prior_a: float = 1.0, prior_b: float = 1.0) -> float:
    """Posterior mean of P0 via Beta-Binomial update (Suhir Ch. 2.4.10).

    Posterior Beta(a + nonfail, b + fail); mean = (a+s)/(a+b+n).
    """
    s = n_nonfail
    n = n_total
    a, b = prior_a + s, prior_b + (n - s)
    return a / (a + b)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/test_calibration.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/suhir/calibration.py tests/suhir/test_calibration.py
git commit -m "feat(suhir): FOAT calibration (Eq 5.19-5.21) + Beta-update for P0"
```

---

### Task 6: Mission-outcome composition

Eq. 5.10: `Q = 1 - Σ q_i · P^e_i(t_i) · P^h_i(t_i)`. Validate against Example 5.1, which yields mission failure `Q = 1%`.

**Files:**
- Create: `matb_integration/suhir/mission.py`
- Test: `tests/suhir/test_mission.py`

- [ ] **Step 1: Write the failing test**

Create `tests/suhir/test_mission.py`:

```python
from __future__ import annotations

import pytest

from matb_integration.suhir.mission import Segment, mission_failure_Q


def test_normalization_violation_raises():
    segs = [Segment(q=0.6, p_human=0.99, lam_e=0.0, t=1.0, beta_e=2.0)]
    with pytest.raises(ValueError):  # q sums to 0.6, not 1.0
        mission_failure_Q(segs)


def test_example_5_1_gives_one_percent():
    # Example 5.1: 6 segments, equal P^e*P^h = 0.9900 each, q_i sum to 1.
    qs = [0.9530, 0.0399, 0.0050, 0.0010, 0.0006, 0.0005]
    segs = [
        Segment(q=q, p_human=0.9900, lam_e=0.0, t=4.0, beta_e=2.0)
        for q in qs
    ]
    # lam_e = 0 -> P^e = 1, so weighted sum = 0.99 -> Q = 0.01.
    assert mission_failure_Q(segs) == pytest.approx(0.01, abs=1e-4)


def test_equipment_weibull_lowers_nonfailure():
    segs = [Segment(q=1.0, p_human=1.0, lam_e=0.1, t=5.0, beta_e=2.0)]
    q = mission_failure_Q(segs)
    assert 0.0 < q < 1.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/test_mission.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'matb_integration.suhir.mission'`.

- [ ] **Step 3: Implement the composer**

Create `matb_integration/suhir/mission.py`:

```python
"""Mission-outcome composition (Suhir Eq. 5.8-5.10).

Combines per-segment human nonfailure, equipment Weibull nonfailure, and
environment-severity weights q_i (which must sum to 1, Eq. 5.9).
"""

from __future__ import annotations

from dataclasses import dataclass

from matb_integration.suhir.depdf import weibull_nonfailure


@dataclass
class Segment:
    q: float          # probability of the anticipated harsh environment (Eq. 5.9)
    p_human: float    # P^h_i(0): human nonfailure at segment start (Eq. 5.7)
    lam_e: float      # equipment failure rate (1/time)
    t: float          # elapsed time on the segment
    beta_e: float     # equipment Weibull shape parameter


def mission_failure_Q(segments: list[Segment], tol: float = 1e-6) -> float:
    """Overall mission failure probability Q (Eq. 5.10)."""
    total_q = sum(s.q for s in segments)
    if abs(total_q - 1.0) > tol:
        raise ValueError(f"segment q_i must sum to 1 (Eq. 5.9); got {total_q}")
    success = 0.0
    for s in segments:
        p_e = weibull_nonfailure(s.lam_e, s.t, s.beta_e) if s.lam_e > 0 else 1.0
        success += s.q * p_e * s.p_human
    return 1.0 - success
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/test_mission.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/suhir/mission.py tests/suhir/test_mission.py
git commit -m "feat(suhir): mission-outcome composition validated vs Example 5.1"
```

---

### Task 7: Actionable reports

The three products from spec §9 that are pure functions of fitted parameters: the individualized training target (the MWL ratio at which `P^h` crosses a threshold) and the selection ranking.

**Files:**
- Create: `matb_integration/suhir/report.py`
- Test: `tests/suhir/test_report.py`

- [ ] **Step 1: Write the failing test**

Create `tests/suhir/test_report.py`:

```python
from __future__ import annotations

import math

import pytest

from matb_integration.suhir.report import training_target_ratio, rank_participants


def test_training_target_ratio_solves_threshold():
    # Ordinary form: P^h = P0*exp(1 - (G/G0)^2). With P0=0.99, threshold 0.5:
    # 0.5 = 0.99*exp(1 - r^2) -> r = sqrt(1 - ln(0.5/0.99)).
    r = training_target_ratio(p0=0.99, threshold=0.5)
    expected = math.sqrt(1.0 - math.log(0.5 / 0.99))
    assert r == pytest.approx(expected, rel=1e-6)


def test_training_target_capped_at_factor_three():
    # Suhir: beyond G/G0 = 3 the model saturates; report caps at 3.0.
    r = training_target_ratio(p0=0.999999, threshold=1e-9)
    assert r == pytest.approx(3.0)


def test_rank_participants_orders_by_capacity():
    rows = [
        {"participant_id": "P01", "target_ratio": 1.5},
        {"participant_id": "P02", "target_ratio": 2.8},
        {"participant_id": "P03", "target_ratio": 2.1},
    ]
    ranked = rank_participants(rows)
    assert [r["participant_id"] for r in ranked] == ["P02", "P03", "P01"]
    assert ranked[0]["rank"] == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/test_report.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'matb_integration.suhir.report'`.

- [ ] **Step 3: Implement the reports**

Create `matb_integration/suhir/report.py`:

```python
"""Actionable products derived from fitted DEPDF parameters (spec §9).

- training_target_ratio: the MWL ratio G/G0 at which ordinary-capacity
  nonfailure drops to a chosen threshold (operationalizes Suhir's
  "trained to factor-of-3" guidance; capped at 3.0 where the model saturates).
- rank_participants: selection ranking by tolerated MWL.
"""

from __future__ import annotations

import math
from typing import Any

# Suhir: F/F0 and G/G0 above ~3.0 have negligible further effect (§5.3, §9.6).
SATURATION_RATIO = 3.0


def training_target_ratio(p0: float, threshold: float) -> float:
    """G/G0 where P^h(G) = threshold in the ordinary-capacity form (Eq. 5.16).

    P^h = p0*exp(1 - r^2) = threshold  ->  r = sqrt(1 - ln(threshold/p0)).
    Capped at SATURATION_RATIO; floored at 1.0 (baseline).
    """
    if not (0.0 < threshold <= p0):
        raise ValueError("threshold must be in (0, p0]")
    r = math.sqrt(max(0.0, 1.0 - math.log(threshold / p0)))
    return min(max(r, 1.0), SATURATION_RATIO)


def rank_participants(rows: list[dict[str, Any]], key: str = "target_ratio") -> list[dict[str, Any]]:
    """Return rows sorted by `key` descending, each annotated with 1-based rank."""
    ranked = sorted(rows, key=lambda r: r[key], reverse=True)
    return [{**r, "rank": i + 1} for i, r in enumerate(ranked)]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/test_report.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/suhir/report.py tests/suhir/test_report.py
git commit -m "feat(suhir): training-target and selection-ranking reports"
```

---

### Task 8: End-to-end fit pipeline + CLI

Wire the modules: given per-participant block records (LOW/MEDIUM/HIGH) and their raw rows, produce a fitted-parameters dict and write it as JSON. The orchestration function `fit_participant` is unit-tested with synthetic inputs; the CLI is a thin wrapper.

**Files:**
- Create: `matb_integration/suhir/pipeline.py`
- Create: `matb_integration/suhir/cli.py`
- Test: `tests/suhir/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

Create `tests/suhir/test_pipeline.py`:

```python
from __future__ import annotations

import json

import pytest

from matb_integration.suhir.calibration import synth_tau
from matb_integration.suhir.pipeline import fit_participant

G0_TRUE, P0_TRUE, TAU0_TRUE = 40.0, 0.99, 12.0


def _block(raw_tlx, failure_times, duration):
    """Build a minimal (record, raw_rows) pair the pipeline consumes."""
    record = {
        "nasatlx": {"raw_tlx": raw_tlx},
        "isa": {"mean": raw_tlx / 20.0, "probes": []},
        "bedford": {"value": raw_tlx / 10.0},
        "scenario_time_max_s": duration,
    }
    rows = [
        {"scenario_time": str(t), "type": "performance",
         "module": "sysmon", "address": "signal_detection", "value": "MISS"}
        for t in failure_times
    ]
    return record, rows


def _failures_for(g, duration):
    """Synthesize SYSMON MISS times whose MTTF matches synth_tau(g)."""
    tau = synth_tau(g, G0_TRUE, P0_TRUE, TAU0_TRUE)
    times, t = [], tau
    while t < duration:
        times.append(round(t, 3))
        t += tau
    return times


def test_fit_participant_recovers_parameters_and_serializes():
    duration = 100000.0  # long block so MTTF ~ tau
    blocks = {
        "LOW":    _block(44.0, _failures_for(44.0, duration), duration),
        "MEDIUM": _block(60.0, _failures_for(60.0, duration), duration),
        "HIGH":   _block(80.0, _failures_for(80.0, duration), duration),
    }
    out = fit_participant("P01", blocks, source="raw_tlx")
    assert out["participant_id"] == "P01"
    assert out["g0"] == pytest.approx(G0_TRUE, rel=2e-2)
    assert out["p0"] == pytest.approx(P0_TRUE, rel=2e-2)
    assert out["hcf_source"] == "F0_default"
    assert out["criteria_version"] == 1
    # Must be JSON-serializable.
    json.dumps(out)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/test_pipeline.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'matb_integration.suhir.pipeline'`.

- [ ] **Step 3: Implement the pipeline**

Create `matb_integration/suhir/pipeline.py`:

```python
"""End-to-end per-participant DEPDF fit.

Consumes block records (from log_converter.convert_session) plus their raw rows
(from log_converter.parse_csv), one each for LOW/MEDIUM/HIGH. Produces a fitted
parameter dict suitable for json.dump.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from matb_integration.suhir import hcf
from matb_integration.suhir.calibration import estimate_p0, estimate_tau0, solve_g0
from matb_integration.suhir.failure_events import failure_metrics, sysmon_failure_times
from matb_integration.suhir.mwl import absolute_mwl

_CRITERIA_PATH = Path(__file__).with_name("failure_criteria.yaml")


def _criteria_version() -> int:
    with open(_CRITERIA_PATH, encoding="utf-8") as fh:
        return int(yaml.safe_load(fh)["version"])


def fit_participant(
    participant_id: str,
    blocks: dict[str, tuple[dict[str, Any], list[dict[str, str]]]],
    source: str = "raw_tlx",
    hcf_store: dict[str, hcf.HCFEstimate] | None = None,
) -> dict[str, Any]:
    """Fit G0, P0, tau0 for one participant from LOW/MEDIUM/HIGH blocks.

    Args:
        participant_id: e.g. "P01".
        blocks: maps level name -> (record, raw_rows).
        source: MWL instrument for the calibration levels.
        hcf_store: optional external HCF estimates; absent -> F0 default.
    """
    levels: list[tuple[float, float]] = []
    per_level: dict[str, Any] = {}
    for name, (record, rows) in blocks.items():
        g = absolute_mwl(record, source)
        duration = float(record.get("scenario_time_max_s") or 0.0)
        metrics = failure_metrics(sysmon_failure_times(rows), duration)
        per_level[name] = {"mwl": g, **metrics}
        if metrics["mttf_s"] is not None:
            levels.append((g, metrics["mttf_s"]))

    if len(levels) < 3:
        raise ValueError(
            f"need 3 MWL levels with observed failures to fit; got {len(levels)}"
        )
    levels.sort(key=lambda x: x[0])
    (g1, t1), (g2, t2), (g3, _t3) = levels
    g0 = solve_g0(levels)
    p0 = estimate_p0(g1, g2, t1, t2, g0=g0)
    tau0 = estimate_tau0(g1, t1, g0=g0, p0=p0)
    hcf_est = hcf.resolve(participant_id, store=hcf_store)

    return {
        "participant_id": participant_id,
        "mwl_source": source,
        "criteria_version": _criteria_version(),
        "g0": g0,
        "p0": p0,
        "tau0": tau0,
        "hcf_value": hcf_est.value,
        "hcf_source": hcf_est.source,
        "per_level": per_level,
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/test_pipeline.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Implement the CLI wrapper**

Create `matb_integration/suhir/cli.py`:

```python
"""CLI for the Suhir DEPDF layer.

Usage:
    python3 -m matb_integration.suhir.cli fit \
        --participant P01 \
        --low  LOW.csv  --medium MED.csv --high HIGH.csv \
        --source raw_tlx --out P01_suhir.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from matb_integration.log_converter import convert_session, parse_csv
from matb_integration.suhir.pipeline import fit_participant


def _build_block(csv_path: str, level: str):
    path = Path(csv_path)
    record = convert_session(path, workload_level=level)
    rows = parse_csv(path)
    return record, rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="matb-suhir")
    sub = parser.add_subparsers(dest="cmd", required=True)

    fit = sub.add_parser("fit", help="fit per-participant DEPDF parameters")
    fit.add_argument("--participant", required=True)
    fit.add_argument("--low", required=True)
    fit.add_argument("--medium", required=True)
    fit.add_argument("--high", required=True)
    fit.add_argument("--source", default="raw_tlx")
    fit.add_argument("--out", required=True)

    args = parser.parse_args(argv)
    if args.cmd == "fit":
        blocks = {
            "LOW": _build_block(args.low, "LOW"),
            "MEDIUM": _build_block(args.medium, "MEDIUM"),
            "HIGH": _build_block(args.high, "HIGH"),
        }
        out = fit_participant(args.participant, blocks, source=args.source)
        Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Verify the CLI help runs (no crash on import)**

Run: `cd /root/repos/MATB && python3 -m matb_integration.suhir.cli fit --help`
Expected: argparse usage text for the `fit` subcommand prints; exit 0.

- [ ] **Step 7: Run the whole suite**

Run: `cd /root/repos/MATB && python3 -m pytest tests/suhir/ -q`
Expected: PASS (all suhir tests green).

- [ ] **Step 8: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/suhir/pipeline.py matb_integration/suhir/cli.py tests/suhir/test_pipeline.py
git commit -m "feat(suhir): end-to-end fit pipeline + CLI"
```

---

### Task 9: Documentation + CHANGELOG

**Files:**
- Create: `matb_integration/suhir/README.md`
- Modify: `CHANGELOG.md` (add entry under `[Unreleased]`)

- [ ] **Step 1: Write the package README**

Create `matb_integration/suhir/README.md`:

```markdown
# suhir — DEPDF mission-outcome layer

Read-only analysis layer implementing Suhir (2018) *Human-in-the-Loop*
probabilistic mission-outcome model on OpenMATB `log_converter` output.

## What it computes
- `depdf.py` — basic DEPDF (Eq. 5.1), ordinary-capacity form (Eq. 5.16), Weibull degradation.
- `failure_events.py` — discrete per-task failures → MTTF, failure rate.
- `mwl.py` — within-participant MWL normalization (G/G0 anchored to LOW block).
- `hcf.py` — HCF input contract (external neurocognitive screen; F0 default).
- `calibration.py` — FOAT fit (Eq. 5.19–5.21) + Beta-update for P0.
- `mission.py` — mission failure Q (Eq. 5.10).
- `report.py` — training targets, selection ranking.
- `pipeline.py` / `cli.py` — end-to-end per-participant fit.

## Run
```bash
python3 -m matb_integration.suhir.cli fit \
  --participant P01 --low LOW.csv --medium MED.csv --high HIGH.csv \
  --source raw_tlx --out P01_suhir.json
```

## Validity (read before citing)
- Within-participant **comparative** model only (Suhir's framing); MWL ratios
  are anchored to each participant's LOW block.
- 3 MWL levels exactly-identify G0/P0/tau0 → no goodness-of-fit df.
- TLX/ISA/Bedford are ordinal/interval; run the `--source` sensitivity sweep.
- Phase 1 runs F = F0 (Eq. 5.16); per-participant HCF requires the external
  neurocognitive screen. Phase 2 adds the Ch. 9 physiological-symptom term.
- Research instrument — not a certified safety tool.

Spec: `docs/superpowers/specs/2026-06-03-suhir-depdf-mission-outcome-design.md`
```

- [ ] **Step 2: Add the CHANGELOG entry**

In `CHANGELOG.md`, under the `[Unreleased]` section's `### Added` list (create the `### Added` subheading if absent), add:

```markdown
- **Suhir DEPDF mission-outcome layer** (`matb_integration/suhir/`): implements
  Suhir (2018) probabilistic human-nonfailure (Eq. 5.1/5.16), FOAT calibration
  (Eq. 5.19–5.21), and mission-outcome composition (Eq. 5.10) on existing
  log_converter output. Model core validated against book Table 5.1 and
  Example 5.1. Phase 1 (F = F0); HCF via external neurocognitive screen.
```

- [ ] **Step 3: Run the full repository test suite (regression guard)**

Run: `cd /root/repos/MATB && python3 -m pytest -q`
Expected: previously-passing tests still pass; new suhir tests pass.

- [ ] **Step 4: Commit**

```bash
cd /root/repos/MATB
git add matb_integration/suhir/README.md CHANGELOG.md
git commit -m "docs(suhir): package README + CHANGELOG entry"
```

---

## Self-review notes (completed by plan author)

- **Spec coverage:** §4 modules → Tasks 1–8 (depdf/failure_events/mwl/hcf/calibration/mission + pipeline/cli; report adds §9 products). §6 failure spec → Task 2 + `failure_criteria.yaml`. §7 HCF contract → Task 4. §8 validation oracle (Table 5.1, Example 5.1) → Tasks 1 & 6. §9 actionable outputs 1–2 → Task 7; output 3 (adaptive-automation trigger) consumes `P^h(t)` from `depdf` + `mwl.isa_timeseries` and is wired by the separate engine sub-project (spec §11), not here; output 4 (BIDS) is the params JSON from Task 8 + a deferred naming wrapper. §10 sensitivity analysis → `--source` switch (Task 3 multi-source + Task 8 CLI). §11 Phase boundaries respected (no Ch. 9 term, no screen internals, no engine).
- **Type consistency:** `HCFEstimate(participant_id, value, source, components)` used identically in Task 4 and Task 8; `failure_metrics` returns `{n_failures, mttf_s, lambda_per_s}` consumed unchanged in Task 8; `solve_g0` takes `list[(mwl, tau)]` in Tasks 5 and 8.
- **No placeholders:** every code step contains complete, runnable code and an exact run command with expected result.
