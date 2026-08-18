"""Atomic writes and profile-scoped checksum inventories."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Set
from dataclasses import asdict, dataclass, is_dataclass
from enum import StrEnum
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from .records import ArtifactInfo


@dataclass(frozen=True, slots=True)
class ArtifactProfile:
    frozen_names: tuple[str, ...]
    sealed_names: tuple[str, ...]
    partial_name: str = "partial-run.json"
    checksum_name: str = "checksums.sha256"
    additional_globs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        names = (*self.frozen_names, *self.sealed_names, self.partial_name, self.checksum_name)
        if len(set(names)) != len(names):
            raise ValueError("artifact profile names must be unique")
        for name in names:
            path = Path(name)
            if not name or path.is_absolute() or ".." in path.parts:
                raise ValueError("artifact profile names must be safe relative paths")
        for pattern in self.additional_globs:
            path = Path(pattern)
            if not pattern or path.is_absolute() or ".." in path.parts:
                raise ValueError("artifact profile globs must be safe relative patterns")


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON does not support non-finite floats")
        return value
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        converted: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical mappings require string keys")
            converted[key] = _json_safe(item)
        return converted
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Set) and not isinstance(value, (str, bytes, bytearray)):
        converted = [_json_safe(item) for item in value]
        return sorted(converted, key=_canonical_json_data)
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _canonical_json_data(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def _canonical_json(value: Any) -> str:
    return _canonical_json_data(_json_safe(value))


def _write_atomic(path: Path, payload: bytes) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
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


def write_json_artifact(
    path: Path,
    payload: Any,
    *,
    serializer: Callable[[Any], str] = _canonical_json,
) -> Path:
    """Write one canonical JSON document through a same-directory temporary file."""

    return _write_atomic(Path(path), serializer(payload).encode("utf-8"))


def checksum_paths(run_dir: Path, *, profile: ArtifactProfile) -> tuple[Path, ...]:
    """Return extant immutable files declared by one artifact profile."""

    root = Path(run_dir)
    names = (*profile.frozen_names, *profile.sealed_names, profile.partial_name)
    paths = [root / name for name in names if (root / name).is_file()]
    for pattern in profile.additional_globs:
        paths.extend(
            path
            for path in root.glob(pattern)
            if path.is_file() and not path.name.endswith(".tmp")
        )
    return tuple(sorted(set(paths), key=lambda path: path.relative_to(root).as_posix()))


def build_checksum_file(run_dir: Path, *, profile: ArtifactProfile) -> Path:
    """Atomically write the profile's deterministic SHA-256 inventory."""

    root = Path(run_dir)
    entries = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}"
        for path in checksum_paths(root, profile=profile)
    ]
    payload = ("\n".join(entries) + "\n").encode("utf-8") if entries else b""
    return _write_atomic(root / profile.checksum_name, payload)


def verify_checksum_file(path: Path, *, profile: ArtifactProfile) -> tuple[str, ...]:
    """Verify one profile-scoped checksum inventory and return stable codes."""

    checksum_path = Path(path)
    if checksum_path.is_dir():
        checksum_path = checksum_path / profile.checksum_name
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
        if not line or len(line) < 66 or line[64:66] != "  ":
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

    actual = {
        item.relative_to(root).as_posix(): item
        for item in checksum_paths(root, profile=profile)
    }
    for relative in sorted(expected):
        artifact_path = actual.get(relative)
        if artifact_path is None:
            codes.append(f"checksum_missing:{relative}")
            continue
        try:
            digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        except OSError:
            codes.append(f"checksum_unreadable:{relative}")
            continue
        if digest != expected[relative]:
            codes.append(f"checksum_mismatch:{relative}")
    for relative in sorted(set(actual) - set(expected)):
        codes.append(f"checksum_unlisted:{relative}")
    return tuple(codes)


def artifact_inventory(
    run_dir: Path,
    *,
    profile: ArtifactProfile,
    partial: bool = False,
    kind_by_name: Mapping[str, str] | None = None,
) -> tuple[ArtifactInfo, ...]:
    """Build a stable inventory including the checksum file itself."""

    root = Path(run_dir)
    paths = list(checksum_paths(root, profile=profile))
    checksum_path = root / profile.checksum_name
    if checksum_path.is_file():
        paths.append(checksum_path)
    inventory: list[ArtifactInfo] = []
    kinds = kind_by_name or {}
    for artifact_path in sorted(
        set(paths),
        key=lambda item: item.relative_to(root).as_posix(),
    ):
        relative = artifact_path.relative_to(root).as_posix()
        if relative == profile.partial_name:
            kind = "partial_unverified" if partial else "partial"
        elif relative == profile.checksum_name:
            kind = "checksums"
        else:
            kind = kinds.get(relative, "artifact")
        data = artifact_path.read_bytes()
        inventory.append(
            ArtifactInfo(
                kind=kind,
                path=artifact_path,
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=len(data),
            )
        )
    return tuple(inventory)


__all__ = [
    "ArtifactProfile",
    "artifact_inventory",
    "build_checksum_file",
    "checksum_paths",
    "verify_checksum_file",
    "write_json_artifact",
]
