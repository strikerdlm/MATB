"""Local geography preparation jobs and public traffic endpoints."""

from __future__ import annotations
import asyncio, hashlib, json, os, subprocess, sys, uuid
from datetime import date
from pathlib import Path
from typing import Literal
from fastapi.responses import Response
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from matb_integration.suas.presentation.geography import (
    ROOT,
    PUBLIC,
    regions,
    data_root,
)
from matb_integration.suas.presentation.packages import (
    catalog,
    read_package,
    package_root,
)
from ..traffic_service import traffic_service, recording_catalog, recording_path
from .simulation import get_simulation_manager, _managed
from ..simulation_runtime import SimulationManager
from matb_integration.suas.recording.artifacts import verify_checksum_file

router = APIRouter(prefix="/geography", tags=["geography"])
JOBS = {}


class AreaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    lat: float = Field(ge=-5, le=16)
    lon: float = Field(ge=-84, le=-66)
    title: str = Field(min_length=1, max_length=80)
    region: str = Field(default="Colombia", max_length=80)
    end_date: date = Field(default_factory=date.today)


class CaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=80)


def public_job(job):
    return {k: v for k, v in job.items() if k not in {"task", "process"}}


@router.get("/catalog")
async def geography_catalog():
    reference = (
        json.loads((PUBLIC / "catalog.json").read_text(encoding="utf-8"))
        if (PUBLIC / "catalog.json").exists()
        else None
    )
    return {
        "regions": regions(),
        "scenes": catalog(),
        "reference": reference,
        "providers": [
            {"id": "adsb.lol", "available": True},
            {
                "id": "opensky",
                "available": bool(
                    os.environ.get("OPENSKY_CLIENT_ID")
                    and os.environ.get("OPENSKY_CLIENT_SECRET")
                ),
            },
        ],
    }


@router.get("/scenes/{scene_id}/{filename}")
def scene_asset(
    scene_id: str,
    filename: Literal[
        "manifest.json", "elevation.json", "imagery.png", "overlays.json"
    ],
):
    # Serve newly prepared assets immediately; Next's production public-file list
    # is fixed at startup. A synchronous route keeps hashing off the event loop.
    try:
        manifest = read_package(scene_id)
        if filename != "manifest.json" and filename not in manifest["files"]:
            raise ValueError("scene asset unavailable")
        raw = (package_root() / scene_id / filename).read_bytes()
    except (OSError, ValueError) as error:
        raise HTTPException(404, "Verified scene asset unavailable") from error
    digest = hashlib.sha256(raw).hexdigest()
    return Response(
        raw,
        media_type="image/png" if filename.endswith(".png") else "application/json",
        headers={"ETag": f'"{digest}"', "Cache-Control": "no-cache"},
    )


@router.get("/traffic")
async def traffic(
    lat: float = Query(ge=-5, le=16),
    lon: float = Query(ge=-84, le=-66),
    radius_nm: int = Query(default=50, ge=1, le=250),
    provider: str = "adsb.lol",
):
    try:
        return await traffic_service.snapshot(lat, lon, radius_nm, provider)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/recordings")
async def recordings():
    return recording_catalog()


async def prepare(job, body):
    scene_id = job["scene_id"]
    local_python = (
        ROOT
        / ".venv-geography"
        / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    executable = os.environ.get("MATB_GEOGRAPHY_PYTHON") or (
        str(local_python) if local_python.exists() else sys.executable
    )
    args = [
        executable,
        "-X",
        "utf8",
        str(ROOT / "scripts/package_suas_scene.py"),
        "--output",
        str(package_root() / scene_id),
        "--lat",
        str(body.lat),
        "--lon",
        str(body.lon),
        "--title",
        body.title,
        "--region",
        body.region,
        "--end-date",
        body.end_date.isoformat(),
    ]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
    process = None
    try:
        job["status"] = "running"
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=ROOT,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            **(
                {"creationflags": subprocess.CREATE_NO_WINDOW}
                if os.name == "nt"
                else {}
            ),
        )
        job["process"] = process
        while line := await process.stdout.readline():
            value = line.decode("utf-8", errors="replace").strip()
            if value.startswith(("Preparing", "Cloud sampling", "Downloading")):
                job["progress"] = value
            job["last_output"] = value[-300:]
        code = await process.wait()
        if code:
            raise ValueError(
                "Preparation failed. Check geographic dependencies, connectivity and source coverage. "
                + job.get("last_output", "")
            )
        job["scene"] = read_package(scene_id)
        job["status"] = "ready"
        job["progress"] = "Package verified"
    except asyncio.CancelledError:
        if process and process.returncode is None:
            process.terminate()
            await process.wait()
        job["status"] = "cancelled"
    except (OSError, ValueError) as e:
        job["status"] = "failed"
        job["error"] = str(e)
    finally:
        job.pop("process", None)


