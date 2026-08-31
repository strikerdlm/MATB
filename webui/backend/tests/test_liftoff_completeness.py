from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from app.completeness import build_liftoff_completeness_grid
from app.liftoff_models import LiftoffSession
from app.models import Participant, Visit
from app.study_protocol import get_protocol


def _seed(engine) -> None:
    with Session(engine) as session:
        session.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        for definition in get_protocol("astra-2026").visits:
            session.add(Visit(
                participant_id="P01",
                visit_ordinal=definition.ordinal,
                scheduled_day=definition.scheduled_day,
            ))
        session.commit()


def test_liftoff_grid_uses_first_valid_attempt_and_three_protocol_visits(engine):
    _seed(engine)
    with Session(engine) as session:
        visit = session.exec(select(Visit).where(Visit.visit_ordinal == 1)).one()
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
