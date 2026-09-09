"""Build a bounded Colombia scene from open elevation and Sentinel-2 COGs.

Run with Python containing numpy, rasterio, pyproj, Pillow and requests.
Network acquisition is confined to preparation; the browser serves local files.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import uuid
import shutil
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import requests
import rasterio
from PIL import Image
from pyproj import CRS, Transformer
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling

ROOT = Path(__file__).resolve().parents[1]
ID = "villavicencio-v1"
LOCAL = CRS.from_proj4("+proj=aeqd +lat_0=4.15 +lon_0=-73.65 +datum=WGS84 +units=m")
BOUNDS = (-8000, -6000, 8000, 6000)


def dump(path: Path, data: object) -> None:
    path.write_text(
        json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )


def masked_rgb(channels):
    """Retain sparse source nodata as alpha, never fabricate missing reflectance."""
    stack = np.stack(channels, axis=-1)
    valid = np.isfinite(stack).all(axis=-1)
    if 1 - float(valid.mean()) > 0.0001:
        return None
    pixels = np.uint8(
        np.clip(np.nan_to_num(stack, nan=0) / 0.3, 0, 1) ** (1 / 2.2) * 255
    )
    alpha = np.uint8(valid) * 255
    return np.dstack((pixels, alpha)), float(valid.mean() * 100)


def build(
    output: Path,
    end_date: str,
    product_id: str | None,
    lat: float = 4.15,
    lon: float = -73.65,
    title: str = "Villavicencio",
    region: str = "Meta",
) -> None:
    LOCAL = CRS.from_proj4(
        f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m"
    )
    origin_lat, origin_lon = lat, lon
    print(f"Preparing {title}: searching acquisitions", flush=True)
    to_geo = Transformer.from_crs(LOCAL, "EPSG:4326", always_xy=True)
    west, south = to_geo.transform(BOUNDS[0], BOUNDS[1])
    east, north = to_geo.transform(BOUNDS[2], BOUNDS[3])
    start = (date.fromisoformat(end_date) - timedelta(days=365)).isoformat()
    query = {
        "collections": ["sentinel-2-l2a"],
        "bbox": [west, south, east, north],
        "datetime": f"{start}T00:00:00Z/{end_date}T23:59:59Z",
        "limit": 100,
        "sortby": [
            {"field": "properties.eo:cloud_cover", "direction": "asc"},
            {"field": "properties.datetime", "direction": "desc"},
        ],
    }
    if product_id:
        query["ids"] = [product_id]
    response = requests.post(
        "https://earth-search.aws.element84.com/v1/search", json=query, timeout=120
    )
    response.raise_for_status()
    page = response.json()
    candidates = page["features"]
    while next_link := next(
        (link for link in page.get("links", []) if link["rel"] == "next"), None
    ):
        response = requests.request(
            next_link.get("method", "GET"),
            next_link["href"],
            json=next_link.get("body"),
            timeout=120,
        )
        response.raise_for_status()
        page = response.json()
        candidates.extend(page["features"])

    if not candidates:
        raise RuntimeError("no Sentinel-2 scenes cover the pilot")
    # Coverage is verified by reprojection below; no unobserved pixels are filled.
    candidates.sort(key=lambda f: f["properties"]["datetime"], reverse=True)
    scored = []
    for candidate in candidates:
        print("Cloud sampling " + candidate["id"], flush=True)
        mask = np.zeros((120, 160), dtype="uint8")
        with rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
        ):
            with rasterio.open(candidate["assets"]["scl"]["href"]) as src:
                reproject(
                    rasterio.band(src, 1),
                    mask,
                    dst_transform=from_bounds(*BOUNDS, 160, 120),
                    dst_crs=LOCAL,
                    src_nodata=0,
                    dst_nodata=0,
                    resampling=Resampling.nearest,
                )
        if (mask == 0).any():
            continue
        score = float(np.isin(mask[20:100, 20:140], [8, 9, 10]).mean() * 100)
        candidate["matb_footprint_cloud_percent"] = score
        scored.append(candidate)
        if score == 0:  # Newest-first traversal makes this the optimal tie break.
            break
    candidates = sorted(scored, key=lambda f: f["matb_footprint_cloud_percent"])

    selected = None
    rgb = None
    transform = from_bounds(*BOUNDS, 1600, 1200)
    for candidate in candidates:
        channels = []
        try:
            for band in ("red", "green", "blue"):
                asset = candidate["assets"][band]["href"]
                with rasterio.Env(
                    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                ):
                    with rasterio.open(asset) as src:
                        data = np.full((1200, 1600), np.nan, dtype="float32")
                        reproject(
                            rasterio.band(src, 1),
                            data,
                            dst_transform=transform,
                            dst_crs=LOCAL,
                            src_nodata=0,
                            dst_nodata=np.nan,
                            resampling=Resampling.bilinear,
                        )
                radiometry = candidate["assets"][band]["raster:bands"][0]
                offset = (
                    0
                    if candidate["properties"].get(
                        "earthsearch:boa_offset_applied", False
                    )
                    else radiometry.get("offset", 0)
                )
                channels.append(data * radiometry.get("scale", 1) + offset)
            rendered = masked_rgb(channels)
            if rendered is not None:
                selected = candidate
                rgb, valid_percent = rendered
                break
        except rasterio.errors.RasterioError:
            if product_id:
                raise
    if selected is None or rgb is None:
        raise RuntimeError(
            "no acquisition completely covers the pilot; package not written"
        )

    print("Downloading terrain and overlays", flush=True)
    # Terrarium decoding yields EGM96 orthometric metres. Sample a fixed 100 m grid.
    cols, rows = 161, 121
    xs, ys = np.meshgrid(np.linspace(-8000, 8000, cols), np.linspace(-6000, 6000, rows))
    lon, lat = to_geo.transform(xs, ys)
    zoom = 12
    px = (lon + 180) / 360 * (2**zoom) * 256
    py = (1 - np.arcsinh(np.tan(np.radians(lat))) / math.pi) / 2 * (2**zoom) * 256
    values = np.empty((rows, cols))
    sources = []
    for tx, ty in sorted(
        set(zip((px // 256).astype(int).flat, (py // 256).astype(int).flat))
    ):
        url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom}/{tx}/{ty}.png"
        tile_response = requests.get(url, timeout=60)
        tile_response.raise_for_status()
        tile = np.asarray(
            Image.open(io.BytesIO(tile_response.content)).convert("RGB"), dtype=float
        )
        mask = ((px // 256) == tx) & ((py // 256) == ty)
        samples = tile[(py[mask] % 256).astype(int), (px[mask] % 256).astype(int)]
        values[mask] = samples[:, 0] * 256 + samples[:, 1] + samples[:, 2] / 256 - 32768
        sources.append(
            {"url": url, "sha256": hashlib.sha256(tile_response.content).hexdigest()}
        )
    if not np.isfinite(values).all():
        raise RuntimeError("terrain has gaps")
    if output.exists():
        raise RuntimeError(
            "refusing to replace a versioned scene; use a new output directory"
        )
    output.mkdir(parents=True)
    Image.fromarray(rgb).save(output / "imagery.png")
    dump(
        output / "elevation.json",
        {
            "width": cols,
            "height": rows,
            "bounds_m": [-2000, -2000, 14000, 10000],
            "values": np.round(values, 2).flatten().tolist(),
        },
    )
    overlays, overlay_sources = geographic_overlays(west, south, east, north)
    dump(output / "overlays.json", overlays)
    manifest = {
        "version": 2,
        "id": output.name,
        "title": title,
        "region": region,
        "geographic_bounds": [west, south, east, north],
        "available_layers": [
            "imagery",
            "terrain",
            "roads",
            "rivers",
            "settlements",
            "boundaries",
            "airports",
        ],
        "overlay_sources": overlay_sources,
        "origin": {
            "lat": origin_lat,
            "lon": origin_lon,
            "mission_x_m": 6000,
            "mission_y_m": 4000,
        },
        "crs": LOCAL.to_proj4(),
        "terrain_datum": "EGM96",
        "altitude_reference": "terrain_relative_illustrative",
        "imagery_resolution_m": 10,
        "imagery_valid_percent": valid_percent,
        "nodata_policy": "Source RGB gaps are transparent; at most 0.01 percent of pixels may be missing; no imputation",
        "elevation_grid_m": 100,
        "imagery_product": selected["id"],
        "acquired_at": selected["properties"]["datetime"],
        "selection": "least SCL cloud fraction over 12x8 km footprint at 100 m; newest tie break",
        "footprint_cloud_percent": selected["matb_footprint_cloud_percent"],
        "cloud_cover_percent": selected["properties"].get("eo:cloud_cover"),
        "imagery_assets": {k: selected["assets"][k] for k in ("red", "green", "blue")},
        "terrain_sources": sources,
        "boa_offset_already_applied": selected["properties"].get(
            "earthsearch:boa_offset_applied", False
        ),
        "rgb_stretch": "clip((DN*source_scale+effective_offset)/0.3,0,1)^(1/2.2); effective_offset=0 when boa_offset_already_applied",
        "attribution": "Contains modified Copernicus Sentinel data. Terrain: Mapzen / Tilezen; SRTM and contributing sources.",
        "source_terms": [
            "https://dataspace.copernicus.eu/terms-and-conditions",
            "https://github.com/tilezen/joerd/blob/master/docs/attribution.md",
        ],
        "files": {
            name: hashlib.sha256((output / name).read_bytes()).hexdigest()
            for name in ("elevation.json", "imagery.png", "overlays.json")
        },
    }
    dump(output / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "id": output.name,
                "sha256": hashlib.sha256(
                    (output / "manifest.json").read_bytes()
                ).hexdigest(),
            }
        )
    )


def geographic_overlays(west, south, east, north):
    import mapbox_vector_tile
    from shapely.geometry import shape, mapping, box
    from shapely.ops import transform as transform_geometry

    session = requests.Session()
    session.headers["User-Agent"] = (
        "MATB-research-geography/1.0 (+https://github.com/strikerdlm/MATB)"
    )
    response = session.get("https://tiles.openfreemap.org/planet", timeout=30)
    response.raise_for_status()
    tilejson = response.json()
    template = tilejson["tiles"][0]
    if not template.startswith("https://tiles.openfreemap.org/"):
        raise RuntimeError("Unexpected tile host")
    sources = [
        {
            "url": response.url,
            "sha256": hashlib.sha256(response.content).hexdigest(),
            "attribution": "OpenFreeMap / OpenMapTiles / © OpenStreetMap contributors (ODbL 1.0)",
        }
    ]
    zoom = 12
    n = 2**zoom

    def tile_x(lon):
        return int((lon + 180) / 360 * n)

    def tile_y(lat):
        return int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)

    clip = box(west, south, east, north)
    features = []
    seen = set()
    for tx in range(tile_x(west), tile_x(east) + 1):
        for ty in range(tile_y(north), tile_y(south) + 1):
            url = template.format(z=zoom, x=tx, y=ty)
            r = session.get(url, timeout=40)
            r.raise_for_status()
            sources.append(
                {"url": url, "sha256": hashlib.sha256(r.content).hexdigest()}
            )
            for source_layer, layer in [
                ("transportation", "roads"),
                ("waterway", "rivers"),
                ("place", "settlements"),
                ("boundary", "boundaries"),
            ]:
                decoded = mapbox_vector_tile.decode(r.content).get(source_layer)
                if not decoded:
                    continue
                extent = decoded["extent"]

                def world(x, y, z=None):
                    return (
                        (tx + np.asarray(x) / extent) / n * 360 - 180,
                        np.degrees(
                            np.arctan(
                                np.sinh(
                                    math.pi
                                    * (1 - 2 * (ty + 1 - np.asarray(y) / extent) / n)
                                )
                            )
                        ),
                    )

                for item in decoded["features"]:
                    geo = transform_geometry(
                        world, shape(item["geometry"])
                    ).intersection(clip)
                    if geo.is_empty:
                        continue
                    identity = (layer, geo.wkb)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    properties = item.get("properties", {})
                    features.append(
                        {
                            "type": "Feature",
                            "geometry": mapping(geo),
                            "properties": {
                                "layer": layer,
                                "name": properties.get(
                                    "name:es", properties.get("name", "")
                                ),
                                "class": properties.get("class", ""),
                            },
                        }
                    )
    airport_path = ROOT / "webui/frontend/public/geography/airports.json"
    for feature in json.loads(airport_path.read_text(encoding="utf-8"))["features"]:
        x, y = feature["geometry"]["coordinates"]
        if west <= x <= east and south <= y <= north:
            feature["properties"]["layer"] = "airports"
            features.append(feature)
    sources.append(
        {
            "url": "https://ourairports.com/data/",
            "sha256": hashlib.sha256(airport_path.read_bytes()).hexdigest(),
            "attribution": "OurAirports (public domain)",
        }
    )
    return {"type": "FeatureCollection", "features": features}, sources


def build_atomic(output, end_date, product_id, lat, lon, title, region):
    if output.exists():
        raise RuntimeError("refusing to replace an installed scene")
    output = output.resolve()
    staging_parent = (output.parent / ".pending" / uuid.uuid4().hex).resolve()
    if not staging_parent.is_relative_to(output.parent):
        raise ValueError("staging directory escaped the scene root")
    staging = staging_parent / output.name
    try:
        build(staging, end_date, product_id, lat, lon, title, region)
        output.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(output)
    finally:
        # Only the unique preparation-owned staging directory is removed.
        if staging_parent.exists():
            if not staging_parent.resolve().is_relative_to(output.parent):
                raise ValueError("staging directory escaped the scene root")
            shutil.rmtree(staging_parent)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "webui/frontend/public/scenes" / ID
    )
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--product-id")
    parser.add_argument("--lat", type=float, default=4.15)
    parser.add_argument("--lon", type=float, default=-73.65)
    parser.add_argument("--title", default="Villavicencio")
    parser.add_argument("--region", default="Meta")
    args = parser.parse_args()
    if not (-5 <= args.lat <= 16 and -84 <= args.lon <= -66):
        parser.error("area must be in the Colombia explorer extent")
    build_atomic(
        args.output,
        args.end_date,
        args.product_id,
        args.lat,
        args.lon,
        args.title,
        args.region,
    )
