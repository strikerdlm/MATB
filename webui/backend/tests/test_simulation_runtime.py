from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.models import Participant, PvtAssessment, Visit
from app.simulation_persistence import InMemorySimulationPersistence
from app.simulation_runtime import InvalidLease, SimulationConflict, SimulationManager
from app.simulation_schemas import CommandRequest, CreateSimulationSession
from matb_integration.suas.research.protocol import ActiveProbe
from tests.study_fixtures import mission_request


@pytest.fixture
def runtime_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    import app.models  # noqa: F401
    import app.simulation_models  # noqa: F401
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        db.add(Visit(participant_id="P01", visit_ordinal=1, scheduled_day=0))
        db.commit()
        db.add(PvtAssessment(participant_id="P01", visit_id=1, kss_score=3,
            administered_at="2026-06-01T12:00:00Z", duration_ms=600000, pvt_version=2,
            protocol_valid=True, raw_trials_json="[]", metrics_json="{}"))
        db.commit()
    return engine


@pytest.fixture
def manager(tmp_path: Path):
    return SimulationManager(
        scenario_root=Path(__file__).resolve().parents[3] / "scenarios" / "suas",
        artifact_root=tmp_path / "exports",
        persistence=InMemorySimulationPersistence(),
        run_background_tasks=False,
    )


def request(engine, **changes) -> CreateSimulationSession:
    return mission_request(engine, execution_purpose="study", participant_id="P01", visit_ordinal=1, scenario_id="reference_area_search", locale="en", **changes)


@pytest.mark.anyio
async def test_prepare_start_tick_snapshot_and_lease(manager, runtime_db):
    with Session(runtime_db) as db:
        prepared = await manager.prepare(request(runtime_db), db)
    assert prepared.controller_lease
    assert prepared.lifecycle == "PREPARED"
    with pytest.raises(InvalidLease):
        await manager.start(prepared.id, "PRACTICE", "wrong")
    await manager.start(prepared.id, "PRACTICE", prepared.controller_lease)
    await manager.tick_once()
    await manager.tick_once()
    state = await manager.state(prepared.id)
    assert state["simulation_time_ms"] == 200
    first = await manager.snapshot_once()
    second = await manager.snapshot_once()
    assert first["state_version"] == second["state_version"]
    await manager.shutdown()


@pytest.mark.anyio
async def test_stream_snapshot_includes_active_probe(manager, runtime_db):
    with Session(runtime_db) as db:
        prepared = await manager.prepare(request(runtime_db), db)
    await manager.start(prepared.id, "PRACTICE", prepared.controller_lease)
    probe = {
        "kind": "SAGAT",
        "probe_id": "sagat-1",
        "sa_level": 1,
        "domain": "perception",
        "question": "Which aircraft has the lowest battery?",
        "options": ["UAS-01"],
        "timeout_ms": 15_000,
        "conceal_operational_state": True,
    }
    handle = manager.active
    assert handle is not None and handle.protocol is not None
    handle.protocol.active_probe = ActiveProbe(
        kind="SAGAT",
        probe_id="sagat-1",
        public_payload=probe,
        timeout_ms=15_000,
    )

    envelope = await manager.snapshot_envelope(prepared.id)

    assert envelope.payload["active_probe"] == probe
    await manager.shutdown()


@pytest.mark.anyio
async def test_only_one_active_session(manager, runtime_db):
    with Session(runtime_db) as db:
        first = await manager.prepare(request(runtime_db), db)
        with pytest.raises(SimulationConflict):
            await manager.prepare(request(runtime_db), db)
    await manager.shutdown()


@pytest.mark.anyio
async def test_submit_is_queued_until_tick(manager, runtime_db):
    with Session(runtime_db) as db:
        prepared = await manager.prepare(request(runtime_db), db)
    await manager.start(prepared.id, "PRACTICE", prepared.controller_lease)
    task = asyncio.create_task(manager.submit(prepared.id, prepared.controller_lease, CommandRequest(
        command_id="11111111-1111-1111-1111-111111111111", expected_state_version=0,
        kind="HOLD", payload={"aircraft_id": "UAS-01"},
    )))
    await asyncio.sleep(0)
    await manager.tick_once()
    result = await task
    assert result.status.value in {"accepted", "rejected"}
    await manager.shutdown()


