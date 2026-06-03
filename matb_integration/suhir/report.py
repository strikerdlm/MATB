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
