"""Participant CRUD and immutable study context."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.constants import protocol_visits
from app.db import get_session
from app.models import Participant, ParticipantRoster, Visit
from app.astra_roster import participant_view
from app.schemas import (
    ParticipantCreate,
    ParticipantOut,
    StudyContextCreate,
    StudyContextView,
    VisitOut,
)
from app.study_models import StudyParticipantContext
from app.study_protocol import selected_protocol

router = APIRouter(prefix="/participants", tags=["participants"])


@router.post("", response_model=ParticipantOut, status_code=status.HTTP_201_CREATED)
def create_participant(body: ParticipantCreate, session: Session = Depends(get_session)):
    if session.get(Participant, body.id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"participant {body.id} exists")
    if body.mission:
        from app.astra_roster import add_person
        participant = add_person(session, callsign=body.callsign or body.id,
                                 mission=body.mission, participant_id=body.id, age_band=body.age_band)
        participant.enrollment_date = body.enrollment_date
        participant.sex = body.sex
        participant.notes = body.notes
        session.add(participant)
        session.commit()
        return participant_view(session, participant)
    participant = Participant(**body.model_dump(exclude={"callsign", "mission"}))
    session.add(participant)
    if body.callsign:
        callsign = body.callsign.strip().upper()
        if not callsign or session.exec(select(ParticipantRoster).where(ParticipantRoster.callsign == callsign)).first():
            raise HTTPException(409, "El indicativo ya existe o está vacío.")
        session.flush()
        session.add(ParticipantRoster(participant_id=body.id, callsign=callsign))
    from app.study_registry import active_version, get_version
    from app.study_protocol import VisitDefinition
    import json
    version_id = active_version(session)
    definitions = [VisitDefinition(**v) for v in json.loads(get_version(session, version_id).study_json)['visits']] if version_id else protocol_visits()
    for definition in definitions:
        session.add(
            Visit(
                participant_id=body.id,
                visit_ordinal=definition.ordinal,
                scheduled_day=definition.scheduled_day,
            )
        )
    session.commit()
    return participant_view(session, participant)


@router.get("", response_model=list[ParticipantOut])
def list_participants(include_archived: bool = False, session: Session = Depends(get_session)):
    rows = [participant_view(session, p) for p in session.exec(select(Participant).order_by(Participant.id)).all()]
    return rows if include_archived else [p for p in rows if not p["archived"]]


@router.delete("/{participant_id}", response_model=ParticipantOut)
def remove_participant(participant_id: str, session: Session = Depends(get_session)):
    """Remove from the launch roster while retaining research data and identity."""
    from datetime import datetime, timezone
    from sqlalchemy import inspect, text
    person = session.get(Participant, participant_id)
    if person is None:
        raise HTTPException(404, "participant not found")
    tables = set(inspect(session.connection()).get_table_names())
    active = "openmatb_suite_session" in tables and session.execute(text(
        "SELECT id FROM openmatb_suite_session WHERE participant_id=:pid AND lifecycle NOT IN ('COMPLETE','ABORTED','FAILED','INTERRUPTED') LIMIT 1"
    ), {"pid": participant_id}).first()
    if not active and {"assessment_attempt", "assessment_occasion"} <= tables:
        active = session.execute(text("SELECT a.id FROM assessment_attempt a JOIN assessment_occasion o ON a.occasion_id=o.id WHERE o.participant_id=:pid AND a.acquisition_state='started' LIMIT 1"), {"pid": participant_id}).first()
    if active:
        raise HTTPException(409, "Cierre la evaluación activa antes de retirar al participante.")
    roster = session.get(ParticipantRoster, participant_id) or ParticipantRoster(participant_id=participant_id, callsign=participant_id)
    roster.archived_at = datetime.now(timezone.utc)
    session.add(roster)
    session.commit()
    return participant_view(session, person)


@router.post("/{participant_id}/restore", response_model=ParticipantOut)
def restore_participant(participant_id: str, session: Session = Depends(get_session)):
    person = session.get(Participant, participant_id)
    if person is None:
        raise HTTPException(404, "participant not found")
    roster = session.get(ParticipantRoster, participant_id)
    if roster:
        roster.archived_at = None
        session.add(roster)
        session.commit()
    return participant_view(session, person)


@router.get("/{participant_id}/visits", response_model=list[VisitOut])
def list_visits(participant_id: str, session: Session = Depends(get_session)):
    if session.get(Participant, participant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "participant not found")
    return session.exec(
        select(Visit).where(Visit.participant_id == participant_id).order_by(Visit.visit_ordinal)
    ).all()


@router.put(
    "/{participant_id}/study-context",
    response_model=StudyContextView,
    status_code=status.HTTP_201_CREATED,
)
def create_study_context(
    participant_id: str,
    body: StudyContextCreate,
    session: Session = Depends(get_session),
):
    if session.get(Participant, participant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "participant not found")
    if session.get(StudyParticipantContext, participant_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "study context already exists")
    context = StudyParticipantContext(
        participant_id=participant_id,
        protocol_id=selected_protocol().protocol_id,
        **body.model_dump(),
    )
    session.add(context)
    session.commit()
    session.refresh(context)
    return context


@router.get("/{participant_id}/study-context", response_model=StudyContextView)
def get_study_context(participant_id: str, session: Session = Depends(get_session)):
    if session.get(Participant, participant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "participant not found")
    context = session.get(StudyParticipantContext, participant_id)
    if context is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "study context not found")
    return context