@pytest.mark.anyio
async def test_stale_controller_disconnect_does_not_pause_replacement_stream(manager, runtime_db):
    with Session(runtime_db) as db:
        prepared = await manager.prepare(request(runtime_db), db)
    await manager.start(prepared.id, "PRACTICE", prepared.controller_lease)

    replacement = await manager.hub.subscribe(prepared.id, role="controller")
    await manager.controller_disconnected(prepared.id, prepared.controller_lease)
    assert manager.active is not None
    assert manager.active.lifecycle == "RUNNING"

    await manager.hub.unsubscribe(replacement)
    await manager.controller_disconnected(prepared.id, prepared.controller_lease)
    assert manager.active.lifecycle == "PAUSED"
    await manager.shutdown()


@pytest.mark.anyio
async def test_pending_controller_handoff_defers_disconnect_pause(manager, runtime_db):
    with Session(runtime_db) as db:
        prepared = await manager.prepare(request(runtime_db), db)
    await manager.start(prepared.id, "PRACTICE", prepared.controller_lease)

    await manager.controller_connected(prepared.id, prepared.controller_lease)
    await manager.controller_disconnected(prepared.id, prepared.controller_lease)
    assert manager.active is not None and manager.active.lifecycle == "RUNNING"

    await manager.controller_stream_established(prepared.id, prepared.controller_lease)
    await manager.controller_disconnected(prepared.id, prepared.controller_lease)
    assert manager.active.lifecycle == "PAUSED"
    await manager.shutdown()


@pytest.mark.anyio
async def test_protocol_probe_pauses_and_redacts_operational_state(manager, runtime_db):
    with Session(runtime_db) as db:
        prepared = await manager.prepare(request(runtime_db), db)
    await manager.start(prepared.id, "PRACTICE", prepared.controller_lease)

    # Practice ISA is scheduled at 150 s. One-shot ticks keep the test fully
    # deterministic and avoid depending on wall-clock scheduling.
    while manager.active is not None and manager.active.protocol is not None and manager.active.protocol.active_probe is None:
        await manager.tick_once()
    assert manager.active is not None and manager.active.protocol is not None
    assert manager.active.protocol.phase.value == "ISA_ACTIVE"
    isa = manager.active.protocol.active_probe
    assert isa is not None and isa.probe_id
    isa_result = await manager.submit(
        prepared.id,
        prepared.controller_lease,
        CommandRequest(
            command_id=uuid4(), expected_state_version=manager.active.engine.snapshot()["state_version"],
            kind="SUBMIT_ISA", payload={"probe_id": isa.probe_id, "rating": 5},
        ),
    )
    assert isa_result.status.value == "accepted"

    while manager.active.protocol.active_probe is None:
        await manager.tick_once()
    sagat = manager.active.protocol.active_probe
    assert sagat is not None and sagat.kind == "SAGAT"
    state = await manager.state(prepared.id)
    assert "aircraft" not in state
    assert "truth" not in str(state)
    assert "correct_answer" not in str(sagat.public_payload)

    while manager.active.protocol.active_probe is not None:
        current = manager.active.protocol.active_probe
        assert current.probe_id
        result = await manager.submit(
            prepared.id,
            prepared.controller_lease,
            CommandRequest(
                command_id=uuid4(), expected_state_version=manager.active.engine.snapshot()["state_version"],
                kind="SUBMIT_SAGAT", payload={"probe_id": current.probe_id, "answer": "Unknown"},
            ),
        )
        assert result.status.value == "accepted"
    assert manager.active.lifecycle == "RUNNING"
    await manager.shutdown()


