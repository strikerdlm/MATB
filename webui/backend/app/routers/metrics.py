"""Tidy long-format metrics endpoint for visualization/statistics."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.db import get_session
from app.metrics_long import extract_long_metrics
from app.models import Block, Visit

router = APIRouter(tags=["metrics"])


@router.get("/metrics/long")
def metrics_long(
    participant_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    query = select(Block, Visit).where(Block.visit_id == Visit.id)
    if participant_id is not None:
        query = query.where(Visit.participant_id == participant_id)
    rows: list[dict[str, Any]] = []
    for block, visit in session.exec(query).all():
        record = json.loads(block.metrics_json)
        for metric, value in extract_long_metrics(record):
            rows.append({
                "participant_id": visit.participant_id,
                "visit_ordinal": visit.visit_ordinal,
                "workload_level": block.workload_level,
                "metric": metric,
                "value": value,
            })
    return rows
