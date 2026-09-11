"""Software-only cross-instrument restoration rehearsal; no hardware qualification."""

import asyncio
import json
from pathlib import Path
import sqlite3
from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.mark.anyio
async def test_whole_synthetic_visit_repeat_amendment_native_h10_and_offline_restore(
    tmp_path, monkeypatch
):
    from app.components import is_component_active

    if not all(
        is_component_active(key) for key in ("matb-openmatb", "matb-physiology")
    ):
        pytest.skip(
            "Cross-instrument native/H10 journey requires auto components; core restore is tested separately"
        )
    from app import db as database, station_resources, study_analysis
    from app.study_registry import (
        template,
        create_draft,
        rehearse,
        freeze,
        activate,
        assign,
        amend,
    )
    from app.study_bindings import binding_options
    from app.study_registry_models import StudyPreparationAdmission
    from app.study_preparation import (
        begin,
        record_stage,
        begin_practice,
        finish_practice,
    )
    from app.assessment_service import create_attempt, transition
    from app.assessment_schemas import AttemptIn
    from app.assessment_models import AssessmentAttempt
    from app.models import Participant, Visit
    from app.openmatb_models import OpenMatbSuiteSession
    from app.openmatb_schemas import CreateOpenMatbSession, WorkloadScaleRequest
    from app.physiology_runtime import PolarCaptureManager
    from matb_integration.physiology.transport import SimulatedPolarTransport
    from app.routers.pvt import ingest_pvt, PvtAssessmentIn
    from app.routers.study_registry import recovery_start, recovery_finish, Attestation
    from app.purpose_service import classify_retrospectively
    from app.study_backup import backup, restore, reproduce
    from app.artifact_paths import resolve_artifact
    from tests.test_openmatb_runtime import _manager
    from tests.test_study_acquisition import native_binding
    from tests.study_policy_fixtures import fixture_policies

    original = tmp_path / "original station ñ"
    original.mkdir()
    path = original / "study.sqlite3"
    engine = create_engine(
        "sqlite:///" + str(path), connect_args={"check_same_thread": False}
    )
    database._configure_sqlite_foreign_keys(engine)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "_engine", engine)
    native = _manager(engine, original)
    monkeypatch.setattr(native, "schedule_evidence_processing", lambda: None)
    monkeypatch.setenv("MATB_OPENMATB_OUTPUT_DIR", str(native.artifact_root))
    monkeypatch.setenv("MATB_PHYSIOLOGY_DIR", str(original / "polar"))
    from types import SimpleNamespace

    monkeypatch.setattr(native, "readiness", lambda: SimpleNamespace(ready=True))
    snapshot = dict(
        schema_version="native-preflight-v1",
        enabled_tasks=["communications"],
        controller=None,
        issues=[],
        mapping={
            "communications": {
                "keys": {"validateresponse": "ENTER"},
                "owncallsign": "SYN001",
            }
        },
        sha256="synthetic-preflight",
    )
    processes = []

    class Process:
        def __init__(self, csv, identity):
            self.csv, self.identity = csv, identity
            self.pid = 934561
            self.returncode = None
            self.stdout, self.stderr = asyncio.StreamReader(), asyncio.StreamReader()
            self.done = asyncio.Event()
            self.stdin = self
            self.stdout.feed_data(
                (
                    json.dumps(
                        dict(event="ready", session_csv=str(csv), preflight=snapshot)
                    )
                    + "\n"
                ).encode()
            )

        def write(self, data):
            if json.loads(data)["command"] == "release_preflight":
                self.stdout.feed_data(b'{"event":"preflight_released"}\n')

        async def drain(self):
            pass

        async def wait(self):
            await self.done.wait()
            return self.returncode

        def terminate(self):
            self.returncode = 0
            self.stdout.feed_eof()
            self.stderr.feed_eof()
            self.done.set()

        kill = terminate

    async def spawn(*command, **kwargs):
        assert kwargs["env"]["MATB_PREPARATION_HOLD"] == "1"
        csv = Path(command[command.index("--session-dir") + 1]) / "synthetic.csv"
        process = Process(csv, json.loads(kwargs["env"]["MATB_EVIDENCE_IDENTITY"]))
        processes.append(process)
        return process

    monkeypatch.setattr("app.openmatb_runtime.asyncio.create_subprocess_exec", spawn)
    monkeypatch.setattr("app.openmatb_runtime._WindowsJob", lambda _: None)
    transport = SimulatedPolarTransport()
    polar = PolarCaptureManager(
        engine=engine, artifact_root=original / "polar", transport=transport
    )
    await polar.startup()
    token, _ = (await polar.scan(0.25))[0]
    await polar.connect(token)

    with Session(engine) as db:
        for participant in ("P01", "P02"):
            db.add(Participant(id=participant, enrollment_date=date(2026, 9, 10)))
            db.flush()
            db.add(Visit(participant_id=participant, visit_ordinal=1, scheduled_day=0))
        db.commit()
        payload = template("pre-post-recovery")
        initial = payload["study"]["occasions"][0]
        binding = native_binding(db)
        physiology = binding_options(db)["physiology"][0]
        occasions = [
            dict(initial, key="pre", order=1),
            dict(
                initial,
                key="native",
                order=2,
                instrument="openmatb",
                config=binding,
                condition_by_arm={"A": "HIGH"},
                collection_group="native-h10",
            ),
            dict(
                initial,
                key="h10",
                order=3,
                instrument="physiology",
                config=physiology,
                collection_group="native-h10",
                accompanying_key="native",
            ),
            dict(
                initial,
                key="rating",
                order=4,
                instrument="questionnaire",
                target_key="native",
                config=dict(
                    binding_id="MATB-FAC-WORKLOAD-1.0",
                    input_mapping="browser-ratings",
                    scoring="rtlx-mean-bedford",
                ),
            ),
            dict(initial, key="post", order=5),
            dict(initial, key="recovery", order=6),
        ]
        payload["study"].update(
            synthetic=False,
            title="Synthetic restoration fixture",
            enabled_instruments=["pvt", "openmatb", "physiology", "questionnaire"],
            occasions=occasions,
            rules=dict(
                preparation="Synthetic measured preparation",
                repeat="Retain explicit interrupted repeats",
                interruption="Retain all sources",
            ),
            recovery_intervals=[
                dict(
                    key="rest",
                    anchor_key="post",
                    before_key="recovery",
                    duration_seconds=1,
                )
            ],
        )
        payload["analysis"].update(
            outcomes=[
                dict(
                    key=key,
                    metric="pvt.median_rt_ms",
                    units="ms",
                    occasion_keys=[key],
                    summary="individual",
                )
                for key in ("pre", "post", "recovery")
            ],
            contrasts=[
                dict(
                    key="change",
                    left_outcome="post",
                    right_outcome="pre",
                    operation="difference",
                )
            ],
            rules=dict(
                exclusions="Report short synthetic observations",
                denominators="All assigned fixtures",
                qualification="Software only",
                pooling="Identical only",
                historical_unknowns="exclude",
            ),
        )
        payload["analysis"]["outcomes"].append(
            dict(
                key="native_hit_rate",
                metric="openmatb.sysmon_hit_rate",
                units="proportion",
                occasion_keys=["native"],
                summary="individual",
            )
        )
        payload["analysis"]["outcomes"].append(
            dict(
                key="h10_hr",
                metric="physiology.mean_hr_bpm",
                units="bpm",
                occasion_keys=["h10"],
                summary="individual",
                source_keys=["baseline"],
            )
        )
        fixture_policies(payload)
        requirement = payload["study"]["preparation_policy"][0]
        requirement.update(
            demonstration_required=True,
            acknowledgement_required=True,
            comprehension=[
                dict(
                    id="fixture-comprehension",
                    metric="comprehension.correct_fraction",
                    comparator="eq",
                    threshold=1,
                    rationale="Software only",
                )
            ],
            practice=[
                dict(
                    id="fixture-practice",
                    metric="pvt.median_rt_ms",
                    comparator="lte",
                    threshold=400,
                    rationale="Software only",
                )
            ],
        )
        draft = create_draft(db, payload)
        rehearsal = rehearse(db, draft.id)
        version = freeze(
            db,
            draft.id,
            dict(
                actor="Dr Synthetic",
                reason="Software only",
                sha256=draft.sha256,
                rehearsal_id=rehearsal.id,
            ),
        )
        activate(db, version.id, actor="Dr Synthetic", reason="Software fixture")
        assignment = assign(db, version.id, "P01", 1, "A", actor="Dr Synthetic")
        future = assign(db, version.id, "P02", 2, "A", actor="Dr Synthetic")
        identities = json.loads(assignment.occasions_json)
        assignment_id, version_id, study_id = (
            assignment.id,
            version.id,
            version.study_id,
        )
        preparation = begin(db, assignment.id, "pre")
        for stage in ("demonstration", "acknowledgement"):
            record_stage(db, preparation.id, stage, {})
        record_stage(db, preparation.id, "comprehension", {"response": "SPACE"})
        practice = begin_practice(db, preparation.id)
        station_resources.admit_attempt(db, practice)
        transition(db, practice.id, "started")

        def save_pvt(attempt, rt, purpose="study"):
            ingest_pvt(
                PvtAssessmentIn(
                    participant_id="P01",
                    visit_ordinal=1,
                    execution_purpose=purpose,
                    attempt_id=attempt.id,
                    kss_score=3,
                    administered_at="2026-09-10T00:00:00Z",
                    duration_ms=12000,
                    fast_mode=purpose == "practice",
                    locale="es-419",
                    trials=[
                        dict(
                            index=0,
                            wait_ms=2000,
                            stimulus_at_ms=2000,
                            response_at_ms=2000 + rt,
                            rt_ms=rt,
                            outcome="response",
                        )
                    ],
                ),
                db,
            )

        save_pvt(practice, 300, "practice")
        finish_practice(db, preparation.id, practice.id)
        attempts = {
            key: create_attempt(db, occasion, AttemptIn(execution_purpose="study")).id
            for key, occasion in identities.items()
            if key != "rating"
        }
        future_id = future.id
        original_payload = draft.payload_json
        db.commit()
    # Native scenario/profile initialization is completed before protected baseline.
    prepared = await native.create_session(
        CreateOpenMatbSession(
            execution_purpose="study",
            participant_id="P01",
            visit_ordinal=1,
            attempt_id=attempts["native"],
            preparation_only=True,
            visual_profile_id="matb-fac-modern",
            visual_profile_version="1.0.0",
        )
    )
    held = await native.start_block(
        prepared.session.id, prepared.controller_lease, preparation_only=True
    )
    assert held.lifecycle == "PREFLIGHT_HELD"
    with Session(engine) as db:
        assert (
            db.get(AssessmentAttempt, attempts["native"]).acquisition_state == "created"
        )
        baseline = db.get(AssessmentAttempt, attempts["pre"])
        station_resources.admit_attempt(db, baseline)
        transition(db, baseline.id, "started")
        save_pvt(baseline, 300)
        db.commit()
    running = await native.start_block(prepared.session.id, prepared.controller_lease)
    assert running.lifecycle == "RUNNING" and len(processes) == 1
    capture, lease = polar.create_capture(
        participant_id="P01",
        session_kind="openmatb",
        session_id=prepared.session.id,
        settings=physiology["settings"],
        execution_purpose="study",
        attempt_id=attempts["h10"],
    )
    await polar.start_capture(capture.capture_id, lease)
    await polar.add_marker(
        capture.capture_id, lease, "baseline", {"software_only": True}
    )
    for _ in range(6):
        transport.emit_hr(bytes.fromhex("16 3c 00 04"))
        await asyncio.sleep(0.01)
    from hashlib import sha256
    from uuid import uuid4
    from matb_integration.evidence.writer import EvidenceWriter
    from matb_integration.evidence.contracts import canonical_bytes

    process = processes[0]
    csv = process.csv
    csv.write_text(
        "logtime,scenario_time,type,module,address,value\n", encoding="utf-8"
    )
    scenario = csv.with_suffix(".scenario.manifest.json")
    scenario.write_bytes(
        canonical_bytes(
            {
                "manifest_version": 3,
                "scenario": {"sha256": "a" * 64},
                "participant_id": "P01",
                "visit_ordinal": 1,
                "questionnaires": {"include_nasatlx": False, "include_bedford": False},
            }
        )
    )
    writer = EvidenceWriter(
        csv,
        str(uuid4()),
        dict(
            scenario_sha256="a" * 64,
            profile_id="synthetic-restoration",
            source_commit="b" * 40,
            source_dirty=False,
            component_version="synthetic-1",
            scenario_manifest_status="verified",
        ),
        process.identity,
    )
    writer.lifecycle("prepared", 0, 100)
    writer.lifecycle("started", 0, 1000)
    writer.record(
        dict(
            type="scenario_manifest_evidence",
            module="",
            address="",
            scenario_time=0,
            value=canonical_bytes(
                dict(
                    status="verified",
                    scenario_manifest_sha256=sha256(scenario.read_bytes()).hexdigest(),
                )
            ).decode(),
        ),
        {"recorded_monotonic_ns": 1100},
    )
    writer.lifecycle("completed", 1, 2000, "completed")
    writer.seal(
        completion="completed",
        artifacts={"scenario_manifest": scenario, "legacy_csv": csv},
    )
    block_id, capture_id = (
        process.identity["block_instance_id"],
        writer.manifest.capture_id,
    )
    original_events = writer.paths["events"].read_bytes()
    process.terminate()
    for _ in range(100):
        if native.session_view(prepared.session.id).lifecycle == "AWAITING_SCALE":
            break
        await asyncio.sleep(0.01)
    assert native.session_view(prepared.session.id).lifecycle == "AWAITING_SCALE"
    await polar.stop_capture(capture.capture_id, lease)
    await polar.shutdown()
    with Session(engine) as db:
        suite = db.get(OpenMatbSuiteSession, prepared.session.id)
        suite.lifecycle = "AWAITING_SCALE"
        db.add(suite)
        db.commit()
    native.submit_scale(
        prepared.session.id,
        prepared.participant_token,
        WorkloadScaleRequest(
            block_instance_id=block_id,
            nasa_tlx={
                key: 40
                for key in (
                    "mental_demand",
                    "physical_demand",
                    "temporal_demand",
                    "performance",
                    "effort",
                    "frustration",
                )
            },
            bedford=3,
        ),
    )
    with Session(engine) as db:
        # An interrupted post-task attempt is retained beside its explicit repeat.
        interrupted = db.get(AssessmentAttempt, attempts["post"])
        station_resources.admit_attempt(db, interrupted)
        transition(db, interrupted.id, "started")
        transition(db, interrupted.id, "interrupted", category="operator_stop")
        interrupted_id = interrupted.id
        repeat = create_attempt(
            db,
            identities["post"],
            AttemptIn(execution_purpose="study"),
            repeat_of=interrupted.id,
            reason="operator_stop",
        )
        station_resources.admit_attempt(db, repeat)
        transition(db, repeat.id, "started")
        save_pvt(repeat, 400)
        attempts["post"] = repeat.id
        attestation = Attestation(
            actor="Dr Synthetic", reason="Software one-second recovery"
        )
        recovery_start(assignment_id, "rest", attestation, repeat.id, db)
    await asyncio.sleep(1.05)
    with Session(engine) as db:
        recovery_finish(assignment_id, "rest", attestation, db)
        recovery = db.get(AssessmentAttempt, attempts["recovery"])
        station_resources.admit_attempt(db, recovery)
        transition(db, recovery.id, "started")
        save_pvt(recovery, 320)
        station_resources.close_visit(
            db, actor="Dr Synthetic", reason="All software recordings stopped"
        )
        db.commit()
    native.records.process(block_id)
    with Session(engine) as db:
        from app.evidence_models import EvidenceMetric

        metric = db.exec(
            select(EvidenceMetric).where(
                EvidenceMetric.capture_id == capture_id,
                EvidenceMetric.key == "sysmon_hit_rate",
            )
        ).one()
        result = study_analysis.execute(
            db,
            dict(
                native_metric_ids={attempts["native"]: [metric.id]},
                version_id=version_id,
                actor="Dr Synthetic",
                reason="Frozen three-PVT descriptive comparison",
                attempts={identities[key]: value for key, value in attempts.items()},
            ),
        )
        assert json.loads(result.result_json)["contrasts"]["change"]["values"] == {
            "P01": 100
        }
        assert db.get(StudyPreparationAdmission, attempts["pre"]) is not None
        classify_retrospectively(
            db,
            db.get(AssessmentAttempt, attempts["post"]).purpose_provenance_id,
            purpose="practice",
            reviewer="Dr Synthetic",
            reason="Retain later classification separately",
        )
        amended_payload = json.loads(original_payload)
        amended_payload["study"]["title"] = "Future assignment amendment fixture"
        amended_draft = create_draft(db, amended_payload)
        amended_rehearsal = rehearse(db, amended_draft.id)
        amended_version = freeze(
            db,
            amended_draft.id,
            dict(
                actor="Dr Synthetic",
                reason="Future-only amendment",
                sha256=amended_draft.sha256,
                rehearsal_id=amended_rehearsal.id,
            ),
        )
        activate(db, amended_version.id, actor="Dr Synthetic", reason="Future version")
        amended = amend(
            db,
            amended_version.id,
            [future_id],
            actor="Dr Synthetic",
            reason="Only unstarted visit changes",
        )
        assert len(amended) == 1
        station_resources.maintenance(
            db, True, actor="Dr Synthetic", reason="Restoration rehearsal"
        )
        db.commit()
    archive = tmp_path / "complete study.zip"
    manifest = backup(path, archive)
    engine.dispose()
    original.rename(tmp_path / "original unavailable")
    destination = tmp_path / "restored station ñ"
    restore(archive, destination, expected_study_id=study_id)
    monkeypatch.setenv("MATB_ARTIFACT_RELOCATION", str(destination / "relocation.json"))
    with sqlite3.connect(destination / "study.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM study_amendment").fetchone()[0] == 1
        assert (
            db.execute(
                "SELECT acquisition_state FROM assessment_attempt WHERE id=?",
                (interrupted_id,),
            ).fetchone()[0]
            == "interrupted"
        )
        root, manifest_json = db.execute(
            "SELECT artifact_root,manifest_json FROM polar_capture"
        ).fetchone()
        assert resolve_artifact(Path(root) / "rr.parquet").is_file()
        assert json.loads(manifest_json)["artifacts"]
        assert (
            db.execute(
                "SELECT content FROM evidence_artifact WHERE capture_id=? AND role='events'",
                (capture_id,),
            ).fetchone()[0]
            == original_events
        )
    offline = reproduce(destination, tmp_path / "offline reproduction")
    assert offline["executions"][0]["status"] == "reproduced"
    assert manifest["workspace"]["study_id"] == study_id
