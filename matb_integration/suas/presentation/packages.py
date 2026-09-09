"""Validate immutable, public-only offline scene packages before use."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


def package_root() -> Path:
    return (
        Path(__file__).resolve().parents[3] / "webui" / "frontend" / "public" / "scenes"
    )


def _read_package(package_id: str, expected_hash: str | None = None) -> dict:
    if not package_id or any(
        c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in package_id
    ):
        raise ValueError("invalid scene package id")
    root = package_root() / package_id
    raw = (root / "manifest.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_hash is not None and expected_hash != digest:
        raise ValueError("scene manifest checksum mismatch")
    manifest = json.loads(raw)
    if manifest.get("version") not in (1, 2) or manifest.get("id") != package_id:
        raise ValueError("unsupported scene manifest")
    if manifest.get("altitude_reference") != "terrain_relative_illustrative":
        raise ValueError("unsupported aircraft altitude reference")
    required = {"elevation.json", "imagery.png"} | (
        {"overlays.json"} if manifest["version"] == 2 else set()
    )
    if set(manifest.get("files", {})) != required:
        raise ValueError("invalid scene file inventory")
    origin = manifest.get("origin", {})
    if not all(
        isinstance(origin.get(k), (int, float)) and math.isfinite(origin[k])
        for k in ("lat", "lon", "mission_x_m", "mission_y_m")
    ):
        raise ValueError("invalid scene origin")
    if not (-90 <= origin["lat"] <= 90 and -180 <= origin["lon"] <= 180):
        raise ValueError("invalid scene coordinate")
    for name in required:
        if (
            hashlib.sha256((root / name).read_bytes()).hexdigest()
            != manifest["files"][name]
        ):
            raise ValueError(f"scene checksum mismatch: {name}")
    elevation = json.loads((root / "elevation.json").read_bytes())
    width, height = elevation["width"], elevation["height"]
    if (
        not (2 <= width <= 2048 and 2 <= height <= 2048)
        or len(elevation["values"]) != width * height
    ):
        raise ValueError("invalid elevation dimensions")
    if not all(
        isinstance(v, (int, float)) and math.isfinite(v) for v in elevation["values"]
    ):
        raise ValueError("elevation contains gaps")
    if elevation["bounds_m"] != [-2000, -2000, 14000, 10000]:
        raise ValueError("scene does not cover the reference area and margin")
    return {**manifest, "sha256": digest}


def read_package(package_id: str, expected_hash: str | None = None) -> dict:
    try:
        return _read_package(package_id, expected_hash)
    except (OSError, KeyError, TypeError) as error:
        raise ValueError("scene package unavailable or malformed") from error


def catalog() -> list[dict]:
    result = []
    for path in sorted(package_root().glob("*/manifest.json")):
        try:
            result.append(read_package(path.parent.name))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return result
