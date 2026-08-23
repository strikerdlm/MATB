from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import time
import zipfile

import fastapi.concurrency
import fastapi.dependencies.utils
import fastapi.routing
import httpx
import pytest
import starlette.concurrency
from sqlmodel import Session

from app.classic_persistence import SQLModelClassicPersistence
from app.classic_runtime import ClassicManager
from app.main import app
from app.models import Participant, Visit
from matb_integration.physiology.acquisition import PolarConnectionManager
from matb_integration.physiology.backend import SimulatedPolarBackend
from matb_integration.physiology.openmatb_process import OpenMATBProcessResult


class EndpointFakeLauncher:
    def __init__(self, backend: SimulatedPolarBackend) -> None:
        self.backend = backend

    def available_scenarios(self):
        return (
            "military_aviation/low_workload.txt",
            "military_aviation/medium_workload.txt",
            "military_aviation/high_workload.txt",
        )

    def scenario_sha256(self, scenario_name: str) -> str:
        assert scenario_name in self.available_scenarios()
        return hashlib.sha256(scenario_name.encode("utf-8")).hexdigest()

    def application_sha256(self) -> str:
        return hashlib.sha256(b"endpoint fake OpenMATB source").hexdigest()

    async def run(self, *, scenario_name: str, session_id: str, output_dir: Path):
        del scenario_name
        await self.backend.emit_rr_ticks((1024, 1024, 1024))
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / "openmatb-session.csv"
        csv_path.write_text(
            "logtime,scenario_time,type,module,address,value\n"
            "901.0,900.0,performance,track,cursor_in_target,True\n",
            encoding="utf-8",
        )
        events = output_dir / "openmatb-events.jsonl"
        start_monotonic = time.monotonic_ns()
        start_utc = time.time_ns()
        event_names = (
            "scenario_started",
            "task_window_completed",
            "scenario_completed",
            "scenario_finished",
        )
        events.write_text(
            "".join(
                json.dumps(
                    {
                        "schema_version": "openmatb-synchronized-event-v1",
                        "session_id": session_id,
                        "sequence": sequence,
                        "received_monotonic_ns": start_monotonic
                        + (0 if event_name == "scenario_started" else 900_000_000_000),
                        "received_utc_ns": start_utc
                        + (0 if event_name == "scenario_started" else 900_000_000_000),
                        "scenario_time": 0.0 if event_name == "scenario_started" else 900.0,
                        "event": event_name,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
                for sequence, event_name in enumerate(event_names, start=1)
            ),
            encoding="utf-8",
        )
        now = datetime.now(timezone.utc)
        return OpenMATBProcessResult(
            exit_code=0,
            source_csv=csv_path,
            synchronized_events=events,
            stdout_log=output_dir / "stdout.log",
            stderr_log=output_dir / "stderr.log",
            started_at=now,
            finished_at=now,
        )

    async def abort(self, *, timeout_seconds: float = 5.0):
        del timeout_seconds


@pytest.mark.anyio
async def test_classic_history_accepts_safe_pseudonymous_participant_id(
    classic_client,
) -> None:
    client, _manager, _backend = classic_client

    response = await client.get(
        "/classic/sessions",
        params={"participant_id": "UI-P01", "visit_ordinal": 1},
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.fixture
async def classic_client(engine, tmp_path, monkeypatch):
    async def _run_direct(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(starlette.concurrency, "run_in_threadpool", _run_direct)
    monkeypatch.setattr(fastapi.concurrency, "run_in_threadpool", _run_direct)
    monkeypatch.setattr(fastapi.dependencies.utils, "run_in_threadpool", _run_direct)
    monkeypatch.setattr(fastapi.routing, "run_in_threadpool", _run_direct)
    with Session(engine) as db:
        db.add(Participant(id="P40", enrollment_date=date(2026, 8, 23)))
        db.add(Visit(participant_id="P40", visit_ordinal=1, scheduled_day=0))
        db.commit()
    backend = SimulatedPolarBackend()
    polar = PolarConnectionManager(backend)

    async def phase_sleep(_seconds: float):
        await backend.emit_rr_ticks((1024, 1024, 1024))

    manager = ClassicManager(
        artifact_root=tmp_path / "classic",
        persistence=SQLModelClassicPersistence(engine),
        polar=polar,
        launcher=EndpointFakeLauncher(backend),
        sleep=phase_sleep,
    )
    app.state.classic_manager = manager
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client, manager, backend
    finally:
        await manager.shutdown()
        if hasattr(app.state, "classic_manager"):
            del app.state.classic_manager


@pytest.mark.anyio
async def test_polar_and_classic_session_api_seals_downloadable_bundle(classic_client) -> None:
    client, manager, backend = classic_client
    capabilities = await client.get("/classic/polar/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["heart_rate_measurement_uuid"].startswith("00002a37")
    scan = await client.post("/classic/polar/scan", json={"timeout_seconds": 0.1})
    assert scan.status_code == 200
    assert isinstance(scan.json()[0]["token_expires_at_utc_ns"], str)
    token = scan.json()[0]["device_token"]
    connected = await client.post("/classic/polar/connect", json={"device_token": token})
    assert connected.status_code == 200
    assert connected.json()["battery_level"] == 95
    pending_preflight = asyncio.create_task(
        client.post("/classic/polar/preflight", json={"timeout_seconds": 1.0})
    )
    await asyncio.sleep(0)
    await backend.emit_rr_ticks((1024,))
    preflight = await pending_preflight
    assert preflight.status_code == 200
    assert preflight.json()["ready"] is True
    assert isinstance(preflight.json()["measured_at_utc_ns"], str)

    prepared = await client.post(
        "/classic/sessions/prepare",
        json={
            "participant_id": "P40",
            "visit_ordinal": 1,
            "workload_level": "LOW",
            "scenario_name": "military_aviation/low_workload.txt",
        },
    )
    assert prepared.status_code == 201
    session_id = prepared.json()["id"]
    lease = prepared.json()["controller_lease"]
    public = await client.get(f"/classic/sessions/{session_id}")
    assert "controller_lease" not in public.json()
    assert public.json()["created_at"].endswith(("Z", "+00:00"))
    assert len(public.json()["scenario_sha256"]) == 64
    assert len(public.json()["openmatb_source_sha256"]) == 64
    assert public.json()["test_mode"] is False
    assert public.json()["wall_time_scale"] == 1.0

    started = await client.post(
        f"/classic/sessions/{session_id}/start",
        headers={"X-Classic-Controller": lease},
        json={},
    )
    assert started.status_code == 200
    await manager.wait_until_finished(session_id)

    debrief = await client.get(f"/classic/sessions/{session_id}/debrief")
    assert debrief.status_code == 200
    assert debrief.json()["selected_for_visit"] is True
    artifacts = await client.get(f"/classic/sessions/{session_id}/artifacts")
    assert len(artifacts.json()) == 12
    report = await client.get(f"/classic/sessions/{session_id}/artifacts/report.en.md")
    assert report.status_code == 200
    assert "Research use only" in report.text
    bundle = await client.get(f"/classic/sessions/{session_id}/bundle")
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        assert set(archive.namelist()) == {
            artifact["relative_path"] for artifact in artifacts.json()
        }
    summary_json = await client.get("/classic/visits/P40/1/summary.json")
    assert summary_json.status_code == 200
    assert summary_json.json()["workloads"]["LOW"]["selected_attempt_id"] == session_id
    summary_csv = await client.get("/classic/visits/P40/1/summary.csv")
    assert "tracking" in summary_csv.text
    summary_markdown = await client.get("/classic/visits/P40/1/summary.md")
    assert "Research use only" in summary_markdown.text

    events_path = manager.resolve_artifact(session_id, "openmatb-events.jsonl")
    events_path.write_text("tampered\n", encoding="utf-8")
    events_response = await client.get(f"/classic/sessions/{session_id}/events")
    assert events_response.status_code == 500
    assert events_response.json()["detail"]["code"] == "classic_artifact_integrity_failed"


@pytest.mark.anyio
async def test_api_requires_controller_lease_for_start(classic_client) -> None:
    client, _manager, _backend = classic_client
    prepared = await client.post(
        "/classic/sessions/prepare",
        json={
            "participant_id": "P40",
            "visit_ordinal": 1,
            "workload_level": "HIGH",
            "scenario_name": "military_aviation/high_workload.txt",
            "performance_only_override": True,
            "override_reason_code": "sensor_unavailable",
        },
    )
    session_id = prepared.json()["id"]

    response = await client.post(f"/classic/sessions/{session_id}/start", json={})

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "classic_invalid_lease"


@pytest.mark.anyio
async def test_missing_debrief_is_translated_to_structured_404(classic_client) -> None:
    client, _manager, _backend = classic_client

    response = await client.get("/classic/sessions/not-a-session/debrief")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "session_not_found"


@pytest.mark.anyio
async def test_abort_before_start_seals_a_partial_evidence_bundle(classic_client) -> None:
    client, _manager, _backend = classic_client
    prepared = await client.post(
        "/classic/sessions/prepare",
        json={
            "participant_id": "P40",
            "visit_ordinal": 1,
            "workload_level": "MEDIUM",
            "scenario_name": "military_aviation/medium_workload.txt",
            "performance_only_override": True,
            "override_reason_code": "sensor_unavailable",
        },
    )
    session_id = prepared.json()["id"]
    lease = prepared.json()["controller_lease"]

    aborted = await client.post(
        f"/classic/sessions/{session_id}/abort",
        headers={"X-Classic-Controller": lease},
        json={"reason_code": "participant_requested_stop"},
    )

    assert aborted.status_code == 200
    assert aborted.json()["status"] == "ABORTED"
    debrief = await client.get(f"/classic/sessions/{session_id}/debrief")
    assert debrief.status_code == 200
    assert debrief.json()["matb_metrics"]["n_rows"] == 0
    artifacts = await client.get(f"/classic/sessions/{session_id}/artifacts")
    assert len(artifacts.json()) == 12


@pytest.mark.anyio
async def test_windows_capability_contract_matches_supported_bleak_platform(
    classic_client,
    monkeypatch,
) -> None:
    client, _manager, _backend = classic_client
    monkeypatch.setattr("app.routers.classic.platform.system", lambda: "Windows")

    response = await client.get("/classic/polar/capabilities")

    assert response.status_code == 200
    assert any(
        "Windows 11 build 22000" in requirement
        for requirement in response.json()["requirements"]
    )
