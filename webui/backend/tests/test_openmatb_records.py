from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
import httpx
from sqlmodel import Session

from app.models import Participant, Visit
from app.openmatb_models import OpenMatbSuiteSession
from app.openmatb_runtime import OpenMatbManager, OpenMatbRuntimeError
from app.openmatb_schemas import CreateOpenMatbSession, WorkloadScaleRequest


@pytest.fixture
def controlled(engine, tmp_path):
    with Session(engine) as db:
        db.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        db.add(Visit(participant_id="P01", visit_ordinal=1, scheduled_day=0))
        db.commit()
    manager = OpenMatbManager(engine=engine, repo_root=Path(__file__).resolve().parents[3],
                             artifact_root=tmp_path / "controlled", python_executable=Path(__file__))
    manager.displays = lambda: [{"index": 0, "label": "Display 1", "width": 1920, "height": 1080, "x": 0, "y": 0},
                                {"index": 1, "label": "Display 2", "width": 1920, "height": 1080, "x": 1920, "y": 0}]
    prepared = asyncio.run(manager.create_session(CreateOpenMatbSession(execution_purpose="study", participant_id="P01", visit_ordinal=1)))
    return manager, prepared


def awaiting_scale(manager, prepared, engine):
    with Session(engine) as db:
        row = db.get(OpenMatbSuiteSession, prepared.session.id)
        order = json.loads(row.block_order_json)
        row.current_block_index = 1
        attempt = manager.records.begin(db, row, order[1])
        attempt.task_status = "completed"
        row.lifecycle = "AWAITING_SCALE"
        db.add(attempt)
        db.add(row)
        db.commit()
        return attempt.id, order[1]


def ratings(block_id=None, value=50):
    return WorkloadScaleRequest(nasa_tlx={key: value for key in (
        "mental_demand", "physical_demand", "temporal_demand", "performance", "effort", "frustration")},
        bedford=4, **({"block_instance_id": block_id} if block_id else {}))


def test_new_session_exposes_empty_attempt_and_truthful_receipt(controlled):
    manager, prepared = controlled
    assert prepared.session.active_block_instance_id is None
    receipt = manager.receipt(prepared.session.id)
    assert receipt["attempts"] == []
    assert receipt["lifecycle"] == "INSTRUCTIONS"
    assert receipt["execution_purpose"] == "study"


def test_unbound_and_stale_ratings_cannot_save_to_current_block(controlled, engine):
    manager, prepared = controlled
    attempt_id, _ = awaiting_scale(manager, prepared, engine)
    with pytest.raises(OpenMatbRuntimeError, match="block_identity_required"):
        manager.submit_scale(prepared.session.id, prepared.participant_token, ratings())
    with pytest.raises(OpenMatbRuntimeError, match="block_mismatch"):
        manager.submit_scale(prepared.session.id, prepared.participant_token, ratings(str(uuid4())))
    current = manager.session_view(prepared.session.id)
    assert current.active_block_instance_id == attempt_id
    assert current.scores == {}
    assert current.lifecycle == "AWAITING_SCALE"


def test_duplicate_scale_save_is_idempotent_and_never_moves_next_block(controlled, engine):
    manager, prepared = controlled
    attempt_id, block = awaiting_scale(manager, prepared, engine)
    request = ratings(attempt_id)
    first, changed = manager.submit_scale_once(prepared.session.id, prepared.participant_token, request)
    assert changed is True
    assert first.current_block_index == 2
    assert first.scores[block]["rtlx_mean_0_100"] == 50
    assert first.scores[block]["block_instance_id"] == attempt_id
    second, changed = manager.submit_scale_once(prepared.session.id, prepared.participant_token, request)
    assert changed is False
    assert second.scores == first.scores
    assert second.current_block_index == 2
    with pytest.raises(OpenMatbRuntimeError, match="scale_already_saved"):
        manager.submit_scale(prepared.session.id, prepared.participant_token, ratings(attempt_id, 55))


