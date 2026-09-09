import base64
from copy import deepcopy
from hashlib import sha256
import json
import zipfile
import pytest

from matb_integration.evidence.reference import synthetic_capture
from matb_integration.evidence.__main__ import verify_bundle


def submission():
    context = {"rig_id": "synthetic-test-rig", "os": "synthetic-test-os",
        "display": {"id": "synthetic-display"}, "input_device": {"id": "synthetic-input"},
        "audio_path": {"id": "synthetic-audio"}, "acquisition": {"mode": "synthetic-test"},
        "presentation": {"profile_id": "synthetic-software-reference", "renderer": "test"},
        "software_versions": {"acquisition_commit": "b" * 40}, "protocol_id": "test", "protocol_version": "1"}
    artifact = b"SYNTHETIC SOFTWARE TEST ONLY. No physical measurements."
    return {"schema_version": "1.0", "kind": "physical_timing", "context": context,
        "reviewer": "test-fixture", "assessed_at": "2026-09-09T00:00:00Z",
        "evidence": [{"name": "synthetic.txt", "sha256": sha256(artifact).hexdigest(),
                      "content_base64": base64.b64encode(artifact).decode()}],
        "assessment": {"use_tier": "block_level", "rig": {"rig_id": context["rig_id"], "os": context["os"],
                        "display": context["display"], "audio_device": context["audio_path"], "input_device": context["input_device"]},
            "physical_measurement": {"measured": False}, "measurement_summaries": [],
            "representative_full_block_recorded": False}}


def test_linked_evidence_and_revocation_do_not_promote_metrics(client, seeded_participant, tmp_path):
    source = synthetic_capture(tmp_path / "capture")
    capture = client.post("/ingest/evidence", files={k: (k, v) for k, v in source.items()}).json()
    registered = client.post("/evidence/qualifications", json=submission())
    assert registered.status_code == 200, registered.text
    record = registered.json()
    assert record["assessment"]["status"] == "NOT_MEASURED"
    assert client.post("/evidence/qualifications", json=submission()).json()["id"] == record["id"]
    binding = {"record_id": record["id"], "capture_manifest_sha256": capture["manifest_sha256"],
        "context": record["context"], "context_source": "reviewer_attestation", "reviewer": "test", "rationale": "Synthetic test"}
    path = f"/evidence/captures/{capture['id']}"
    assert client.post(path + "/qualifications", json=binding).status_code == 200
    linked = client.get(path).json()
    assert linked["metrics"] == capture["metrics"]
    assert linked["qualification"]["protocol_eligibility"]["status"] == "not_assessed"
    export = tmp_path / "qualified.zip"
    export.write_bytes(client.get(path + "/export").content)
    assert verify_bundle(str(export))["fingerprint"] == capture["reconciliation"]["fingerprint"]
    changed = deepcopy(binding)
    changed["context"]["display"]["id"] = "different-display"
    assert client.post(path + "/qualifications", json=changed).status_code == 409
    assert client.post(f"/evidence/qualifications/{record['id']}/revoke", json={"reviewer": "test", "reason": "Replaced display"}).status_code == 200
    revoked = client.get(path).json()
    assert revoked["qualification"]["items"][0]["status"] == "invalidated"
    assert revoked["metrics"] == capture["metrics"]
    assert client.post(path + "/qualifications", json=binding).status_code == 409
    export.write_bytes(client.get(path + "/export").content)
    assert verify_bundle(str(export))["fingerprint"] == capture["reconciliation"]["fingerprint"]
    # Checksums alone cannot substitute for a valid qualification relationship.
    with zipfile.ZipFile(export) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    report = json.loads(files["report.json"])
    report["qualification"]["items"][0]["status"] = "linked_report"
    files["report.json"] = json.dumps(report).encode()
    checksums = json.loads(files["checksums.json"])
    checksums["report.json"] = sha256(files["report.json"]).hexdigest()
    files["checksums.json"] = json.dumps(checksums).encode()
    with zipfile.ZipFile(export, "w") as archive:
        for name, content in files.items(): archive.writestr(name, content)
    with pytest.raises(ValueError, match="qualification status mismatch"):
        verify_bundle(str(export))


def test_qualification_requires_exact_artifact_and_context(client):
    bad = submission()
    bad["evidence"][0]["sha256"] = "0" * 64
    assert client.post("/evidence/qualifications", json=bad).status_code == 422
    bad = submission()
    bad["assessment"]["rig"]["os"] = "different"
    assert client.post("/evidence/qualifications", json=bad).status_code == 422
