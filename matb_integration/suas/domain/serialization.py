"""Canonical, JSON-safe conversion and hashing for deterministic state."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import StrEnum
import hashlib
import json
import math
from collections.abc import Mapping, Set
from typing import Any

from .geometry import PointMM


def canonical_data(value: Any) -> Any:
    """Convert supported domain values into deterministic JSON-compatible data."""

    if isinstance(value, PointMM):
        return {"x_mm": value.x_mm, "y_mm": value.y_mm}
    if isinstance(value, StrEnum):
        return value.value
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON does not support non-finite floats")
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: canonical_data(getattr(value, field.name)) for field in fields(value)
                if not (field.metadata.get("omit_none") and getattr(value, field.name) is None)}
    if isinstance(value, Mapping):
        converted: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical mappings require string keys")
            converted[key] = canonical_data(item)
        return converted
    if isinstance(value, (tuple, list)):
        return [canonical_data(item) for item in value]
    if isinstance(value, Set) and not isinstance(value, (str, bytes, bytearray)):
        converted = [canonical_data(item) for item in value]
        return sorted(converted, key=_canonical_json_data)
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize a supported object using compact, sorted, UTF-8-safe JSON."""

    return _canonical_json_data(canonical_data(value))


def canonical_sha256(value: Any) -> str:
    """Return the SHA-256 digest for the canonical UTF-8 JSON bytes."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json_data(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )
