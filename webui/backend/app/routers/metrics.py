"""Tidy long-format metrics endpoint for visualization/statistics."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.db import get_session
from app.metrics_long import extract_long_metrics, metric_metadata
from app.models import Block, BlockProvenance, Visit

router = APIRouter(tags=["metrics"])


def collect_metric_rows(session: Session, participant_id: str | None = None) -> list[dict[str, Any]]:
    query = select(Block, Visit).where(Block.visit_id == Visit.id)
    if participant_id is not None:
        query = query.where(Visit.participant_id == participant_id)
    rows: list[dict[str, Any]] = []
    for block, visit in session.exec(query).all():
        record = json.loads(block.metrics_json)
        provenance = session.exec(
            select(BlockProvenance).where(BlockProvenance.block_id == block.id)
        ).first()
        for metric, value in extract_long_metrics(record):
            metric_row = {
                "participant_id": visit.participant_id,
                "visit_ordinal": visit.visit_ordinal,
                "workload_level": block.workload_level,
                "metric": metric,
                "value": value,
            }
            metric_row.update(metric_metadata(
                metric,
                record,
                provenance_validation_status=(
                    provenance.validation_status if provenance is not None else None
                ),
            ))
            rows.append(metric_row)
    return rows


def collect_liftoff_metric_rows(
    session: Session,
    participant_id: str | None = None,
) -> list[dict[str, Any]]:
    """Compatibility wrapper; implementation belongs to the optional component."""
    from app.liftoff_research import collect_liftoff_metric_rows as implementation

    return implementation(session, participant_id)


@router.get("/metrics/long")
def metrics_long(
    participant_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return collect_metric_rows(session, participant_id)
