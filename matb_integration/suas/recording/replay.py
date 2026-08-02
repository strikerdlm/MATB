"""Offline verification of deterministic sUAS session recordings."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from matb_integration.suas.domain.commands import (
    AcknowledgeAlert, AssignSector, ClassifyContact, CommandEnvelope, Hold,
    InspectContact, ReportContact, ResumeMission, ReturnToBase, SetContactPriority,
    SetWaypoint,
)
from matb_integration.suas.domain.enums import ContactClassification, ContactPriority
from matb_integration.suas.domain.geometry import PointMM
from matb_integration.suas.domain.serialization import canonical_data, canonical_json
from matb_integration.suas.engine.runtime import ENGINE_VERSION, TICK_MS, SimulationEngine
from matb_integration.suas.recording.checkpoints import load_checkpoint
from matb_integration.suas.recording.records import RecordKind, SessionRecord
from matb_integration.suas.scenarios.loader import load_scenario_text


class ReplayStatus(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"
    INVALID_RECORD = "invalid_record"
    INCOMPATIBLE_ENGINE = "incompatible_engine"


@dataclass(frozen=True, slots=True)
class ReplayResult:
    status: ReplayStatus
    expected_state_sha256: str | None
    actual_state_sha256: str | None
    expected_event_sha256: str | None
    actual_event_sha256: str | None
    records_read: int
    ticks_replayed: int
    differences: tuple[str, ...]


_COMMANDS = {
    "AssignSector": (AssignSector, {"aircraft_id", "sector_id"}),
    "SetWaypoint": (SetWaypoint, {"aircraft_id", "waypoint"}),
    "Hold": (Hold, {"aircraft_id"}),
    "ResumeMission": (ResumeMission, {"aircraft_id"}),
    "ReturnToBase": (ReturnToBase, {"aircraft_id"}),
    "AcknowledgeAlert": (AcknowledgeAlert, {"alert_id"}),
    "InspectContact": (InspectContact, {"contact_id"}),
    "ClassifyContact": (ClassifyContact, {"contact_id", "classification"}),
    "SetContactPriority": (SetContactPriority, {"contact_id", "priority"}),
    "ReportContact": (ReportContact, {"contact_id", "note_code"}),
}
_CHECKPOINT_NAME = re.compile(r"checkpoint-([0-9]{8})\.json\.gz")


def deserialize_command(data: Mapping[str, object]) -> CommandEnvelope:
    """Deserialize one closed, JSON-safe command envelope.

    The serialized form is ``command_id``, ``expected_state_version``, ``kind``,
    and ``payload``.  No best-effort coercion is performed during replay.
    """
    if not isinstance(data, Mapping) or set(data) != {"command_id", "expected_state_version", "kind", "payload"}:
        raise ValueError("invalid_command_shape")
    command_id = data["command_id"]
    expected = data["expected_state_version"]
    kind = data["kind"]
    payload = data["payload"]
    if not isinstance(command_id, str) or not command_id or isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
        raise ValueError("invalid_command_envelope")
    if not isinstance(kind, str) or kind not in _COMMANDS or not isinstance(payload, Mapping):
        raise ValueError("invalid_command_kind")
    command_type, fields = _COMMANDS[kind]
    if set(payload) != fields:
        raise ValueError("invalid_command_payload")
    values = dict(payload)
    try:
        for field in fields - {"waypoint", "classification", "priority"}:
            if not isinstance(values[field], str) or not values[field]:
                raise ValueError("invalid_command_payload")
        if command_type is SetWaypoint:
            waypoint = values["waypoint"]
            if not isinstance(waypoint, Mapping) or set(waypoint) != {"x_mm", "y_mm"}:
                raise ValueError("invalid_command_payload")
            x, y = waypoint["x_mm"], waypoint["y_mm"]
            if any(isinstance(value, bool) or not isinstance(value, int) for value in (x, y)):
                raise ValueError("invalid_command_payload")
            values["waypoint"] = PointMM(x, y)
        elif command_type is ClassifyContact:
            values["classification"] = ContactClassification(values["classification"])
        elif command_type is SetContactPriority:
            values["priority"] = ContactPriority(values["priority"])
        command = command_type(**values)
    except (TypeError, ValueError) as error:
        raise ValueError("invalid_command_payload") from error
    return CommandEnvelope(command_id=command_id, expected_state_version=expected, command=command)


def event_chain_hash(events: Iterable[object]) -> str:
    chain = bytes(32)
    for event in events:
        chain = hashlib.sha256(chain + canonical_json(event).encode("utf-8")).digest()
    return chain.hex()


class _InvalidRecord(ValueError):
    pass


class ReplayVerifier:
    """Rebuild recorded blocks without consulting checkpoints or wall-clock time."""

    def verify(self, run_dir: Path) -> ReplayResult:
        records_read = ticks = 0
        try:
            run_dir = Path(run_dir)
            manifest = self._load_manifest(run_dir)
            if manifest.get("engine_version") != ENGINE_VERSION:
                return self._result(ReplayStatus.INCOMPATIBLE_ENGINE, records_read, ticks, "engine_version")
            scenario = load_scenario_text((run_dir / "scenario.yaml").read_text(encoding="utf-8"), source_name="frozen scenario")
            if manifest.get("scenario_id") != scenario.definition.scenario_id or manifest.get("scenario_sha256") != scenario.sha256:
                raise _InvalidRecord("scenario_sha256")
            self._validate_checkpoints(run_dir)
            records = self._load_records(run_dir / "events.jsonl")
            records_read = len(records)
            blocks = self._blocks(records, tuple(scenario.definition.blocks))
            expected_state = actual_state = expected_event = actual_event = None
            all_expected_events: list[object] = []
            all_actual_events: list[object] = []
            differences: list[str] = []
            for block_id, block_records, finish in blocks:
                commands, recorded_events = self._block_records(block_records)
                target = finish.simulation_time_ms
                if target % TICK_MS:
                    raise _InvalidRecord("block_finish_time")
                if any(tick > target // TICK_MS for tick in commands):
                    raise _InvalidRecord("command_tick_out_of_range")
                engine = SimulationEngine(scenario.definition, block_id)
                actual_events: list[object] = []
                for tick in range(1, target // TICK_MS + 1):
                    actual_events.extend(canonical_data(event) for event in engine.step(commands.get(tick, ())).events)
                ticks += target // TICK_MS
                expected_state = self._required_hash(finish.payload, "state_sha256")
                expected_block_event = self._required_hash(finish.payload, "event_sha256")
                actual_state = engine.state_hash
                actual_block_event = event_chain_hash(actual_events)
                if expected_state != actual_state and "state_sha256" not in differences:
                    differences.append("state_sha256")
                if expected_block_event != event_chain_hash(recorded_events) or recorded_events != actual_events:
                    if "event_sha256" not in differences:
                        differences.append("event_sha256")
                all_expected_events.extend(recorded_events)
                all_actual_events.extend(actual_events)
                expected_event, actual_event = event_chain_hash(all_expected_events), event_chain_hash(all_actual_events)
                self._check_session_hashes(finish.payload, actual_state, actual_event, differences)
            if not blocks:
                raise _InvalidRecord("missing_block")
            if expected_event != actual_event and "event_sha256" not in differences:
                differences.append("event_sha256")
            return ReplayResult(ReplayStatus.MISMATCH if differences else ReplayStatus.MATCH, expected_state, actual_state, expected_event, actual_event, records_read, ticks, tuple(differences))
        except _InvalidRecord as error:
            return self._result(ReplayStatus.INVALID_RECORD, records_read, ticks, str(error))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            return self._result(ReplayStatus.INVALID_RECORD, records_read, ticks, "malformed_record")

    @staticmethod
    def _result(status: ReplayStatus, records: int, ticks: int, difference: str) -> ReplayResult:
        return ReplayResult(status, None, None, None, None, records, ticks, (difference,))

    @staticmethod
    def _load_manifest(run_dir: Path) -> Mapping[str, object]:
        try:
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise _InvalidRecord("manifest") from error
        if not isinstance(manifest, dict):
            raise _InvalidRecord("manifest")
        return manifest

    @staticmethod
    def _load_records(path: Path) -> list[SessionRecord]:
        raw = path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            raise _InvalidRecord("incomplete_jsonl")
        records: list[SessionRecord] = []
        for line in raw.splitlines():
            if not line or b"\r" in line:
                raise _InvalidRecord("malformed_jsonl")
            try:
                data = json.loads(line.decode("utf-8"))
                record = SessionRecord(**data)
            except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise _InvalidRecord("malformed_record") from error
            if canonical_json(record).encode("utf-8") != line:
                raise _InvalidRecord("noncanonical_record")
            if record.sequence != len(records) + 1:
                raise _InvalidRecord("sequence_gap")
            records.append(record)
        return records

    @staticmethod
    def _validate_checkpoints(run_dir: Path) -> None:
        directory = run_dir / "checkpoints"
        if not directory.is_dir():
            raise _InvalidRecord("checkpoints_missing")
        names = sorted(directory.iterdir())
        for expected, path in enumerate(names, start=1):
            match = _CHECKPOINT_NAME.fullmatch(path.name)
            if not path.is_file() or match is None or int(match.group(1)) != expected:
                raise _InvalidRecord("checkpoint_ordinal_gap")
            try:
                wrapper = load_checkpoint(path)
            except Exception as error:
                raise _InvalidRecord("invalid_checkpoint") from error
            if wrapper.get("checkpoint_version") != expected:
                raise _InvalidRecord("checkpoint_ordinal_gap")

    @staticmethod
    def _blocks(
        records: list[SessionRecord], allowed_order: tuple[str, ...],
    ) -> list[tuple[str, list[SessionRecord], SessionRecord]]:
        blocks: list[tuple[str, list[SessionRecord], SessionRecord]] = []
        active: tuple[str, list[SessionRecord]] | None = None
        for record in records:
            if record.kind is RecordKind.LIFECYCLE:
                event = record.payload.get("event")
                if event not in {"block_started", "block_finished"}:
                    raise _InvalidRecord("unknown_lifecycle_event")
                if event == "block_started":
                    if active is not None:
                        raise _InvalidRecord("overlapping_block")
                    if record.block_id not in allowed_order:
                        raise _InvalidRecord("invalid_block_protocol")
                    active = (record.block_id, [])
                    continue
                if event == "block_finished":
                    if active is None or active[0] != record.block_id:
                        raise _InvalidRecord("missing_block_start")
                    blocks.append((active[0], active[1], record))
                    active = None
                    continue
            if active is not None:
                if record.block_id != active[0]:
                    raise _InvalidRecord("block_id_mismatch")
                active[1].append(record)
            elif record.kind is not RecordKind.CHECKPOINT:
                raise _InvalidRecord("record_outside_block")
        if active is not None:
            raise _InvalidRecord("missing_block_finish")
        completed = tuple(block_id for block_id, _, _ in blocks)
        if len(completed) != 1 and completed != allowed_order:
            raise _InvalidRecord("invalid_block_protocol")
        return blocks

    @staticmethod
    def _block_records(records: list[SessionRecord]) -> tuple[dict[int, tuple[CommandEnvelope, ...]], list[object]]:
        commands: defaultdict[int, list[CommandEnvelope]] = defaultdict(list)
        events: list[object] = []
        for record in records:
            if record.kind is RecordKind.COMMAND:
                payload = record.payload
                tick = payload.get("applied_tick")
                serialized = payload.get("command", payload)
                if isinstance(tick, bool) or not isinstance(tick, int) or tick <= 0 or not isinstance(serialized, Mapping):
                    raise _InvalidRecord("invalid_command_record")
                try:
                    commands[tick].append(deserialize_command(serialized))
                except ValueError as error:
                    raise _InvalidRecord(str(error)) from error
            elif record.kind is RecordKind.DOMAIN_EVENT:
                event = record.payload.get("event", record.payload)
                if not isinstance(event, Mapping):
                    raise _InvalidRecord("invalid_domain_event")
                events.append(canonical_data(event))
        return {tick: tuple(items) for tick, items in commands.items()}, events

    @staticmethod
    def _required_hash(payload: Mapping[str, object], field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or len(value) != 64:
            raise _InvalidRecord(f"missing_{field}")
        return value

    @staticmethod
    def _check_session_hashes(payload: Mapping[str, object], state: str, event: str, differences: list[str]) -> None:
        expected_state = payload.get("session_state_sha256")
        expected_event = payload.get("session_event_sha256")
        if expected_state is not None and expected_state != state and "state_sha256" not in differences:
            differences.append("state_sha256")
        if expected_event is not None and expected_event != event and "event_sha256" not in differences:
            differences.append("event_sha256")