@pytest.mark.anyio
async def test_repeated_pause_reconnect_and_checkpoint_recovery_cycles(manager, runtime_db):
    """Repeated operator/controller failures do not leak tasks or state."""

    with Session(runtime_db) as db:
        prepared = await manager.prepare(request(runtime_db), db)
    await manager.start(prepared.id, "PRACTICE", prepared.controller_lease)

    for _ in range(25):
        # One checkpoint is emitted at each 5-second simulation boundary.
        for _ in range(50):
            await manager.tick_once()
        handle = manager.active
        assert handle is not None
        checkpoint_paths = sorted(handle.recorder.checkpoints_dir.glob("checkpoint-*.json.gz"))
        assert checkpoint_paths
        checkpoint_version = int(checkpoint_paths[-1].name.split("-")[-1].split(".")[0])

        await manager.pause(prepared.id, prepared.controller_lease, reason="cycle_pause")
        await manager.resume(prepared.id, prepared.controller_lease)
        await manager.controller_connected(prepared.id, prepared.controller_lease)
        await manager.controller_stream_established(prepared.id, prepared.controller_lease)
        await manager.controller_disconnected(prepared.id, prepared.controller_lease)
        assert manager.active.lifecycle == "PAUSED"

        await manager._interrupt(handle, "cycle_interruption", {"reason": "cycle"})  # noqa: SLF001
        recovered = await manager.recover(
            prepared.id, prepared.controller_lease, checkpoint_version,
        )
        assert recovered.lifecycle == "PAUSED"
        assert recovered.console_profile == prepared.console_profile
        await manager.resume(prepared.id, prepared.controller_lease)
        assert manager.active.lifecycle == "RUNNING"

    await manager.finish(prepared.id, prepared.controller_lease, "abort")
    await manager.shutdown()

@pytest.mark.anyio
async def test_presentation_readiness_failure_and_authoritative_state(manager, runtime_db):
    from app.simulation_schemas import PresentationConfig, PresentationEvent
    from app.simulation_runtime import InvalidTransition
    from matb_integration.suas.presentation.packages import catalog
    from matb_integration.suas.engine.runtime import SimulationEngine
    scene = catalog()[0]
    config = PresentationConfig(blocks={"PRACTICE": "3d"}, scene_id=scene["id"], scene_sha256=scene["sha256"])
    with Session(runtime_db) as db:
        prepared = await manager.prepare(request(runtime_db, presentation=config.model_dump(mode="json")), db)
    assert prepared.presentation == config
    with pytest.raises(InvalidTransition, match="presentation_not_ready"):
        await manager.start(prepared.id, "PRACTICE", prepared.controller_lease)
    ready = PresentationEvent(event_id=uuid4(), block_id="PRACTICE", kind="ready", scene_sha256=scene["sha256"])
    with pytest.raises(InvalidLease):
        await manager.presentation_event(prepared.id, "observer", ready)
    await manager.presentation_event(prepared.id, prepared.controller_lease, ready)
    await manager.presentation_event(prepared.id, prepared.controller_lease, ready)
    assert len((manager.active.recorder.run_dir / "presentation.jsonl").read_text().splitlines()) == 1
    await manager.start(prepared.id, "PRACTICE", prepared.controller_lease)
    baseline = SimulationEngine(manager.active.scenario.definition, "PRACTICE")
    await manager.tick_once()
    baseline.step()
    assert manager.active.engine.state_hash == baseline.state_hash
    assert (await manager.state(prepared.id))["aircraft"]["UAS-01"]["altitude_mm"] > 0
    failure = PresentationEvent(event_id=uuid4(), block_id="PRACTICE", kind="failure")
    await manager.presentation_event(prepared.id, prepared.controller_lease, failure)
    assert manager.active.lifecycle == "PAUSED"
    assert manager.active.validity == "valid_with_deviation"
    with pytest.raises(InvalidTransition, match="presentation_not_ready"):
        await manager.resume(prepared.id, prepared.controller_lease)
    with pytest.raises(InvalidTransition, match="locked"):
        await manager.presentation_event(prepared.id, prepared.controller_lease, PresentationEvent(event_id=uuid4(), block_id="PRACTICE", kind="fallback"))
    await manager.presentation_event(prepared.id, prepared.controller_lease, ready.model_copy(update={"event_id": uuid4()}))
    await manager.resume(prepared.id, prepared.controller_lease)
    assert manager.active.engine.state_hash == baseline.state_hash
    await manager.finish(prepared.id, prepared.controller_lease, "abort")
    from tests.station_fixtures import close_and_drain
    await close_and_drain(runtime_db)
    assert "presentation.jsonl" in (manager.active.recorder.run_dir / "checksums.sha256").read_text()
    with pytest.raises(InvalidTransition, match="sealed"):
        await manager.presentation_event(prepared.id, prepared.controller_lease, failure)
    await manager.shutdown()


