"""Study-protocol helpers and task constants."""

from __future__ import annotations

from app.study_protocol import VisitDefinition, selected_protocol

WORKLOAD_LEVELS: tuple[str, ...] = ("LOW", "MEDIUM", "HIGH")


def protocol_visits() -> tuple[VisitDefinition, ...]:
    return selected_protocol().visits
