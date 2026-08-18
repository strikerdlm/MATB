"""Derive the expected-vs-actual OpenMATB completeness grid.

The expected grid = enrolled participants × active protocol visits × 3 workload levels.
Each cell is present (a Block row exists for that visit+level) or
expected-but-absent. Nothing about missingness is stored; it is derived.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.constants import WORKLOAD_LEVELS, protocol_visits
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
        for definition in protocol_visits():
            visit = visit_by_key.get((p.id, definition.ordinal))
            have = present_levels.get(visit.id, set()) if visit else set()
            for level in WORKLOAD_LEVELS:
                grid.append({
                    "participant_id": p.id,
                    "visit_ordinal": definition.ordinal,
                    "scheduled_day": definition.scheduled_day,
                    "workload_level": level,
                    "present": level in have,
                })
    return grid