def test_presentation_config_requires_pinned_scene():
    from app.simulation_schemas import PresentationConfig
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        PresentationConfig(blocks={"LOW": "3d"})


def test_scene_corruption_rejected(tmp_path, monkeypatch):
    import shutil
    from matb_integration.suas.presentation import packages
    source = packages.package_root() / "villavicencio-v1"
    shutil.copytree(source, tmp_path / source.name)
    monkeypatch.setattr(packages, "package_root", lambda: tmp_path)
    assert len(packages.catalog()) == 1
    (tmp_path / source.name / "elevation.json").write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        packages.read_package(source.name)
    assert packages.catalog() == []

@pytest.mark.anyio
async def test_traffic_research_rejects_live_and_recording_requires_duration(manager, runtime_db, monkeypatch):
    from app.simulation_schemas import PresentationConfig, TrafficConfig
    from matb_integration.suas.presentation.packages import catalog
    import app.traffic_service as service
    scene=catalog()[0]
    config=PresentationConfig(scene_id=scene['id'],scene_sha256=scene['sha256'],traffic=TrafficConfig(mode='live'))
    # Pure binding contract: authoring and launch use the same validator.
    # Invalid presentation overrides cannot be passed through a frozen assignment.
    from app.simulation_presentation_bindings import bind_presentation
    from matb_integration.suas.scenarios.loader import load_scenario
    loaded=load_scenario(manager.scenario_root/'reference_area_search.yaml')
    with pytest.raises(ValueError,match='recorded traffic'):
        bind_presentation({},config,loaded)
    config.traffic=TrafficConfig(mode='recorded',recording_id='short',recording_sha256='a'*64)
    monkeypatch.setattr(service,'load_recording',lambda *args:{'scene_id':scene['id'],'scene_sha256':scene['sha256'],'duration_ms':10,'provider':'adsb.lol'})
    with pytest.raises(ValueError,match='shorter'):
        bind_presentation({},config,loaded)

@pytest.mark.anyio
async def test_live_traffic_is_separate_paused_concealed_and_sealed(manager,runtime_db,monkeypatch):
    from app.simulation_schemas import CreateTechnicalSimulationSession,PresentationConfig,TrafficConfig
    from matb_integration.suas.presentation.packages import catalog
    from matb_integration.suas.recording.artifacts import verify_checksum_file
    import app.traffic_service as service
    scene=catalog()[0]
    async def snapshot(*args):
        return {'version':1,'provider':'adsb.lol','status':'live','sampled_at':1000,'tracks':[{'id':'a12345','callsign':'TEST','lat':scene['origin']['lat'],'lon':scene['origin']['lon'],'observed_at':1000,'received_at':1000,'geometric_altitude_m':6000,'barometric_altitude_m':5800,'speed_mps':80,'track_deg':90,'vertical_rate_mps':0,'on_ground':False,'age_s':0,'stale':False,'source':'adsb.lol'}]}
    monkeypatch.setattr(service.traffic_service,'snapshot',snapshot)
    config=PresentationConfig(scene_id=scene['id'],scene_sha256=scene['sha256'],traffic=TrafficConfig(mode='live'))
    with Session(runtime_db) as db:
        prepared=await manager.prepare_technical(CreateTechnicalSimulationSession(execution_purpose="practice", scenario_id='reference_area_search',block_id='LOW',locale='en',presentation=config),db)
    await manager.start(prepared.id,'LOW',prepared.controller_lease)
    before=manager.active.engine.state_hash
    await manager.traffic_once()
    assert manager.active.engine.state_hash==before
    file=manager.active.recorder.run_dir/'traffic.jsonl'
    first=file.read_bytes()
    assert manager.active.traffic_frame['tracks'][0]['position']=={'x_mm':6000000,'y_mm':4000000}
    await manager.pause(prepared.id,prepared.controller_lease)
    await manager.traffic_once();assert file.read_bytes()==first
    await manager.resume(prepared.id,prepared.controller_lease)
    await manager.traffic_once();assert manager.active.traffic_frame['discontinuity']
    # Protocol pauses cancel acquisition immediately, even before its next poll.
    async with manager._lock:
        await manager._pause_for_protocol_locked(manager.active, 'sagat_freeze')
        assert manager.active.traffic_discontinuity
        await manager._resume_after_protocol_locked(manager.active)
    await manager.traffic_once()
    assert manager.active.traffic_frame['discontinuity']
    # The protocol's public concealment property is authoritative for traffic too.
    from unittest.mock import patch,PropertyMock
    with patch.object(type(manager.active.protocol),'conceal_operational_state',new_callable=PropertyMock,return_value=True):
        previous=file.read_bytes();await manager.traffic_once();assert file.read_bytes()==previous
    await manager.finish(prepared.id,prepared.controller_lease,'abort')
    assert verify_checksum_file(manager.active.recorder.run_dir)==()
    assert 'traffic.jsonl' in (manager.active.recorder.run_dir/'checksums.sha256').read_text()
    await manager.traffic_once();assert manager.active.lifecycle=='ABORTED'

