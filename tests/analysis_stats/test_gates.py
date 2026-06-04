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
