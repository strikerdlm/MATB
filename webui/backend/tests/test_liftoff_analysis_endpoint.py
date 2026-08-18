from __future__ import annotations

import json

from sqlmodel import Session, select

from app.liftoff_models import LiftoffSession
from app.models import Visit
from app.study_models import StudyParticipantContext


def test_liftoff_analysis_endpoint_runs_and_caches(client, engine):
    for index in range(3):
        participant_id = f"P{index + 1:02d}"
        client.post("/participants", json={"id": participant_id, "enrollment_date": "2026-08-18"})
    with Session(engine) as session:
        visits = session.exec(select(Visit).order_by(Visit.participant_id, Visit.visit_ordinal)).all()
        for index, participant_id in enumerate(("P01", "P02", "P03")):
            session.add(StudyParticipantContext(
                participant_id=participant_id,
                protocol_id="astra-2026",
                task_sequence="MATB_LIFTOFF" if index % 2 == 0 else "LIFTOFF_MATB",
                prior_fpv_hours=float(index * 5),
                gaming_hours_per_week=2.0,
            ))
        for visit in visits:
            manifest = {
                "visit_code": {1: "T0", 2: "DM8", 3: "DM15"}[visit.visit_ordinal],
                "visit_ordinal": visit.visit_ordinal,
            }
            session.add(LiftoffSession(
                id=f"{visit.participant_id}-{visit.visit_ordinal}",
                participant_id=visit.participant_id,
                visit_id=visit.id,
                attempt_number=1,
                protocol_id="astra-2026",
                protocol_version="1.0.0",
                liftoff_build="test",
                configuration_sha256="a" * 64,
                track_id="track",
                telemetry_profile="liftoff-telemetry-all-v1",
                manifest_json=json.dumps(manifest),
                status="FINISHED",
                validity="valid",
                artifact_root="/tmp/test",
                controller_lease_hash="b" * 64,
                metrics_json=json.dumps({
                    "metrics_version": "liftoff-metrics-v1",
                    "primary": {
                        "median_lap_time_s": 65.0 - visit.visit_ordinal + int(visit.participant_id[-1]),
                        "valid_laps": 8 + visit.visit_ordinal,
                    },
                    "telemetry": {},
                }),
            ))
        session.commit()

    first = client.post("/analysis/liftoff/run")
    second = client.post("/analysis/liftoff/run")

    assert first.status_code == 200, first.text
    assert first.json()["analysis_version"] == "liftoff-analysis-v1"
    assert first.json()["status"] == "ok"
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