@pytest.mark.anyio
async def test_recorded_traffic_uses_simulation_time_and_embedded_source(manager,runtime_db,tmp_path,monkeypatch):
    import json,hashlib
    import app.traffic_service as service
    from app.simulation_schemas import CreateTechnicalSimulationSession,PresentationConfig,TrafficConfig
    from matb_integration.suas.presentation.packages import catalog
    scene=catalog()[0]
    base={'provider':'adsb.lol','status':'live','sampled_at':1000,'tracks':[{'id':'a12345','callsign':'TEST','lat':scene['origin']['lat'],'lon':scene['origin']['lon'],'observed_at':1000,'received_at':1000,'geometric_altitude_m':6000,'barometric_altitude_m':None,'speed_mps':80,'track_deg':90,'vertical_rate_mps':0,'on_ground':False,'age_s':0,'stale':False,'source':'adsb.lol'}]}
    source=tmp_path/'capture.json';raw=json.dumps({'version':1,'id':'test','title':'Test','scene_id':scene['id'],'scene_sha256':scene['sha256'],'duration_ms':600000,'provider':'adsb.lol','frames':[{**base,'simulation_time_ms':0},{**base,'simulation_time_ms':200,'tracks':[]}]}).encode();source.write_bytes(raw)
    monkeypatch.setattr(service,'recording_path',lambda identifier:source)
    config=PresentationConfig(scene_id=scene['id'],scene_sha256=scene['sha256'],traffic=TrafficConfig(mode='recorded',recording_id='test',recording_sha256=hashlib.sha256(raw).hexdigest()))
    with Session(runtime_db) as db:prepared=await manager.prepare_technical(CreateTechnicalSimulationSession(execution_purpose="practice", scenario_id='reference_area_search',block_id='LOW',locale='en',presentation=config),db)
    source.unlink() # The active run owns its verified immutable source.
    await manager.start(prepared.id,'LOW',prepared.controller_lease);await manager.traffic_once()
    assert len(manager.active.traffic_frame['tracks'])==1
    await manager.tick_once();await manager.traffic_once()
    assert manager.active.traffic_frame['tracks'][0]['age_s']==pytest.approx(.1)
    await manager.tick_once();await manager.traffic_once()
    assert manager.active.traffic_frame['tracks']==[]
    await manager.finish(prepared.id,prepared.controller_lease,'abort')
    assert 'traffic-source.json' in (manager.active.recorder.run_dir/'checksums.sha256').read_text()


def v2_exposure(scene, sequence=1, **patch):
    from app.simulation_schemas import PresentationEvent
    state = dict(version=2, condition="3d", camera="overview", focus=None,
                 aircraft_id=None, contact_id=None, observed_id=None,
                 operational_layers=dict(routes=True, coverage=True, contacts=True, sensors=True, labels=True),
                 geographic_layers=["roads", "rivers", "settlements", "boundaries", "airports"],
                 pose=None, map_view=dict(zoom=1, pan=dict(x=0, y=0)), viewport=None,
                 visibility="visible", transition_ms=0, visual_profile="standard-v1",
                 model_version="schematic-drone-v1-scale12", scene_sha256=scene["sha256"], capture_sha256=None)
    state.update(patch)
    return PresentationEvent(version=2, event_id=uuid4(), block_id="PRACTICE", kind="resolved",
                             sequence=sequence, client_time_ms=sequence * 100, scene_sha256=scene["sha256"], resolved=state)