def test_saved_ratings_do_not_claim_missing_task_artifacts_or_qualification(controlled, engine):
    manager, prepared = controlled
    attempt_id, _ = awaiting_scale(manager, prepared, engine)
    manager.submit_scale(prepared.session.id, prepared.participant_token, ratings(attempt_id))
    receipt = manager.receipt(prepared.session.id)
    attempt = receipt["attempts"][0]
    assert attempt["ratings_status"] == "saved"
    assert attempt["legacy_import_status"] == "missing"
    assert attempt["capture_id"] is None
    assert attempt["qualification"] is None
    assert attempt["artifact_status"] != "saved"


def test_repeated_practice_uses_different_attempt_ids(controlled, engine):
    manager, prepared = controlled
    with Session(engine) as db:
        row = db.get(OpenMatbSuiteSession, prepared.session.id)
        first = manager.records.begin(db, row, "PRACTICE")
        first.task_status = "completed"
        db.add(first)
        row.current_block_index = 1
        row.lifecycle = "BETWEEN_BLOCKS"
        db.add(row)
        db.commit()
        first_id = first.id
    manager.repeat_practice(prepared.session.id, prepared.controller_lease)
    with Session(engine) as db:
        row = db.get(OpenMatbSuiteSession, prepared.session.id)
        second = manager.records.begin(db, row, "PRACTICE")
        db.commit()
        assert second.id != first_id
    attempts = manager.receipt(prepared.session.id)["attempts"]
    assert len(attempts) == 2
    assert all(item["ratings_status"] == "not_required" for item in attempts)


def test_display_disappearing_blocks_preparation(controlled):
    manager, prepared = controlled
    asyncio.run(manager.abort(prepared.session.id, prepared.controller_lease, "test_abort"))
    manager.displays = lambda: [{"index": 0, "label": "Display 1", "width": 1920, "height": 1080, "x": 0, "y": 0}]
    with pytest.raises(OpenMatbRuntimeError, match="display_unavailable"):
        asyncio.run(manager.create_session(CreateOpenMatbSession(execution_purpose="study", participant_id="P01", visit_ordinal=1, display_index=1)))


def sealed_attempt(controlled, engine, *, terminal=True):
    from hashlib import sha256
    from matb_integration.evidence.writer import EvidenceWriter
    from matb_integration.evidence.contracts import canonical_bytes
    manager, prepared = controlled
    with Session(engine) as db:
        suite = db.get(OpenMatbSuiteSession, prepared.session.id)
        attempt = manager.records.begin(db, suite, "PRACTICE")
        aid = attempt.id
        db.commit()
    root = manager.artifact_root / prepared.session.id / "sessions" / "PRACTICE"
    root.mkdir(parents=True, exist_ok=True)
    csv = root / f"{aid}.csv"
    csv.write_text("logtime,scenario_time,type,module,address,value\n", encoding="utf-8")
    scenario = csv.with_suffix(".scenario.manifest.json")
    scenario.write_bytes(canonical_bytes({"manifest_version": 3, "scenario": {"sha256": "a" * 64},
        "participant_id": "P01", "visit_ordinal": 1, "questionnaires": {"include_nasatlx": False, "include_bedford": False}}))
    context = {"scenario_sha256": "a" * 64, "profile_id": "synthetic-records-test",
        "source_commit": "b" * 40, "source_dirty": False, "component_version": "synthetic-test-1", "scenario_manifest_status": "verified"}
    writer = EvidenceWriter(csv, str(uuid4()), context, {"parent_session_id": prepared.session.id,
        "block_instance_id": aid, "participant_id": "P01", "visit_ordinal": 1, "condition": "PRACTICE", "execution_purpose": "practice"})
    writer.lifecycle("started", 0, 1000)
    writer.record({"type": "scenario_manifest_evidence", "module": "", "address": "", "scenario_time": 0,
        "value": canonical_bytes({"status": "verified", "scenario_manifest_sha256": sha256(scenario.read_bytes()).hexdigest()}).decode()}, {"recorded_monotonic_ns": 1100})
    writer.lifecycle("completed", 1, 2000, "completed")
    writer.seal(completion="completed", artifacts={"scenario_manifest": scenario, "legacy_csv": csv})
    with Session(engine) as db:
        suite = db.get(OpenMatbSuiteSession, prepared.session.id)
        manager.records.finish(db, suite, outcome="completed", csv=csv)
        suite.lifecycle = "COMPLETE" if terminal else "BETWEEN_BLOCKS"
        db.add(suite)
        db.commit()
    return aid, writer.manifest.capture_id, writer.paths["events"].read_bytes()


