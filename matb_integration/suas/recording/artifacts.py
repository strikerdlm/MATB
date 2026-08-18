"""sUAS compatibility wrappers for shared recording artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from matb_integration.recording.artifacts import (
    ArtifactProfile,
    artifact_inventory as generic_artifact_inventory,
    build_checksum_file as generic_build_checksum_file,
    checksum_paths as generic_checksum_paths,
    verify_checksum_file as generic_verify_checksum_file,
    write_json_artifact as generic_write_json_artifact,
)
from matb_integration.recording.records import ArtifactInfo
from matb_integration.suas.domain.serialization import canonical_json

SUAS_PROFILE = ArtifactProfile(
    frozen_names=("scenario.yaml", "manifest.json", "events.jsonl"),
    sealed_names=(
        "questionnaires.json",
        "metrics.json",
        "debrief.json",
        "replay-verification.json",
    ),
    additional_globs=("checkpoints/*.json.gz",),
)
CHECKSUM_FILENAME = SUAS_PROFILE.checksum_name
_SUAS_KINDS = {
    "scenario.yaml": "scenario",
    "manifest.json": "manifest",
    "events.jsonl": "events",
    "questionnaires.json": "questionnaires",
    "metrics.json": "metrics",
    "debrief.json": "debrief",
    "replay-verification.json": "replay_verification",
}


def write_json_artifact(path: Path, payload: Any) -> Path:
    return generic_write_json_artifact(path, payload, serializer=canonical_json)


def checksum_paths(run_dir: Path) -> tuple[Path, ...]:
    return generic_checksum_paths(run_dir, profile=SUAS_PROFILE)


def build_checksum_file(run_dir: Path) -> Path:
    return generic_build_checksum_file(run_dir, profile=SUAS_PROFILE)


def verify_checksum_file(path: Path) -> tuple[str, ...]:
    return generic_verify_checksum_file(path, profile=SUAS_PROFILE)


def artifact_inventory(run_dir: Path, *, partial: bool = False) -> tuple[ArtifactInfo, ...]:
    root = Path(run_dir)
    kinds = dict(_SUAS_KINDS)
    for checkpoint in root.glob("checkpoints/*.json.gz"):
        kinds[checkpoint.relative_to(root).as_posix()] = "checkpoint"
    return generic_artifact_inventory(
        root,
        profile=SUAS_PROFILE,
        partial=partial,
        kind_by_name=kinds,
    )


__all__ = [
    "CHECKSUM_FILENAME",
    "SUAS_PROFILE",
    "artifact_inventory",
    "build_checksum_file",
    "checksum_paths",
    "verify_checksum_file",
    "write_json_artifact",
]