@pytest.mark.anyio
async def test_v2_exposure_permissions_ordering_and_engine_equivalence(manager, runtime_db):
    from app.simulation_schemas import PresentationConfig
    from matb_integration.suas.presentation.packages import catalog
    from matb_integration.suas.engine.runtime import SimulationEngine
    scene = catalog()[0]
    config = PresentationConfig(version=2, blocks={"PRACTICE": "3d"}, scene_id=scene["id"], scene_sha256=scene["sha256"])
    with Session(runtime_db) as db:
        prepared = await manager.prepare(request(runtime_db, presentation=config.model_dump(mode="json")), db)
    lease = prepared.controller_lease
    ready = v2_exposure(scene).model_copy(update={"kind": "ready"})
    await manager.presentation_event(prepared.id, lease, ready)
    await manager.presentation_event(prepared.id, lease, ready)  # idempotent retry
    await manager.start(prepared.id, "PRACTICE", lease)
    baseline = SimulationEngine(manager.active.scenario.definition, "PRACTICE")
    await manager.tick_once()
    baseline.step()
    good = v2_exposure(scene, 2, aircraft_id="UAS-01", focus=dict(category="aircraft", id="UAS-01"))
    await manager.presentation_event(prepared.id, lease, good)
    assert manager.active.engine.state_hash == baseline.state_hash
    with pytest.raises(ValueError, match="sequence"):
        await manager.presentation_event(prepared.id, lease, v2_exposure(scene, 2))
    with pytest.raises(ValueError, match="locked"):
        await manager.presentation_event(prepared.id, lease, v2_exposure(scene, 3, operational_layers=dict(routes=False)))
    with pytest.raises(ValueError, match="assistance"):
        await manager.presentation_event(prepared.id, lease, v2_exposure(scene, 3, transition_ms=600))
    with pytest.raises(ValueError, match="permitted"):
        await manager.presentation_event(prepared.id, lease, v2_exposure(scene, 3, observed_id="UAS-01"))
    with pytest.raises(ValueError, match="asset"):
        await manager.presentation_event(prepared.id, lease, v2_exposure(scene, 3, scene_sha256="0" * 64))
    with pytest.raises(ValueError, match="navigation"):
        await manager.presentation_event(prepared.id, lease, v2_exposure(scene, 3).model_copy(update={"kind": "navigate"}))
    from app.simulation_schemas import PresentationEvent
    with pytest.raises(ValueError, match="v2 sessions"):
        await manager.presentation_event(prepared.id, lease, PresentationEvent(event_id=uuid4(), block_id="PRACTICE", kind="camera"))
    manager.active.presentation_ids.update(str(i) for i in range(20000))
    with pytest.raises(ValueError, match="limit"):
        await manager.presentation_event(prepared.id, lease, v2_exposure(scene, 3))
    assert manager.active.lifecycle == "PAUSED"
    assert "PRACTICE" not in manager.active.presentation_ready
    assert manager.active.engine.state_hash == baseline.state_hash
    await manager.shutdown()


def test_v2_strict_contract_and_legacy_reader():
    from app.simulation_schemas import PresentationEvent
    from pydantic import ValidationError
    assert PresentationEvent(event_id=uuid4(), block_id="LOW", kind="camera").version == 1
    with pytest.raises(ValidationError):
        PresentationEvent(event_id=uuid4(), block_id="LOW", kind="layers")
    with pytest.raises(ValidationError):
        PresentationEvent(version=2, event_id=uuid4(), block_id="LOW", kind="camera")
    with pytest.raises(ValidationError):
        v2_exposure(dict(sha256="0" * 64), pose=dict(camera_position=[float("nan"), 0, 0], camera_quaternion=[0, 0, 0, 1]))
    with pytest.raises(ValidationError):
        v2_exposure(dict(sha256="0" * 64), pose=dict(camera_position=[0, 0, 0], camera_quaternion=[0, 0, 0, 2]))

