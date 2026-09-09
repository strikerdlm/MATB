from __future__ import annotations
import asyncio, json, math
import httpx
import pytest
from app.traffic_service import TrafficService, normalized
from matb_integration.suas.presentation.geography import (
    regions,
    local_position,
    projected_track,
    geoid_height,
)
from matb_integration.suas.presentation.packages import catalog


@pytest.fixture
def anyio_backend():
    return "asyncio"


def payload(now=1000):
    return {
        "now": now,
        "ac": [
            {
                "hex": "a12345",
                "flight": "TEST 01",
                "lat": 4.15,
                "lon": -73.65,
                "seen_pos": 0,
                "alt_baro": 10000,
                "alt_geom": 11000,
                "gs": 100,
                "track": 90,
                "baro_rate": 600,
            }
        ],
    }


def response(data, status=200, headers=None):
    return httpx.Response(
        status,
        json=data,
        headers=headers,
        request=httpx.Request("GET", "https://api.adsb.lol/test"),
    )


def test_normalization_preserves_units_missing_data_and_timestamps():
    track = normalized("adsb.lol", payload(), 1000)[0]
    assert track["geometric_altitude_m"] == pytest.approx(3352.8)
    assert track["barometric_altitude_m"] == 3048
    assert track["speed_mps"] == pytest.approx(51.4444)
    assert track["vertical_rate_mps"] == pytest.approx(3.048)
    invalid = payload()
    invalid["ac"][0]["seen_pos"] = None
    assert normalized("adsb.lol", invalid, 1000) == []
    invalid = payload()
    invalid["ac"][0]["lat"] = float("nan")
    assert normalized("adsb.lol", invalid, 1000) == []
    row = [
        "a12345",
        "TEST",
        None,
        998,
        999,
        -73.65,
        4.15,
        None,
        False,
        None,
        None,
        None,
        None,
        None,
    ]
    missing = normalized("opensky", {"time": 1000, "states": [row]}, 1000)[0]
    assert missing["geometric_altitude_m"] is None and missing["speed_mps"] is None
    with pytest.raises(ValueError):
        normalized("adsb.lol", {}, 1000)


@pytest.mark.anyio
async def test_coalescing_staleness_expiry_throttling_and_empty():
    now = [1000]
    calls = []
    mode = ["live"]

    async def fetch(*args):
        calls.append(args)
        if mode[0] == "throttle":
            return response({}, 429, {"Retry-After": "120"})
        return response(payload() if mode[0] == "live" else {"now": now[0], "ac": []})

    service = TrafficService(fetch, lambda: now[0])
    values = await asyncio.gather(*(service.snapshot(4.15, -73.65) for _ in range(5)))
    assert len(calls) == 1 and len(values[0]["tracks"]) == 1
    mode[0] = "throttle"
    now[0] = 1016
    frame = await service.snapshot(4.15, -73.65)
    assert frame["status"] == "throttled" and frame["tracks"][0]["stale"]
    now[0] = 1061
    assert (await service.snapshot(4.15, -73.65))["tracks"] == [] and len(calls) == 2
    now[0] = 1137
    mode[0] = "empty"
    assert (await service.snapshot(4.15, -73.65))["status"] == "empty"
    with pytest.raises(ValueError):
        await service.snapshot(4.15, -73.65, 251)
    with pytest.raises(ValueError):
        await service.snapshot(float("nan"), -73.65)


@pytest.mark.anyio
async def test_outage_preserves_age_and_invalid_payload_is_not_empty():
    now = [1000]

    async def fetch(*args):
        if now[0] > 1000:
            return response({"error": "bad"})
        return response(payload())

    service = TrafficService(fetch, lambda: now[0])
    await service.snapshot(4.15, -73.65)
    now[0] = 1020
    frame = await service.snapshot(4.15, -73.65)
    assert frame["status"] == "unavailable" and frame["tracks"][0]["age_s"] == 20


