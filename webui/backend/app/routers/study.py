"""Read-only study-protocol metadata."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.study_protocol import selected_protocol

router = APIRouter(prefix="/study", tags=["study"])


class VisitDefinitionView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ordinal: int
    code: str
    scheduled_day: int


class StudyProtocolView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_id: str
    protocol_version: str
    schedule_sha256: str
    visits: tuple[VisitDefinitionView, ...]


@router.get("/protocol", response_model=StudyProtocolView)
def get_selected_study_protocol() -> StudyProtocolView:
    protocol = selected_protocol()
    return StudyProtocolView(
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        schedule_sha256=protocol.schedule_sha256,
        visits=tuple(
            VisitDefinitionView(
                ordinal=visit.ordinal,
                code=visit.code,
                scheduled_day=visit.scheduled_day,
            )
            for visit in protocol.visits
        ),
    )
