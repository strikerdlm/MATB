"""Read-only progress derived from saved study evidence, per experiment family."""
from __future__ import annotations
import json
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import inspect
from sqlmodel import Session, select
from app.db import get_session
from app.models import Participant, PvtAssessment, ScreenResult, Visit
from app.experiment_catalog import EXPERIMENTS

router = APIRouter(prefix="/journey", tags=["journey"])
Experiment = Literal["suas", "openmatb", "liftoff", "screen", "pvt", "physiology"]


def _step(step_id: str, complete: bool, *, optional=False, available=True):
    return {"id": step_id, "complete": complete, "optional": optional,
            "status": "complete" if complete else "unavailable" if not available else "optional" if optional else "upcoming"}


def _json(raw):
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


@router.get("/{participant_id}/{visit_ordinal}")
def participant_journey(participant_id: str, visit_ordinal: int, request: Request,
                        experiment: Experiment = "suas", session: Session = Depends(get_session)):
    if session.get(Participant, participant_id) is None:
        raise HTTPException(404, "participant not found")
    visit = session.exec(select(Visit).where(Visit.participant_id == participant_id,
                                           Visit.visit_ordinal == visit_ordinal)).first()
    if visit is None:
        raise HTTPException(404, "visit not found")
    tables = set(inspect(session.connection()).get_table_names())
    pvt = session.exec(select(PvtAssessment).where(PvtAssessment.visit_id == visit.id,
                    PvtAssessment.execution_purpose == "study", PvtAssessment.pvt_version >= 2,
                    PvtAssessment.protocol_valid == True)).first()  # noqa: E712
    registry = getattr(request.app.state, "component_registry", None)
    active = {item.component_id for item in registry.manifests()} if registry else set()
    descriptor = next(row for row in EXPERIMENTS if row["id"] == experiment)
    available = descriptor["component_id"] is None or descriptor["component_id"] in active
    polar_complete = False
    if "polar_capture" in tables:
        from app.physiology_models import PolarCaptureRecord
        baseline_id = f"baseline:{participant_id}:V{visit_ordinal}"
        captures = session.exec(select(PolarCaptureRecord).where(
            PolarCaptureRecord.participant_id == participant_id,
            PolarCaptureRecord.matb_session_kind == "generic",
            PolarCaptureRecord.matb_session_id == baseline_id,
            PolarCaptureRecord.execution_purpose == "study",
            PolarCaptureRecord.artifact_state == "finalized")).all()
        # Saved capture completion is not a claim that its HRV quality gate passed.
        polar_complete = any(row.started_at and row.ended_at and
                             (row.ended_at - row.started_at).total_seconds() >= 300 and
                             not json.loads(row.incomplete_reasons_json) for row in captures)
    if experiment == "suas":
        prepared = practice = blocks_done = workload = complete = False
        if "simulation_session" in tables and "simulation_block" in tables:
            from app.simulation_models import SimulationBlock, SimulationSession
            missions = session.exec(select(SimulationSession).where(
                SimulationSession.participant_id == participant_id,
                SimulationSession.visit_id == visit.id).order_by(SimulationSession.created_at.desc())).all()
            for mission in missions:
                blocks = session.exec(select(SimulationBlock).where(SimulationBlock.session_id == mission.id)).all()
                by_id = {block.block_id: block for block in blocks}
                required = [by_id.get(level) for level in ("LOW", "MEDIUM", "HIGH")]
                this_blocks = all(row is not None and row.lifecycle == "FINISHED" and
                                  row.validity in {"valid", "valid_with_deviation"} for row in required)
                this_workload = all(row is not None and
                    _json(row.metrics_json).get("nasa_tlx", {}).get("complete_count", 0) > 0 and
                    _json(row.metrics_json).get("bedford", {}).get("count", 0) > 0 for row in required)
                if not prepared or (this_blocks and this_workload):
                    prepared = True
                    practice = bool(by_id.get("PRACTICE") and by_id["PRACTICE"].lifecycle == "FINISHED")
                    blocks_done, workload = this_blocks, this_workload
                    complete = bool(pvt and practice and this_blocks and this_workload and
                                    mission.lifecycle == "FINISHED" and mission.validity in {"valid", "valid_with_deviation"})
                if complete:
                    break
        steps = [_step("welcome", True), _step("kss", pvt is not None), _step("pvt", pvt is not None),
                 _step("polar", polar_complete, optional=True, available="matb-physiology" in active),
                 _step("briefing", prepared), _step("practice", practice), _step("blocks", blocks_done),
                 _step("workload", workload), _step("complete", complete)]
    elif experiment == "pvt":
        steps = [_step("welcome", True), _step("kss", pvt is not None), _step("pvt", pvt is not None), _step("complete", pvt is not None)]
    elif experiment == "screen":
        from matb_integration.screen.hcf_mapping import SCREEN_VERSION
        row = session.exec(select(ScreenResult).where(ScreenResult.participant_id == participant_id,
            ScreenResult.execution_purpose == "study", ScreenResult.screen_version == SCREEN_VERSION)).first()
        scores = _json(row.scores_json) if row else {}
        steps = [_step("welcome", True)] + [_step(task, scores.get(task, {}).get("valid") is True)
                    for task in ("simple_rt", "choice_rt", "nback", "tracking")]
        steps.append(_step("complete", all(item["complete"] for item in steps)))
    elif experiment == "openmatb":
        complete = prepared = False
        if "openmatb_suite_session" in tables:
            from app.openmatb_models import OpenMatbSuiteSession
            rows = session.exec(select(OpenMatbSuiteSession).where(
                OpenMatbSuiteSession.visit_id == visit.id, OpenMatbSuiteSession.execution_purpose == "study")).all()
            prepared = bool(rows)
            complete = any(row.lifecycle == "COMPLETE" and all(level in _json(row.scores_json)
                           for level in ("LOW", "MEDIUM", "HIGH")) for row in rows)
        steps = [_step("welcome", True), _step("prepare", prepared), _step("blocks", complete), _step("complete", complete)]
    elif experiment == "liftoff":
        complete = prepared = False
        if "liftoff_session" in tables:
            from app.liftoff_models import LiftoffSession
            rows = session.exec(select(LiftoffSession).where(LiftoffSession.visit_id == visit.id,
                                     LiftoffSession.execution_purpose == "study")).all()
            prepared = bool(rows)
            complete = any(row.status == "FINISHED" and row.validity == "valid" and row.metrics_json for row in rows)
        steps = [_step("welcome", True), _step("prepare", prepared), _step("record", complete), _step("complete", complete)]
    else:
        steps = [_step("welcome", True), _step("record", polar_complete), _step("complete", polar_complete)]
    for item in steps:
        if item["status"] == "upcoming":
            item["status"] = "current" if available else "unavailable"
            break
    return {"participant_id": participant_id, "visit_id": visit.id, "visit_ordinal": visit.visit_ordinal,
            "selected_experiment": experiment, "execution_purpose": "study", "steps": steps}
