"""Statistics-engine endpoints. The engine itself lives in
matb_integration.analysis.stats (paper-first); this router only collects rows,
caches by input fingerprint, and persists artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
import uuid
from datetime import datetime, timezone
from time import monotonic
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db import get_session
from app.models import AnalysisResult
from app.routers.fits import collect_fit_rows
from app.routers.metrics import collect_metric_rows

router = APIRouter(tags=["analysis"])

_BAYES_MAX_ACTIVE_JOBS = 1
_BAYES_MAX_TOTAL_DRAWS = 20_000
_BAYES_SHUTDOWN_DRAIN_SECONDS = 30.0
_ANALYSIS_JOB_LOCK = threading.RLock()
_BAYES_JOB_LOCK = threading.RLock()
_BAYES_CAPACITY = threading.BoundedSemaphore(_BAYES_MAX_ACTIVE_JOBS)
_BAYES_THREADS: dict[int, threading.Thread] = {}
_BAYES_GENERATION = 0
_BAYES_PROCESS_OWNER = uuid.uuid4().hex
_BAYES_OWNER_PID = os.getpid()
_BACKEND_LEASE_NAME = "research-console"


def _current_bayes_process_owner() -> str:
    """Return a token that changes after a preloaded process forks."""

    global _BAYES_OWNER_PID, _BAYES_PROCESS_OWNER
    current_pid = os.getpid()
    if current_pid != _BAYES_OWNER_PID:
        _BAYES_OWNER_PID = current_pid
        _BAYES_PROCESS_OWNER = uuid.uuid4().hex
    return _BAYES_PROCESS_OWNER


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_backend_instance_lease(
    engine: Any,
    *,
    owner_token: str | None = None,
    owner_pid: int | None = None,
    owner_host: str | None = None,
) -> None:
    """Atomically admit one backend process for a SQLite research database."""

    owner_token = owner_token or _current_bayes_process_owner()
    pid = os.getpid() if owner_pid is None else owner_pid
    host = socket.gethostname() if owner_host is None else owner_host
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS matb_backend_instance_lease (
                lease_name VARCHAR PRIMARY KEY,
                owner_token VARCHAR NOT NULL,
                owner_pid INTEGER NOT NULL,
                owner_host VARCHAR NOT NULL,
                acquired_at DATETIME NOT NULL
            )
        """))
        connection.execute(text("""
            INSERT OR IGNORE INTO matb_backend_instance_lease (
                lease_name, owner_token, owner_pid, owner_host, acquired_at
            ) VALUES (
                :lease_name, :owner_token, :owner_pid, :owner_host, CURRENT_TIMESTAMP
            )
        """), {
            "lease_name": _BACKEND_LEASE_NAME,
            "owner_token": owner_token,
            "owner_pid": pid,
            "owner_host": host,
        })
        row = connection.execute(text("""
            SELECT owner_token, owner_pid, owner_host
            FROM matb_backend_instance_lease
            WHERE lease_name = :lease_name
        """), {"lease_name": _BACKEND_LEASE_NAME}).mappings().one()
        if row["owner_token"] == owner_token:
            return
        previous_is_live = (
            row["owner_host"] != host or _pid_is_alive(int(row["owner_pid"]))
        )
        if previous_is_live:
            raise RuntimeError(
                "another MATB backend instance owns this research database; "
                "run exactly one Uvicorn worker per MATB_DB_PATH"
            )
        result = connection.execute(text("""
            UPDATE matb_backend_instance_lease
            SET owner_token = :owner_token,
                owner_pid = :owner_pid,
                owner_host = :owner_host,
                acquired_at = CURRENT_TIMESTAMP
            WHERE lease_name = :lease_name
              AND owner_token = :previous_owner
        """), {
            "lease_name": _BACKEND_LEASE_NAME,
            "owner_token": owner_token,
            "owner_pid": pid,
            "owner_host": host,
            "previous_owner": row["owner_token"],
        })
        if result.rowcount != 1:
            raise RuntimeError("MATB backend lease changed during stale-owner recovery")


def release_backend_instance_lease(
    engine: Any, *, owner_token: str | None = None
) -> bool:
    """Release only the lease owned by this process."""

    owner_token = owner_token or _current_bayes_process_owner()
    with engine.begin() as connection:
        result = connection.execute(text("""
            DELETE FROM matb_backend_instance_lease
            WHERE lease_name = :lease_name AND owner_token = :owner_token
        """), {
            "lease_name": _BACKEND_LEASE_NAME,
            "owner_token": owner_token,
        })
        return result.rowcount == 1


