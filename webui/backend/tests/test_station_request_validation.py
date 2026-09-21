"""Invalid deferred requests must not bypass endpoint validation or enter the queue."""
import pytest
from sqlmodel import Session, select

from app.station_resources import StationJob


@pytest.mark.parametrize("path", ["/study/analyses", "/study/analyses/preview", "/study/analyses/inputs"])
@pytest.mark.parametrize("body", [b"{", b"[]", b"null", b"{}", b'{"version_id": 42, "actor": "A", "reason": "test"}'])
def test_invalid_analysis_selection_is_rejected_before_queueing(client, engine, path, body):
    response = client.post(path, content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"
    assert response.headers["access-control-allow-origin"] == "http://localhost:3100"
    with Session(engine) as db:
        assert list(db.exec(select(StationJob))) == []


def test_queue_size_rejection_is_readable_by_the_browser(client):
    response = client.post("/analysis/run", content=b"x" * (65 * 1024))
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "station_queue_payload_too_large"
    assert response.headers["access-control-allow-origin"] == "http://localhost:3100"
