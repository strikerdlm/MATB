"""Async Bayesian job lifecycle: queued -> running -> done; caching; status."""
from __future__ import annotations

import time


def _wait_done(client, timeout_s: float = 180.0  # first pymc import may hit a cold pytensor compile-lock under load) -> dict:
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
