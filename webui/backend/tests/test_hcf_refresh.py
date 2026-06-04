"""Screen ingest must refresh hcf_value on ALL existing DepdfFits; new fits
must pick up the screen HCF; /fits curves switch to Eq. 5.1."""
from __future__ import annotations

from sqlmodel import Session, select

from app.models import DepdfFit

from .test_fit_trigger import LEVEL_MWL, _misses_for
from .test_screen_endpoint import _enroll, _payload


def _fill_visit(client, sample_csv_bytes, pid, visit=1):
    _enroll(client, pid)
    for level, g in LEVEL_MWL.items():
        r = client.post(
            "/ingest",
            data={"participant_id": pid, "visit_ordinal": str(visit),
                  "workload_level": level},
            files={"file": (f"{pid}_{level}.csv",
                            sample_csv_bytes(misses=_misses_for(g), raw_tlx=g),
                            "text/csv")},
        )
        assert r.status_code == 201, r.text


def test_existing_fits_refresh_when_cohort_gate_crossed(client, engine,
                                                        sample_csv_bytes):
    _fill_visit(client, sample_csv_bytes, "P01")
    with Session(engine) as s:
        fit = s.exec(select(DepdfFit)).one()
        assert fit.hcf_source == "F0_default" and fit.hcf_value == 1.0
    # screens for P01..P03 crosses the >=3 gate; P01 is fastest -> F > 1
    for pid, simple in (("P01", 260.0), ("P02", 320.0), ("P03", 380.0)):
        _enroll(client, pid)
        client.post("/screen", json={"participant_id": pid,
                                     "payload": _payload(simple=simple)})
    with Session(engine) as s:
        fit = s.exec(select(DepdfFit)).one()
        assert fit.hcf_source == "screen" and fit.hcf_value > 1.0


def test_new_fit_uses_screen_hcf(client, engine, sample_csv_bytes):
    for pid, simple in (("P01", 260.0), ("P02", 320.0), ("P03", 380.0)):
        _enroll(client, pid)
        client.post("/screen", json={"participant_id": pid,
                                     "payload": _payload(simple=simple)})
    _fill_visit(client, sample_csv_bytes, "P03")
    with Session(engine) as s:
        fit = s.exec(select(DepdfFit)).one()
        assert fit.hcf_source == "screen" and fit.hcf_value < 1.0


def test_fits_endpoint_curve_uses_f(client, sample_csv_bytes):
    for pid, simple in (("P01", 260.0), ("P02", 320.0), ("P03", 380.0)):
        _enroll(client, pid)
        client.post("/screen", json={"participant_id": pid,
                                     "payload": _payload(simple=simple)})
    _fill_visit(client, sample_csv_bytes, "P01")
    fit = client.get("/fits").json()[0]
    assert fit["hcf_source"] == "screen"
    # P01's F > 1 -> inner exponent exp(1-f^2) < 1 -> curve DECAYS SLOWER than
    # the ordinary form: at r=3, p > p0*exp(1-9)
    p0 = fit["p0"]
    import math
    ordinary_at_3 = p0 * math.exp((1 - 9) * 1.0)
    assert fit["curve"][-1]["p"] > ordinary_at_3
    assert "hcf_value" in fit