def test_evidence_waits_until_suite_ends_and_preserves_original_bytes(controlled, engine):
    from app.evidence_models import EvidenceArtifact, EvidenceCapture
    from sqlmodel import select
    manager, prepared = controlled
    aid, cid, events = sealed_attempt(controlled, engine, terminal=False)
    manager.records.process(aid)
    with Session(engine) as db:
        assert db.get(EvidenceCapture, cid) is None
        suite = db.get(OpenMatbSuiteSession, prepared.session.id)
        suite.lifecycle = "COMPLETE"
        db.add(suite)
        db.commit()
    asyncio.run(manager._process_evidence())
    receipt = manager.receipt(prepared.session.id)
    assert receipt["attempts"][0]["capture_id"] == cid
    assert receipt["attempts"][0]["evidence_status"] == "processed"
    assert receipt["attempts"][0]["ratings_status"] == "not_required"
    with Session(engine) as db:
        capture = db.get(EvidenceCapture, cid)
        assert capture.execution_purpose == "practice"
        artifact = db.exec(select(EvidenceArtifact).where(EvidenceArtifact.capture_id == cid, EvidenceArtifact.role == "events")).one()
        assert artifact.content == events


def test_failed_derivation_retry_reuses_capture_and_creates_new_processing_attempt(controlled, engine, monkeypatch):
    from app import evidence_service
    from app.evidence_models import EvidenceCapture, EvidenceRun
    from sqlmodel import select
    manager, prepared = controlled
    aid, cid, _ = sealed_attempt(controlled, engine)
    original = evidence_service.reconcile
    def fail(*args, **kwargs):
        raise RuntimeError("simulated processor failure")
    monkeypatch.setattr(evidence_service, "reconcile", fail)
    asyncio.run(manager._process_evidence())
    assert manager.receipt(prepared.session.id)["attempts"][0]["evidence_status"] == "failed"
    monkeypatch.setattr(evidence_service, "reconcile", original)
    async def retry():
        await manager.retry_evidence(prepared.session.id, aid, prepared.controller_lease)
        await manager._evidence_task
    asyncio.run(retry())
    assert manager.receipt(prepared.session.id)["attempts"][0]["evidence_status"] == "processed"
    with Session(engine) as db:
        assert len(db.exec(select(EvidenceCapture)).all()) == 1
        assert len(db.exec(select(EvidenceRun).where(EvidenceRun.capture_id == cid)).all()) == 2


def test_processor_prevents_overlapping_native_acquisition(controlled):
    manager, prepared = controlled
    manager._processing_evidence = True
    with pytest.raises(OpenMatbRuntimeError, match="evidence_processing_active"):
        asyncio.run(manager.start_block(prepared.session.id, prepared.controller_lease))
    from app.openmatb_schemas import VisualProfilePreviewRequest
    with pytest.raises(OpenMatbRuntimeError, match="evidence_processing_active"):
        asyncio.run(manager.start_visual_profile_preview("missing", "1", VisualProfilePreviewRequest(display_index=0, windowed=True)))


def test_partial_artifacts_are_not_reported_as_saved(controlled, engine):
    manager, prepared = controlled
    aid, _, _ = sealed_attempt(controlled, engine)
    with Session(engine) as db:
        from app.openmatb_models import OpenMatbBlockAttempt
        attempt = db.get(OpenMatbBlockAttempt, aid)
        csv = Path(attempt.session_csv)
        csv.with_suffix(".timing.observations.jsonl").unlink()
        suite = db.get(OpenMatbSuiteSession, prepared.session.id)
        manager.records.finish(db, suite, outcome="completed", csv=csv)
        db.commit()
    item = manager.receipt(prepared.session.id)["attempts"][0]
    assert item["artifact_status"] == "partial"
    assert item["evidence_status"] == "unavailable"


