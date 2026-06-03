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
