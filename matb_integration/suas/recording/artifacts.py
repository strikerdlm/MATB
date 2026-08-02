"""Atomic research-artifact writes and deterministic checksum inventories."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from matb_integration.suas.domain.serialization import canonical_json

from .records import ArtifactInfo

CHECKSUM_FILENAME = "checksums.sha256"
_FROZEN_NAMES = ("scenario.yaml", "manifest.json", "events.jsonl")
_SEALED_NAMES = ("questionnaires.json", "metrics.json", "debrief.json", "replay-verification.json")


def write_json_artifact(path: Path, payload: Any) -> Path:
    """Write one canonical JSON document through a same-directory temporary file."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json(payload).encode("utf-8")
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        # A failed artifact write must not leave an apparently durable temp
        # file that can be mistaken for a closed artifact on reopen.
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    return destination


def checksum_paths(run_dir: Path) -> tuple[Path, ...]:
    """Return the immutable, checksum-covered files in relative-path order."""

    root = Path(run_dir)
    paths: list[Path] = []
    for name in (*_FROZEN_NAMES, *_SEALED_NAMES, "partial-run.json"):
        path = root / name
        if path.is_file():
            paths.append(path)
    checkpoint_dir = root / "checkpoints"
    if checkpoint_dir.is_dir():
        paths.extend(
            path for path in sorted(checkpoint_dir.iterdir(), key=lambda item: item.name)
            if path.is_file() and path.suffix == ".gz" and not path.name.endswith(".tmp")
        )
    return tuple(sorted(paths, key=lambda path: path.relative_to(root).as_posix()))


def build_checksum_file(run_dir: Path) -> Path:
    """Write ``checksums.sha256`` for all extant immutable run artifacts."""

    root = Path(run_dir)
    entries = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}"
        for path in checksum_paths(root)
    ]
    payload = ("\n".join(entries) + "\n").encode("utf-8") if entries else b""
    destination = root / CHECKSUM_FILENAME
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    return destination


def verify_checksum_file(path: Path) -> tuple[str, ...]:
    """Verify a checksum inventory and return stable diagnostic codes.

    An empty tuple is the only success value.  Codes contain the affected
    relative path where that makes a repair or audit unambiguous.
    """

    checksum_path = Path(path)
    if checksum_path.is_dir():
        checksum_path = checksum_path / CHECKSUM_FILENAME
    if not checksum_path.is_file():
        return ("checksum_missing",)
    root = checksum_path.parent
    try:
        raw = checksum_path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return ("checksum_unreadable",)
    if raw and not raw.endswith(b"\n"):
        return ("checksum_incomplete",)

    expected: dict[str, str] = {}
    codes: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line:
            codes.append(f"checksum_invalid_line:{line_number}")
            continue
        if len(line) < 66 or line[64:66] != "  ":
            codes.append(f"checksum_invalid_line:{line_number}")
            continue
        digest, relative = line[:64], line[66:]
        if (
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            codes.append(f"checksum_invalid_line:{line_number}")
            continue
        if relative in expected:
            codes.append(f"checksum_duplicate:{relative}")
            continue
        expected[relative] = digest

    listed_order = tuple(expected)
    if listed_order != tuple(sorted(listed_order)):
        codes.append("checksum_order")

    actual = {path.relative_to(root).as_posix(): path for path in checksum_paths(root)}
    for relative in sorted(expected):
        path = actual.get(relative)
        if path is None:
            codes.append(f"checksum_missing:{relative}")
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            codes.append(f"checksum_unreadable:{relative}")
            continue
        if digest != expected[relative]:
            codes.append(f"checksum_mismatch:{relative}")
    for relative in sorted(set(actual) - set(expected)):
        codes.append(f"checksum_unlisted:{relative}")
    return tuple(codes)


def artifact_inventory(run_dir: Path, *, partial: bool = False) -> tuple[ArtifactInfo, ...]:
    """Build a stable artifact inventory, including the checksum file itself."""

    root = Path(run_dir)
    kinds = {
        "scenario.yaml": "scenario",
        "manifest.json": "manifest",
        "events.jsonl": "events",
        "questionnaires.json": "questionnaires",
        "metrics.json": "metrics",
        "debrief.json": "debrief",
        "replay-verification.json": "replay_verification",
        "partial-run.json": "partial_unverified" if partial else "partial",
        CHECKSUM_FILENAME: "checksums",
    }
    paths = list(checksum_paths(root))
    checksum_path = root / CHECKSUM_FILENAME
    if checksum_path.is_file():
        paths.append(checksum_path)
    paths = sorted(set(paths), key=lambda path: path.relative_to(root).as_posix())
    inventory: list[ArtifactInfo] = []
    for path in paths:
        relative = path.relative_to(root)
        kind = "checkpoint" if relative.parts and relative.parts[0] == "checkpoints" else kinds.get(relative.as_posix(), "artifact")
        data = path.read_bytes()
        inventory.append(ArtifactInfo(
            kind=kind,
            path=path,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
        ))
    return tuple(inventory)


__all__ = [
    "CHECKSUM_FILENAME",
    "artifact_inventory",
    "build_checksum_file",
    "checksum_paths",
    "verify_checksum_file",
    "write_json_artifact",
]
