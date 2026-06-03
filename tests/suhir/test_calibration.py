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
