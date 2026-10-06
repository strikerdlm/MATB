"""Confirmed ASTRA-1 collection days; legacy V0-V7 identities stay unchanged."""
from datetime import date, timedelta, timezone

from app.study_protocol import VisitDefinition

BOGOTA = timezone(timedelta(hours=-5), "America/Bogota")
MISSION_START = date(2026, 10, 5)
VISITS = (
    VisitDefinition(9, "DM3", 3),
    VisitDefinition(10, "DM7", 7),
    VisitDefinition(11, "DM11", 11),
    VisitDefinition(12, "POST", 16),
)


def planned_date(ordinal):
    visit = next(v for v in VISITS if v.ordinal == ordinal)
    return MISSION_START + timedelta(days=visit.scheduled_day - 1)


def label(ordinal):
    visit = next(v for v in VISITS if v.ordinal == ordinal)
    return "Postmisión" if visit.code == "POST" else visit.code