def test_all_six_sites_and_geoid_are_packaged():
    scenes = catalog()
    assert len(scenes) >= 6
    for site in regions():
        scene = next(
            s
            for s in scenes
            if s["origin"]["lat"] == site["lat"] and s["origin"]["lon"] == site["lon"]
        )
        assert local_position(site["lat"], site["lon"], scene["origin"]) == {
            "x_mm": 6000000,
            "y_mm": 4000000,
        }
        assert math.isfinite(geoid_height(site["lat"], site["lon"]))
    track = normalized("adsb.lol", payload(), 1000)[0]
    origin = {"lat": 4.15, "lon": -73.65, "mission_x_m": 6000, "mission_y_m": 4000}
    projected = projected_track(track, origin)
    assert projected["orthometric_altitude_m"] == pytest.approx(
        track["geometric_altitude_m"] - geoid_height(4.15, -73.65)
    )
    track["geometric_altitude_m"] = None
    assert projected_track(track, origin)["orthometric_altitude_m"] is None


@pytest.mark.anyio
async def test_preparation_job_is_exclusive_and_cancellable(monkeypatch):
    from app.routers import geography as api
    from fastapi import HTTPException
    from pydantic import ValidationError

    api.JOBS.clear()
    started = asyncio.Event()

    async def prepare(job, body):
        job["status"] = "running"
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            job["status"] = "cancelled"

    monkeypatch.setattr(api, "prepare", prepare)
    body = api.AreaRequest(lat=4.15, lon=-73.65, title="Bounded test area")
    job = await api.prepare_area(body)
    await started.wait()
    assert "task" not in job and "process" not in job
    with pytest.raises(HTTPException) as error:
        await api.prepare_area(body)
    assert error.value.status_code == 409
    result = await api.cancel_preparation(job["id"])
    assert result["status"] == "cancelled"
    with pytest.raises(ValidationError):
        api.AreaRequest(lat=90, lon=0, title="Outside")
    with pytest.raises(ValidationError):
        api.AreaRequest(lat=4, lon=-73, title="Invalid", output="../escape")
    await api.stop_jobs()
    api.JOBS.clear()


@pytest.mark.anyio
async def test_failed_preparation_never_advertises_a_scene(monkeypatch):
    from app.routers import geography as api

    async def unavailable(*args, **kwargs):
        raise OSError("dependency unavailable")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", unavailable)
    job = {"id": "test", "scene_id": "area-test", "status": "queued"}
    await api.prepare(job, api.AreaRequest(lat=4, lon=-73, title="Test"))
    assert job["status"] == "failed" and "scene" not in job and "process" not in job


@pytest.mark.anyio
async def test_new_verified_scene_assets_are_served_without_restart(
    tmp_path, monkeypatch
):
    import shutil
    from fastapi import FastAPI
    from app.routers import geography as api
    from matb_integration.suas.presentation import packages

    source = packages.package_root() / "villavicencio-v1"
    monkeypatch.setattr(packages, "package_root", lambda: tmp_path)
    monkeypatch.setattr(api, "package_root", lambda: tmp_path)
    app = FastAPI()
    app.include_router(api.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        url = "/geography/scenes/villavicencio-v1/imagery.png"
        assert (await client.get(url)).status_code == 404
        shutil.copytree(source, tmp_path / "villavicencio-v1")
        response = await client.get(url)
        assert (
            response.status_code == 200
            and response.headers["content-type"] == "image/png"
        )
        assert response.content == (source / "imagery.png").read_bytes()
        assert (
            await client.get("/geography/scenes/villavicencio-v1/private.txt")
        ).status_code == 422
        (tmp_path / "villavicencio-v1" / "imagery.png").write_bytes(b"corrupt")
        assert (await client.get(url)).status_code == 404


def test_recording_checksum_and_timeline_validation(tmp_path, monkeypatch):
    import hashlib
    import app.traffic_service as service

    path = tmp_path / "recording.json"
    monkeypatch.setattr(service, "recording_path", lambda identifier: path)
    recording = {
        "version": 1,
        "provider": "adsb.lol",
        "duration_ms": 2000,
        "frames": [
            {"simulation_time_ms": 0, "tracks": []},
            {"simulation_time_ms": 1000, "tracks": []},
        ],
    }
    raw = json.dumps(recording).encode()
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    assert service.load_recording("test", digest)["sha256"] == digest
    with pytest.raises(ValueError, match="checksum"):
        service.load_recording("test", "0" * 64)
    recording["frames"].reverse()
    path.write_text(json.dumps(recording))
    with pytest.raises(ValueError, match="timeline"):
        service.load_recording("test")
