"""Domain-neutral research artifact metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ArtifactInfo:
    kind: str
    path: Path
    sha256: str
    size_bytes: int
