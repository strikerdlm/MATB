"""Explicit test-only server: synthetic provider responses, never production fallback."""

import os
import time
import httpx

if os.environ.get("MATB_SIMULATION_TEST_MODE") != "1":
    raise RuntimeError("Traffic fixture requires MATB_SIMULATION_TEST_MODE=1")

from app.main import app  # noqa: E402,F401
from app.traffic_service import traffic_service  # noqa: E402


async def fixture(provider, lat, lon, radius):
    aircraft = [
        {
            "hex": "a12345",
            "flight": "FIXTURE01",
            "lat": lat,
            "lon": lon,
            "seen_pos": 0,
            "alt_geom": 22000,
            "alt_baro": 21500,
            "gs": 120,
            "track": 90,
        },
        {
            "hex": "a23456",
            "flight": "FIXTURE02",
            "lat": lat + 0.01,
            "lon": lon,
            "seen_pos": 20,
            "alt_geom": 20000,
            "gs": 80,
            "track": 180,
        },
        {
            "hex": "a34567",
            "flight": "BARO-ONLY",
            "lat": lat,
            "lon": lon + 0.01,
            "seen_pos": 0,
            "alt_baro": 16000,
            "gs": 100,
            "track": 45,
        },
    ]
    return httpx.Response(
        200,
        json={"now": time.time(), "ac": aircraft},
        request=httpx.Request("GET", "https://traffic-fixture.invalid"),
    )


traffic_service.fetch = fixture