def current_analysis_data_fingerprint(session: Session) -> str:
    """Fingerprint the exact rows consumed by both inference engines."""
    from matb_integration.analysis.stats import fingerprint

    return fingerprint(collect_metric_rows(session), collect_fit_rows(session))


def artifact_data_fingerprint(artifact: dict[str, Any]) -> str | None:
    provenance = artifact.get("provenance")
    if not isinstance(provenance, dict):
        return None
    value = provenance.get("fingerprint")
    return value if isinstance(value, str) else None


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _load_artifact_object(artifact_json: str | None) -> dict[str, Any]:
    """Parse persisted evidence using strict RFC-compatible JSON semantics."""

    try:
        artifact = json.loads(
            artifact_json or "", parse_constant=_reject_nonfinite_json
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "analysis_artifact_invalid_json"},
        ) from exc
    if not isinstance(artifact, dict):
        raise HTTPException(
            status_code=500,
            detail={"code": "analysis_artifact_invalid_json"},
        )
    return artifact


def _validated_cached_artifact(
    artifact_json: str | None,
    *,
    expected_data_fingerprint: str,
    version_field: str | None = None,
    expected_version: str | None = None,
) -> dict[str, Any]:
    artifact = _load_artifact_object(artifact_json)
    if artifact_data_fingerprint(artifact) != expected_data_fingerprint:
        raise HTTPException(
            status_code=500,
            detail={"code": "analysis_artifact_fingerprint_mismatch"},
        )
    if version_field is not None and artifact.get(version_field) != expected_version:
        raise HTTPException(
            status_code=500,
            detail={"code": "analysis_artifact_version_mismatch"},
        )
    return artifact


