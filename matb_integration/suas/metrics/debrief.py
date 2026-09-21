"""Public debrief construction for sealed native sUAS recordings."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from matb_integration.suas.domain.serialization import canonical_data
from matb_integration.suas.engine.runtime import SimulationEngine
from matb_integration.suas.metrics.mission import derive_block_metrics
from matb_integration.suas.metrics.research import derive_research_metrics
from matb_integration.suas.recording.checkpoints import load_checkpoint
from matb_integration.suas.recording.records import RecordKind, SessionRecord
from matb_integration.suas.recording.replay import ReplayResult, effective_records
from matb_integration.suas.scenarios.loader import load_scenario


# This is intentionally stricter than the UI router's defensive redactor:
# private probe answers must not be copied into a public artifact at all.
_PRIVATE_KEYS = frozenset({
    "answer", "correct_answer", "truth", "truth_priority", "required_report",
    "private_probe", "lease", "lease_hash", "controller_lease", "artifact_root",
    "run_dir", "absolute_path", "future_schedule", "evaluator", "provenance",
})


def _public(value: Any, *, key: str | None = None) -> Any:
    if key is not None and key.lower() in _PRIVATE_KEYS:
        return None
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for child_key, child_value in value.items():
            if str(child_key).lower() in _PRIVATE_KEYS:
                continue
            projected = _public(child_value, key=str(child_key))
            if projected is not None or child_value is None:
                output[str(child_key)] = projected
        return output
    if isinstance(value, (tuple, list)):
        return [_public(item) for item in value]
    return canonical_data(value)


def _read_records(path: Path) -> tuple[SessionRecord, ...]:
    rows: list[SessionRecord] = []
    for line in path.read_bytes().splitlines():
        if not line:
            continue
        rows.append(SessionRecord(**json.loads(line.decode("utf-8"))))
    return tuple(rows)


def _resequence(records: Sequence[SessionRecord]) -> tuple[SessionRecord, ...]:
    return tuple(replace(record, sequence=index) for index, record in enumerate(records, start=1))


def block_metric_summary(records: Sequence[SessionRecord], manifest: Mapping[str, object]) -> dict[str, object]:
    grouped: dict[str, list[SessionRecord]] = defaultdict(list)
    for record in records:
        grouped[record.block_id].append(record)
    block_rows = [derive_block_metrics(_resequence(rows), manifest).to_dict() for _, rows in sorted(grouped.items())]
    components = {name: [] for name in ("coverage", "contacts", "assets", "timeliness")}
    for row in block_rows:
        for name in components:
            component = row.get(name)
            if isinstance(component, Mapping) and isinstance(component.get("component"), (int, float)):
                components[name].append(float(component["component"]))
    reduced: dict[str, object] = {
        name: round(sum(values) / len(values), 2) if values else None
        for name, values in components.items()
    }
    reduced["mission_score"] = (
        round(sum(float(row["mission_score"]) for row in block_rows) / len(block_rows), 2)
        if block_rows else None
    )
    reduced["composite_label"] = "descriptive_feedback_only"
    reduced["blocks"] = block_rows
    return reduced


def swarm_metric_summary(frames: Sequence[Mapping[str, object]]) -> dict[str, object] | None:
    """Descriptive observations from reconstructed replay frames, never event payloads."""
    grouped = defaultdict(list)
    for frame in frames:
        snapshot = frame.get("snapshot", frame)
        if isinstance(snapshot, Mapping) and snapshot.get("swarms"):
            grouped[frame.get("block_id", snapshot.get("block_id"))].append(snapshot)
    blocks = []
    for block_id, samples in sorted(grouped.items()):
        samples.sort(key=lambda frame: (frame["simulation_time_ms"], frame["state_version"]))
        groups = {}
        for gid, group in samples[-1]["swarms"].items():
            errors = [frame["swarms"][gid].get("formation_error_mm") for frame in samples if gid in frame["swarms"]]
            errors = [value for value in errors if isinstance(value, int)]
            faults = [frame for frame in samples if frame["swarms"].get(gid, {}).get("fault_at_ms") is not None]
            recovery = None
            if faults:
                first = faults[0]
                def count_cells(frame):
                    return sum(len(v.get("covered_cells", [])) for v in frame.get("coverage", {}).get("sectors", {}).values())
                baseline = count_cells(first)
                recovered = next((frame for frame in samples if frame["simulation_time_ms"] > first["simulation_time_ms"] and count_cells(frame) > baseline), None)
                if recovered:
                    recovery = recovered["simulation_time_ms"] - first["simulation_time_ms"]
            groups[gid] = {"group_command_count": group["command_count"],
                           "last_fault_response_ms": group["last_response_ms"],
                           "sampled_mean_formation_error_mm": sum(errors) // len(errors) if errors else None,
                           "first_new_coverage_after_observed_fault_ms": recovery}
        blocks.append({"block_id": block_id, "groups": groups})
    return {"version": "swarm-descriptive-v1", "sampling": "reconstructed public frames", "blocks": blocks} if blocks else None


def _timeline(records: Iterable[SessionRecord]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for record in records:
        payload = record.payload
        include = False
        projected: dict[str, object] = {}
        if record.kind is RecordKind.DOMAIN_EVENT and isinstance(payload.get("event"), Mapping):
            event = payload["event"]
            projected = {
                "event_id": event.get("event_id"),
                "kind": event.get("kind"),
                "entity_ids": event.get("entity_ids", []),
                "payload": _public(event.get("payload", {})),
            }
            include = True
        elif record.kind is RecordKind.PROBE:
            projected = {key: _public(value, key=key) for key, value in payload.items()}
            include = True
        elif record.kind is RecordKind.QUESTIONNAIRE and payload.get("event") != "probe_started":
            # Keep only scored, non-sensitive fields.  The raw answer remains
            # in questionnaires.json, which is a private server artifact.
            allowed = {
                "instrument", "scale_id", "probe_id", "sa_level", "correct",
                "timed_out", "latency_ms", "unscorable_reason", "raw_tlx", "value",
            }
            projected = {key: _public(payload[key], key=key) for key in sorted(set(payload) & allowed)}
            include = True
        elif record.kind is RecordKind.PROTOCOL_DEVIATION:
            projected = _public(payload)
            include = True
        elif record.kind is RecordKind.LIFECYCLE and payload.get("event") in {
            "checkpoint_recovery", "recording_failure", "runtime_failure", "controller_disconnected",
            "session_paused", "session_resumed",
        }:
            projected = _public(payload)
            include = True
        if include:
            output.append({
                "sequence": record.sequence,
                "block_id": record.block_id,
                "simulation_time_ms": record.simulation_time_ms,
                "state_version": record.state_version,
                **projected,
            })
    return output


def _checkpoint_frames(run_dir: Path) -> list[dict[str, object]]:
    scenario = load_scenario(run_dir / "scenario.yaml")
    frames: list[dict[str, object]] = []
    checkpoints = run_dir / "checkpoints"
    for path in sorted(checkpoints.glob("checkpoint-*.json.gz")):
        wrapper = load_checkpoint(path)
        engine_data = wrapper["engine"]
        if not isinstance(engine_data, Mapping):
            continue
        block_id = engine_data.get("block_id")
        if not isinstance(block_id, str):
            continue
        engine = SimulationEngine(scenario.definition, block_id)
        engine.restore(engine_data)
        snapshot = _public(engine.snapshot())
        frames.append({
            "block_id": block_id,
            "checkpoint_version": wrapper["checkpoint_version"],
            "record_sequence": wrapper["record_sequence"],
            "simulation_time_ms": snapshot.get("simulation_time_ms", 0),
            "state_version": snapshot.get("state_version", 0),
            "state_sha256": snapshot.get("state_sha256"),
            "snapshot": snapshot,
        })
    return frames


def private_questionnaire_artifact(records: Iterable[SessionRecord]) -> dict[str, object]:
    """Build the private questionnaire artifact without altering source records."""

    return {
        "schema_version": 2,
        "calculation_version": "suas-debrief-v2",
        "visibility": "server_private",
        "records": [
            {
                "sequence": record.sequence,
                "block_id": record.block_id,
                "simulation_time_ms": record.simulation_time_ms,
                "payload": canonical_data(record.payload),
            }
            for record in records
            if record.kind is RecordKind.QUESTIONNAIRE
        ],
    }


def build_public_debrief(
    run_dir: Path,
    manifest: Mapping[str, object],
    replay: ReplayResult,
    records: Sequence[SessionRecord],
    *,
    validity: str = "valid",
    live_frames: Sequence[Mapping[str, object]] = (),
) -> tuple[dict[str, object], dict[str, object]]:
    """Return ``(public_debrief, private_questionnaires)`` for a sealed run."""

    effective = tuple(effective_records(records))
    metric_summary = block_metric_summary(effective, manifest)
    research = derive_research_metrics(effective).to_dict()
    metrics = {**metric_summary, **research}
    from matb_integration.suas.recording.replay import ReplayVerifier
    frames = ReplayVerifier().public_frames(Path(run_dir)) or _checkpoint_frames(Path(run_dir))
    for raw in live_frames:
        if not isinstance(raw, Mapping):
            continue
        snapshot = _public(raw)
        if not isinstance(snapshot, Mapping):
            continue
        frames.append({
            "block_id": snapshot.get("block_id"),
            "checkpoint_version": None,
            "record_sequence": None,
            "simulation_time_ms": snapshot.get("simulation_time_ms", 0),
            "state_version": snapshot.get("state_version", 0),
            "state_sha256": snapshot.get("state_sha256"),
            "snapshot": snapshot,
        })
    seen: set[tuple[object, object, object]] = set()
    unique_frames: list[dict[str, object]] = []
    order = ([manifest["selected_block_id"]] if manifest.get("selected_block_id") else ["PRACTICE", *manifest.get("block_order", [])])
    for frame in sorted(frames, key=lambda item: (order.index(item.get("block_id")) if item.get("block_id") in order else len(order), int(item.get("simulation_time_ms") or 0), int(item.get("state_version") or 0))):
        key = (frame.get("block_id"), frame.get("simulation_time_ms"), frame.get("state_version"))
        if key in seen:
            continue
        seen.add(key)
        unique_frames.append(frame)
    swarm = swarm_metric_summary(unique_frames)
    if swarm is not None:
        metrics["swarm"] = swarm
    replay_public = _public(replay)
    public = {
        "calculation_version": "suas-debrief-v2",
        "status": "sealed" if str(replay.status) == "match" else "partial_unverified",
        "validity": validity,
        "session_mode": manifest.get("session_mode", "research"),
        "record_class": manifest.get("record_class", "research"),
        "selected_block_id": manifest.get("selected_block_id"),
        "session_id": manifest.get("session_id"),
        "scenario_id": manifest.get("scenario_id"),
        "scenario_sha256": manifest.get("scenario_sha256"),
        "engine_version": manifest.get("engine_version"),
        "replay_status": str(replay.status),
        "deterministic_replay_verified": str(replay.status) == "match",
        "replay": replay_public,
        "metrics": metrics,
        "frames": unique_frames,
        "presentation": manifest.get("presentation"),
        **({"console_profile": manifest["console_profile"]} if "console_profile" in manifest else {}),
        "traffic_frames": [json.loads(line) for line in (Path(run_dir) / "traffic.jsonl").read_text().splitlines()] if (Path(run_dir) / "traffic.jsonl").exists() else [],
        "presentation_events": [json.loads(line) for line in (Path(run_dir) / "presentation.jsonl").read_text().splitlines()] if (Path(run_dir) / "presentation.jsonl").exists() else [],
        "timeline": _timeline(effective),
        "privacy": {
            "correct_answers_excluded": True,
            "operational_truth_excluded": True,
            "raw_questionnaire_answers_excluded": True,
        },
    }
    return public, private_questionnaire_artifact(effective)


__all__ = ["build_public_debrief", "private_questionnaire_artifact"]
