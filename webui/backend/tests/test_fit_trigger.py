from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from matb_integration.suhir.calibration import synth_tau
from app.ingestion import ingest_csv
from app.models import DepdfFit, Participant, Visit

# Ground truth for a guaranteed-valid Suhir fit (mirrors the suhir pipeline test).
G0_TRUE, P0_TRUE, TAU0_TRUE = 40.0, 0.99, 12.0
LEVEL_MWL = {"LOW": 44.0, "MEDIUM": 60.0, "HIGH": 80.0}


def _enroll(engine):
    with Session(engine) as s:
        s.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        for ordinal, day in enumerate((0, 3, 6, 9, 12, 15), start=1):
            s.add(Visit(participant_id="P01", visit_ordinal=ordinal, scheduled_day=day))
        s.commit()


def _misses_for(g: float) -> tuple[float, ...]:
    # MISS times spaced by synth_tau so failure_metrics MTTF == synth_tau(g),
    # which makes solve_g0 recover G0_TRUE exactly.
    tau = synth_tau(g, G0_TRUE, P0_TRUE, TAU0_TRUE)
    times, t = [], tau
    while t < 800.0:
        times.append(round(t, 3))
        t += tau
    return tuple(times)


def test_fit_created_when_three_levels_present(engine, sample_csv_bytes):
    _enroll(engine)
    with Session(engine) as s:
        for level, g in LEVEL_MWL.items():
            ingest_csv(s, content=sample_csv_bytes(misses=_misses_for(g), raw_tlx=g),
                       filename=f"{level}.csv", participant_id="P01",
                       visit_ordinal=1, workload_level=level)
        fit = s.exec(select(DepdfFit).where(DepdfFit.participant_id == "P01")).first()
        assert fit is not None
        assert fit.g0 == __import__("pytest").approx(G0_TRUE, rel=2e-2)
        assert 0.0 < fit.p0 <= 1.0
        assert fit.hcf_source == "F0_default"
        assert fit.mwl_source == "raw_tlx"


def test_no_fit_with_two_levels(engine, sample_csv_bytes):
    _enroll(engine)
    with Session(engine) as s:
        for level in ("LOW", "MEDIUM"):
            g = LEVEL_MWL[level]
            ingest_csv(s, content=sample_csv_bytes(misses=_misses_for(g), raw_tlx=g),
                       filename=f"{level}.csv", participant_id="P01",
                       visit_ordinal=1, workload_level=level)
        assert s.exec(select(DepdfFit)).first() is None
