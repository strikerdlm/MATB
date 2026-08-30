"""Deidentified reference-session and BIDS-compatible event exports."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from matb_integration.recording.artifacts import write_json_artifact

REFERENCE_SESSION_SCHEMA_VERSION = "1.0"
PSEUDONYM = re.compile(r"^[A-Za-z0-9_-]+$")
FORBIDDEN_METADATA_KEYS = {
    "name",
    "full_name",
    "email",
    "phone",
    "address",
    "date_of_birth",
    "birth_date",
    "numero_identificacion",
    "identification_number",
    "military_id",
    "rank",
    "unit",
    "roster",
}


def _forbidden_paths(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if str(key).lower() in FORBIDDEN_METADATA_KEYS:
                found.append(path)
            found.extend(_forbidden_paths(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_forbidden_paths(item, f"{prefix}[{index}]"))
    return found


def artifact_rows(paths: Iterable[Path], *, root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = Path(root).resolve()
    for path in sorted((Path(item).resolve() for item in paths), key=str):
        if root != path and root not in path.parents:
            raise ValueError(f"artifact is outside session root: {path}")
        data = path.read_bytes()
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
        )
    return rows


def build_reference_session(
    metadata: Mapping[str, Any],
    *,
    artifact_paths: Iterable[Path],
    session_root: Path,
) -> dict[str, Any]:
    forbidden = _forbidden_paths(metadata)
    if forbidden:
        raise ValueError("direct or operational identifiers are forbidden: " + ", ".join(forbidden))
    pseudonym = str(metadata.get("participant_pseudonym") or "")
    if not PSEUDONYM.fullmatch(pseudonym):
        raise ValueError("participant_pseudonym must use only letters, digits, underscore or hyphen")
    required_mappings = ("locale", "scenario", "runtime", "metrics", "timing")
    for key in required_mappings:
        if not isinstance(metadata.get(key), Mapping):
            raise ValueError(f"reference session requires {key}")
    payload = dict(metadata)
    payload["schema_version"] = REFERENCE_SESSION_SCHEMA_VERSION
    payload.setdefault("questionnaires", [])
    payload.setdefault("exclusions", [])
    payload["artifacts"] = artifact_rows(artifact_paths, root=session_root)
    return payload


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"JSONL line {line_number} is not an object")
        records.append(payload)
    return records


def export_bids_events(
    events_jsonl: Path,
    events_tsv: Path,
    sidecar_json: Path,
    *,
    profile_id: str,
    scenario_sha256: str,
    source_commit: str,
    timing_qualification_status: str,
) -> tuple[Path, Path]:
    records = read_jsonl(events_jsonl)
    destination = Path(events_tsv)
    destination.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "onset",
        "duration",
        "trial_type",
        "event_id",
        "module",
        "address",
        "value",
        "scheduled_onset",
        "dispatch_lateness_ms",
        "clock_domain",
    ]
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for record in records:
            sequence = record.get("sequence")
            module = str(record.get("module") or "")
            address = str(record.get("address") or "")
            record_type = str(record.get("record_type") or "unknown")
            writer.writerow(
                {
                    "onset": record.get("scenario_time_s", "n/a"),
                    "duration": 0,
                    "trial_type": ".".join(part for part in (record_type, module, address) if part),
                    "event_id": f"event-{sequence}" if sequence is not None else "n/a",
                    "module": module or "n/a",
                    "address": address or "n/a",
                    "value": record.get("value", "n/a"),
                    "scheduled_onset": record.get("scheduled_scenario_time_s", "n/a"),
                    "dispatch_lateness_ms": record.get("dispatch_lateness_ms", "n/a"),
                    "clock_domain": record.get("clock_domain", "unknown"),
                }
            )
    sidecar = {
        "schema_version": "1.0",
        "profile_id": profile_id,
        "scenario_sha256": scenario_sha256,
        "source_commit": source_commit,
        "timing_qualification_status": timing_qualification_status,
        "onset": {
            "Description": "Scenario-clock onset, not physical onset unless the exact rig is qualified.",
            "Units": "seconds",
        },
        "scheduled_onset": {"Description": "Scheduled scenario time", "Units": "seconds"},
        "dispatch_lateness_ms": {"Description": "Software dispatch lateness", "Units": "milliseconds"},
        "SourceEventSchema": "OpenMATB event schema 1.0",
        "NativeAuthoritativeArtifact": Path(events_jsonl).name,
    }
    write_json_artifact(Path(sidecar_json), sidecar)
    return destination, Path(sidecar_json)