def test_restart_recovers_attempt_without_claiming_completion(controlled, engine):
    from app.openmatb_models import OpenMatbBlockAttempt
    manager, prepared = controlled
    aid, _, _ = sealed_attempt(controlled, engine)
    with Session(engine) as db:
        suite = db.get(OpenMatbSuiteSession, prepared.session.id)
        suite.lifecycle = "RUNNING"
        attempt = db.get(OpenMatbBlockAttempt, aid)
        attempt.task_status = "running"
        attempt.evidence_status = "processing"
        db.add(suite)
        db.add(attempt)
        db.commit()
    manager._mark_interrupted()
    manager.records.recover()
    item = manager.receipt(prepared.session.id)["attempts"][0]
    assert item["task_status"] == "interrupted"
    assert manager.receipt(prepared.session.id)["lifecycle"] == "INTERRUPTED"
    assert item["finished_at"]


def test_retry_requires_matching_controller_and_attempt(controlled, engine):
    manager, prepared = controlled
    aid, _, _ = sealed_attempt(controlled, engine)
    with pytest.raises(OpenMatbRuntimeError, match="invalid_lease"):
        asyncio.run(manager.retry_evidence(prepared.session.id, aid, "wrong"))
    with pytest.raises(OpenMatbRuntimeError, match="block_mismatch"):
        asyncio.run(manager.retry_evidence(prepared.session.id, str(uuid4()), prepared.controller_lease))


def test_concurrent_duplicate_scale_requests_only_import_once(controlled, engine, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import time
    manager, prepared = controlled
    aid, _ = awaiting_scale(manager, prepared, engine)
    imports = []
    def slow_import(*args):
        time.sleep(0.05)
        imports.append(True)
        return "saved", None
    monkeypatch.setattr(manager, "_ingest_completed_block", slow_import)
    def submit():
        return manager.submit_scale_once(prepared.session.id, prepared.participant_token, ratings(aid))[1]
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: submit(), range(2)))
    assert sorted(outcomes) == [False, True]
    assert len(imports) == 1
    assert manager.session_view(prepared.session.id).current_block_index == 2


@pytest.mark.anyio
async def test_scale_endpoint_emits_one_marker_and_receipt_keeps_saved_block(controlled, engine):
    from fastapi import FastAPI
    from app.routers.openmatb import router
    from types import SimpleNamespace
    manager, prepared = controlled
    aid, _ = awaiting_scale(manager, prepared, engine)
    markers = []
    async def marker(*args):
        markers.append(args)
    # Exercise the component router without depending on the global app's
    # MATB_COMPONENTS selection (the core-only CI app omits native routes).
    app = FastAPI()
    app.include_router(router)
    app.state.openmatb_manager = manager
    app.state.polar_manager = SimpleNamespace(system_marker_for_session=marker)
    url = f"/openmatb/sessions/{prepared.session.id}/scales"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        assert (await client.post(url, json=ratings(aid).model_dump())).status_code == 403
        for _ in range(2):
            response = await client.post(url, json=ratings(aid).model_dump(), headers={"X-OpenMATB-Participant": prepared.participant_token})
            assert response.status_code == 200, response.text
        assert len(markers) == 1
        receipt = (await client.get(f"/openmatb/sessions/{prepared.session.id}/receipt")).json()
    assert receipt["attempts"][0]["block_instance_id"] == aid
    assert receipt["attempts"][0]["ratings_status"] == "saved"


def test_legacy_import_rollback_cannot_discard_confirmed_ratings(controlled, engine, monkeypatch):
    manager, prepared = controlled
    aid, block = awaiting_scale(manager, prepared, engine)
    def rolled_back_import(db, *_args):
        db.rollback()
        return "failed", "automatic_ingest_failed"
    monkeypatch.setattr(manager, "_ingest_completed_block", rolled_back_import)
    result, changed = manager.submit_scale_once(prepared.session.id, prepared.participant_token, ratings(aid))
    assert changed is True
    assert result.scores[block]["block_instance_id"] == aid
    assert manager.receipt(prepared.session.id)["attempts"][0]["legacy_import_status"] == "failed"


