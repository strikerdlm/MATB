"""Participant CRUD and immutable study context."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.constants import protocol_visits
from app.db import get_session
from app.models import Participant, Visit
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
    participant = Participant(**body.model_dump())
    session.add(participant)
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
    return participant


@router.get("", response_model=list[ParticipantOut])
def list_participants(session: Session = Depends(get_session)):
    return session.exec(select(Participant).order_by(Participant.id)).all()


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
