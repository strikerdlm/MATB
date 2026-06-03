from __future__ import annotations

from datetime import date

from sqlmodel import Session

from app.completeness import build_completeness_grid
from app.models import Block, Participant, Visit


def _seed(engine):
    with Session(engine) as s:
        s.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        for ordinal, day in enumerate((0, 3, 6, 9, 12, 15), start=1):
            s.add(Visit(participant_id="P01", visit_ordinal=ordinal, scheduled_day=day))
        s.commit()
        v1 = s.exec(
            __import__("sqlmodel").select(Visit).where(Visit.visit_ordinal == 1)
        ).first()
        s.add(Block(visit_id=v1.id, workload_level="LOW", source_csv_filename="a.csv",
                    source_csv_sha256="sa", metrics_json="{}"))
        s.commit()


def test_grid_marks_present_and_absent(engine):
    _seed(engine)
    with Session(engine) as s:
        grid = build_completeness_grid(s)
    # one participant -> 6 visits x 3 levels = 18 cells
    assert len(grid) == 18
    present = {(c["participant_id"], c["visit_ordinal"], c["workload_level"])
               for c in grid if c["present"]}
    assert ("P01", 1, "LOW") in present
    absent = [c for c in grid if not c["present"]]
    assert len(absent) == 17
    # summary counts
    by_visit1 = [c for c in grid if c["visit_ordinal"] == 1]
    assert sum(c["present"] for c in by_visit1) == 1
