from __future__ import annotations

import json
from datetime import date

import pytest
from sqlmodel import Session, select

from app.ingestion import IngestionError, ingest_csv
from app.models import Block, Participant, Visit


def _participant_with_visits(engine):
    with Session(engine) as s:
        s.add(Participant(id="P01", enrollment_date=date(2026, 6, 1)))
        for ordinal, day in enumerate((0, 3, 6, 9, 12, 15), start=1):
            s.add(Visit(participant_id="P01", visit_ordinal=ordinal, scheduled_day=day))
        s.commit()


def test_ingest_stores_block_with_metrics(engine, sample_csv_bytes):
    _participant_with_visits(engine)
    with Session(engine) as s:
        block = ingest_csv(s, content=sample_csv_bytes(misses=(5.0, 25.0)),
                           filename="run1.csv", participant_id="P01",
                           visit_ordinal=1, workload_level="LOW")
        assert block.workload_level == "LOW"
        metrics = json.loads(block.metrics_json)
        assert metrics["sysmon"]["n_misses"] == 2


def test_duplicate_sha_rejected(engine, sample_csv_bytes):
    _participant_with_visits(engine)
    content = sample_csv_bytes()
    with Session(engine) as s:
        ingest_csv(s, content=content, filename="a.csv", participant_id="P01",
                   visit_ordinal=1, workload_level="LOW")
        with pytest.raises(IngestionError, match="already ingested"):
            ingest_csv(s, content=content, filename="b.csv", participant_id="P01",
                       visit_ordinal=2, workload_level="LOW")


def test_cross_cell_sha_collision_rejected_even_with_overwrite(engine, sample_csv_bytes):
    # The critical mislabel guard: a file already stored in one cell must never
    # be re-filed into a DIFFERENT cell, even with overwrite=True.
    _participant_with_visits(engine)
    content = sample_csv_bytes(misses=(5.0, 25.0))
    with Session(engine) as s:
        ingest_csv(s, content=content, filename="a.csv", participant_id="P01",
                   visit_ordinal=1, workload_level="LOW")
        with pytest.raises(IngestionError, match="already ingested"):
            ingest_csv(s, content=content, filename="a.csv", participant_id="P01",
                       visit_ordinal=2, workload_level="HIGH", overwrite=True)


def test_filled_cell_requires_overwrite(engine, sample_csv_bytes):
    _participant_with_visits(engine)
    with Session(engine) as s:
        ingest_csv(s, content=sample_csv_bytes(misses=(5.0,)), filename="a.csv",
                   participant_id="P01", visit_ordinal=1, workload_level="LOW")
        with pytest.raises(IngestionError, match="already filled"):
            ingest_csv(s, content=sample_csv_bytes(misses=(7.0,)), filename="c.csv",
                       participant_id="P01", visit_ordinal=1, workload_level="LOW")
        block = ingest_csv(s, content=sample_csv_bytes(misses=(9.0,)), filename="d.csv",
                           participant_id="P01", visit_ordinal=1, workload_level="LOW",
                           overwrite=True)
        assert json.loads(block.metrics_json)["sysmon"]["n_misses"] == 1


def test_unknown_visit_rejected(engine, sample_csv_bytes):
    _participant_with_visits(engine)
    with Session(engine) as s:
        with pytest.raises(IngestionError, match="no visit"):
            ingest_csv(s, content=sample_csv_bytes(), filename="a.csv",
                       participant_id="P01", visit_ordinal=99, workload_level="LOW")


def test_csv_without_sysmon_rejected(engine):
    _participant_with_visits(engine)
    empty = b"scenario_time,type,module,address,value\n900.0,event,foo,bar,baz\n"
    with Session(engine) as s:
        with pytest.raises(IngestionError, match="no usable"):
            ingest_csv(s, content=empty, filename="a.csv", participant_id="P01",
                       visit_ordinal=1, workload_level="LOW")
