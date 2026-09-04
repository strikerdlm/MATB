"""Read-only participant journey status assembled across installed components."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import inspect
from sqlmodel import Session, select

from app.db import get_session
from app.models import Participant, PvtAssessment, Visit

router = APIRouter(prefix="/journey", tags=["journey"])


def _step(step_id: str, complete: bool) -> dict[str, object]:
    return {"id": step_id, "complete": complete, "status": "complete" if complete else "upcoming"}


@router.get("/{participant_id}/{visit_ordinal}")
def participant_journey(
    participant_id: str,
    visit_ordinal: int,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    if session.get(Participant, participant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "participant not found")
    visit = session.exec(select(Visit).where(
        Visit.participant_id == participant_id,
        Visit.visit_ordinal == visit_ordinal,
    )).first()
    if visit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "visit not found")

    pvt = session.exec(select(PvtAssessment).where(PvtAssessment.visit_id == visit.id)).first()
    polar_complete = False
    mission_prepared = False
    practice_complete = False
    blocks_complete = False
    workload_complete = False
    visit_complete = visit.status == "complete"

    connection = session.connection()
    tables = set(inspect(connection).get_table_names())
    if "polar_capture" in tables:
        from app.physiology_models import PolarCaptureRecord

        baseline_id = f"baseline:{participant_id}:V{visit_ordinal}"
        polar_complete = session.exec(select(PolarCaptureRecord).where(
            PolarCaptureRecord.participant_id == participant_id,
            PolarCaptureRecord.matb_session_kind == "generic",
            PolarCaptureRecord.matb_session_id == baseline_id,
            PolarCaptureRecord.artifact_state == "finalized",
        )).first() is not None

    if "simulation_session" in tables and "simulation_block" in tables:
        from app.simulation_models import SimulationBlock, SimulationSession

        mission = session.exec(select(SimulationSession).where(
            SimulationSession.participant_id == participant_id,
            SimulationSession.visit_id == visit.id,
        ).order_by(SimulationSession.created_at.desc())).first()
        if mission is not None:
            mission_prepared = True
            blocks = session.exec(select(SimulationBlock).where(
                SimulationBlock.session_id == mission.id,
            )).all()
            by_id = {block.block_id: block for block in blocks}
            practice_complete = by_id.get("PRACTICE") is not None and by_id["PRACTICE"].lifecycle == "FINISHED"
            mission_blocks = [by_id.get(level) for level in ("LOW", "MEDIUM", "HIGH")]
            blocks_complete = all(block is not None and block.lifecycle == "FINISHED" for block in mission_blocks)
            workload_complete = all(block is not None and block.metrics_json is not None for block in mission_blocks)
            visit_complete = visit_complete or mission.lifecycle == "FINISHED"

    steps = [
        _step("welcome", True),
        _step("kss", pvt is not None),
        _step("pvt", pvt is not None),
        _step("polar", polar_complete),
        _step("briefing", mission_prepared),
        _step("practice", practice_complete),
        _step("blocks", blocks_complete),
        _step("workload", workload_complete),
        _step("complete", visit_complete),
    ]
    first_pending = next((index for index, step in enumerate(steps) if not step["complete"]), None)
    if first_pending is not None:
        steps[first_pending]["status"] = "current"
    return {
        "participant_id": participant_id,
        "visit_id": visit.id,
        "visit_ordinal": visit.visit_ordinal,
        "steps": steps,
    }
