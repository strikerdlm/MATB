import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlmodel import Session

from app.openmatb_models import OpenMatbSuiteSession
from app.openmatb_runtime import OpenMatbRuntimeError
from app.openmatb_schemas import CreateOpenMatbSession
from tests.test_openmatb_runtime import _manager, _seed_visit

pytestmark = pytest.mark.anyio


def station(engine, tmp_path, monkeypatch):
    _seed_visit(engine)
    manager = _manager(engine, tmp_path)
    monkeypatch.setattr(manager, "readiness", lambda: SimpleNamespace(ready=True))
    monkeypatch.setattr(manager, "schedule_evidence_processing", lambda: None)
    processes = []

    class Process:
        def __init__(self):
            self.pid = 23456
            self.returncode = None
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self.stdin = self
            self.done = asyncio.Event()
            self.stdout.feed_data(b'{"event":"ready"}\n')

        def write(self, data):
            if b"abort" in data:
                self.terminate()

        async def drain(self):
            pass

        async def wait(self):
            await self.done.wait()
            return self.returncode

        def terminate(self):
            if self.returncode is None:
                self.returncode = 0
                self.stdout.feed_eof()
                self.stderr.feed_eof()
                self.done.set()

        kill = terminate

    async def spawn(*args, **kwargs):
        process = Process()
        processes.append(process)
        return process

    monkeypatch.setattr("app.openmatb_runtime.asyncio.create_subprocess_exec", spawn)
    monkeypatch.setattr("app.openmatb_runtime._WindowsJob", lambda _: None)
    monkeypatch.setattr("app.openmatb_runtime.os.killpg", lambda *_: processes[-1].terminate(), raising=False)
    return manager, processes


@pytest.mark.parametrize("acknowledged", [False, True])
async def test_ready_starts_once_without_controller_and_preserves_controller_authority(engine, tmp_path, monkeypatch, acknowledged):
    manager, processes = station(engine, tmp_path, monkeypatch)
    prepared = await manager.create_session(CreateOpenMatbSession(participant_id="P01", visit_ordinal=1, execution_purpose="practice"))
    if acknowledged:
        manager.acknowledge_instructions(prepared.session.id, prepared.participant_token)
    try:
        first, repeated = await asyncio.gather(
            manager.participant_ready(prepared.session.id, prepared.participant_token, 0),
            manager.participant_ready(prepared.session.id, prepared.participant_token, 0),
        )
        assert first[0].lifecycle == repeated[0].lifecycle == "RUNNING"
        assert first[1] is True and repeated[1] is False
        assert len(processes) == 1
        with pytest.raises(OpenMatbRuntimeError, match="invalid_lease"):
            await manager.abort(prepared.session.id, prepared.participant_token, "operator_abort")
    finally:
        await manager.abort(prepared.session.id, prepared.controller_lease, "operator_abort")
        await manager.shutdown()


async def test_ready_rejects_missing_authority_stale_blocks_and_saved_or_paused_states(engine, tmp_path, monkeypatch):
    manager, processes = station(engine, tmp_path, monkeypatch)
    prepared = await manager.create_session(CreateOpenMatbSession(participant_id="P01", visit_ordinal=1, execution_purpose="practice"))
    with pytest.raises(OpenMatbRuntimeError, match="invalid_participant_token"):
        await manager.participant_ready(prepared.session.id, "wrong", 0)
    with pytest.raises(OpenMatbRuntimeError, match="ready_block_changed"):
        await manager.participant_ready(prepared.session.id, prepared.participant_token, 1)
    assert manager.session_view(prepared.session.id).lifecycle == "INSTRUCTIONS"
    for lifecycle in ("AWAITING_SCALE", "COMPLETE", "ABORTED", "PAUSED"):
        with Session(engine) as db:
            row = db.get(OpenMatbSuiteSession, prepared.session.id)
            row.lifecycle = lifecycle
            db.add(row); db.commit()
        with pytest.raises(OpenMatbRuntimeError, match="invalid_transition"):
            await manager.participant_ready(prepared.session.id, prepared.participant_token, 0)
    assert not processes


async def test_ready_keeps_station_checks_and_frozen_study_admission(engine, tmp_path, monkeypatch):
    manager, processes = station(engine, tmp_path, monkeypatch)
    prepared = await manager.create_session(CreateOpenMatbSession(participant_id="P01", visit_ordinal=1, execution_purpose="practice"))
    monkeypatch.setattr(manager, "readiness", lambda: SimpleNamespace(ready=False))
    with pytest.raises(OpenMatbRuntimeError, match="station_not_ready"):
        await manager.participant_ready(prepared.session.id, prepared.participant_token, 0)
    monkeypatch.setattr(manager, "readiness", lambda: SimpleNamespace(ready=True))
    def blocked(*args):
        raise HTTPException(409, "Frozen study preparation is required")
    monkeypatch.setattr("app.study_admission.guard_source", blocked)
    with pytest.raises(HTTPException, match="Frozen study preparation"):
        await manager.participant_ready(prepared.session.id, prepared.participant_token, 0)
    assert not processes
