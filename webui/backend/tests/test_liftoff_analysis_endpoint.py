from __future__ import annotations

import json

from sqlmodel import Session, select

from app.liftoff_models import LiftoffSession
from app.models import Visit
from app.study_models import StudyParticipantContext


def test_research_context_includes_liftoff_three_visit_grid(client, engine):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    with Session(engine) as session:
        visit = session.exec(
            select(Visit).where(Visit.participant_id == "P01", Visit.visit_ordinal == 1)
        ).one()
        session.add(LiftoffSession(
            id="liftoff-valid",
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
            status="FINISHED",
            validity="valid",
            artifact_root="/tmp/valid",
            controller_lease_hash="b" * 64,
            hrv_measurement_id="hrv-123",
            sync_quality="good",
            metrics_json='{"metrics_version":"liftoff-metrics-v1","primary":{"median_lap_time_s":61.2,"valid_laps":3},"telemetry":{"active_duration_s":900.0}}',
        ))
        session.commit()

    context = client.get("/exports/research-context").json()
    assert len(context["liftoff_tracker"]) == 3
    assert context["liftoff_tracker"][0]["visit_code"] == "T0"
    assert context["liftoff_tracker"][0]["present"] is True
    assert context["liftoff_metrics_long"]
    assert context["liftoff_tracker"][0]["hrv_measurement_id"] == "hrv-123"


def test_liftoff_analysis_endpoint_runs_and_caches(client, engine):
    import numpy as np
    rng = np.random.default_rng(9317)
    participants = tuple(f"P{index + 1:02d}" for index in range(12))
    intercepts = dict(zip(participants, rng.normal(0, 4, len(participants))))
    for index in range(12):
        participant_id = f"P{index + 1:02d}"
        client.post("/participants", json={"id": participant_id, "enrollment_date": "2026-08-18"})
    with Session(engine) as session:
        visits = session.exec(select(Visit).order_by(Visit.participant_id, Visit.visit_ordinal)).all()
        for index, participant_id in enumerate(participants):
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
                        "median_lap_time_s": 65.0 - visit.visit_ordinal + intercepts[visit.participant_id] + rng.normal(0, 1.5),
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