@pytest.mark.anyio
@pytest.mark.parametrize("technical", [False, True])
async def test_console_profile_frozen_without_optional_scene(manager, runtime_db, technical):
    import json
    from app.console_profile import current_console_profile
    from app.simulation_schemas import CreateTechnicalSimulationSession

    with Session(runtime_db) as db:
        prepared = (await manager.prepare_technical(CreateTechnicalSimulationSession(execution_purpose="practice",
            scenario_id="reference_area_search", block_id="LOW", locale="en"), db)
            if technical else await manager.prepare(request(runtime_db), db))
    expected = current_console_profile()
    assert prepared.console_profile.model_dump() == expected
    assert prepared.presentation is None
    handle = manager.active
    frozen = (handle.recorder.run_dir / "manifest.json").read_bytes()
    assert json.loads(frozen)["console_profile"] == expected
    assert manager._view(handle).console_profile.model_dump() == expected
    # Read paths neither bind current identity to historical runs nor replace
    # unknown recorded identity with the currently supported definition.
    handle.manifest.pop("console_profile")
    assert manager._view(handle).console_profile is None
    handle.manifest["console_profile"] = {**expected, "version": 99}
    assert manager._view(handle).console_profile.version == 99
    assert (handle.recorder.run_dir / "manifest.json").read_bytes() == frozen
    await manager.shutdown()


def test_console_profile_frontend_matches_frozen_definition():
    from app.console_profile import current_console_profile
    from hashlib import sha256
    root = Path(__file__).resolve().parents[3]
    artifact = root / "matb_integration/suas/presentation/console-profile.v1.json"
    expected = current_console_profile()
    assert expected["sha256"] == sha256(artifact.read_bytes()).hexdigest()
    frontend = (root / "webui/frontend/src/lib/simulation/console-profile.ts").read_text()
    assert f'id: "{expected["id"]}"' in frontend
    assert f'version: {expected["version"]}' in frontend
    assert f'sha256: "{expected["sha256"]}"' in frontend


@pytest.mark.anyio
async def test_mission_block_sources_keep_practice_separate(manager, runtime_db):
    from app.assessment_models import AssessmentAttempt, AssessmentSourceLink
    from app.simulation_models import SimulationBlock
    from sqlmodel import select
    with Session(runtime_db) as db:
        prepared = await manager.prepare(request(runtime_db), db)
        blocks = db.exec(select(SimulationBlock).where(SimulationBlock.session_id == prepared.id)).all()
        assert len(blocks) == 4
        for block in blocks:
            link = db.exec(select(AssessmentSourceLink).where(AssessmentSourceLink.source_table == 'simulation_block', AssessmentSourceLink.source_id == str(block.id))).one()
            attempt = db.get(AssessmentAttempt, link.attempt_id)
            assert attempt.execution_purpose == ('practice' if block.profile == 'PRACTICE' else 'study')
            assert attempt.purpose_provenance_id is not None
    await manager.shutdown()


@pytest.mark.anyio
async def test_swarm_v3_recording_group_commands_and_sealed_replay(manager, runtime_db):
    from app.simulation_schemas import CreateTechnicalSimulationSession, PresentationConfig, PresentationEvent
    from matb_integration.suas.presentation.packages import catalog
    from matb_integration.suas.recording.replay import ReplayVerifier
    scene = catalog()[0]
    config = PresentationConfig(version=3, blocks={"LOW": "3d"}, scene_id=scene["id"], scene_sha256=scene["sha256"], camera="swarm")
    with Session(runtime_db) as db:
        prepared = await manager.prepare_technical(CreateTechnicalSimulationSession(execution_purpose="practice", scenario_id="swarm_supervision", block_id="LOW", locale="en", presentation=config), db)
    lease = prepared.controller_lease
    base = v2_exposure(scene).model_dump(mode="json")
    base.update(version=3, kind="ready", block_id="LOW", camera="swarm")
    base["resolved"].update(version=3, camera="swarm", model_version="racing-quad-v1-scale80", group_id=None, inset=True)
    await manager.presentation_event(prepared.id, lease, PresentationEvent.model_validate(base))
    await manager.start(prepared.id, "LOW", lease)
    state = await manager.state(prepared.id)
    task = asyncio.create_task(manager.submit(prepared.id, lease, CommandRequest(command_id=uuid4(),expected_state_version=state["state_version"],kind="SWARM_TASK",payload={"group_id":"ALPHA","action":"SEARCH","target_id":"sector_alpha"})))
    await asyncio.sleep(0)
    await manager.tick_once()
    result = await task
    assert result.code == "accepted"
    for _ in range(5): await manager.tick_once()
    await manager.snapshot_once()
    assert manager.active.engine.snapshot()["swarms"]["ALPHA"]["command_count"] == 1
    await manager.finish(prepared.id,lease,"complete")
    replay=ReplayVerifier().verify(manager.active.recorder.run_dir)
    assert replay.status == "match", replay
    assert manager.active.manifest["engine_version"] == "2.0.0-swarm.1"


