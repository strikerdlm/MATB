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
from app import crew_workflow

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
    include_polar: bool = False
    baseline_minutes: Literal[5, 10] = 5


@router.post("/protocol/activate")
def activate(body: ActivationIn, db: Session = Depends(get_session), runtime: OpenMatbManager = Depends(manager)):
    return astra_deployment.configure(db, runtime, body.actor, include_polar=body.include_polar, baseline_minutes=body.baseline_minutes)


class VisitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    participant_id: str
    visit_ordinal: int = Field(ge=1, le=8)


@router.post("/visits/prepare")
def prepare(body: VisitIn, db: Session = Depends(get_session)):
    row = astra_deployment.assign_visit(db, body.participant_id, body.visit_ordinal)
    return dict(assignment_id=row.id, url=f"/study/participant?assignment={row.id}")


CrewActivity = Literal["openmatb", "suas", "screen", "pvt"]


class CrewConfigurationIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    actor: str = Field(min_length=3, max_length=150)
    reason: str = Field(min_length=10, max_length=1000)


class CrewStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    callsign: Literal["CUELLAR", "COLORADO", "ICEMAN", "WHITE", "PIRATA"]
    instrument: CrewActivity
    retry: bool = False


@router.post("/crew/configure")
def configure_crew(body: CrewConfigurationIn, db: Session = Depends(get_session), runtime: OpenMatbManager = Depends(manager)):
    result = crew_workflow.configure(db, runtime, **body.model_dump())
    db.commit()
    from app.crew_exports import prepare_directories
    prepare_directories()
    return result


@router.get("/crew")
def crew(instrument: CrewActivity = "openmatb", db: Session = Depends(get_session)):
    return crew_workflow.roster(db, instrument)


@router.post("/crew/prepare")
def prepare_crew(body: CrewStartIn, db: Session = Depends(get_session)):
    result = crew_workflow.prepare(db, **body.model_dump())
    db.commit()
    return result


@router.post("/crew/exports")
def rebuild_crew_exports(db: Session = Depends(get_session)):
    from app.crew_exports import queue_all
    queued = queue_all(db)
    db.commit()
    return {"queued": queued}
