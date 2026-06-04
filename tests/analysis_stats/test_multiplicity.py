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
