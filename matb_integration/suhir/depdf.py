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
    """Ordinary-capacity reduction F = F0 (Eq. 5.16).

    Delegates to p_bar with f2=1 (exp(1-1)=1) so the formula stays single-sourced.
    """
    return p0 * p_bar((g / g0) ** 2, 1.0)


def weibull_nonfailure(lam: float, t: float, beta: float) -> float:
    """Time-degraded nonfailure probability, Weibull form (Eq. 5.5 / 5.24)."""
    return math.exp(-((lam * t) ** beta))


def entropy(p: float) -> float:
    """Distribution entropy H = -P ln P (used in Eq. 5.3); H(0)=H(1)=0."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -p * math.log(p)
