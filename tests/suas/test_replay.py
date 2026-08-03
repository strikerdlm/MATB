"""Replay verification regressions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from matb_integration.suas.domain.commands import CommandEnvelope, Hold
from matb_integration.suas.domain.serialization import canonical_data, canonical_json
from matb_integration.suas.engine.runtime import ENGINE_VERSION, SimulationEngine
from matb_integration.suas.recording.recorder import RecordKind, SessionRecord, SessionRecorder
from matb_integration.suas.recording.replay import ReplayStatus, ReplayVerifier, effective_records, event_chain_hash
from matb_integration.suas.scenarios.loader import load_scenario


def _record(
    seq: int, kind: RecordKind, time: int, version: int, payload: dict[str, object], block_id: str = "LOW",
) -> SessionRecord:
    return SessionRecord("session-1", block_id, seq, time, "2026-08-01T12:00:00Z", version, kind, payload)


@pytest.fixture
def recorded_low_run(tmp_path: Path) -> Path:
    loaded = load_scenario(Path("scenarios/suas/reference_area_search.yaml"))
    run = tmp_path / "run"
    recorder = SessionRecorder(run, {"manifest_version": 1, "engine_version": ENGINE_VERSION, "scenario_id": loaded.definition.scenario_id, "scenario_sha256": loaded.sha256, "block_order": ["LOW", "MEDIUM", "HIGH"]}, loaded.normalized_yaml)
    sequence = 1
    recorder.append(_record(sequence, RecordKind.LIFECYCLE, 0, 0, {"event": "block_started"}))
    sequence += 1
    engine = SimulationEngine(loaded.definition, "LOW")
    events: list[object] = []
    for tick in range(1, 101):
        commands = ()
        if tick == 5:
            envelope = CommandEnvelope("hold-1", engine.snapshot()["state_version"], Hold("UAS-01"))
            recorder.append(_record(sequence, RecordKind.COMMAND, (tick - 1) * 100, int(engine.snapshot()["state_version"]), {"applied_tick": tick, "command": {"command_id": envelope.command_id, "expected_state_version": envelope.expected_state_version, "kind": "Hold", "payload": {"aircraft_id": "UAS-01"}}}))
            sequence += 1
            commands = (envelope,)
        result = engine.step(commands)
        for event in result.events:
            item = canonical_data(event)
            events.append(item)
            recorder.append(_record(sequence, RecordKind.DOMAIN_EVENT, event.simulation_time_ms, result.snapshot["state_version"], {"event": item}))
            sequence += 1
    recorder.append(_record(sequence, RecordKind.LIFECYCLE, 10_000, engine.snapshot()["state_version"], {"event": "block_finished", "state_sha256": engine.state_hash, "event_sha256": event_chain_hash(events)}))
    recorder.close()
    return run


@pytest.fixture
def recorded_full_run(tmp_path: Path) -> Path:
    loaded = load_scenario(Path("scenarios/suas/reference_area_search.yaml"))
    run = tmp_path / "full-run"
    recorder = SessionRecorder(run, {"manifest_version": 1, "engine_version": ENGINE_VERSION, "scenario_id": loaded.definition.scenario_id, "scenario_sha256": loaded.sha256, "block_order": ["LOW", "MEDIUM", "HIGH"]}, loaded.normalized_yaml)
    sequence = 1
    for block_id in ("PRACTICE", "LOW", "MEDIUM", "HIGH"):
        recorder.append(_record(sequence, RecordKind.LIFECYCLE, 0, 0, {"event": "block_started"}, block_id))
        sequence += 1
        engine = SimulationEngine(loaded.definition, block_id)
        result = engine.step()
        events = [canonical_data(event) for event in result.events]
        for event in events:
            recorder.append(_record(sequence, RecordKind.DOMAIN_EVENT, 100, result.snapshot["state_version"], {"event": event}, block_id))
            sequence += 1
        recorder.append(_record(sequence, RecordKind.LIFECYCLE, 100, result.snapshot["state_version"], {"event": "block_finished", "state_sha256": engine.state_hash, "event_sha256": event_chain_hash(events)}, block_id))
        sequence += 1
    recorder.close()
    return run


def rewrite_record(path: Path, *, kind: str, applied_tick: int) -> None:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for row in rows:
        if row["kind"] == kind:
            row["payload"]["applied_tick"] = applied_tick
            break
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")


def rewrite_manifest(run: Path, *, engine_version: str) -> None:
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    manifest["engine_version"] = engine_version
    (run / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")


def remove_manifest_block_order(run: Path) -> None:
    path = run / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.pop("block_order", None)
    path.write_text(canonical_json(manifest), encoding="utf-8")


def rewrite_manifest_block_order(run: Path, block_order: object) -> None:
    path = run / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["block_order"] = block_order
    path.write_text(canonical_json(manifest), encoding="utf-8")


def rewrite_rows(run: Path, mutate) -> None:
    path = run / "events.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    mutate(rows)
    for sequence, row in enumerate(rows, start=1):
        row["sequence"] = sequence
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")


def test_replay_matches_final_state_and_event_chain(recorded_low_run: Path) -> None:
    result = ReplayVerifier().verify(recorded_low_run)
    assert result.status is ReplayStatus.MATCH
    assert result.expected_state_sha256 == result.actual_state_sha256
    assert result.expected_event_sha256 == result.actual_event_sha256


def test_replay_detects_tampered_applied_tick(recorded_low_run: Path) -> None:
    rewrite_record(recorded_low_run / "events.jsonl", kind="command", applied_tick=7)
    result = ReplayVerifier().verify(recorded_low_run)
    assert result.status is ReplayStatus.MISMATCH
    assert "state_sha256" in result.differences or "event_sha256" in result.differences


def test_replay_refuses_engine_version_mismatch(recorded_low_run: Path) -> None:
    rewrite_manifest(recorded_low_run, engine_version="99.0.0")
    result = ReplayVerifier().verify(recorded_low_run)
    assert result.status is ReplayStatus.INCOMPATIBLE_ENGINE


def test_replay_accepts_one_block_cli_without_block_order(recorded_low_run: Path) -> None:
    remove_manifest_block_order(recorded_low_run)
    result = ReplayVerifier().verify(recorded_low_run)
    assert result.status is ReplayStatus.MATCH


def test_replay_rejects_duplicate_block_protocol(recorded_low_run: Path) -> None:
    def duplicate(rows: list[dict[str, object]]) -> None:
        rows.extend(json.loads(canonical_json(row)) for row in rows[:])

    rewrite_rows(recorded_low_run, duplicate)
    result = ReplayVerifier().verify(recorded_low_run)
    assert result.status is ReplayStatus.INVALID_RECORD
    assert result.differences == ("invalid_block_protocol",)


def test_replay_rejects_partial_block_protocol(recorded_low_run: Path) -> None:
    def add_medium(rows: list[dict[str, object]]) -> None:
        copied = [json.loads(canonical_json(row)) for row in rows[:]]
        for row in copied:
            row["block_id"] = "MEDIUM"
        rows.extend(copied)

    rewrite_rows(recorded_low_run, add_medium)
    result = ReplayVerifier().verify(recorded_low_run)
    assert result.status is ReplayStatus.INVALID_RECORD
    assert result.differences == ("invalid_block_protocol",)


def test_replay_rejects_unknown_lifecycle_event(recorded_low_run: Path) -> None:
    def insert_unknown(rows: list[dict[str, object]]) -> None:
        first = json.loads(canonical_json(rows[0]))
        first["payload"] = {"event": "block_paused"}
        rows.insert(1, first)

    rewrite_rows(recorded_low_run, insert_unknown)
    result = ReplayVerifier().verify(recorded_low_run)
    assert result.status is ReplayStatus.INVALID_RECORD
    assert result.differences == ("unknown_lifecycle_event",)


def test_replay_matches_complete_manifest_ordered_protocol(recorded_full_run: Path) -> None:
    result = ReplayVerifier().verify(recorded_full_run)
    assert result.status is ReplayStatus.MATCH
    assert result.ticks_replayed == 4


def test_replay_rejects_full_protocol_without_block_order(recorded_full_run: Path) -> None:
    remove_manifest_block_order(recorded_full_run)
    result = ReplayVerifier().verify(recorded_full_run)
    assert result.status is ReplayStatus.INVALID_RECORD
    assert result.differences == ("missing_block_order",)


def test_replay_rejects_malformed_manifest_block_order(recorded_full_run: Path) -> None:
    rewrite_manifest_block_order(recorded_full_run, ["LOW", "LOW", "HIGH"])
    result = ReplayVerifier().verify(recorded_full_run)
    assert result.status is ReplayStatus.INVALID_RECORD
    assert result.differences == ("invalid_block_order",)


def test_replay_rejects_full_protocol_in_wrong_manifest_order(recorded_full_run: Path) -> None:
    def swap_low_medium(rows: list[dict[str, object]]) -> None:
        for row in rows:
            if row["block_id"] == "LOW":
                row["block_id"] = "MEDIUM"
            elif row["block_id"] == "MEDIUM":
                row["block_id"] = "LOW"

    rewrite_rows(recorded_full_run, swap_low_medium)
    result = ReplayVerifier().verify(recorded_full_run)
    assert result.status is ReplayStatus.INVALID_RECORD
    assert result.differences == ("invalid_block_protocol",)


def test_effective_records_excludes_invalidated_branch_but_keeps_recovery_audit() -> None:
    records = [
        _record(1, RecordKind.LIFECYCLE, 0, 0, {"event": "block_started"}),
        _record(2, RecordKind.COMMAND, 100, 0, {"applied_tick": 1, "command": {"command_id": "a", "expected_state_version": 0, "kind": "Hold", "payload": {"aircraft_id": "UAS-01"}}}),
        _record(3, RecordKind.DOMAIN_EVENT, 100, 1, {"event": {"event_id": "old"}}),
        _record(4, RecordKind.LIFECYCLE, 100, 1, {"event": "checkpoint_recovery", "invalidated_sequence_start": 2, "invalidated_sequence_end": 3}),
        _record(5, RecordKind.DOMAIN_EVENT, 200, 2, {"event": {"event_id": "new"}}),
    ]
    assert [record.sequence for record in effective_records(records)] == [1, 4, 5]


def test_effective_records_rejects_overlapping_recovery_ranges() -> None:
    records = [
        _record(1, RecordKind.LIFECYCLE, 0, 0, {"event": "checkpoint_recovery", "invalidated_sequence_start": 1, "invalidated_sequence_end": 0}),
    ]
    with pytest.raises(ValueError, match="invalid_recovery_range"):
        effective_records(records)
