"""Immutable study-protocol definitions selected at deployment time."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os


@dataclass(frozen=True, slots=True)
class VisitDefinition:
    ordinal: int
    code: str
    scheduled_day: int


@dataclass(frozen=True, slots=True)
class StudyProtocolDefinition:
    protocol_id: str
    protocol_version: str
    visits: tuple[VisitDefinition, ...]

    @property
    def schedule_sha256(self) -> str:
        payload = json.dumps(
            [asdict(visit) for visit in self.visits],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


_PROTOCOLS = {
    "astra-2026": StudyProtocolDefinition(
        protocol_id="astra-2026",
        protocol_version="1.0.0",
        visits=(
            VisitDefinition(ordinal=1, code="T0", scheduled_day=0),
            VisitDefinition(ordinal=2, code="DM8", scheduled_day=8),
            VisitDefinition(ordinal=3, code="DM15", scheduled_day=15),
        ),
    ),
    "matb-longitudinal-6-visit-v1": StudyProtocolDefinition(
        protocol_id="matb-longitudinal-6-visit-v1",
        protocol_version="1.0.0",
        visits=tuple(
            VisitDefinition(ordinal=ordinal, code=f"D{day}", scheduled_day=day)
            for ordinal, day in enumerate((0, 3, 6, 9, 12, 15), start=1)
        ),
    ),
}


def get_protocol(protocol_id: str) -> StudyProtocolDefinition:
    try:
        return _PROTOCOLS[protocol_id]
    except KeyError as exc:
        raise ValueError(f"unknown study protocol: {protocol_id!r}") from exc


def selected_protocol() -> StudyProtocolDefinition:
    raw_protocol_id = os.getenv("MATB_STUDY_PROTOCOL", "astra-2026")
    protocol_id = raw_protocol_id.strip()
    if not protocol_id:
        raise ValueError("MATB_STUDY_PROTOCOL must not be blank")
    return get_protocol(protocol_id)
