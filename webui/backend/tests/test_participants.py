def test_create_participant_generates_six_visits(client):
    r = client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "P01"

    visits = client.get("/participants/P01/visits").json()
    assert [v["visit_ordinal"] for v in visits] == [1, 2, 3, 4, 5, 6]
    assert [v["scheduled_day"] for v in visits] == [0, 3, 6, 9, 12, 15]
    assert all(v["status"] == "planned" for v in visits)


def test_list_participants(client):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    client.post("/participants", json={"id": "P02", "enrollment_date": "2026-06-02"})
    ids = [p["id"] for p in client.get("/participants").json()]
    assert ids == ["P01", "P02"]


def test_duplicate_participant_rejected(client):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    r = client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    assert r.status_code == 409
