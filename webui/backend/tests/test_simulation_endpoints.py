from __future__ import annotations

import asyncio
import io
import json
import zipfile
from uuid import uuid4

import pytest


async def _prepare(client, *, scenario_id: str = "reference_area_search"):
    return await client.post(
        "/simulation/sessions",
        json={
            "participant_id": "P01",
            "visit_ordinal": 1,
            "scenario_id": scenario_id,
            "locale": "en",
        },
    )


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
        json={"participant_id": "P02", "visit_ordinal": 1, "scenario_id": "reference_area_search", "locale": "en"},
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
        json={
            "participant_id": "P01",
            "visit_ordinal": 16,
            "scenario_id": "reference_area_search",
            "locale": "en",
        },
    )
    outside_transport_bound = await client.post(
        "/simulation/sessions",
        json={
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

    artifacts = await client.get(f"/simulation/sessions/{session_id}/artifacts")
    assert artifacts.status_code == 200
    artifact_paths = {item["relative_path"] for item in artifacts.json()}
    assert "debrief.json" in artifact_paths
    assert all(not item.startswith("/") for item in artifact_paths)

    debrief = await client.get(f"/simulation/sessions/{session_id}/debrief")
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
    debrief = await client.get(f"/simulation/sessions/{session_id}/debrief")
    assert debrief.status_code == 200
    assert debrief.json()["session_id"] == session_id
    bundle = await client.get(f"/simulation/sessions/{session_id}/bundle")
    assert bundle.status_code == 200, bundle.text
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "debrief.json" in names
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
    invalid = await client.post("/simulation/sessions", json={})
    assert invalid.status_code == 422
    detail = invalid.json()["detail"]
    assert detail["code"] == "invalid_request"
    assert isinstance(detail["context"]["fields"], list)
