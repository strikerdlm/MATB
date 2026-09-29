"""ASTRA 5/7 deployment roster, separate from permanent research identities.

Sources: candidate register updated 2026-09-29; field guide v2 of the same date;
Operations Manual 2026, section 4.7.6. Source dates are planned, never actuals.
Only operational aliases, rank, unit, role and age bands are distributed here.
"""
import json
from datetime import date, timedelta
from fastapi import HTTPException
from sqlmodel import select
from app.models import Participant, ParticipantRoster, Visit
from app.study_protocol import VisitDefinition

VISITS = tuple(VisitDefinition(i + 1, f"V{i}", day)
               for i, day in enumerate((0, 2, 4, 7, 10, 13, 15, 16)))
MISSION_START = {"ASTRA-1": date(2026, 10, 5), "ASTRA-2": date(2026, 10, 21)}
BASELINE_PLANNED = {"ASTRA-1": date(2026, 9, 29), "ASTRA-2": date(2026, 9, 28)}
SLOTS = ("08:30–10:00", "10:15–11:45", "14:00–15:30", "15:45–17:15")
CREW = (
    ("ASTRA-1", "CUELLAR", "T1", "COFAC", "Administración", "40–49"),
    ("ASTRA-1", "ICEMAN", "ST", "CETIA-COFAC", "Ingeniero industrial", "30–39"),
    ("ASTRA-1", "COLORADO", "T1", "CAMAN", "Mantenimiento aeronáutico", "30–39"),
    ("ASTRA-1", "WHITE", "TE", "CACOM 3", "Piloto", "20–29"),
    ("ASTRA-1", "PIRATA", "TE", "GAORI", "Talento humano", "20–29"),
    ("ASTRA-2", "BART", "ST", "CETIA-COFAC", "Ingeniero electrónico", "20–29"),
    ("ASTRA-2", "CHUCKY", "ST", "CACOM 1", "COP ECN 235", "20–29"),
    ("ASTRA-2", "VOLCANO", "T1", "CACOM 3", "Seguridad y defensa de bases", "40–49"),
    ("ASTRA-2", "ALFA-1", None, None, None, None),
    ("ASTRA-2", "ALFA-2", None, None, None, None),
    ("ASTRA-2", "ALFA-3", None, None, None, None),
    ("ASTRA-2", "ALFA-4", None, None, None, None),
)


def participant_view(db, person):
    roster = db.get(ParticipantRoster, person.id)
    return dict(**person.model_dump(), callsign=roster.callsign if roster else None,
                mission=roster.mission if roster else None, archived=bool(roster and roster.archived_at))


def require_active(db, participant_id):
    row = db.get(ParticipantRoster, participant_id)
    if row and row.archived_at:
        raise HTTPException(409, detail={"code": "participant_archived", "message": "Restaure al participante antes de iniciar otra prueba."})


def next_id(db):
    used = set(db.exec(select(Participant.id)).all())
    for number in range(1, 1000000):
        candidate = f"P{number:02d}"
        if candidate not in used:
            return candidate
    raise HTTPException(409, "No hay códigos de participante disponibles.")


def add_person(db, *, callsign, mission, participant_id=None, **details):
    callsign = callsign.strip().upper()
    if db.exec(select(ParticipantRoster).where(ParticipantRoster.callsign == callsign)).first():
        raise HTTPException(409, "El indicativo ya existe; puede restaurarlo si fue retirado.")
    identity = participant_id or next_id(db)
    if db.get(Participant, identity):
        raise HTTPException(409, "El código ya existe. No se reasignan identidades con este formulario.")
    positions = db.exec(select(ParticipantRoster.position).where(ParticipantRoster.mission == mission)).all()
    position = max((p for p in positions if p is not None), default=0) + 1
    person = Participant(id=identity, enrollment_date=date.today(), age_band=details.pop("age_band", None))
    db.add(person)
    db.flush()
    roster = ParticipantRoster(participant_id=identity, callsign=callsign, mission=mission, position=position, **details)
    db.add(roster)
    for visit in VISITS:
        db.add(Visit(participant_id=identity, visit_ordinal=visit.ordinal, scheduled_day=visit.scheduled_day))
    db.flush()
    return person


def initialize(db):
    """Idempotent bootstrap; archived seed rows remain archived on every restart."""
    for mission, callsign, rank, unit, role, age_band in CREW:
        source = f"astra-2026-09-29:{callsign}"
        existing = db.exec(select(ParticipantRoster).where(ParticipantRoster.source_key == source)).first()
        if existing:
            continue
        # Never silently attach a nominal alias to an existing scientific ID.
        if db.exec(select(ParticipantRoster).where(ParticipantRoster.callsign == callsign)).first():
            raise HTTPException(409, f"Revise el registro existente de {callsign} antes de cargar el grupo.")
        add_person(db, callsign=callsign, mission=mission, rank=rank, unit=unit, role=role,
                   age_band=age_band, source_key=source)
    db.commit()


def visit_definition(db, participant_id, ordinal):
    row = db.get(ParticipantRoster, participant_id)
    if row and row.mission in MISSION_START:
        return next((v for v in VISITS if v.ordinal == ordinal), None)
    return None


def dashboard(db, *, include_archived=False):
    from matb_integration.scenario_builder import block_order_for_participant
    from app.openmatb_models import OpenMatbSuiteSession
    people = []
    for roster in db.exec(select(ParticipantRoster).order_by(ParticipantRoster.mission, ParticipantRoster.position)).all():
        if roster.archived_at and not include_archived:
            continue
        person = db.get(Participant, roster.participant_id)
        sessions = db.exec(select(OpenMatbSuiteSession).where(OpenMatbSuiteSession.participant_id == person.id)).all()
        visits = []
        for visit in db.exec(select(Visit).where(Visit.participant_id == person.id).order_by(Visit.visit_ordinal)).all():
            definition = visit_definition(db, person.id, visit.visit_ordinal)
            if not definition:
                continue
            planned = BASELINE_PLANNED[roster.mission] if definition.ordinal == 1 else MISSION_START[roster.mission] + timedelta(days=definition.scheduled_day - 1)
            acquired = [s for s in sessions if s.visit_id == visit.id and s.execution_purpose == "study"]
            completed = {level for s in acquired if s.lifecycle == "COMPLETE" for level in json.loads(s.block_order_json) if level != "PRACTICE"}
            visits.append(dict(visit.model_dump(), code=definition.code, planned_date=planned,
                               completed_blocks=len(completed), status="complete" if len(completed) == 3 else "in_progress" if acquired else "planned"))
        position = roster.position or 1
        people.append(dict(**participant_view(db, person), rank=roster.rank, unit=roster.unit,
                           role=roster.role, position=position,
                           time_slot=SLOTS[(position - 1) // 2] if position <= 8 else None,
                           station=(position - 1) % 2 + 1,
                           block_order=[level.value.upper() for level in block_order_for_participant(person.id)], visits=visits))
    return {"participants": people, "session_minutes": 90, "experimental_block_seconds": 900}