def test_native_launch_injects_durable_identity_and_finishes_practice_without_ratings(controlled, engine, monkeypatch):
    from types import SimpleNamespace
    manager, prepared = controlled
    with Session(engine) as db:
        suite = db.get(OpenMatbSuiteSession, prepared.session.id)
        suite.execution_purpose = "practice"
        suite.block_order_json = '["PRACTICE"]'
        db.add(suite)
        db.commit()
    monkeypatch.setattr(manager, "readiness", lambda: SimpleNamespace(ready=True))
    captured = {}
    class CompletedProcess:
        pid = 12345
        returncode = 0
        stdin = None
        def __init__(self):
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self.stdout.feed_data(b'{"event":"ready"}\n{"event":"finished"}\n')
            self.stdout.feed_eof()
            self.stderr.feed_eof()
        async def wait(self):
            return 0
    async def launch(*args, **kwargs):
        captured.update(json.loads(kwargs["env"]["MATB_EVIDENCE_IDENTITY"]))
        return CompletedProcess()
    monkeypatch.setattr("app.openmatb_runtime.asyncio.create_subprocess_exec", launch)
    monkeypatch.setattr("app.openmatb_runtime._WindowsJob", lambda _: None)
    async def run():
        manager.acknowledge_instructions(prepared.session.id, prepared.participant_token)
        await manager.start_block(prepared.session.id, prepared.controller_lease)
        await asyncio.gather(*(h.monitor for h in manager._handles.values()))
        await manager.shutdown()
    asyncio.run(run())
    receipt = manager.receipt(prepared.session.id)
    assert receipt["lifecycle"] == "COMPLETE"
    assert len(receipt["attempts"]) == 1
    attempt = receipt["attempts"][0]
    assert captured["block_instance_id"] == attempt["block_instance_id"]
    assert captured["parent_session_id"] == prepared.session.id
    assert captured["execution_purpose"] == "practice"
    assert attempt["task_status"] == "completed"
    assert attempt["ratings_status"] == "not_required"
    assert attempt["evidence_status"] == "unavailable"


def test_later_launch_failure_still_processes_prior_sealed_blocks(controlled, engine, monkeypatch):
    from types import SimpleNamespace
    manager, prepared = controlled
    aid, cid, _ = sealed_attempt(controlled, engine, terminal=False)
    with Session(engine) as db:
        suite = db.get(OpenMatbSuiteSession, prepared.session.id)
        suite.current_block_index = 1
        suite.execution_purpose = "practice"
        db.add(suite)
        db.commit()
    monkeypatch.setattr(manager, "readiness", lambda: SimpleNamespace(ready=True))
    async def failed_launch(*args, **kwargs):
        raise OSError("simulated launch failure")
    monkeypatch.setattr("app.openmatb_runtime.asyncio.create_subprocess_exec", failed_launch)
    async def run():
        with pytest.raises(OpenMatbRuntimeError, match="openmatb_launch_failed"):
            await manager.start_block(prepared.session.id, prepared.controller_lease)
        assert manager._evidence_task is not None
        await manager._evidence_task
    asyncio.run(run())
    item = next(a for a in manager.receipt(prepared.session.id)["attempts"] if a["block_instance_id"] == aid)
    assert item["capture_id"] == cid
    assert item["evidence_status"] == "processed"


def test_restart_does_not_process_while_a_previous_native_process_survives(controlled, engine, monkeypatch):
    from app.evidence_models import EvidenceCapture
    manager, prepared = controlled
    _, cid, _ = sealed_attempt(controlled, engine, terminal=False)
    with Session(engine) as db:
        suite = db.get(OpenMatbSuiteSession, prepared.session.id)
        suite.lifecycle = "RUNNING"
        suite.active_pid = 12345
        db.add(suite)
        db.commit()
    monkeypatch.setattr("app.openmatb_runtime._process_alive", lambda _pid: True, raising=False)
    manager._mark_interrupted()
    asyncio.run(manager._process_evidence())
    with Session(engine) as db:
        assert db.get(EvidenceCapture, cid) is None
    # Recovery tracking must survive another backend restart too.
    second = OpenMatbManager(engine=engine, repo_root=manager.repo_root, artifact_root=manager.artifact_root,
                            python_executable=manager.python_executable)
    asyncio.run(second._process_evidence())
    with Session(engine) as db:
        assert db.get(EvidenceCapture, cid) is None
    with pytest.raises(OpenMatbRuntimeError, match="native_recovery_required"):
        asyncio.run(second.start_block(prepared.session.id, prepared.controller_lease))
    monkeypatch.setattr("app.openmatb_runtime._process_alive", lambda _pid: False)
    asyncio.run(second._process_evidence())
    with Session(engine) as db:
        assert db.get(EvidenceCapture, cid) is not None
