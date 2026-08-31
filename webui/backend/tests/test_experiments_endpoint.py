from __future__ import annotations

from matb_integration.contracts import MAX_EXPERIMENT_BODY_BYTES


def _spec_payload(*, onset_ns: int = 10_000_000_000) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "experiment_id": "designer-preview",
        "revision": 1,
        "title": "Designer preview",
        "seed": 42,
        "profile_id": "MATB-EXTENDED-2.0",
        "duration_ns": 60_000_000_000,
        "components": ["matb-runtime"],
        "timeline": [
            {
                "event_key": "sysmon-start",
                "at_ns": 0,
                "duration_ns": None,
                "component_id": "matb-runtime",
                "task": "sysmon",
                "event_type": "openmatb.command",
                "parameters": {"command": "start"},
            },
            {
                "event_key": "nontarget-1",
                "at_ns": onset_ns,
                "duration_ns": 2_000_000_000,
                "component_id": "matb-runtime",
                "task": "sysmon",
                "event_type": "openmatb.command",
                "parameters": {"command": "open_nontarget_opportunity"},
            },
            {
                "event_key": "sysmon-stop",
                "at_ns": 59_000_000_000,
                "duration_ns": None,
                "component_id": "matb-runtime",
                "task": "sysmon",
                "event_type": "openmatb.command",
                "parameters": {"command": "stop"},
            },
        ],
        "metadata": {
            "workload_label_status": "engineering_preset_pending_human_calibration"
        },
    }


def test_compile_experiment_endpoint_returns_scenario_manifest_and_claim_boundary(client):
    response = client.post("/experiments/compile", json=_spec_payload())

    assert response.status_code == 200, response.text
    payload = response.json()
    assert ";sysmon;open_nontarget_opportunity" in payload["scenario_text"]
    assert len(payload["manifest"]["spec"]["sha256"]) == 64
    assert payload["manifest"]["summary"]["sysmon_nontarget_opportunities"] == 1
    assert "does not establish workload calibration" in payload["manifest"]["claim_boundary"]


def test_compile_experiment_endpoint_records_verified_clean_source(client, monkeypatch):
    monkeypatch.setenv("MATB_SOURCE_COMMIT", "a" * 40)
    monkeypatch.setenv("MATB_SOURCE_DIRTY", "false")

    response = client.post("/experiments/compile", json=_spec_payload())

    assert response.status_code == 200, response.text
    manifest = response.json()["manifest"]
    assert manifest["source_commit"] == "a" * 40
    assert manifest["source_dirty"] is False
    assert manifest["provenance_status"] == "complete"


def test_compile_experiment_endpoint_treats_unknown_dirty_state_as_provisional(client, monkeypatch):
    monkeypatch.setenv("MATB_SOURCE_COMMIT", "b" * 40)
    monkeypatch.delenv("MATB_SOURCE_DIRTY", raising=False)

    response = client.post("/experiments/compile", json=_spec_payload())

    assert response.status_code == 200, response.text
    manifest = response.json()["manifest"]
    assert manifest["source_dirty"] is None
    assert manifest["provenance_status"] == "provisional_unverified_source_tree"


def test_compile_experiment_endpoint_rejects_invalid_dirty_environment(client, monkeypatch):
    monkeypatch.setenv("MATB_SOURCE_COMMIT", "c" * 40)
    monkeypatch.setenv("MATB_SOURCE_DIRTY", "perhaps")

    response = client.post("/experiments/compile", json=_spec_payload())

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "invalid_source_provenance_configuration"


def test_compile_experiment_endpoint_rejects_noncanonical_source_commit(client, monkeypatch):
    monkeypatch.setenv("MATB_SOURCE_COMMIT", " " + "d" * 40)
    monkeypatch.setenv("MATB_SOURCE_DIRTY", "false")

    response = client.post("/experiments/compile", json=_spec_payload())

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "experiment_compile_error"
    assert "full lowercase Git object ID" in response.json()["detail"]["message"]


def test_compile_experiment_endpoint_refuses_lossy_subsecond_timing(client):
    response = client.post("/experiments/compile", json=_spec_payload(onset_ns=1_500_000_000))

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "experiment_compile_error"
    assert "whole-second" in response.json()["detail"]["message"]


def test_compile_experiment_endpoint_rejects_declared_oversized_body_before_parsing(client):
    response = client.post(
        "/experiments/compile",
        content=b"{}",
        headers={
            "content-type": "application/json",
            "content-length": str(MAX_EXPERIMENT_BODY_BYTES + 1),
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "experiment_request_too_large"
