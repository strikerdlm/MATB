"""POST /analysis/run + GET /analysis/latest: caching by fingerprint, statuses."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

import app.routers.analysis as analysis_module
from app.models import AnalysisResult


def test_analysis_run_on_empty_db(client):
    r = client.post("/analysis/run")
    assert r.status_code == 200
    art = r.json()
    assert art["cached"] is False
    assert art["confirmatory"]["family_size_actual"] == 0
    assert all(v["status"] == "insufficient_data" for v in art["q1"].values())


def test_analysis_run_caches_by_fingerprint(client):
    first = client.post("/analysis/run").json()
    second = client.post("/analysis/run").json()
    assert first["cached"] is False and second["cached"] is True
    assert first["provenance"]["fingerprint"] == second["provenance"]["fingerprint"]


def test_analysis_latest(client):
    assert client.get("/analysis/latest").status_code == 404
    client.post("/analysis/run")
    r = client.get("/analysis/latest")
    assert r.status_code == 200
    assert r.json()["engine_version"]


def test_analysis_reruns_after_new_ingest(client, ingest_one_block):
    """Ingesting data changes the fingerprint -> a fresh (non-cached) run."""
    before = client.post("/analysis/run").json()
    ingest_one_block(participant_id="P01", visit_ordinal=1, workload_level="LOW")
    after = client.post("/analysis/run").json()
    assert after["cached"] is False
    assert after["provenance"]["fingerprint"] != before["provenance"]["fingerprint"]


def test_analysis_latest_rejects_artifact_for_previous_data(client, ingest_one_block):
    stale = client.post("/analysis/run").json()
    ingest_one_block(participant_id="P01", visit_ordinal=1, workload_level="LOW")

    response = client.get("/analysis/latest")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "analysis_stale_for_current_data"
    assert detail["artifact_data_fingerprint"] == stale["provenance"]["fingerprint"]
    assert detail["current_data_fingerprint"] != detail["artifact_data_fingerprint"]


def test_concurrent_identical_analysis_requests_persist_one_artifact(
    tmp_path, monkeypatch
):
    """The cache key remains atomic even when two requests start together."""

    import matb_integration.analysis.stats as stats_module

    engine = create_engine(
        f"sqlite:///{tmp_path / 'analysis-concurrent.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    calls = 0
    calls_lock = threading.Lock()

    def fake_run(metric_rows, fit_rows, *, created_utc):
        nonlocal calls
        del metric_rows, fit_rows
        with calls_lock:
            calls += 1
        return {
            "engine_version": stats_module.ENGINE_VERSION,
            "provenance": {
                "fingerprint": stats_module.fingerprint([], []),
                "created_utc": created_utc,
            },
        }

    monkeypatch.setattr(stats_module, "run_analysis", fake_run)
    barrier = threading.Barrier(2)

    def invoke() -> dict:
        with Session(engine) as session:
            barrier.wait()
            return analysis_module.run_analysis_endpoint(session=session)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in (pool.submit(invoke), pool.submit(invoke))]

    assert sorted(result["cached"] for result in results) == [False, True]
    assert calls == 1
    with Session(engine) as session:
        assert len(session.exec(select(AnalysisResult)).all()) == 1


def test_analysis_rejects_nonfinite_artifact_before_persistence(engine, monkeypatch):
    import matb_integration.analysis.stats as stats_module

    monkeypatch.setattr(
        stats_module,
        "run_analysis",
        lambda *args, **kwargs: {"diagnostic": float("nan")},
    )

    with Session(engine) as session, pytest.raises(
        ValueError, match="Out of range float values"
    ):
        analysis_module.run_analysis_endpoint(session=session)

    with Session(engine) as session:
        assert session.exec(select(AnalysisResult)).all() == []


def test_cached_analysis_post_rejects_artifact_with_wrong_data_fingerprint(
    client, engine, monkeypatch
):
    import matb_integration.analysis.stats as stats_module

    monkeypatch.setattr(analysis_module, "collect_metric_rows", lambda _session: [])
    monkeypatch.setattr(analysis_module, "collect_fit_rows", lambda _session: [])
    current = stats_module.fingerprint([], [])
    with Session(engine) as session:
        session.add(AnalysisResult(
            fingerprint=current,
            engine_version=stats_module.ENGINE_VERSION,
            artifact_json='{"provenance":{"fingerprint":"wrong"}}',
        ))
        session.commit()

    response = client.post("/analysis/run")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "analysis_artifact_fingerprint_mismatch"


@pytest.mark.parametrize(
    ("artifact_json", "code"),
    [
        (
            '{"engine_version":"0.0.0","provenance":{"fingerprint":"FP"}}',
            "analysis_artifact_version_mismatch",
        ),
        (
            '{"engine_version":"VERSION","provenance":{"fingerprint":"FP"},"x":NaN}',
            "analysis_artifact_invalid_json",
        ),
    ],
)
def test_frequentist_cache_rejects_wrong_engine_or_nonfinite_json(
    client, engine, monkeypatch, artifact_json, code
):
    import matb_integration.analysis.stats as stats_module

    monkeypatch.setattr(analysis_module, "collect_metric_rows", lambda _session: [])
    monkeypatch.setattr(analysis_module, "collect_fit_rows", lambda _session: [])
    current = stats_module.fingerprint([], [])
    artifact_json = artifact_json.replace("FP", current).replace(
        "VERSION", stats_module.ENGINE_VERSION
    )
    with Session(engine) as session:
        session.add(AnalysisResult(
            fingerprint=current,
            engine_version=stats_module.ENGINE_VERSION,
            artifact_json=artifact_json,
        ))
        session.commit()

    response = client.post("/analysis/run")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == code
