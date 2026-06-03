"""Participant CRUD; creating a participant auto-generates the 6 planned visits."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.constants import SCHEDULED_DAYS
from app.db import get_session
from app.models import Participant, Visit
from app.schemas import ParticipantCreate, ParticipantOut, VisitOut

router = APIRouter(prefix="/participants", tags=["participants"])


@router.post("", response_model=ParticipantOut, status_code=status.HTTP_201_CREATED)
def create_participant(body: ParticipantCreate, session: Session = Depends(get_session)):
    if session.get(Participant, body.id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"participant {body.id} exists")
    participant = Participant(**body.model_dump())
    session.add(participant)
    for ordinal, day in enumerate(SCHEDULED_DAYS, start=1):
        session.add(Visit(participant_id=body.id, visit_ordinal=ordinal, scheduled_day=day))
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
