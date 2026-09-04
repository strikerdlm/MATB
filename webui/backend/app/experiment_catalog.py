"""Small, import-safe catalog; availability never imports an optional runtime."""
from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import PvtAssessment


EXPERIMENTS = (
    {"id": "openmatb", "component_id": "matb-openmatb", "route": "/openmatb/setup",
     "configuration_url": "/openmatb/presets", "readiness_url": "/openmatb/readiness",
     "profiles": ["PRACTICE", "LOW", "MEDIUM", "HIGH"], "duration_seconds": None,
     "study_prerequisites": []},
    {"id": "suas", "component_id": "matb-suas", "route": "/mission/setup",
     "configuration_url": "/simulation/scenarios", "readiness_url": None,
     "profiles": ["PRACTICE", "LOW", "MEDIUM", "HIGH"], "duration_seconds": None,
     "study_prerequisites": ["pvt"]},
    {"id": "liftoff", "component_id": "matb-liftoff", "route": "/liftoff/setup",
     "configuration_url": "/liftoff/protocol", "readiness_url": "/liftoff/readiness",
     "profiles": [], "duration_seconds": None, "study_prerequisites": ["study_context"]},
    {"id": "screen", "component_id": None, "route": "/screen",
     "configuration_url": None, "readiness_url": None,
     "profiles": ["simple_rt", "choice_rt", "nback", "tracking"],
     "duration_seconds": None, "study_prerequisites": []},
    {"id": "pvt", "component_id": None, "route": "/pvt",
     "configuration_url": None, "readiness_url": None, "profiles": ["KSS", "PVT"],
     "duration_seconds": 600, "study_prerequisites": []},
    {"id": "physiology", "component_id": "matb-physiology", "route": "/physiology/polar-h10",
     "configuration_url": None, "readiness_url": "/physiology/polar-h10/v1/connection",
     "profiles": [], "duration_seconds": 300, "study_prerequisites": []},
)


def require_study_pvt(session: Session, visit_id: int) -> None:
    assessment = session.exec(select(PvtAssessment).where(
        PvtAssessment.visit_id == visit_id, PvtAssessment.execution_purpose == "study",
        PvtAssessment.pvt_version >= 2,
        PvtAssessment.protocol_valid == True,  # noqa: E712
    )).first()
    if assessment is None:
        raise HTTPException(409, detail={"code": "study_pvt_required",
                                        "message": "Complete a valid study PVT for this visit first."})


def require_task_order(session: Session, participant_id: str, visit_id: int, family: str,
                       *, require_context: bool = False) -> None:
    from app.study_models import StudyParticipantContext
    from app.models import Block
    from sqlalchemy import inspect
    context = session.get(StudyParticipantContext, participant_id)
    if context is None:
        if require_context:
            raise ValueError("study_context_required")
        return
    if context.task_sequence == "MATB_LIFTOFF" and family == "liftoff":
        # Imported classical MATB blocks or a finished native study suite satisfy the assignment.
        blocks = session.exec(select(Block).where(Block.visit_id == visit_id)).all()
        if {row.workload_level for row in blocks} >= {"LOW", "MEDIUM", "HIGH"}:
            return
        if "openmatb_suite_session" in inspect(session.connection()).get_table_names():
            from app.openmatb_models import OpenMatbSuiteSession
            row = session.exec(select(OpenMatbSuiteSession).where(OpenMatbSuiteSession.visit_id == visit_id,
                  OpenMatbSuiteSession.execution_purpose == "study", OpenMatbSuiteSession.lifecycle == "COMPLETE")).first()
            if row is not None:
                return
        raise ValueError("assigned_matb_first")
    if context.task_sequence == "LIFTOFF_MATB" and family == "openmatb":
        if "liftoff_session" in inspect(session.connection()).get_table_names():
            from app.liftoff_models import LiftoffSession
            row = session.exec(select(LiftoffSession).where(LiftoffSession.visit_id == visit_id,
                  LiftoffSession.execution_purpose == "study", LiftoffSession.status == "FINISHED",
                  LiftoffSession.validity == "valid")).first()
            if row is not None:
                return
        raise ValueError("assigned_liftoff_first")
