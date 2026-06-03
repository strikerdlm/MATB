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
        # lam_e == 0 means a perfectly reliable equipment segment (Suhir lets
        # P^e_i = 1, e.g. take-off where the human is not the limiting factor).
        # weibull_nonfailure(0, ...) already returns 1.0; the branch just makes
        # that intent explicit (optimization, not a correctness fix).
        p_e = weibull_nonfailure(s.lam_e, s.t, s.beta_e) if s.lam_e > 0 else 1.0
        success += s.q * p_e * s.p_human
    return 1.0 - success
