"""Concise operator entry point for the ASTRA MATB field deployment."""
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session
from app.db import get_session
from app import astra_roster
from app import astra_deployment
from app.routers.openmatb import manager
from app.openmatb_runtime import OpenMatbManager

router = APIRouter(prefix="/astra", tags=["ASTRA deployment"])


@router.get("/roster")
def roster(include_archived: bool = False, db: Session = Depends(get_session)):
    return astra_roster.dashboard(db, include_archived=include_archived)


@router.post("/initialize")
def initialize(db: Session = Depends(get_session), runtime: OpenMatbManager = Depends(manager)):
    astra_deployment.ensure_preset(runtime)
    astra_roster.initialize(db)
    return astra_roster.dashboard(db)


class CrewMemberIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    callsign: str = Field(min_length=1, max_length=60)
    mission: Literal["ASTRA-1", "ASTRA-2"]


@router.post("/participants", status_code=201)
def add_person(body: CrewMemberIn, db: Session = Depends(get_session)):
    person = astra_roster.add_person(db, **body.model_dump())
    db.commit()
    return astra_roster.participant_view(db, person)


@router.get("/protocol")
def protocol(db: Session = Depends(get_session)):
    return astra_deployment.status(db)


class ActivationIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    actor: str = Field(min_length=3, max_length=150)


@router.post("/protocol/activate")
def activate(body: ActivationIn, db: Session = Depends(get_session), runtime: OpenMatbManager = Depends(manager)):
    return astra_deployment.configure(db, runtime, body.actor)


class VisitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    participant_id: str
    visit_ordinal: int = Field(ge=1, le=8)


@router.post("/visits/prepare")
def prepare(body: VisitIn, db: Session = Depends(get_session)):
    row = astra_deployment.assign_visit(db, body.participant_id, body.visit_ordinal)
    return dict(assignment_id=row.id, url=f"/study/participant?assignment={row.id}")
