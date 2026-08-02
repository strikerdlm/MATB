"""Checkpoint loading and validation helpers."""

from __future__ import annotations

import gzip
import json
from collections.abc import Mapping
from pathlib import Path

from matb_integration.suas.domain.serialization import canonical_data

from .records import RecordingError


def load_checkpoint(path: Path) -> dict[str, object]:
    """Load one closed checkpoint wrapper without attempting recovery or repair."""

    try:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            loaded = json.load(stream)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecordingError(f"checkpoint load failed: {exc}") from exc
    if not isinstance(loaded, dict) or set(loaded) != {"checkpoint_version", "record_sequence", "engine"}:
        raise RecordingError("checkpoint has an invalid wrapper")
    if (isinstance(loaded["checkpoint_version"], bool) or not isinstance(loaded["checkpoint_version"], int)
            or loaded["checkpoint_version"] <= 0):
        raise RecordingError("checkpoint has an invalid version")
    if (isinstance(loaded["record_sequence"], bool) or not isinstance(loaded["record_sequence"], int)
            or loaded["record_sequence"] < 0):
        raise RecordingError("checkpoint has an invalid record sequence")
    if not isinstance(loaded["engine"], Mapping):
        raise RecordingError("checkpoint has no engine snapshot")
    try:
        canonical_data(loaded)
    except (TypeError, ValueError) as exc:
        raise RecordingError(f"checkpoint is not canonical JSON-safe: {exc}") from exc
    return loaded
