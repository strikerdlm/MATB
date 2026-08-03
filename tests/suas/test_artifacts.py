"""Artifact sealing and checksum inventory tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from matb_integration.suas.domain.serialization import canonical_data
from matb_integration.suas.engine.runtime import ENGINE_VERSION, SimulationEngine
from matb_integration.suas.recording.artifacts import verify_checksum_file
from matb_integration.suas.recording.recorder import (
    RecordKind, RecordingError, SessionRecord, SessionRecorder,
)
from matb_integration.suas.recording.replay import ReplayStatus, ReplayVerifier
from matb_integration.suas.scenarios.loader import load_scenario


@pytest.fixture
def recorded_low_run(tmp_path: Path) -> Path:
    loaded = load_scenario(Path("scenarios/suas/reference_area_search.yaml"))
    run = tmp_path / "run"
    recorder = SessionRecorder(
        run,
        {
            "manifest_version": 1,
            "engine_version": ENGINE_VERSION,
            "scenario_id": loaded.definition.scenario_id,
            "scenario_sha256": loaded.sha256,
        },
        loaded.normalized_yaml,
    )
    sequence = 1
    recorder.append(SessionRecord(
        "session-1", "LOW", sequence, 0, "2026-08-01T12:00:00Z", 0,
        RecordKind.LIFECYCLE, {"event": "block_started", "active_aircraft": 1, "required_contacts": 0},
    ))
    sequence += 1
    engine = SimulationEngine(loaded.definition, "LOW")
    events: list[object] = []
    for _ in range(1):
        result = engine.step()
        for event in result.events:
            value = canonical_data(event)
            events.append(value)
            recorder.append(SessionRecord(
                "session-1", "LOW", sequence, result.snapshot["simulation_time_ms"],
                "2026-08-01T12:00:00Z", result.snapshot["state_version"],
                RecordKind.DOMAIN_EVENT, {"event": value},
            ))
            sequence += 1
    from matb_integration.suas.recording.replay import event_chain_hash

    recorder.append(SessionRecord(
        "session-1", "LOW", sequence, 100, "2026-08-01T12:00:00Z", engine.snapshot()["state_version"],
        RecordKind.LIFECYCLE,
        {"event": "block_finished", "state_sha256": engine.state_hash, "event_sha256": event_chain_hash(events)},
    ))
    recorder.close()
    return run


def test_seal_writes_complete_inventory_and_valid_checksums(recorded_low_run: Path) -> None:
    recorder = SessionRecorder.open_existing(recorded_low_run)
    replay = ReplayVerifier().verify(recorded_low_run)
    artifacts = recorder.seal(
        questionnaires={}, metrics={"coverage": {}}, debrief={"timeline": []}, replay=replay,
    )
    names = {item.path.name for item in artifacts}
    assert {
        "questionnaires.json", "metrics.json", "debrief.json", "replay-verification.json",
        "checksums.sha256",
    } <= names
    assert verify_checksum_file(recorded_low_run / "checksums.sha256") == ()


def test_seal_refuses_replay_mismatch(recorded_low_run: Path) -> None:
    mismatch = replace(ReplayVerifier().verify(recorded_low_run), status=ReplayStatus.MISMATCH)
    with pytest.raises(RecordingError, match="replay must match"):
        SessionRecorder.open_existing(recorded_low_run).seal(
            questionnaires={}, metrics={}, debrief={}, replay=mismatch,
        )


def test_partial_seal_is_checksum_verifiable_but_not_replay_verified(recorded_low_run: Path) -> None:
    artifacts = SessionRecorder.open_existing(recorded_low_run).seal_partial(reason="aborted")
    assert verify_checksum_file(recorded_low_run / "checksums.sha256") == ()
    assert not (recorded_low_run / "replay-verification.json").exists()
    assert any(item.path.name == "partial-run.json" for item in artifacts)
    assert any(item.kind == "partial_unverified" for item in artifacts)


def test_complete_seal_is_idempotent_and_immutable(recorded_low_run: Path) -> None:
    recorder = SessionRecorder.open_existing(recorded_low_run)
    replay = ReplayVerifier().verify(recorded_low_run)
    first = recorder.seal(questionnaires={}, metrics={}, debrief={}, replay=replay)
    second = recorder.seal(questionnaires={}, metrics={}, debrief={}, replay=replay)
    assert first == second
    with pytest.raises(RecordingError, match="sealed run is immutable"):
        recorder.seal(questionnaires={"changed": True}, metrics={}, debrief={}, replay=replay)


def test_partial_seal_is_idempotent_for_same_reason_and_immutable_for_new_reason(
    recorded_low_run: Path,
) -> None:
    recorder = SessionRecorder.open_existing(recorded_low_run)
    first = recorder.seal_partial(reason="aborted")
    second = recorder.seal_partial(reason="aborted")
    assert first == second
    with pytest.raises(RecordingError, match="sealed run is immutable"):
        recorder.seal_partial(reason="operator_cancelled")
