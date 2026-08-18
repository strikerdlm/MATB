from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from matb_integration.suhir.calibration import synth_tau
from app.ingestion import ingest_csv
from app.models import DepdfFit, Participant, Visit
from app.study_protocol import get_protocol

# Ground truth for a guaranteed-valid Suhir fit (mirrors the suhir pipeline test).
G0_TRUE, P0_TRUE, TAU0_TRUE = 40.0, 0.99, 12.0
LEVEL_MWL = {"LOW": 44.0, "MEDIUM": 60.0, "HIGH": 80.0}


def _enroll(engine):
    with Session(engine) as s:
        s.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        for definition in get_protocol("astra-2026").visits:
            s.add(
                Visit(
                    participant_id="P01",
                    visit_ordinal=definition.ordinal,
                    scheduled_day=definition.scheduled_day,
                )
            )
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


def test_fit_failure_does_not_break_ingestion(engine, sample_csv_bytes):
    # One level has SYSMON data (so it ingests) but NO NASA-TLX row, so its
    # raw_tlx is None. When the visit completes, fit_participant's MWL lookup
    # raises on the None -> the fit must be swallowed: all 3 Blocks stay
    # committed and no DepdfFit row is created.
    from app.models import Block

    no_tlx_csv = (
        b"scenario_time,type,module,address,value\n"
        b"5.0,performance,sysmon,signal_detection,MISS\n"
        b"25.0,performance,sysmon,signal_detection,MISS\n"
    )
    _enroll(engine)
    with Session(engine) as s:
        b1 = ingest_csv(s, content=sample_csv_bytes(misses=(5.0,), raw_tlx=44.0),
                        filename="LOW.csv", participant_id="P01",
                        visit_ordinal=1, workload_level="LOW")
        b2 = ingest_csv(s, content=sample_csv_bytes(misses=(5.0, 25.0), raw_tlx=60.0),
                        filename="MEDIUM.csv", participant_id="P01",
                        visit_ordinal=1, workload_level="MEDIUM")
        b3 = ingest_csv(s, content=no_tlx_csv, filename="HIGH.csv",
                        participant_id="P01", visit_ordinal=1, workload_level="HIGH")
        assert b1.id and b2.id and b3.id  # all ingested despite the doomed fit
        v = s.exec(select(Visit).where(Visit.visit_ordinal == 1)).first()
        assert len(s.exec(select(Block).where(Block.visit_id == v.id)).all()) == 3
        assert s.exec(select(DepdfFit)).first() is None  # fit failed, swallowed