def test_v3_rejects_model_version_downgrade_and_missing_inset():
    from app.simulation_schemas import PresentationEvent
    from pydantic import ValidationError
    base=v2_exposure({"sha256":"a"*64}).model_dump(mode="json")
    base["resolved"]["model_version"]="racing-quad-v1-scale80"
    with pytest.raises(ValidationError): PresentationEvent.model_validate(base)
    base.update(version=3)
    base["resolved"].update(version=3,group_id=None,inset=False)
    with pytest.raises(ValidationError): PresentationEvent.model_validate(base)


def test_swarm_research_condition_is_explicit_and_versioned():
    from app.simulation_presentation_bindings import bind_presentation
    from app.simulation_schemas import PresentationConfig
    from matb_integration.suas.scenarios.loader import load_scenario
    root = Path(__file__).resolve().parents[3]
    loaded = load_scenario(root / "scenarios/suas/swarm_supervision.yaml")
    for config in (None, PresentationConfig(version=2)):
        with pytest.raises(ValueError, match="explicit v3"):
            bind_presentation({}, config, loaded)
    manifest = {}
    bind_presentation(manifest, PresentationConfig(version=3, camera="swarm"), loaded)
    assert manifest["presentation"]["version"] == 3
    assert manifest["swarm"] == {"algorithm": "fixed-slot-v1", "spacing_mm": 60000, "metrics": "swarm-descriptive-v1"}


@pytest.mark.anyio
async def test_swarm_research_webgl_failure_requires_requalification(manager, runtime_db):
    from app.simulation_schemas import PresentationConfig, PresentationEvent
    from app.simulation_runtime import InvalidTransition
    from matb_integration.suas.presentation.packages import catalog
    scene=catalog()[0]
    config=PresentationConfig(version=3,blocks={"PRACTICE":"3d"},scene_id=scene["id"],scene_sha256=scene["sha256"],camera="swarm")
    authored=mission_request(runtime_db,execution_purpose="study",participant_id="P01",visit_ordinal=1,scenario_id="swarm_supervision",locale="en",presentation=config.model_dump(mode="json"))
    with Session(runtime_db) as db: prepared=await manager.prepare(authored,db)
    lease=prepared.controller_lease
    base=v2_exposure(scene).model_dump(mode="json")
    base.update(version=3,kind="ready",block_id="PRACTICE",camera="swarm")
    base["resolved"].update(version=3,camera="swarm",model_version="racing-quad-v1-scale80",group_id=None,inset=True)
    await manager.presentation_event(prepared.id,lease,PresentationEvent.model_validate(base))
    await manager.start(prepared.id,"PRACTICE",lease)
    state=await manager.state(prepared.id)
    with pytest.raises(InvalidLease):
        await manager.submit(prepared.id,"observer",CommandRequest(command_id=uuid4(),expected_state_version=state["state_version"],kind="SWARM_TASK",payload={"group_id":"ALPHA","action":"HOLD","target_id":""}))
    base.update(event_id=str(uuid4()),sequence=base["sequence"]+1,kind="failure")
    base["resolved"]["visibility"]="unavailable"
    await manager.presentation_event(prepared.id,lease,PresentationEvent.model_validate(base))
    assert manager.active.lifecycle == "PAUSED"
    with pytest.raises(InvalidTransition,match="presentation_not_ready"):
        await manager.resume(prepared.id,lease)
    base.update(event_id=str(uuid4()),sequence=base["sequence"]+1,kind="ready")
    base["resolved"]["visibility"]="visible"
    await manager.presentation_event(prepared.id,lease,PresentationEvent.model_validate(base))
    await manager.resume(prepared.id,lease)
    assert manager.active.lifecycle == "RUNNING"
    await manager.shutdown()
