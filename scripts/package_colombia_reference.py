"""Acquire versioned public Colombia aviation and EGM96 reference assets."""

from pathlib import Path
from datetime import datetime, timezone
import csv, io, json, hashlib
import requests
import numpy as np
import rasterio
from rasterio.io import MemoryFile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "webui/frontend/public/geography"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sources = []

    def fetch(url):
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        sources.append({"url": url, "sha256": hashlib.sha256(r.content).hexdigest()})
        return r.content

    raw = fetch("https://davidmegginson.github.io/ourairports-data/airports.csv")
    features = []
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        if row["iso_country"] != "CO" or row["type"] == "closed":
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        float(row["longitude_deg"]),
                        float(row["latitude_deg"]),
                    ],
                },
                "properties": {
                    k: row.get(k)
                    for k in [
                        "ident",
                        "name",
                        "type",
                        "elevation_ft",
                        "iata_code",
                        "icao_code",
                        "municipality",
                    ]
                },
            }
        )
    (OUT / "airports.json").write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": features},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    raw = fetch("https://cdn.proj.org/us_nga_egm96_15.tif")
    xs = np.arange(-84.0, -65.999, 0.25)
    ys = np.arange(-5.0, 16.001, 0.25)
    with MemoryFile(raw) as mem:
        with mem.open() as src:
            values = [
                float(sample[0])
                for sample in src.sample([(x, y) for y in ys for x in xs])
            ]
    (OUT / "geoid.json").write_text(
        json.dumps(
            {
                "model": "EGM96 15 arc-minute",
                "bounds": [-84, -5, -66, 16],
                "width": len(xs),
                "height": len(ys),
                "values": values,
            },
            separators=(",", ":"),
        )
    )
    catalog = {
        "version": 1,
        "acquired_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "attribution": "Airports: OurAirports (public domain). Geoid: NGA EGM96, distributed by PROJ.",
        "files": {
            f: hashlib.sha256((OUT / f).read_bytes()).hexdigest()
            for f in ["airports.json", "geoid.json"]
        },
    }
    (OUT / "catalog.json").write_text(json.dumps(catalog, indent=2))
    print(f"Packaged {len(features)} Colombia airports and {len(values)} geoid samples")


if __name__ == "__main__":
    main()
