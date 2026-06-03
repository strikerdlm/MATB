"""Derive the expected-vs-actual study completeness grid.

The expected grid = enrolled participants × 6 visits × 3 workload levels.
Each cell is present (a Block row exists for that visit+level) or
expected-but-absent. Nothing about missingness is stored; it is derived.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.constants import SCHEDULED_DAYS, WORKLOAD_LEVELS
from app.models import Block, Participant, Visit


def build_completeness_grid(session: Session) -> list[dict[str, Any]]:
    participants = session.exec(select(Participant).order_by(Participant.id)).all()
    visits = session.exec(select(Visit)).all()
    blocks = session.exec(select(Block)).all()

    visit_by_key = {(v.participant_id, v.visit_ordinal): v for v in visits}
    present_levels: dict[int, set[str]] = {}
    for b in blocks:
        present_levels.setdefault(b.visit_id, set()).add(b.workload_level)

    grid: list[dict[str, Any]] = []
    for p in participants:
        for ordinal, day in enumerate(SCHEDULED_DAYS, start=1):
            visit = visit_by_key.get((p.id, ordinal))
            have = present_levels.get(visit.id, set()) if visit else set()
            for level in WORKLOAD_LEVELS:
                grid.append({
                    "participant_id": p.id,
                    "visit_ordinal": ordinal,
                    "scheduled_day": day,
                    "workload_level": level,
                    "present": level in have,
                })
    return grid
