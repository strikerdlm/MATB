"""Async Bayesian job lifecycle: queued -> running -> done; caching; status."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import threading
import time

import pytest
from fastapi import Response
from sqlmodel import Session, SQLModel, create_engine, select

import app.routers.analysis as analysis_module
from app.models import BayesResult
from app.routers.analysis import (
    _BAYES_PROCESS_OWNER,
    _bayes_job_fingerprint,
    _next_bayes_attempt_at,
    acquire_backend_instance_lease,
    reconcile_interrupted_bayes_jobs,
    release_backend_instance_lease,
    shutdown_bayes_jobs,
)


# The worker's first `import pymc` may hit a cold/contended pytensor
# compile-lock under load — hence the generous poll timeout.
def _wait_done(client, timeout_s: float = 180.0) -> dict:
    body = None
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        body = client.get("/analysis/bayes/status").json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.2)
    raise AssertionError(f"job not finished in {timeout_s}s: {body}")


def test_bayes_status_404_before_any_job(client):
    assert client.get("/analysis/bayes/status").status_code == 404


def test_bayes_job_on_empty_db_completes(client):
    r = client.post("/analysis/bayes/run?draws=50&tune=50&chains=2")
    assert r.status_code == 202
    assert r.json()["status"] in ("queued", "running")
    body = _wait_done(client)
    assert body["status"] == "done"
    art = body["artifact"]
    assert art["bayes_version"]
    # empty DB -> every model gated out; nothing sampled
    assert all(v["status"] == "insufficient_data" for v in art["q2"].values())
    assert all(v["status"] == "insufficient_data" for v in art["q4"].values())


def test_bayes_cached_by_fingerprint(client):
    client.post("/analysis/bayes/run?draws=50&tune=50&chains=2")
    _wait_done(client)
    r = client.post("/analysis/bayes/run?draws=50&tune=50&chains=2")
    assert r.status_code == 200          # cached completed artifact, no new job
    assert r.json()["cached"] is True and r.json()["status"] == "done"


def test_bayes_cached_post_rejects_artifact_with_wrong_data_fingerprint(
    client, engine, monkeypatch
):
    from matb_integration.analysis.stats import fingerprint
    from matb_integration.analysis.stats.bayes import BAYES_VERSION

    monkeypatch.setattr(analysis_module, "collect_metric_rows", lambda _session: [])
    monkeypatch.setattr(analysis_module, "collect_fit_rows", lambda _session: [])
    data_fingerprint = fingerprint([], [])
    job_fingerprint = _bayes_job_fingerprint(
        data_fingerprint, seed=20260604, draws=50, tune=50, chains=2
    )
    with Session(engine) as session:
        session.add(BayesResult(
            fingerprint=job_fingerprint,
            bayes_version=BAYES_VERSION,
            status="done",
            artifact_json='{"provenance":{"fingerprint":"wrong"}}',
            owner_token="completed-owner",
        ))
        session.commit()

    response = client.post("/analysis/bayes/run?draws=50&tune=50&chains=2")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "analysis_artifact_fingerprint_mismatch"


@pytest.mark.parametrize(
    ("mutator", "code"),
    [
        (lambda artifact: artifact.update(bayes_version="0.0.0"),
         "analysis_artifact_version_mismatch"),
        (lambda artifact: artifact["sampler"].update(seed=999),
         "bayes_artifact_sampler_mismatch"),
    ],
)
def test_bayes_cache_rejects_wrong_version_or_sampler(
    client, engine, monkeypatch, mutator, code
):
    import json
    from matb_integration.analysis.stats import fingerprint
    from matb_integration.analysis.stats.bayes import BAYES_VERSION

    monkeypatch.setattr(analysis_module, "collect_metric_rows", lambda _session: [])
    monkeypatch.setattr(analysis_module, "collect_fit_rows", lambda _session: [])
    data_fingerprint = fingerprint([], [])
    sampler = {"seed": 20260604, "draws": 50, "tune": 50, "chains": 2}
    artifact = {
        "bayes_version": BAYES_VERSION,
        "sampler": dict(sampler),
        "provenance": {"fingerprint": data_fingerprint},
    }
    mutator(artifact)
    job_fingerprint = _bayes_job_fingerprint(data_fingerprint, **sampler)
    with Session(engine) as session:
        session.add(BayesResult(
            fingerprint=job_fingerprint,
            bayes_version=BAYES_VERSION,
            status="done",
            artifact_json=json.dumps(artifact, allow_nan=False),
            owner_token="completed-owner",
        ))
        session.commit()

    response = client.post("/analysis/bayes/run?draws=50&tune=50&chains=2")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == code


def test_bayes_cache_identity_includes_every_sampler_parameter():
    base = _bayes_job_fingerprint(
        "a" * 64, seed=1, draws=100, tune=100, chains=2
    )
    variants = {
        _bayes_job_fingerprint("a" * 64, seed=2, draws=100, tune=100, chains=2),
        _bayes_job_fingerprint("a" * 64, seed=1, draws=101, tune=100, chains=2),
        _bayes_job_fingerprint("a" * 64, seed=1, draws=100, tune=101, chains=2),
        _bayes_job_fingerprint("a" * 64, seed=1, draws=100, tune=100, chains=3),
    }
    assert base not in variants
    assert len(variants) == 4


def test_bayes_status_suppresses_completed_artifact_after_data_change(
    client, ingest_one_block
):
    client.post("/analysis/bayes/run?draws=50&tune=50&chains=2")
    completed = _wait_done(client)
    assert completed["data_current"] is True
    ingest_one_block(participant_id="P01", visit_ordinal=1, workload_level="LOW")

    response = client.get("/analysis/bayes/status")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["data_current"] is False
    assert body["artifact_status"] == "stale_artifact_omitted"
    assert "artifact" not in body


@pytest.mark.parametrize(
    "query",
    [
        "seed=-1",
        "seed=4294967296",
        "draws=49",
        "draws=5001",
        "tune=49",
        "tune=5001",
        "chains=0",
        "chains=1",
        "chains=9",
    ],
)
def test_bayes_sampler_parameters_are_strictly_bounded(client, query):
    response = client.post(f"/analysis/bayes/run?{query}")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"


def test_bayes_sampler_rejects_excessive_cross_parameter_budget(client):
    response = client.post("/analysis/bayes/run?draws=5000&tune=5000&chains=8")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "bayes_sampler_budget_exceeded"


def test_only_one_distinct_bayes_job_can_be_active(client, monkeypatch):
    launched: list[int] = []
    monkeypatch.setattr(
        analysis_module,
        "_launch_bayes_worker",
        lambda **kwargs: launched.append(kwargs["job_id"]),
    )

    first = client.post("/analysis/bayes/run?seed=1&draws=50&tune=50&chains=2")
    duplicate = client.post("/analysis/bayes/run?seed=1&draws=50&tune=50&chains=2")
    distinct = client.post("/analysis/bayes/run?seed=2&draws=50&tune=50&chains=2")

    assert first.status_code == 202
    assert duplicate.status_code == 200
    assert duplicate.json()["job_id"] == first.json()["job_id"]
    assert distinct.status_code == 429
    assert distinct.json()["detail"]["code"] == "bayes_capacity_exhausted"
    assert launched == [first.json()["job_id"]]
    # The fake launcher intentionally retained the real bounded slot. Restore
    # it so later tests cannot inherit artificial capacity exhaustion.
    analysis_module._BAYES_CAPACITY.release()


def test_concurrent_identical_requests_atomically_acquire_one_job(
    tmp_path, monkeypatch
):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'bayes-concurrent.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    launched: list[int] = []
    launch_lock = threading.Lock()

    def fake_launch(**kwargs):
        with launch_lock:
            launched.append(kwargs["job_id"])

    monkeypatch.setattr(analysis_module, "_launch_bayes_worker", fake_launch)
    barrier = threading.Barrier(2)

    def invoke() -> dict:
        with Session(engine) as session:
            barrier.wait()
            return analysis_module.run_bayes_endpoint(
                Response(status_code=202),
                seed=3,
                draws=50,
                tune=50,
                chains=2,
                session=session,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in (pool.submit(invoke), pool.submit(invoke))]

    assert results[0]["job_id"] == results[1]["job_id"]
    assert launched == [results[0]["job_id"]]
    with Session(engine) as session:
        assert len(session.exec(select(BayesResult)).all()) == 1
    analysis_module._BAYES_CAPACITY.release()


def test_database_schema_enforces_one_active_bayesian_job(engine):
    with Session(engine) as session:
        session.add(BayesResult(
            fingerprint="1" * 64,
            bayes_version="test",
            owner_token="owner-a",
        ))
        session.commit()
        session.add(BayesResult(
            fingerprint="2" * 64,
            bayes_version="test",
            owner_token="owner-b",
        ))
        with pytest.raises(Exception):
            session.commit()


def test_bayes_attempt_timestamp_advances_past_clock_collision(engine):
    fixed = datetime(2026, 9, 4, 3, 33, 59, tzinfo=timezone.utc)
    with Session(engine) as session:
        session.add(BayesResult(
            fingerprint="0" * 64,
            bayes_version="test",
            status="failed",
            last_attempt_at=fixed,
        ))
        session.commit()

        assert _next_bayes_attempt_at(session, observed_at=fixed) == (
            fixed + timedelta(microseconds=1)
        )


def test_backend_instance_lease_rejects_a_second_live_owner(engine):
    acquire_backend_instance_lease(
        engine,
        owner_token="first",
        owner_pid=analysis_module.os.getpid(),
        owner_host="test-host",
    )
    try:
        with pytest.raises(RuntimeError, match="another MATB backend instance"):
            acquire_backend_instance_lease(
                engine,
                owner_token="second",
                owner_pid=analysis_module.os.getpid(),
                owner_host="test-host",
            )
    finally:
        release_backend_instance_lease(engine, owner_token="first")


def test_backend_instance_lease_recovers_a_dead_local_owner(engine, monkeypatch):
    acquire_backend_instance_lease(
        engine,
        owner_token="dead-owner",
        owner_pid=987654321,
        owner_host="test-host",
    )
    monkeypatch.setattr(analysis_module, "_pid_is_alive", lambda _pid: False)

    acquire_backend_instance_lease(
        engine,
        owner_token="replacement",
        owner_pid=123,
        owner_host="test-host",
    )

    assert release_backend_instance_lease(engine, owner_token="replacement") is True


@pytest.mark.skipif(os.name != "nt", reason="Windows process API regression")
def test_pid_probe_does_not_signal_the_windows_console():
    assert analysis_module._pid_is_alive(os.getpid()) is True
    assert analysis_module._pid_is_alive(0xFFFFFFFF) is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX os.kill probe")
def test_pid_probe_treats_missing_posix_process_as_dead(monkeypatch):
    def raise_missing_process(_pid: int, _signal: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(analysis_module.os, "kill", raise_missing_process)
    assert analysis_module._pid_is_alive(987654321) is False


def test_worker_cannot_transition_a_job_owned_by_another_process(engine):
    with Session(engine) as session:
        row = BayesResult(
            fingerprint="9" * 64,
            bayes_version="test",
            owner_token="foreign-owner",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        assert row.id is not None
        job_id = row.id

    assert analysis_module._BAYES_CAPACITY.acquire(blocking=False)
    analysis_module._bayes_worker(
        engine,
        job_id,
        [],
        [],
        1,
        50,
        50,
        2,
        analysis_module._BAYES_GENERATION,
        1,
        _BAYES_PROCESS_OWNER,
    )

    with Session(engine) as session:
        row = session.get(BayesResult, job_id)
        assert row is not None
        assert row.status == "queued"
        assert row.owner_token == "foreign-owner"


def test_launch_failure_does_not_leave_a_phantom_worker(engine, monkeypatch):
    class FailingThread:
        def __init__(self, *args, **kwargs):
            del args
            self.name = kwargs["name"]

        def start(self):
            raise RuntimeError("thread start failed")

    monkeypatch.setattr(analysis_module.threading, "Thread", FailingThread)

    with pytest.raises(RuntimeError, match="thread start failed"):
        analysis_module._launch_bayes_worker(
            engine=engine,
            job_id=991,
            metric_rows=[],
            fit_rows=[],
            seed=1,
            draws=50,
            tune=50,
            chains=2,
            attempt_count=1,
        )

    assert 991 not in analysis_module._BAYES_THREADS


def test_bayes_worker_rejects_nonfinite_artifact_before_persistence(
    engine, monkeypatch
):
    import matb_integration.analysis.stats.bayes as bayes_module

    with Session(engine) as session:
        row = BayesResult(fingerprint="a" * 64, bayes_version="test")
        session.add(row)
        session.commit()
        session.refresh(row)
        assert row.id is not None
        job_id = row.id

    monkeypatch.setattr(
        bayes_module,
        "run_bayes",
        lambda *args, **kwargs: {"diagnostic": float("nan")},
    )
    assert analysis_module._BAYES_CAPACITY.acquire(blocking=False)
    analysis_module._bayes_worker(
        engine,
        job_id,
        [],
        [],
        1,
        50,
        50,
        2,
        analysis_module._BAYES_GENERATION,
        1,
    )

    with Session(engine) as session:
        persisted = session.get(BayesResult, job_id)
        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.artifact_json is None
        assert "Out of range float values" in (persisted.error or "")


@pytest.mark.parametrize(
    ("lifecycle", "reason"),
    [
        (reconcile_interrupted_bayes_jobs, "interrupted_by_backend_restart"),
        (shutdown_bayes_jobs, "interrupted_by_backend_shutdown"),
    ],
)
def test_bayes_lifecycle_marks_orphaned_jobs_failed(engine, lifecycle, reason):
    with Session(engine) as session:
        session.add(BayesResult(
            fingerprint="f" * 64,
            bayes_version="test",
            owner_token=_BAYES_PROCESS_OWNER,
        ))
        session.commit()

    assert lifecycle(engine) == 1

    with Session(engine) as session:
        row = session.exec(select(BayesResult)).one()
        assert row.status == "failed"
        assert row.error == reason
        assert row.finished_at is not None


def test_shutdown_cannot_be_reported_complete_while_compute_is_live(engine):
    release = threading.Event()
    worker = threading.Thread(target=release.wait, daemon=True)
    worker.start()
    analysis_module._BAYES_THREADS[-1] = worker
    try:
        with pytest.raises(RuntimeError, match="still active"):
            shutdown_bayes_jobs(engine, drain_timeout_s=0.0)
    finally:
        release.set()
        worker.join(timeout=1.0)
        analysis_module._BAYES_THREADS.pop(-1, None)


def test_shutdown_cannot_be_undone_by_a_stale_worker(engine, monkeypatch):
    import matb_integration.analysis.stats.bayes as bayes_module

    started = threading.Event()
    release = threading.Event()

    def blocked_run(*args, **kwargs):
        del args, kwargs
        started.set()
        assert release.wait(timeout=5.0)
        return {"provenance": {"fingerprint": "stale"}}

    monkeypatch.setattr(bayes_module, "run_bayes", blocked_run)
    with Session(engine) as session:
        row = BayesResult(
            fingerprint="b" * 64,
            bayes_version="test",
            owner_token=_BAYES_PROCESS_OWNER,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        assert row.id is not None
        job_id = row.id

    assert analysis_module._BAYES_CAPACITY.acquire(blocking=False)
    generation = analysis_module._BAYES_GENERATION
    worker = threading.Thread(
        target=analysis_module._bayes_worker,
        args=(
            engine, job_id, [], [], 1, 50, 50, 2, generation, 1,
            _BAYES_PROCESS_OWNER,
        ),
        daemon=True,
    )
    analysis_module._BAYES_THREADS[job_id] = worker
    worker.start()
    assert started.wait(timeout=2.0)

    with pytest.raises(RuntimeError, match="still active"):
        shutdown_bayes_jobs(engine, drain_timeout_s=0.0)

    release.set()
    worker.join(timeout=2.0)
    assert not worker.is_alive()
    with Session(engine) as session:
        persisted = session.get(BayesResult, job_id)
        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.error == "interrupted_by_backend_shutdown"
        assert persisted.artifact_json is None


def test_retry_is_visible_by_job_id_and_as_latest_attempt(client, engine, monkeypatch):
    launched: list[int] = []
    monkeypatch.setattr(
        analysis_module,
        "_launch_bayes_worker",
        lambda **kwargs: launched.append(kwargs["job_id"]),
    )

    first = client.post("/analysis/bayes/run?seed=11&draws=50&tune=50&chains=2")
    first_id = first.json()["job_id"]
    with Session(engine) as session:
        row = session.get(BayesResult, first_id)
        assert row is not None
        row.status = "failed"
        row.error = "first failure"
        session.add(row)
        session.commit()
    analysis_module._BAYES_CAPACITY.release()

    second = client.post("/analysis/bayes/run?seed=12&draws=50&tune=50&chains=2")
    second_id = second.json()["job_id"]
    assert second_id > first_id
    with Session(engine) as session:
        row = session.get(BayesResult, second_id)
        assert row is not None
        row.status = "failed"
        row.error = "second failure"
        session.add(row)
        session.commit()
    analysis_module._BAYES_CAPACITY.release()

    retried = client.post("/analysis/bayes/run?seed=11&draws=50&tune=50&chains=2")
    assert retried.json()["job_id"] == first_id
    assert client.get(f"/analysis/bayes/status/{first_id}").json()["status"] == "queued"
    assert client.get("/analysis/bayes/status").json()["job_id"] == first_id
    assert launched == [first_id, second_id, first_id]
    analysis_module._BAYES_CAPACITY.release()
