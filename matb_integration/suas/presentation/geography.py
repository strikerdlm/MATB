"""Local projections and versioned geography shared by traffic and preparation."""

from __future__ import annotations
import hashlib
import json
import math
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PUBLIC = ROOT / "webui/frontend/public/geography"


def regions():
    return json.loads((PUBLIC / "regions.json").read_text(encoding="utf-8"))


def data_root():
    return Path(os.environ.get("MATB_GEOGRAPHY_DIR", ROOT / "outputs/geography"))


@lru_cache(maxsize=64)
def transformer(lat: float, lon: float):
    from pyproj import CRS, Transformer

    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m"
    )
    return Transformer.from_crs("EPSG:4326", local, always_xy=True)


def local_position(lat, lon, origin):
    x, y = transformer(origin["lat"], origin["lon"]).transform(lon, lat)
    return {
        "x_mm": round((x + origin["mission_x_m"]) * 1000),
        "y_mm": round((y + origin["mission_y_m"]) * 1000),
    }


@lru_cache(maxsize=1)
def geoid_grid():
    raw = (PUBLIC / "geoid.json").read_bytes()
    manifest = json.loads((PUBLIC / "catalog.json").read_text(encoding="utf-8"))
    if hashlib.sha256(raw).hexdigest() != manifest["files"]["geoid.json"]:
        raise ValueError("geoid checksum mismatch")
    return json.loads(raw)


def geoid_height(lat, lon):
    grid = geoid_grid()
    west, south, east, north = grid["bounds"]
    if not (west <= lon <= east and south <= lat <= north):
        return None
    x = (lon - west) / (east - west) * (grid["width"] - 1)
    y = (lat - south) / (north - south) * (grid["height"] - 1)
    col = min(int(x), grid["width"] - 2)
    row = min(int(y), grid["height"] - 2)
    u = x - col
    v = y - row
    i = row * grid["width"] + col
    a = grid["values"]
    return (1 - v) * ((1 - u) * a[i] + u * a[i + 1]) + v * (
        (1 - u) * a[i + grid["width"]] + u * a[i + grid["width"] + 1]
    )


def projected_track(track, origin):
    result = dict(track, position=local_position(track["lat"], track["lon"], origin))
    height = track.get("geometric_altitude_m")
    if height is not None:
        try:
            separation = geoid_height(track["lat"], track["lon"])
        except (OSError, ValueError, KeyError):
            separation = None
        result["orthometric_altitude_m"] = (
            None if separation is None else height - separation
        )
    else:
        result["orthometric_altitude_m"] = None
    return result
