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
    # Scan from hi downward: avoids the numerical-underflow pseudo-roots near 0
    # and finds the physically meaningful root closest to (but below) min(G).
    prev_x = hi
    prev_y = f(prev_x)
    for i in range(1, n + 1):
        x = hi - i * step
        y = f(x)
        if prev_y == 0.0:
            return prev_x
        if prev_y * y < 0.0:
            return brentq(f, x, prev_x, xtol=1e-9)
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