@router.post("/preparations", status_code=202)
async def prepare_area(body: AreaRequest):
    if any(j["status"] in {"queued", "running"} for j in JOBS.values()):
        raise HTTPException(409, "Another area is being prepared")
    identifier = uuid.uuid4().hex
    job = {
        "id": identifier,
        "scene_id": "area-" + identifier,
        "status": "queued",
        "progress": "Queued",
    }
    JOBS[identifier] = job
    if len(JOBS) > 64:
        del JOBS[next(iter(JOBS))]
    job["task"] = asyncio.create_task(prepare(job, body))
    return public_job(job)


@router.get("/preparations/{identifier}")
async def get_preparation(identifier: str):
    if identifier not in JOBS:
        raise HTTPException(
            404, "Preparation not found; interrupted jobs must be prepared again"
        )
    return public_job(JOBS[identifier])


@router.delete("/preparations/{identifier}")
async def cancel_preparation(identifier: str):
    if identifier not in JOBS:
        raise HTTPException(404, "Preparation not found")
    job = JOBS[identifier]
    if job["status"] not in {"queued", "running"}:
        raise HTTPException(409, "Preparation already finished")
    job["task"].cancel()
    await asyncio.gather(job["task"], return_exceptions=True)
    job["status"] = "cancelled"
    return public_job(job)


async def stop_jobs():
    tasks = [j["task"] for j in JOBS.values() if j.get("task") and not j["task"].done()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


@router.post("/captures/{session_id}", status_code=201)
async def promote_capture(
    session_id: str,
    body: CaptureRequest,
    lease: str | None = Header(default=None, alias="X-Simulation-Controller"),
    manager: SimulationManager = Depends(get_simulation_manager),
):
    async def perform():
        async with manager._lock:
            handle = manager._require(session_id, lease)
            if (
                handle.session_mode != "interactive_technical"
                or handle.lifecycle != "FINISHED"
            ):
                raise ValueError(
                    "Finish a technical session before saving its traffic capture"
                )
            config = handle.manifest.get("presentation", {})
            if config.get("traffic", {}).get("mode") != "live":
                raise ValueError("Session did not use live traffic")
            if verify_checksum_file(handle.recorder.run_dir):
                raise ValueError("Capture artifacts did not pass verification")
            source = handle.recorder.run_dir / "traffic.jsonl"
            if not source.exists():
                raise ValueError("No traffic frames were recorded")
            frames = [
                json.loads(line)
                for line in source.read_text(encoding="utf-8").splitlines()
            ]
            if not frames or not any(f["tracks"] for f in frames):
                raise ValueError("No aircraft observations were captured")
            # Preserve the initial no-observation interval instead of shifting the exposure.
            if frames[0]["simulation_time_ms"] > 0:
                frames.insert(
                    0,
                    {
                        **frames[0],
                        "simulation_time_ms": 0,
                        "tracks": [],
                        "status": "unavailable",
                    },
                )
            identifier = "traffic-" + uuid.uuid4().hex
            recording = {
                "version": 1,
                "id": identifier,
                "title": body.title,
                "scene_id": config["scene_id"],
                "scene_sha256": config["scene_sha256"],
                "provider": config["traffic"]["provider"],
                "duration_ms": manager._time(handle),
                "frames": frames,
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "geoid_sha256": json.loads(
                    (PUBLIC / "catalog.json").read_text(encoding="utf-8")
                )["files"]["geoid.json"],
            }
            path = recording_path(identifier)
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(
                recording, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
            with path.open("xb") as stream:
                stream.write(raw)
            return {
                k: v
                for k, v in {
                    **recording,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }.items()
                if k != "frames"
            }

    return await _managed(perform())