def _bayes_job_fingerprint(
    data_fingerprint: str,
    *,
    seed: int,
    draws: int,
    tune: int,
    chains: int,
) -> str:
    """Bind cached/active jobs to both data and every sampler parameter."""
    payload = json.dumps(
        {
            "data_fingerprint": data_fingerprint,
            "sampler": {
                "seed": seed,
                "draws": draws,
                "tune": tune,
                "chains": chains,
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validated_bayes_artifact(
    artifact_json: str | None,
    *,
    expected_data_fingerprint: str | None,
    expected_bayes_version: str,
    expected_job_fingerprint: str,
    expected_sampler: dict[str, int] | None = None,
) -> dict[str, Any]:
    artifact = _load_artifact_object(artifact_json)
    data_fingerprint = artifact_data_fingerprint(artifact)
    if expected_data_fingerprint is not None and data_fingerprint != expected_data_fingerprint:
        raise HTTPException(
            status_code=500,
            detail={"code": "analysis_artifact_fingerprint_mismatch"},
        )
    if data_fingerprint is None:
        raise HTTPException(
            status_code=500,
            detail={"code": "analysis_artifact_fingerprint_mismatch"},
        )
    if artifact.get("bayes_version") != expected_bayes_version:
        raise HTTPException(
            status_code=500,
            detail={"code": "analysis_artifact_version_mismatch"},
        )
    sampler = artifact.get("sampler")
    sampler_keys = ("seed", "draws", "tune", "chains")
    if not isinstance(sampler, dict) or any(
        type(sampler.get(key)) is not int for key in sampler_keys
    ):
        raise HTTPException(
            status_code=500,
            detail={"code": "bayes_artifact_sampler_mismatch"},
        )
    observed_sampler = {key: sampler[key] for key in sampler_keys}
    if expected_sampler is not None and observed_sampler != expected_sampler:
        raise HTTPException(
            status_code=500,
            detail={"code": "bayes_artifact_sampler_mismatch"},
        )
    if _bayes_job_fingerprint(data_fingerprint, **observed_sampler) != expected_job_fingerprint:
        raise HTTPException(
            status_code=500,
            detail={"code": "bayes_artifact_job_fingerprint_mismatch"},
        )
    return artifact


@router.post("/analysis/run")
def run_analysis_endpoint(session: Session = Depends(get_session)) -> dict[str, Any]:
    from matb_integration.analysis.stats import ENGINE_VERSION, fingerprint, run_analysis

    with _ANALYSIS_JOB_LOCK:
        metric_rows = collect_metric_rows(session)
        fit_rows = collect_fit_rows(session)
        fp = fingerprint(metric_rows, fit_rows)
        existing = session.exec(
            select(AnalysisResult)
            .where(AnalysisResult.fingerprint == fp,
                   AnalysisResult.engine_version == ENGINE_VERSION)
        ).first()
        if existing is not None:
            artifact = _validated_cached_artifact(
                existing.artifact_json,
                expected_data_fingerprint=fp,
                version_field="engine_version",
                expected_version=ENGINE_VERSION,
            )
            return {"cached": True, **artifact}
        artifact = run_analysis(
            metric_rows, fit_rows,
            created_utc=datetime.now(timezone.utc).isoformat())
        artifact_json = json.dumps(artifact, allow_nan=False)
        _validated_cached_artifact(
            artifact_json,
            expected_data_fingerprint=fp,
            version_field="engine_version",
            expected_version=ENGINE_VERSION,
        )
        session.add(AnalysisResult(
            fingerprint=fp,
            engine_version=ENGINE_VERSION,
            artifact_json=artifact_json,
        ))
        try:
            session.commit()
        except IntegrityError:
            # A unique-key winner in another process is authoritative. This is
            # still needed even though the in-process lock avoids duplicate fits
            # in one backend worker.
            session.rollback()
            concurrent = session.exec(
                select(AnalysisResult).where(
                    AnalysisResult.fingerprint == fp,
                    AnalysisResult.engine_version == ENGINE_VERSION,
                )
            ).first()
            if concurrent is None:
                raise
            concurrent_artifact = _validated_cached_artifact(
                concurrent.artifact_json,
                expected_data_fingerprint=fp,
                version_field="engine_version",
                expected_version=ENGINE_VERSION,
            )
            return {"cached": True, **concurrent_artifact}
        return {"cached": False, **artifact}


@router.get("/analysis/latest")
def latest_analysis(session: Session = Depends(get_session)) -> dict[str, Any]:
    from matb_integration.analysis.stats import ENGINE_VERSION

    current_fingerprint = current_analysis_data_fingerprint(session)
    row = session.exec(
        select(AnalysisResult)
        .where(
            AnalysisResult.fingerprint == current_fingerprint,
            AnalysisResult.engine_version == ENGINE_VERSION,
        )
        .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
    ).first()
    if row is not None:
        artifact = _validated_cached_artifact(
            row.artifact_json,
            expected_data_fingerprint=current_fingerprint,
            version_field="engine_version",
            expected_version=ENGINE_VERSION,
        )
        return {"cached": True, **artifact}

    previous = session.exec(
        select(AnalysisResult)
        .where(AnalysisResult.engine_version == ENGINE_VERSION)
        .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
    ).first()
    if previous is None:
        raise HTTPException(status_code=404, detail="no analysis has been run yet")
    raise HTTPException(
        status_code=409,
        detail={
            "code": "analysis_stale_for_current_data",
            "message": "Run the analysis again after the data change.",
            "current_data_fingerprint": current_fingerprint,
            "artifact_data_fingerprint": previous.fingerprint,
        },
    )


def _bayes_worker(engine, job_id: int, metric_rows, fit_rows,
                  seed: int, draws: int, tune: int, chains: int,
                  generation: int, attempt_count: int,
                  owner_token: str | None = None) -> None:
    from matb_integration.analysis.stats import fingerprint
    from matb_integration.analysis.stats.bayes import BAYES_VERSION, run_bayes

    from app.models import BayesResult as BR

    def _update_if_owned(
        *, expected_statuses: frozenset[str], **fields: Any
    ) -> bool:
        """Atomically validate process/attempt ownership and transition state."""

        with _BAYES_JOB_LOCK:
            if generation != _BAYES_GENERATION:
                return False
            with Session(engine) as s:
                row = s.get(BR, job_id)
                if (
                    row is None
                    or row.attempt_count != attempt_count
                    or row.owner_token != owner_token
                    or row.status not in expected_statuses
                ):
                    return False
                for key, value in fields.items():
                    setattr(row, key, value)
                s.add(row)
                s.commit()
                return True

    try:
        if not _update_if_owned(
            expected_statuses=frozenset({"queued"}), status="running"
        ):
            return
        artifact = run_bayes(metric_rows, fit_rows, seed=seed, draws=draws,
                             tune=tune, chains=chains,
                             created_utc=datetime.now(timezone.utc).isoformat())
        artifact_json = json.dumps(artifact, allow_nan=False)
        data_fingerprint = fingerprint(metric_rows, fit_rows)
        with Session(engine) as validation_session:
            cache_row = validation_session.get(BR, job_id)
            if cache_row is None:
                raise RuntimeError("Bayesian cache row disappeared during computation")
            cache_fingerprint = cache_row.fingerprint
            cache_version = cache_row.bayes_version
        if cache_version != BAYES_VERSION:
            raise RuntimeError("Bayesian cache row version does not match running engine")
        _validated_bayes_artifact(
            artifact_json,
            expected_data_fingerprint=data_fingerprint,
            expected_bayes_version=BAYES_VERSION,
            expected_job_fingerprint=cache_fingerprint,
            expected_sampler={
                "seed": seed, "draws": draws, "tune": tune, "chains": chains
            },
        )
        _update_if_owned(
            expected_statuses=frozenset({"running"}),
            status="done",
            artifact_json=artifact_json,
            finished_at=datetime.now(timezone.utc),
        )
    except Exception as e:  # noqa: BLE001 — job must record its own failure
        _update_if_owned(
            expected_statuses=frozenset({"queued", "running"}),
            status="failed",
            error=f"{type(e).__name__}: {e}"[:4096],
            finished_at=datetime.now(timezone.utc),
        )
    finally:
        with _BAYES_JOB_LOCK:
            if _BAYES_THREADS.get(job_id) is threading.current_thread():
                _BAYES_THREADS.pop(job_id, None)
            _BAYES_CAPACITY.release()


def _launch_bayes_worker(
    *,
    engine: Any,
    job_id: int,
    metric_rows: list[dict[str, Any]],
    fit_rows: list[dict[str, Any]],
    seed: int,
    draws: int,
    tune: int,
    chains: int,
    attempt_count: int,
) -> None:
    generation = _BAYES_GENERATION
    worker = threading.Thread(
        target=_bayes_worker,
        args=(
            engine,
            job_id,
            metric_rows,
            fit_rows,
            seed,
            draws,
            tune,
            chains,
            generation,
            attempt_count,
            _current_bayes_process_owner(),
        ),
        daemon=True,
        name=f"matb-bayes-{job_id}",
    )
    _BAYES_THREADS[job_id] = worker
    try:
        worker.start()
    except BaseException:
        if _BAYES_THREADS.get(job_id) is worker:
            _BAYES_THREADS.pop(job_id, None)
        raise


def reconcile_interrupted_bayes_jobs(engine: Any) -> int:
    """Fail closed on jobs whose owning backend process no longer exists."""
    global _BAYES_GENERATION

    with _BAYES_JOB_LOCK:
        live = [thread.name for thread in _BAYES_THREADS.values() if thread.is_alive()]
        if live:
            raise RuntimeError(
                "cannot reconcile Bayesian jobs while in-process workers are still active: "
                + ", ".join(sorted(live))
            )
        _BAYES_GENERATION += 1
        with Session(engine) as session:
            from app.models import BayesResult

            rows = session.exec(
                select(BayesResult).where(
                    BayesResult.status.in_(("queued", "running"))  # type: ignore[attr-defined]
                )
            ).all()
            finished_at = datetime.now(timezone.utc)
            for row in rows:
                row.status = "failed"
                row.error = "interrupted_by_backend_restart"
                row.finished_at = finished_at
                session.add(row)
            session.commit()
            return len(rows)


def shutdown_bayes_jobs(
    engine: Any, *, drain_timeout_s: float = _BAYES_SHUTDOWN_DRAIN_SECONDS
) -> int:
    """Invalidate jobs, then truthfully wait a bounded time for live compute."""
    global _BAYES_GENERATION

    if drain_timeout_s < 0:
        raise ValueError("drain_timeout_s must be non-negative")
    with _BAYES_JOB_LOCK:
        _BAYES_GENERATION += 1
        with Session(engine) as session:
            from app.models import BayesResult

            rows = session.exec(
                select(BayesResult).where(
                    BayesResult.status.in_(("queued", "running")),  # type: ignore[attr-defined]
                    BayesResult.owner_token == _current_bayes_process_owner(),
                )
            ).all()
            finished_at = datetime.now(timezone.utc)
            for row in rows:
                row.status = "failed"
                row.error = "interrupted_by_backend_shutdown"
                row.finished_at = finished_at
                session.add(row)
            session.commit()
            interrupted = len(rows)
        workers = tuple(_BAYES_THREADS.values())

    deadline = monotonic() + drain_timeout_s
    for worker in workers:
        remaining = max(0.0, deadline - monotonic())
        worker.join(timeout=remaining)
    with _BAYES_JOB_LOCK:
        live = [thread.name for thread in workers if thread.is_alive()]
    if live:
        raise RuntimeError(
            "Bayesian shutdown incomplete; workers still active after bounded drain: "
            + ", ".join(sorted(live))
        )
    return interrupted


@router.post("/analysis/bayes/run", status_code=202)
def run_bayes_endpoint(
    response: Response,
    seed: int = Query(default=20260604, ge=0, le=4_294_967_295),
    draws: int = Query(default=1000, ge=50, le=5000),
    tune: int = Query(default=1000, ge=50, le=5000),
    chains: int = Query(default=4, ge=2, le=8),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    from matb_integration.analysis.stats import fingerprint
    from matb_integration.analysis.stats.bayes import BAYES_VERSION

    from app.models import BayesResult

    if draws * chains > _BAYES_MAX_TOTAL_DRAWS or tune * chains > _BAYES_MAX_TOTAL_DRAWS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "bayes_sampler_budget_exceeded",
                "message": "draws*chains and tune*chains must each be at most 20000",
            },
        )

    metric_rows = collect_metric_rows(session)
    fit_rows = collect_fit_rows(session)
    data_fingerprint = fingerprint(metric_rows, fit_rows)
    fp = _bayes_job_fingerprint(
        data_fingerprint,
        seed=seed,
        draws=draws,
        tune=tune,
        chains=chains,
    )
    with _BAYES_JOB_LOCK:
        existing = session.exec(
            select(BayesResult).where(
                BayesResult.fingerprint == fp,
                BayesResult.bayes_version == BAYES_VERSION,
            )
        ).first()
        if existing is not None and existing.status == "done":
            artifact = _validated_bayes_artifact(
                existing.artifact_json,
                expected_data_fingerprint=data_fingerprint,
                expected_bayes_version=BAYES_VERSION,
                expected_job_fingerprint=fp,
                expected_sampler={
                    "seed": seed, "draws": draws, "tune": tune, "chains": chains
                },
            )
            response.status_code = 200
            return {
                "job_id": existing.id,
                "status": "done",
                "cached": True,
                "artifact": artifact,
            }
        if existing is not None and existing.status in {"queued", "running"}:
            response.status_code = 200
            return {
                "job_id": existing.id,
                "status": existing.status,
                "cached": False,
            }
        active_count = len(session.exec(
            select(BayesResult).where(
                BayesResult.status.in_(("queued", "running"))  # type: ignore[attr-defined]
            )
        ).all())
        if active_count >= _BAYES_MAX_ACTIVE_JOBS or not _BAYES_CAPACITY.acquire(
            blocking=False
        ):
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "bayes_capacity_exhausted",
                    "message": "A Bayesian job is already active on this workstation.",
                },
            )

        if existing is not None:
            try:
                history = json.loads(existing.error_history_json)
            except (TypeError, json.JSONDecodeError):
                history = []
            if not isinstance(history, list):
                history = []
            history.append({
                "attempt": existing.attempt_count,
                "error": existing.error,
                "finished_at": (
                    existing.finished_at.isoformat() if existing.finished_at else None
                ),
            })
            existing.status = "queued"
            existing.artifact_json = None
            existing.error = None
            existing.finished_at = None
            existing.attempt_count += 1
            existing.error_history_json = json.dumps(history, allow_nan=False)
            existing.last_attempt_at = datetime.now(timezone.utc)
            existing.owner_token = _current_bayes_process_owner()
            row = existing
            session.add(row)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                _BAYES_CAPACITY.release()
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": "bayes_capacity_exhausted",
                        "message": "A Bayesian job is already active on this workstation.",
                    },
                ) from exc
            session.refresh(row)
        else:
            row = BayesResult(
                fingerprint=fp,
                bayes_version=BAYES_VERSION,
                owner_token=_current_bayes_process_owner(),
            )
            try:
                session.add(row)
                session.commit()
                session.refresh(row)
            except IntegrityError:
                session.rollback()
                _BAYES_CAPACITY.release()
                concurrent = session.exec(
                    select(BayesResult).where(
                        BayesResult.fingerprint == fp,
                        BayesResult.bayes_version == BAYES_VERSION,
                    )
                ).first()
                if concurrent is None:
                    active = session.exec(
                        select(BayesResult).where(
                            BayesResult.status.in_(("queued", "running"))  # type: ignore[attr-defined]
                        )
                    ).first()
                    if active is not None:
                        raise HTTPException(
                            status_code=429,
                            detail={
                                "code": "bayes_capacity_exhausted",
                                "message": "A Bayesian job is already active on this workstation.",
                            },
                        )
                    raise
                response.status_code = 200
                if concurrent.status == "done":
                    artifact = _validated_bayes_artifact(
                        concurrent.artifact_json,
                        expected_data_fingerprint=data_fingerprint,
                        expected_bayes_version=BAYES_VERSION,
                        expected_job_fingerprint=fp,
                        expected_sampler={
                            "seed": seed,
                            "draws": draws,
                            "tune": tune,
                            "chains": chains,
                        },
                    )
                    return {
                        "job_id": concurrent.id,
                        "status": concurrent.status,
                        "cached": True,
                        "artifact": artifact,
                    }
                return {
                    "job_id": concurrent.id,
                    "status": concurrent.status,
                    "cached": concurrent.status == "done",
                }
        assert row.id is not None
        try:
            _launch_bayes_worker(
                engine=session.get_bind(),
                job_id=row.id,
                metric_rows=metric_rows,
                fit_rows=fit_rows,
                seed=seed,
                draws=draws,
                tune=tune,
                chains=chains,
                attempt_count=row.attempt_count,
            )
        except Exception as exc:
            _BAYES_CAPACITY.release()
            row.status = "failed"
            row.error = f"worker_start_failed: {type(exc).__name__}: {exc}"[:4096]
            row.finished_at = datetime.now(timezone.utc)
            session.add(row)
            session.commit()
            raise HTTPException(
                status_code=500,
                detail={"code": "bayes_worker_start_failed"},
            ) from exc
        return {"job_id": row.id, "status": "queued", "cached": False}


