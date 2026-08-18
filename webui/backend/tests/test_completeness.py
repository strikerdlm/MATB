from __future__ import annotations

from datetime import date

from sqlmodel import Session

from app.completeness import build_completeness_grid
from app.completeness import build_liftoff_completeness_grid
from app.liftoff_models import LiftoffSession
from app.models import Block, Participant, Visit
from app.study_protocol import get_protocol


def _seed(engine):
    with Session(engine) as s:
        s.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        for definition in get_protocol("astra-2026").visits:
            s.add(
                Visit(
                    participant_id="P01",
                    visit_ordinal=definition.ordinal,
                    scheduled_day=definition.scheduled_day,
                )
            )
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
    # one participant -> 3 visits x 3 levels = 9 cells
    assert len(grid) == 9
    present = {(c["participant_id"], c["visit_ordinal"], c["workload_level"])
               for c in grid if c["present"]}
    assert ("P01", 1, "LOW") in present
    absent = [c for c in grid if not c["present"]]
    assert len(absent) == 8
    # summary counts
    by_visit1 = [c for c in grid if c["visit_ordinal"] == 1]
    assert sum(c["present"] for c in by_visit1) == 1


def test_liftoff_grid_uses_first_valid_attempt_and_three_protocol_visits(engine):
    _seed(engine)
    with Session(engine) as session:
        visit = session.exec(__import__("sqlmodel").select(Visit).where(Visit.visit_ordinal == 1)).one()
        session.add(LiftoffSession(
            id="liftoff-invalid",
            participant_id="P01",
            visit_id=visit.id,
            attempt_number=1,
            protocol_id="astra-2026",
            protocol_version="1.0.0",
            liftoff_build="test",
            configuration_sha256="a" * 64,
            track_id="track",
            telemetry_profile="liftoff-telemetry-all-v1",
            manifest_json='{"visit_code":"T0","visit_ordinal":1}',
            status="ABORTED",
            validity="invalid",
            artifact_root="/tmp/invalid",
            controller_lease_hash="b" * 64,
        ))
        session.add(LiftoffSession(
            id="liftoff-valid",
            participant_id="P01",
            visit_id=visit.id,
            attempt_number=2,
            protocol_id="astra-2026",
            protocol_version="1.0.0",
            liftoff_build="test",
            configuration_sha256="a" * 64,
            track_id="track",
            telemetry_profile="liftoff-telemetry-all-v1",
            manifest_json='{"visit_code":"T0","visit_ordinal":1}',
            status="FINISHED",
            validity="valid",
            artifact_root="/tmp/valid",
            controller_lease_hash="c" * 64,
            hrv_measurement_id="hrv-123",
            sync_quality="good",
            metrics_json='{"metrics_version":"liftoff-metrics-v1","primary":{"median_lap_time_s":61.2}}',
        ))
        session.commit()
        grid = build_liftoff_completeness_grid(session)

    assert len(grid) == 3
    assert grid[0]["visit_code"] == "T0"
    assert grid[0]["attempt_count"] == 2
    assert grid[0]["session_id"] == "liftoff-valid"
    assert grid[0]["present"] is True
    assert grid[0]["hrv_measurement_id"] == "hrv-123"
