from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.models import Participant, Visit
from app.simulation_models import (
    ProtocolDeviation,
    SimulationArtifact,
    SimulationBlock,
    SimulationSession,
)
from app.simulation_schemas import (
    ArtifactView,
    CommandRequest,
    CreateSimulationSession,
    ErrorDetail,
    FinishRequest,
    LifecycleRequest,
    PreparedSession,
    RecoverRequest,
    RecoveryView,
    ScenarioSummary,
    ScenarioValidationView,
    SessionView,
)


def seed_participant_and_visit(engine) -> None:
    with Session(engine) as db:
        db.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        db.add(Visit(participant_id="P01", visit_ordinal=1, scheduled_day=0))
        db.commit()


def seed_simulation_session(engine) -> None:
    seed_participant_and_visit(engine)
    with Session(engine) as db:
        visit = db.query(Visit).first()
        db.add(
            SimulationSession(
                id="sim-001",
                participant_id="P01",
                visit_id=visit.id,
                scenario_id="reference_area_search",
                scenario_sha256="a" * 64,
                manifest_json="{}",
                locale="en",
                lifecycle="PREPARED",
                validity="valid",
                artifact_root="exports/simulation/sim-001",
            )
        )
        db.commit()


def test_simulation_metadata_round_trip(engine) -> None:
    seed_participant_and_visit(engine)
    with Session(engine) as db:
        row = SimulationSession(
            id="sim-001",
            participant_id="P01",
            visit_id=1,
            scenario_id="reference_area_search",
            scenario_sha256="a" * 64,
            manifest_json="{}",
            locale="es-CO",
            lifecycle="PREPARED",
            validity="valid",
            artifact_root="exports/simulation/sim-001",
        )
        db.add(row)
        db.commit()
        assert db.get(SimulationSession, "sim-001").locale == "es-CO"


def test_block_id_is_unique_per_simulation(engine) -> None:
    seed_simulation_session(engine)
    with Session(engine) as db:
        db.add(
            SimulationBlock(
                session_id="sim-001",
                block_id="LOW",
                profile="LOW",
                order_index=1,
                lifecycle="PREPARED",
            )
        )
        db.commit()
        db.add(
            SimulationBlock(
                session_id="sim-001",
                block_id="LOW",
                profile="LOW",
                order_index=2,
                lifecycle="PREPARED",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_artifact_path_is_unique_per_simulation(engine) -> None:
    seed_simulation_session(engine)
    with Session(engine) as db:
        db.add(
            SimulationArtifact(
                session_id="sim-001",
                kind="manifest",
                relative_path="manifest.json",
                sha256="b" * 64,
                size_bytes=2,
            )
        )
        db.commit()
        db.add(
            SimulationArtifact(
                session_id="sim-001",
                kind="manifest-copy",
                relative_path="manifest.json",
                sha256="c" * 64,
                size_bytes=2,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_protocol_deviation_round_trip(engine) -> None:
    seed_simulation_session(engine)
    with Session(engine) as db:
        db.add(
            ProtocolDeviation(
                session_id="sim-001",
                block_id="LOW",
                code="process_restart",
                severity="warning",
                simulation_time_ms=5_000,
                detail_json='{"reason":"restart"}',
            )
        )
        db.commit()
        deviation = db.query(ProtocolDeviation).one()
        assert deviation.disposition == "unreviewed"


def test_create_schema_rejects_real_identity_and_invalid_locale() -> None:
    with pytest.raises(ValidationError):
        CreateSimulationSession(
            participant_id="John Smith",
            visit_ordinal=1,
            scenario_id="reference_area_search",
            locale="en",
        )
    with pytest.raises(ValidationError):
        CreateSimulationSession(
            participant_id="P01",
            visit_ordinal=1,
            scenario_id="reference_area_search",
            locale="fr",
        )


def test_create_schema_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CreateSimulationSession(
            participant_id="P01",
            visit_ordinal=1,
            scenario_id="reference_area_search",
            locale="en",
            participant_name="Jane Doe",
        )


def test_command_schema_accepts_json_payload_and_rejects_unknown_fields() -> None:
    command = CommandRequest(
        command_id=uuid4(),
        expected_state_version=0,
        kind="ASSIGN_SECTOR",
        payload={"aircraft_id": "UAS-01", "sector_id": "SECTOR-A"},
    )
    assert command.payload["aircraft_id"] == "UAS-01"
    with pytest.raises(ValidationError):
        CommandRequest(
            command_id=uuid4(),
            expected_state_version=0,
            kind="HOLD",
            payload={},
            operator_note="free text is not accepted",
        )


@pytest.mark.parametrize(
    ("schema", "values"),
    [
        (LifecycleRequest, {"reason": "operator_pause"}),
        (FinishRequest, {"disposition": "complete"}),
        (RecoverRequest, {"checkpoint_version": 0}),
        (ArtifactView, {"kind": "manifest", "relative_path": "manifest.json", "sha256": "a" * 64, "size_bytes": 2}),
        (ScenarioSummary, {"scenario_id": "reference_area_search"}),
        (ScenarioValidationView, {"valid": True}),
        (ErrorDetail, {"code": "invalid_state", "message": "invalid"}),
    ],
)
def test_public_schemas_forbid_unknown_fields(schema, values) -> None:
    with pytest.raises(ValidationError):
        schema(**values, unknown_field=True)


def test_lease_visibility_is_limited_to_prepared_and_recovery_views() -> None:
    assert "controller_lease" in PreparedSession.model_fields
    assert "controller_lease" not in SessionView.model_fields
    assert "controller_lease" in RecoveryView.model_fields
