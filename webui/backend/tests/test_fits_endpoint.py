from __future__ import annotations

from datetime import date

from sqlmodel import Session

from app.models import DepdfFit, Participant, Visit


def _seed_fit(engine) -> None:
    with Session(engine) as s:
        s.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        v = Visit(participant_id="P01", visit_ordinal=2, scheduled_day=3)
        s.add(v)
        s.commit()
        s.refresh(v)
        s.add(DepdfFit(participant_id="P01", visit_id=v.id, mwl_source="raw_tlx",
                       g0=40.0, p0=0.99, tau0=12.0,
                       hcf_value=1.0, hcf_source="F0_default",
                       criteria_version=1, per_level_json="{}"))
        s.commit()


def test_fits_endpoint_returns_curve(client, engine):
    _seed_fit(engine)
    fits = client.get("/fits").json()
    assert len(fits) == 1
    f = fits[0]
    assert f["participant_id"] == "P01" and f["visit_ordinal"] == 2
    assert f["g0"] == 40.0 and f["p0"] == 0.99
    curve = f["curve"]
    assert len(curve) == 51
    assert curve[0]["r"] == 1.0
    assert abs(curve[0]["p"] - 0.99) < 1e-9        # P^h(G0) == p0
    ps = [pt["p"] for pt in curve]
    assert all(a > b for a, b in zip(ps, ps[1:]))   # strictly decreasing
    assert curve[-1]["r"] == 3.0


def test_fits_filter_by_participant(client, engine):
    _seed_fit(engine)
    assert client.get("/fits", params={"participant_id": "P01"}).json()
    assert client.get("/fits", params={"participant_id": "P99"}).json() == []
