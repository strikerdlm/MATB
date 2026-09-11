"""Read-only progress derived from saved study evidence, per experiment family."""
from __future__ import annotations
import json
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import inspect, text
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
                        experiment: Experiment = "suas", attempt_id: str | None = None, pvt_attempt_id: str | None = None, polar_attempt_id: str | None = None, legacy_screen: bool = False,
                        legacy_polar: bool = False, session: Session = Depends(get_session)):
    if session.get(Participant, participant_id) is None:
        raise HTTPException(404, "participant not found")
    visit = session.exec(select(Visit).where(Visit.participant_id == participant_id,
                                           Visit.visit_ordinal == visit_ordinal)).first()
    if visit is None:
        raise HTTPException(404, "visit not found")
    tables = set(inspect(session.connection()).get_table_names())
    from app.assessment_readers import select_one, select_source_rows
    from app.assessment_models import AssessmentAttempt, AssessmentOccasion

    def selected_context(identity, instrument, *, allow_unknown_screen=False, allow_unknown_polar=False):
        selected = session.get(AssessmentAttempt, identity)
        context = session.get(AssessmentOccasion, selected.occasion_id) if selected else None
        unknown_screen = bool(context and allow_unknown_screen and context.visit_id is None
                              and context.origin in {'legacy', 'legacy_compat'})
        unknown_polar = False
        if (context and instrument == "physiology" and allow_unknown_polar
                and context.visit_id is None and context.origin in {'legacy', 'legacy_compat'}
                and "polar_capture" in tables):
            # Compatibility relies on the exact immutable source link and recorded
            # baseline context, never on an invented occasion visit/assignment.
            linked = session.execute(text("""
                SELECT capture.participant_id, capture.matb_session_kind, capture.matb_session_id
                FROM assessment_source_link AS link
                JOIN polar_capture AS capture ON capture.id = link.source_id
                WHERE link.attempt_id = :attempt_id AND link.source_table = 'polar_capture'
                  AND link.role = 'acquisition'
            """), {'attempt_id': identity}).all()
            unknown_polar = len(linked) == 1 and tuple(linked[0]) == (
                participant_id, "generic", f"baseline:{participant_id}:V{visit_ordinal}")
        if (context is None or context.instrument != instrument or context.participant_id != participant_id
                or (context.visit_id != visit.id and not unknown_screen and not unknown_polar)):
            raise HTTPException(404, "selected attempt not found in this participant visit")
        return context

    if attempt_id:
        selected_context(attempt_id, experiment, allow_unknown_screen=experiment == "screen" and legacy_screen,
                         allow_unknown_polar=experiment == "physiology" and legacy_polar)
    pvt = None
    if experiment in {"pvt", "suas"}:
        pvt_selection = attempt_id if experiment == "pvt" else pvt_attempt_id
        if pvt_selection:
            selected_context(pvt_selection, "pvt")
        pvt_rows = session.exec(select(PvtAssessment).where(PvtAssessment.visit_id == visit.id,
                        PvtAssessment.execution_purpose == "study")).all()
        pvt = select_one(pvt_rows, pvt_selection)
        if pvt and (not pvt.protocol_valid or pvt.pvt_version < 2):
            pvt = None
    registry = getattr(request.app.state, "component_registry", None)
    active = {item.component_id for item in registry.manifests()} if registry else set()
    descriptor = next(row for row in EXPERIMENTS if row["id"] == experiment)
    available = descriptor["component_id"] is None or descriptor["component_id"] in active
    polar_complete = False
    polar_selection = None
    polar_selection_mode = None
    polar_assessment_visit_id = None
    if "polar_capture" in tables and experiment in {"physiology", "suas"}:
        from app.physiology_models import PolarCaptureRecord
        baseline_id = f"baseline:{participant_id}:V{visit_ordinal}"
        captures = session.exec(select(PolarCaptureRecord).where(
            PolarCaptureRecord.participant_id == participant_id,
            PolarCaptureRecord.matb_session_kind == "generic",
            PolarCaptureRecord.matb_session_id == baseline_id,
            PolarCaptureRecord.execution_purpose == "study",
            PolarCaptureRecord.artifact_state == "finalized")).all()
        polar_selection = attempt_id if experiment == "physiology" else polar_attempt_id
        if polar_selection:
            polar_context = selected_context(polar_selection, "physiology", allow_unknown_polar=legacy_polar)
            polar_selection_mode = "legacy_polar_recorded_baseline" if polar_context.visit_id is None else "explicit"
            polar_assessment_visit_id = polar_context.visit_id
        # H10 accompanies a mission; an unselected repeat does not block it.
        if experiment == "suas" and len(captures) > 1 and polar_selection is None:
            captures = []
        else:
            captures = select_source_rows(session, captures, "polar_capture", polar_selection)
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
            missions = select_source_rows(session, missions, "simulation_session", attempt_id)
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
        rows = session.exec(select(ScreenResult).where(ScreenResult.participant_id == participant_id,
            ScreenResult.execution_purpose == "study", ScreenResult.screen_version == SCREEN_VERSION)).all()
        matching = []
        for candidate in rows:
            linked = session.get(AssessmentAttempt, candidate.attempt_id) if candidate.attempt_id else None
            context = session.get(AssessmentOccasion, linked.occasion_id) if linked else None
            unknown = context is None or (context.visit_id is None and context.origin in {"legacy", "legacy_compat"})
            if legacy_screen:
                if unknown:
                    matching.append(candidate)
            elif context and context.visit_id == visit.id and context.participant_id == participant_id:
                matching.append(candidate)
        row = select_one(matching, attempt_id)
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
            rows = select_source_rows(session, rows, "openmatb_suite_session", attempt_id)
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
            rows = select_source_rows(session, rows, "liftoff_session", attempt_id)
            prepared = bool(rows)
            complete = any(row.status == "FINISHED" and row.validity == "valid" and row.metrics_json for row in rows)
        steps = [_step("welcome", True), _step("prepare", prepared), _step("record", complete), _step("complete", complete)]
    else:
        steps = [_step("welcome", True), _step("record", polar_complete), _step("complete", polar_complete)]
    for item in steps:
        if item["status"] == "upcoming":
            item["status"] = "current" if available else "unavailable"
            break
    selection_mode = "explicit" if attempt_id else "legacy_unambiguous"
    assessment_visit_id = visit.id
    if experiment == "screen" and legacy_screen:
        selection_mode, assessment_visit_id = "legacy_screen_visit_unknown", None
    elif experiment == "physiology" and polar_selection_mode == "legacy_polar_recorded_baseline":
        selection_mode, assessment_visit_id = polar_selection_mode, None
    return {"selection_mode": selection_mode, "assessment_visit_id": assessment_visit_id,
            "polar_selection_mode": polar_selection_mode, "polar_assessment_visit_id": polar_assessment_visit_id,
            "polar_attempt_id": polar_selection, "attempt_id": attempt_id, "participant_id": participant_id,
            "visit_id": visit.id, "visit_ordinal": visit.visit_ordinal,
            "selected_experiment": experiment, "execution_purpose": "study", "steps": steps}
