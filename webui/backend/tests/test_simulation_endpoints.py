from __future__ import annotations

import asyncio
import io
import json
import zipfile
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.simulation_models import SimulationSession, TechnicalSimulationSession


async def _prepare(client, *, scenario_id: str = "reference_area_search"):
    from tests.study_fixtures import mission_request
    manager=client._transport.app.state.simulation_manager
    request=mission_request(manager.persistence.engine,participant_id='P01',visit_ordinal=1,scenario_id='reference_area_search',locale='es-CO')
    return await client.post(
        "/simulation/sessions",
        json={**request.model_dump(mode='json'),'scenario_id':scenario_id},
    )


async def _prepare_technical(client, *, block_id: str = "LOW"):
    return await client.post(
        "/simulation/technical-sessions",
        json={"execution_purpose": "practice",
            "scenario_id": "reference_area_search",
            "block_id": block_id,
            "locale": "es-CO",
        },
    )


@pytest.mark.anyio
@pytest.mark.parametrize("block_id", ["PRACTICE", "LOW", "MEDIUM", "HIGH"])
async def test_technical_session_launches_selected_profile_without_research_identity(
    simulation_client,
    engine,
    block_id: str,
) -> None:
    client, manager = simulation_client
    prepared = await _prepare_technical(client, block_id=block_id)
    assert prepared.status_code == 201, prepared.text
    body = prepared.json()
    from app.console_profile import current_console_profile
    assert body["console_profile"] == current_console_profile()
    assert body["participant_id"] is None
    assert body["visit_id"] is None
    assert body["session_mode"] == "interactive_technical"
    assert body["record_class"] == "technical_only"
    assert body["selected_block_id"] == block_id
    assert body["block_order"] == [block_id]
    assert body["next_block_id"] == block_id
    assert body["validity"] == "technical_only"

    with Session(engine) as db:
        assert db.get(SimulationSession, body["id"]) is None
        technical = db.get(TechnicalSimulationSession, body["id"])
        assert technical is not None
        assert technical.selected_block_id == block_id

    headers = {"X-Simulation-Controller": body["controller_lease"]}
    started = await client.post(
        f"/simulation/sessions/{body['id']}/start",
        json={"block_id": block_id},
        headers=headers,
    )
    assert started.status_code == 200, started.text
    assert started.json()["active_block_id"] == block_id
    await manager.tick_once()
    finished = await client.post(
        f"/simulation/sessions/{body['id']}/finish",
        json={"disposition": "complete"},
        headers=headers,
    )
    assert finished.status_code == 200, finished.text
    debrief = await client.get(f"/simulation/sessions/{body['id']}/debrief")
    if debrief.status_code == 202:
        closed=await client.post("/station/close",json={"actor":"Dr Fixture","reason":"Assigned mission finished; inspect derived artifacts"})
        assert closed.status_code == 200, closed.text
        debrief=await client.get(f"/simulation/sessions/{session_id}/debrief")
    assert debrief.status_code == 200, debrief.text
    assert debrief.json()["record_class"] == "technical_only"
    assert debrief.json()["console_profile"] == body["console_profile"]
    manifest = json.loads((manager.active.recorder.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["selected_block_id"] == block_id
    assert manifest["record_class"] == "technical_only"
    assert "participant_id" not in manifest
    assert "visit_ordinal" not in manifest
    assert "block_order" not in manifest


@pytest.mark.anyio
async def test_technical_session_rejects_research_fields_and_other_profile(simulation_client) -> None:
    client, _manager = simulation_client
    contaminated = await client.post(
        "/simulation/technical-sessions",
        json={"execution_purpose": "practice",
            "scenario_id": "reference_area_search",
            "block_id": "LOW",
            "locale": "es-CO",
            "participant_id": "P01",
        },
    )
    assert contaminated.status_code == 422

    prepared = await _prepare_technical(client, block_id="LOW")
    body = prepared.json()
    wrong = await client.post(
        f"/simulation/sessions/{body['id']}/start",
        json={"block_id": "HIGH"},
        headers={"X-Simulation-Controller": body["controller_lease"]},
    )
    assert wrong.status_code == 409
    assert wrong.json()["detail"]["code"] == "invalid_transition"


@pytest.mark.anyio
async def test_scenarios_list_and_validate_without_installing(simulation_client) -> None:
    client, _manager = simulation_client
    listed = await client.get("/simulation/scenarios")
    assert listed.status_code == 200
    assert listed.json()[0]["scenario_id"] == "reference_area_search"
    assert "truth" not in listed.text

    valid_yaml = b"schema_version: 1\n"
    invalid = await client.post(
        "/simulation/scenarios/validate",
        files={"file": ("invalid.yaml", valid_yaml, "text/yaml")},
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "scenario_invalid"

    malformed = await client.post(
        "/simulation/scenarios/validate",
        files={"file": ("malformed.yaml", b"foo: [", "text/yaml")},
    )
    assert malformed.status_code == 422
    assert malformed.json()["detail"]["code"] == "scenario_invalid"



@pytest.mark.anyio
async def test_prepare_unknown_identity_and_path_safe_scenario(simulation_client, seeded_participant) -> None:
    client, _manager = simulation_client
    unknown_participant = await client.post(
        "/simulation/sessions",
        json={"execution_purpose": "study", "participant_id": "P02", "visit_ordinal": 1, "scenario_id": "reference_area_search", "locale": "en"},
    )
    assert unknown_participant.status_code == 404
    assert unknown_participant.json()["detail"]["code"] == "participant_not_found"

    unknown_scenario = await _prepare(client, scenario_id="does_not_exist")
    assert unknown_scenario.status_code == 404
    assert unknown_scenario.json()["detail"]["code"] == "scenario_not_found"

    traversal = await _prepare(client, scenario_id="../reference_area_search")
    assert traversal.status_code == 422


@pytest.mark.anyio
async def test_prepare_transport_allows_legacy_ordinal_but_runtime_requires_visit(
    simulation_client,
    seeded_participant,
) -> None:
    client, _manager = simulation_client

    legacy_ordinal = await client.post(
        "/simulation/sessions",
        json={"execution_purpose": "study",
            "participant_id": "P01",
            "visit_ordinal": 16,
            "scenario_id": "reference_area_search",
            "locale": "en",
        },
    )
    outside_transport_bound = await client.post(
        "/simulation/sessions",
        json={"execution_purpose": "study",
            "participant_id": "P01",
            "visit_ordinal": 17,
            "scenario_id": "reference_area_search",
            "locale": "en",
        },
    )

    assert legacy_ordinal.status_code == 404
    assert legacy_ordinal.json()["detail"]["code"] == "visit_not_found"
    assert outside_transport_bound.status_code == 422


@pytest.mark.anyio
async def test_prepare_start_command_state_flow(simulation_client, seeded_participant) -> None:
    client, manager = simulation_client
    prepared = await _prepare(client)
    assert prepared.status_code == 201, prepared.text
    body = prepared.json()
    assert body["controller_lease"]
    assert "controller_lease" not in (await client.get(f"/simulation/sessions/{body['id']}")).json()
    headers = {"X-Simulation-Controller": body["controller_lease"]}

    missing_lease = await client.post(f"/simulation/sessions/{body['id']}/start", json={"block_id": "PRACTICE"})
    assert missing_lease.status_code == 403
    assert missing_lease.json()["detail"]["code"] == "invalid_lease"
    wrong_lease = await client.post(
        f"/simulation/sessions/{body['id']}/start",
        json={"block_id": "PRACTICE"},
        headers={"X-Simulation-Controller": "wrong"},
    )
    assert wrong_lease.status_code == 403

    started = await client.post(
        f"/simulation/sessions/{body['id']}/start",
        json={"block_id": "PRACTICE"},
        headers=headers,
    )
    assert started.status_code == 200, started.text

    command_id = str(uuid4())
    command_task = asyncio.create_task(
        client.post(
            f"/simulation/sessions/{body['id']}/commands",
            json={
                "command_id": command_id,
                "expected_state_version": 0,
                "kind": "ASSIGN_SECTOR",
                "payload": {"aircraft_id": "UAS-01", "sector_id": "sector_alpha"},
            },
            headers=headers,
        )
    )
    await asyncio.sleep(0)
    await manager.tick_once()
    command = await command_task
    assert command.status_code == 200, command.text
    assert command.json()["status"] == "accepted"

    state = await client.get(f"/simulation/sessions/{body['id']}/state")
    assert state.status_code == 200
    state_body = state.json()
    assert state_body["aircraft"]["UAS-01"]["assigned_sector_id"] == "sector_alpha"
    assert "truth" not in state.text
    assert "controller_lease" not in state.text

    stale = asyncio.create_task(
        client.post(
            f"/simulation/sessions/{body['id']}/commands",
            json={
                "command_id": str(uuid4()),
                "expected_state_version": 0,
                "kind": "HOLD",
                "payload": {"aircraft_id": "UAS-01"},
            },
            headers=headers,
        )
    )
    await asyncio.sleep(0)
    await manager.tick_once()
    stale_response = await stale
    assert stale_response.status_code == 200
    assert stale_response.json()["status"] == "rejected"
    assert stale_response.json()["code"] == "stale_state_version"

    duplicate = asyncio.create_task(
        client.post(
            f"/simulation/sessions/{body['id']}/commands",
            json={
                "command_id": command_id,
                "expected_state_version": 0,
                "kind": "ASSIGN_SECTOR",
                "payload": {"aircraft_id": "UAS-01", "sector_id": "sector_alpha"},
            },
            headers=headers,
        )
    )
    await asyncio.sleep(0)
    await manager.tick_once()
    duplicate_response = await duplicate
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["status"] == "duplicate"


@pytest.mark.anyio
async def test_lifecycle_conflicts_and_terminal_artifacts(simulation_client, seeded_participant) -> None:
    client, manager = simulation_client
    prepared = await _prepare(client)
    assert prepared.status_code == 201
    body = prepared.json()
    session_id = body["id"]
    headers = {"X-Simulation-Controller": body["controller_lease"]}

    second = await _prepare(client)
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "active_session"

    impossible_pause = await client.post(
        f"/simulation/sessions/{session_id}/pause",
        json={},
        headers=headers,
    )
    assert impossible_pause.status_code == 409
    assert impossible_pause.json()["detail"]["code"] == "invalid_transition"

    before_artifacts = await client.get(f"/simulation/sessions/{session_id}/artifacts")
    before_debrief = await client.get(f"/simulation/sessions/{session_id}/debrief")
    assert before_artifacts.status_code == 409
    assert before_debrief.status_code == 409

    started = await client.post(
        f"/simulation/sessions/{session_id}/start",
        json={"block_id": "PRACTICE"},
        headers=headers,
    )
    assert started.status_code == 200
    finished = await client.post(
        f"/simulation/sessions/{session_id}/finish",
        json={"disposition": "complete"},
        headers=headers,
    )
    assert finished.status_code == 200, finished.text
    assert finished.json()["lifecycle"] == "FINISHED"
    from tests.station_fixtures import close_and_drain
    await close_and_drain(manager.persistence.engine)

    artifacts = await client.get(f"/simulation/sessions/{session_id}/artifacts")
    assert artifacts.status_code == 200
    artifact_paths = {item["relative_path"] for item in artifacts.json()}
    assert "debrief.json" in artifact_paths
    assert all(not item.startswith("/") for item in artifact_paths)

    debrief = await client.get(f"/simulation/sessions/{session_id}/debrief")
    if debrief.status_code == 202:
        closed=await client.post("/station/close",json={"actor":"Dr Fixture","reason":"Assigned mission finished; inspect derived artifacts"})
        assert closed.status_code == 200, closed.text
        debrief=await client.get(f"/simulation/sessions/{session_id}/debrief")
    assert debrief.status_code == 200
    assert debrief.json()["timeline"] == []
    assert "/" not in debrief.text

    await manager.shutdown()


@pytest.mark.anyio
async def test_public_bundle_excludes_private_run_files(simulation_client, seeded_participant) -> None:
    client, manager = simulation_client
    prepared = await _prepare(client)
    body = prepared.json()
    session_id = body["id"]
    headers = {"X-Simulation-Controller": body["controller_lease"]}
    started = await client.post(
        f"/simulation/sessions/{session_id}/start",
        json={"block_id": "PRACTICE"},
        headers=headers,
    )
    assert started.status_code == 200
    finished = await client.post(
        f"/simulation/sessions/{session_id}/finish",
        json={"disposition": "complete"},
        headers=headers,
    )
    assert finished.status_code == 200
    from tests.station_fixtures import close_and_drain
    await close_and_drain(manager.persistence.engine)
    debrief = await client.get(f"/simulation/sessions/{session_id}/debrief")
    if debrief.status_code == 202:
        closed=await client.post("/station/close",json={"actor":"Dr Fixture","reason":"Assigned mission finished; inspect derived artifacts"})
        assert closed.status_code == 200, closed.text
        debrief=await client.get(f"/simulation/sessions/{session_id}/debrief")
    assert debrief.status_code == 200
    assert debrief.json()["session_id"] == session_id
    bundle = await client.get(f"/simulation/sessions/{session_id}/bundle")
    assert bundle.status_code == 200, bundle.text
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "debrief.json" in names
        from app.console_profile import current_console_profile
        assert json.loads(archive.read("manifest.json"))["console_profile"] == current_console_profile()
        assert json.loads(archive.read("debrief.json"))["console_profile"] == current_console_profile()
        assert "metrics.json" in names
        assert not {"events.jsonl", "questionnaires.json", "scenario.yaml"} & names
        manifest = json.loads(archive.read("manifest.json"))
        assert "questionnaires.json" in manifest["private_files_excluded"]
    await manager.shutdown()


@pytest.mark.anyio
async def test_recovery_requires_lease_while_runtime_exists(simulation_client, seeded_participant) -> None:
    client, _manager = simulation_client
    prepared = await _prepare(client)
    assert prepared.status_code == 201
    session_id = prepared.json()["id"]
    missing = await client.post(
        f"/simulation/sessions/{session_id}/recover",
        json={"checkpoint_version": 1},
    )
    assert missing.status_code == 403
    assert missing.json()["detail"]["code"] == "invalid_lease"


@pytest.mark.anyio
async def test_request_validation_uses_stable_error_shape(simulation_client, seeded_participant) -> None:
    client, _manager = simulation_client
    invalid = await client.post("/simulation/sessions", json={"execution_purpose": "study", })
    assert invalid.status_code == 422
    detail = invalid.json()["detail"]
    assert detail["code"] == "invalid_request"
    assert isinstance(detail["context"]["fields"], list)

@pytest.mark.anyio
@pytest.mark.parametrize("recorded", ["current", "legacy", "unknown"])
async def test_sealed_view_reads_recorded_profile_without_upgrading(simulation_client, engine, recorded):
    from app.console_profile import current_console_profile
    from app.routers.simulation import _session_view_from_row

    client, manager = simulation_client
    prepared = await _prepare_technical(client)
    body = prepared.json()
    with Session(engine) as db:
        row = db.get(TechnicalSimulationSession, body["id"])
        manifest = json.loads(row.manifest_json)
        if recorded == "legacy":
            manifest.pop("console_profile")
        elif recorded == "unknown":
            manifest["console_profile"]["sha256"] = "0" * 64
        row.manifest_json = json.dumps(manifest)
        original = row.manifest_json
        view = _session_view_from_row(row, db)
        assert view.execution_purpose == "practice"
        assert row.manifest_json == original
        if recorded == "legacy":
            assert view.console_profile is None
        else:
            assert view.console_profile.model_dump() == manifest["console_profile"]
            assert (view.console_profile.model_dump() == current_console_profile()) == (recorded == "current")
    await manager.shutdown()


@pytest.mark.anyio
@pytest.mark.parametrize("recorded", ["current", "legacy", "unknown"])
@pytest.mark.parametrize("technical", [False, True])
async def test_aborted_debrief_preserves_recorded_console_profile(
    simulation_client, seeded_participant, engine, monkeypatch, recorded, technical,
):
    client, manager = simulation_client
    prepared = await (_prepare_technical(client) if technical else _prepare(client))
    assert prepared.status_code == 201, prepared.text
    body = prepared.json()
    session_id = body["id"]
    aborted = await client.post(
        f"/simulation/sessions/{session_id}/finish",
        json={"disposition": "abort"},
        headers={"X-Simulation-Controller": body["controller_lease"]},
    )
    assert aborted.status_code == 200, aborted.text
    assert aborted.json()["lifecycle"] == "ABORTED"
    handle = manager.active
    assert not (handle.recorder.run_dir / "debrief.json").exists()
    expected = dict(body["console_profile"])
    if recorded == "legacy":
        handle.manifest.pop("console_profile")
        expected = None
    elif recorded == "unknown":
        expected = {"id": "future-console", "version": 99, "sha256": "0" * 64}
        handle.manifest["console_profile"] = expected
    # Arrange matching durable metadata so both active and restarted lookup
    # paths exercise the partial debrief without upgrading recorded identity.
    with Session(engine) as db:
        row = db.get(TechnicalSimulationSession if technical else SimulationSession, session_id)
        manifest = json.loads(row.manifest_json)
        if expected is None:
            manifest.pop("console_profile")
        else:
            manifest["console_profile"] = expected
        row.manifest_json = json.dumps(manifest)
        db.add(row)
        db.commit()
    frozen = (handle.recorder.run_dir / "manifest.json").read_bytes()
    for restarted in (False, True):
        with monkeypatch.context() as context:
            if restarted:
                context.setattr(manager, "_handle", None)
            response = await client.get(f"/simulation/sessions/{session_id}/debrief")
        assert response.status_code == 200, response.text
        partial = response.json()
        assert partial["status"] == "partial_unverified"
        assert partial["timeline"] == []
        if expected is None:
            assert "console_profile" not in partial
        else:
            assert partial["console_profile"] == expected
        assert (handle.recorder.run_dir / "manifest.json").read_bytes() == frozen
    await manager.shutdown()
