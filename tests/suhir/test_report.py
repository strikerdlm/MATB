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
