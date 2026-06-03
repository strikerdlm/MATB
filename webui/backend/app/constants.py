"""Study-protocol constants."""

from __future__ import annotations

SCHEDULED_DAYS: tuple[int, ...] = (0, 3, 6, 9, 12, 15)  # 6 visits over 15 days
N_VISITS: int = len(SCHEDULED_DAYS)
WORKLOAD_LEVELS: tuple[str, ...] = ("LOW", "MEDIUM", "HIGH")