def _bayes_status_payload(row: Any, session: Session) -> dict[str, Any]:
    out: dict[str, Any] = {
        "job_id": row.id, "status": row.status, "error": row.error,
        "attempt_count": row.attempt_count,
        "created_at": row.created_at.isoformat(),
        "last_attempt_at": row.last_attempt_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }
    if row.status == "done" and row.artifact_json:
        from matb_integration.analysis.stats.bayes import BAYES_VERSION

        artifact = _validated_bayes_artifact(
            row.artifact_json,
            expected_data_fingerprint=None,
            expected_bayes_version=BAYES_VERSION,
            expected_job_fingerprint=row.fingerprint,
        )
        current_fingerprint = current_analysis_data_fingerprint(session)
        artifact_fingerprint = artifact_data_fingerprint(artifact)
        is_current = artifact_fingerprint == current_fingerprint
        out.update({
            "data_current": is_current,
            "artifact_status": "current" if is_current else "stale_artifact_omitted",
            "current_data_fingerprint": current_fingerprint,
            "artifact_data_fingerprint": artifact_fingerprint,
        })
        if is_current:
            out["artifact"] = artifact
    return out


@router.get("/analysis/bayes/status")
def bayes_status(session: Session = Depends(get_session)) -> dict[str, Any]:
    from app.models import BayesResult

    row = session.exec(
        select(BayesResult).order_by(
            BayesResult.last_attempt_at.desc(),  # type: ignore[arg-type]
            BayesResult.id.desc(),  # type: ignore[arg-type]
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="no Bayesian job yet")
    return _bayes_status_payload(row, session)


@router.get("/analysis/bayes/status/{job_id}")
def bayes_status_by_id(
    job_id: int, session: Session = Depends(get_session)
) -> dict[str, Any]:
    from app.models import BayesResult

    row = session.get(BayesResult, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Bayesian job not found")
    return _bayes_status_payload(row, session)
