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
