"""Protected local purpose review API (shared request-security middleware)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from app.db import get_session
from app.purpose_service import classify_retrospectively, provenance_view

router = APIRouter(prefix='/purpose-provenance', tags=['purpose-provenance'])


class RetrospectiveClassification(BaseModel):
    model_config = ConfigDict(extra='forbid')
    purpose: Literal['study', 'practice', 'exploration']
    reviewer: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=4000)
    supporting_references: list[str] = Field(default_factory=list, max_length=100)


@router.get('/{identity}')
def get_provenance(identity: str, db: Session = Depends(get_session)):
    try:
        return provenance_view(db, identity)
    except KeyError:
        raise HTTPException(404, 'purpose provenance not found')


@router.post('/{identity}/classifications', status_code=201)
def classify(identity: str, body: RetrospectiveClassification, db: Session = Depends(get_session)):
    try:
        classify_retrospectively(db, identity, **body.model_dump())
        db.commit()
        return provenance_view(db, identity)
    except KeyError:
        raise HTTPException(404, 'purpose provenance not found')
    except ValueError as exc:
        raise HTTPException(422, str(exc))
