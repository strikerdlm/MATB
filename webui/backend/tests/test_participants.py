def test_create_participant_generates_astra_visits(client):
    r = client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "P01"

    visits = client.get("/participants/P01/visits").json()
    assert [v["visit_ordinal"] for v in visits] == [1, 2, 3]
    assert [v["scheduled_day"] for v in visits] == [0, 8, 15]
    assert all(v["status"] == "planned" for v in visits)


def test_create_participant_rejects_id_that_other_research_workflows_cannot_use(client):
    response = client.post(
        "/participants",
        json={"id": "pilot-01", "enrollment_date": "2026-06-01"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_request"
    assert "body.id" in detail["context"]["fields"]


def test_list_participants(client):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    client.post("/participants", json={"id": "P02", "enrollment_date": "2026-06-02"})
    ids = [p["id"] for p in client.get("/participants").json()]
    assert ids == ["P01", "P02"]


def test_duplicate_participant_rejected(client):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    r = client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    assert r.status_code == 409


def test_participant_study_context_is_structured_and_immutable(client):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    payload = {
        "task_sequence": "MATB_LIFTOFF",
        "prior_fpv_hours": 12.5,
        "gaming_hours_per_week": 3.0,
    }

    first = client.put("/participants/P01/study-context", json=payload)

    assert first.status_code == 201
    assert {
        "participant_id": first.json()["participant_id"],
        "protocol_id": first.json()["protocol_id"],
        "task_sequence": first.json()["task_sequence"],
        "prior_fpv_hours": first.json()["prior_fpv_hours"],
        "gaming_hours_per_week": first.json()["gaming_hours_per_week"],
    } == {
        "participant_id": "P01",
        "protocol_id": "astra-2026",
        **payload,
    }
    assert client.get("/participants/P01/study-context").json() == first.json()

    second = client.put("/participants/P01/study-context", json=payload)
    assert second.status_code == 409


def test_participant_study_context_rejects_invalid_covariates(client):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})

    response = client.put(
        "/participants/P01/study-context",
        json={
            "task_sequence": "RANDOM",
            "prior_fpv_hours": -1,
            "gaming_hours_per_week": 3.0,
        },
    )

    assert response.status_code == 422
