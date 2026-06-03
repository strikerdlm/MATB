from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.models import Block, DepdfFit, Participant, Visit


def test_participant_visit_block_roundtrip(engine):
    with Session(engine) as s:
        s.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        s.add(Visit(participant_id="P01", visit_ordinal=1, scheduled_day=0))
        s.commit()
        v = s.query(Visit).first()
        s.add(Block(visit_id=v.id, workload_level="LOW",
                    source_csv_filename="a.csv", source_csv_sha256="sha-a",
                    metrics_json="{}"))
        s.commit()
        assert s.query(Block).count() == 1


def test_block_sha256_is_unique(engine):
    with Session(engine) as s:
        s.add(Participant(id="P02", enrollment_date=date(2026, 6, 1)))
        s.add(Visit(participant_id="P02", visit_ordinal=1, scheduled_day=0))
        s.commit()
        vid = s.query(Visit).first().id
        s.add(Block(visit_id=vid, workload_level="LOW", source_csv_filename="a.csv",
                    source_csv_sha256="dup", metrics_json="{}"))
        s.commit()
        s.add(Block(visit_id=vid, workload_level="MEDIUM", source_csv_filename="b.csv",
                    source_csv_sha256="dup", metrics_json="{}"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_visit_ordinal_unique_per_participant(engine):
    with Session(engine) as s:
        s.add(Participant(id="P03", enrollment_date=date(2026, 6, 1)))
        s.add(Visit(participant_id="P03", visit_ordinal=1, scheduled_day=0))
        s.commit()
        s.add(Visit(participant_id="P03", visit_ordinal=1, scheduled_day=3))
        with pytest.raises(IntegrityError):
            s.commit()
