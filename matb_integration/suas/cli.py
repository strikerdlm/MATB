"""Headless validation and deterministic execution entry point."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
from pathlib import Path

from matb_integration.suas.domain.serialization import canonical_json
from matb_integration.suas.engine.runtime import CHECKPOINT_INTERVAL_MS, ENGINE_VERSION, SimulationEngine
from matb_integration.suas.metrics.mission import derive_block_metrics
from matb_integration.suas.recording.artifacts import verify_checksum_file
from matb_integration.suas.recording.recorder import RecordingError, SessionRecord, SessionRecorder
from matb_integration.suas.recording.records import RecordKind
from matb_integration.suas.recording.replay import ReplayVerifier, event_chain_hash
from matb_integration.suas.scenarios.loader import load_scenario


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m matb_integration.suas.cli")
    subcommands = parser.add_subparsers(dest="action", required=True)
    validate = subcommands.add_parser("validate")
    validate.add_argument("path")
    run = subcommands.add_parser("run")
    run.add_argument("path")
    run.add_argument("--block", required=True)
    run.add_argument("--ticks", required=True, type=int)
    record = subcommands.add_parser("record")
    record.add_argument("path")
    record.add_argument("--block", required=True)
    record.add_argument("--ticks", required=True, type=int)
    record.add_argument("--output", required=True)
    record.add_argument("--session-id", required=True)
    verify = subcommands.add_parser("verify")
    verify.add_argument("run_dir")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.action == "verify":
            return _verify(Path(args.run_dir))
        loaded = load_scenario(args.path)
        if args.action == "validate":
            print(canonical_json({
                "scenario_id": loaded.definition.scenario_id,
                "scenario_sha256": loaded.sha256,
                "profile_counts": {
                    block_id: {"aircraft": len(block.aircraft_ids), "contacts": len(block.contact_ids)}
                    for block_id, block in sorted(loaded.definition.blocks.items())
                },
            }))
            return 0
        if args.ticks <= 0:
            raise ValueError("ticks must be a positive integer")
        if args.action == "record":
            return _record(
                loaded,
                block_id=args.block,
                ticks=args.ticks,
                output=Path(args.output),
                session_id=args.session_id,
            )
        engine = SimulationEngine(loaded.definition, args.block)
        event_count = 0
        for _ in range(args.ticks):
            event_count += len(engine.step().events)
        snapshot = engine.snapshot()
        print(canonical_json({
            "engine_version": ENGINE_VERSION,
            "ticks": args.ticks,
            "simulation_time_ms": snapshot["simulation_time_ms"],
            "event_count": event_count,
            "state_sha256": engine.state_hash,
            "snapshot": snapshot,
        }))
        return 0
    except (OSError, ValueError, TypeError, RecordingError) as error:
        print(str(error), file=sys.stderr)
        return 2


def _wall_time() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _record(
    loaded,
    *,
    block_id: str,
    ticks: int,
    output: Path,
    session_id: str,
) -> int:
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session-id must be nonempty")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise RecordingError("record output directory must be empty or absent")
    definition = loaded.definition
    block = definition.blocks.get(block_id)
    if block is None:
        raise ValueError(f"unknown block {block_id}")
    thresholds = definition.metric_thresholds
    manifest = {
        "manifest_version": 1,
        "engine_version": ENGINE_VERSION,
        "scenario_id": definition.scenario_id,
        "scenario_sha256": loaded.sha256,
        "session_id": session_id,
        "block_id": block_id,
        "metric_thresholds": {
            "coverage_target_ppm": thresholds.coverage_target_ppm,
            "contact_effectiveness_target_ppm": thresholds.contact_effectiveness_target_ppm,
            "asset_preservation_target_ppm": thresholds.asset_preservation_target_ppm,
            "timeliness_target_ppm": thresholds.timeliness_target_ppm,
        },
    }
    recorder = SessionRecorder(output, manifest, loaded.normalized_yaml)
    sequence = 0
    wall_time = _wall_time()
    engine = SimulationEngine(definition, block_id)
    recorded_events: list[object] = []

    def append(kind: RecordKind, simulation_time_ms: int, state_version: int, payload: dict[str, object]) -> None:
        nonlocal sequence
        sequence += 1
        recorder.append(SessionRecord(
            session_id=session_id,
            block_id=block_id,
            sequence=sequence,
            simulation_time_ms=simulation_time_ms,
            wall_time_utc=wall_time,
            state_version=state_version,
            kind=kind,
            payload=payload,
        ))

    append(RecordKind.LIFECYCLE, 0, 0, {
        "event": "session_prepared",
        "session_id": session_id,
        "scenario_id": definition.scenario_id,
    })
    append(RecordKind.LIFECYCLE, 0, 0, {
        "event": "block_started",
        "active_aircraft": len(block.aircraft_ids),
        "required_contacts": len(block.contact_ids),
        "required_actions": 0,
    })
    for _ in range(ticks):
        result = engine.step()
        for event in result.events:
            serialized = _canonical_event(event)
            recorded_events.append(serialized)
            append(
                RecordKind.DOMAIN_EVENT,
                event.simulation_time_ms,
                result.snapshot["state_version"],
                {"event": serialized},
            )
        if result.snapshot["simulation_time_ms"] % CHECKPOINT_INTERVAL_MS == 0:
            checkpoint = recorder.checkpoint(engine.checkpoint_snapshot())
            append(
                RecordKind.CHECKPOINT,
                result.snapshot["simulation_time_ms"],
                result.snapshot["state_version"],
                {
                    "path": checkpoint.path.relative_to(output).as_posix(),
                    "checkpoint_version": int(checkpoint.path.name.split("-")[-1].split(".")[0]),
                },
            )
    append(
        RecordKind.LIFECYCLE,
        engine.snapshot()["simulation_time_ms"],
        engine.snapshot()["state_version"],
        {
            "event": "block_finished",
            "state_sha256": engine.state_hash,
            "event_sha256": event_chain_hash(recorded_events),
        },
    )
    recorder.close()
    replay = ReplayVerifier().verify(output)
    if replay.status.value != "match":
        raise RecordingError(f"recorded run failed replay: {replay.differences}")
    records = _read_records(output / "events.jsonl")
    metrics = derive_block_metrics(records, manifest).to_dict()
    timeline = [
        {
            "sequence": record.sequence,
            "simulation_time_ms": record.simulation_time_ms,
            "event_id": record.payload.get("event", {}).get("event_id"),
            "kind": record.payload.get("event", {}).get("kind"),
        }
        for record in records
        if record.kind is RecordKind.DOMAIN_EVENT and isinstance(record.payload.get("event"), dict)
    ]
    recorder.seal(
        questionnaires={},
        metrics=metrics,
        debrief={"timeline": timeline},
        replay=replay,
    )
    print(canonical_json({
        "run_dir": str(output),
        "state_sha256": replay.expected_state_sha256,
        "event_sha256": replay.expected_event_sha256,
        "metrics_path": str(output / "metrics.json"),
        "replay_status": replay.status.value,
        "status": replay.status.value,
    }))
    return 0


def _verify(run_dir: Path) -> int:
    checksum_codes = verify_checksum_file(run_dir / "checksums.sha256")
    replay = ReplayVerifier().verify(run_dir)
    checksums_status = "match" if not checksum_codes else "mismatch"
    status = "match" if checksums_status == "match" and replay.status.value == "match" else "mismatch"
    print(canonical_json({
        "status": status,
        "checksums": {"status": checksums_status, "codes": list(checksum_codes)},
        "replay": _canonical_data(replay),
        "checksum_status": checksums_status,
        "replay_status": replay.status.value,
    }))
    return 0 if status == "match" else 2


def _read_records(path: Path) -> list[SessionRecord]:
    records: list[SessionRecord] = []
    for line in path.read_bytes().splitlines():
        records.append(SessionRecord(**json.loads(line.decode("utf-8"))))
    return records


def _canonical_event(event: object) -> object:
    from matb_integration.suas.domain.serialization import canonical_data

    return canonical_data(event)


def _canonical_data(value: object) -> object:
    from matb_integration.suas.domain.serialization import canonical_data

    return canonical_data(value)


if __name__ == "__main__":
    raise SystemExit(main())
