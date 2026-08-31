from __future__ import annotations

import hashlib
import json
import csv
import io
from datetime import date

import pytest
from sqlmodel import Session, select

from app.ingestion import IngestionError, ingest_csv
from app.metrics_long import metric_metadata
from app.models import Block, BlockProvenance, Participant, Visit
from app.study_protocol import get_protocol


def _participant_with_visits(engine):
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


def test_ingest_stores_block_with_metrics(engine, sample_csv_bytes):
    _participant_with_visits(engine)
    with Session(engine) as s:
        block = ingest_csv(s, content=sample_csv_bytes(misses=(5.0, 25.0)),
                           filename="run1.csv", participant_id="P01",
                           visit_ordinal=1, workload_level="LOW")
        assert block.workload_level == "LOW"
        metrics = json.loads(block.metrics_json)
        assert metrics["sysmon"]["n_misses"] == 2
        assert metrics["participant_id"] == "P01"
        assert metrics["block_name"] == "block_1"
        assert metrics["csv_path"] == "run1.csv"


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
        prov = s.exec(select(BlockProvenance).where(BlockProvenance.block_id == block.id)).first()
        assert prov is not None
        assert prov.validation_status == "missing_manifest"


def test_unknown_visit_rejected(engine, sample_csv_bytes):
    _participant_with_visits(engine)
    with Session(engine) as s:
        with pytest.raises(IngestionError, match="no visit"):
            ingest_csv(s, content=sample_csv_bytes(), filename="a.csv",
                       participant_id="P01", visit_ordinal=99, workload_level="LOW")


def test_csv_without_sysmon_rejected(engine):
    _participant_with_visits(engine)
    empty = b"logtime,scenario_time,type,module,address,value\n900.0,900.0,event,foo,bar,baz\n"
    with Session(engine) as s:
        with pytest.raises(IngestionError, match="no usable"):
            ingest_csv(s, content=empty, filename="a.csv", participant_id="P01",
                       visit_ordinal=1, workload_level="LOW")


def test_malformed_csv_is_reported_as_controlled_ingestion_error(engine):
    _participant_with_visits(engine)
    malformed = (
        b"logtime,scenario_time,type,module,address,value\n"
        b"1,1,performance,sysmon,signal_detection,HIT,unexpected\n"
    )
    with Session(engine) as session:
        with pytest.raises(IngestionError, match="malformed CSV"):
            ingest_csv(
                session,
                content=malformed,
                filename="malformed.csv",
                participant_id="P01",
                visit_ordinal=1,
                workload_level="LOW",
            )


def test_ingest_stores_missing_manifest_warning(engine, sample_csv_bytes):
    _participant_with_visits(engine)
    with Session(engine) as s:
        block = ingest_csv(s, content=sample_csv_bytes(), filename="a.csv",
                           participant_id="P01", visit_ordinal=1, workload_level="LOW")
        prov = s.exec(select(BlockProvenance).where(BlockProvenance.block_id == block.id)).first()
        assert prov is not None
        assert prov.validation_status == "missing_manifest"
        issues = json.loads(prov.validation_issues_json)
        assert issues[0]["code"] == "missing_manifest"


def test_ingest_stores_manifest_validation_errors(engine, sample_csv_bytes):
    _participant_with_visits(engine)
    manifest = {
        "manifest_version": 1,
        "participant_id": "P02",
        "visit_ordinal": 2,
        "workload_level": "HIGH",
        "block_duration_sec": 900,
        "scenario": {"filename": "expected.txt", "sha256": "abc"},
        "questionnaires": {"include_nasatlx": True},
        "expected": {"isa_probe_times_sec": [90], "sagat_freezes": 0},
    }
    with Session(engine) as s:
        block = ingest_csv(
            s,
            content=sample_csv_bytes(),
            filename="a.csv",
            participant_id="P01",
            visit_ordinal=1,
            workload_level="LOW",
            manifest_content=json.dumps(manifest).encode("utf-8"),
            manifest_filename="expected.txt.manifest.json",
        )
        prov = s.exec(select(BlockProvenance).where(BlockProvenance.block_id == block.id)).first()
        assert prov is not None
        assert prov.validation_status == "error"
        codes = {i["code"] for i in json.loads(prov.validation_issues_json)}
        assert {"workload_mismatch", "participant_mismatch", "visit_mismatch"} <= codes


def _observed_opportunity_csv(
    scenario_sha256: str,
    *,
    manifest_content: bytes | None = None,
    evidence_updates: dict | None = None,
) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["logtime", "scenario_time", "type", "module", "address", "value"])
    writer.writerow([0, 0, "scenario_path", "", "", "bound.txt"])
    writer.writerow([0, 0, "scenario_sha256", "", "", scenario_sha256])
    if manifest_content is not None:
        manifest = json.loads(manifest_content)
        generated_by = manifest["generated_by"]
        evidence = {
            "schema_version": "1.0",
            "status": "verified",
            "scenario_sha256": scenario_sha256,
            "adjacent_manifest_filename": "bound.txt.manifest.json",
            "scenario_manifest_sha256": hashlib.sha256(manifest_content).hexdigest(),
            "manifest_identity": {
                "manifest_schema_version": str(manifest["manifest_version"]),
                "metrics_schema_version": manifest["metrics_schema_version"],
                "experiment_spec_sha256": None,
                "experiment_seed": manifest["seed"],
                "scenario_compiler_id": generated_by["component"],
                "scenario_compiler_version": generated_by["version"],
                "manifest_source_commit": generated_by["source_commit"],
                "manifest_source_dirty": generated_by["source_dirty"],
                "manifest_provenance_status": generated_by["provenance_status"],
            },
        }
        evidence.update(evidence_updates or {})
        writer.writerow([
            0,
            0,
            "scenario_manifest_evidence",
            "",
            "",
            json.dumps(evidence, sort_keys=True),
        ])
    payloads = (
        {"opportunity_id": "t1", "phase": "opened", "target": True},
        {
            "opportunity_id": "t1",
            "phase": "closed",
            "target": True,
            "outcome": "HIT",
            "response_time_ms": 500.0,
        },
        {"opportunity_id": "n1", "phase": "opened", "target": False},
        {"opportunity_id": "n1", "phase": "closed", "target": False, "outcome": "CR"},
    )
    for index, payload in enumerate(payloads, 1):
        writer.writerow([index, index, "performance", "sysmon", "opportunity", json.dumps(payload)])
    writer.writerow([4, 4, "performance", "sysmon", "signal_detection", "HIT"])
    return output.getvalue().encode("utf-8")


def _bound_manifest(scenario_sha256: str, **updates) -> bytes:
    manifest = {
        "manifest_version": 3,
        "metrics_schema_version": "2.0",
        "generated_by": {
            "component": "matb_integration.scenario_builder",
            "version": "3.0.0",
            "source_commit": "c" * 40,
            "source_dirty": False,
            "provenance_status": "complete",
        },
        "artifact_scope": "session_bound",
        "workload_label_status": "engineering_preset_pending_human_calibration",
        "seed": 42,
        "participant_id": "P01",
        "visit_ordinal": 1,
        "workload_level": "LOW",
        "block_duration_sec": 4,
        "scenario": {"filename": "bound.txt", "sha256": scenario_sha256},
        "questionnaires": {
            "isa": "isa_en.txt",
            "nasatlx": "nasatlx_en.txt",
            "bedford": "bedford_en.txt",
            "include_nasatlx": False,
            "include_bedford": False,
        },
        "expected": {
            "sysmon_target_opportunities": 1,
            "sysmon_nontarget_opportunities": 1,
            "comm_events": 0,
            "isa_probe_times_sec": [],
            "sagat_freezes": 0,
        },
    }
    manifest.update(updates)
    return json.dumps(manifest).encode("utf-8")


def test_confirmatory_dprime_requires_valid_manifest_and_matching_runtime_scenario_hash(engine):
    _participant_with_visits(engine)
    scenario_sha256 = "a" * 64
    manifest = _bound_manifest(scenario_sha256)
    with Session(engine) as s:
        block = ingest_csv(
            s,
            content=_observed_opportunity_csv(
                scenario_sha256, manifest_content=manifest
            ),
            filename="valid.csv",
            participant_id="P01",
            visit_ordinal=1,
            workload_level="LOW",
            manifest_content=manifest,
            manifest_filename="bound.txt.manifest.json",
        )
        metrics = json.loads(block.metrics_json)["sysmon"]
        provenance = s.exec(
            select(BlockProvenance).where(BlockProvenance.block_id == block.id)
        ).first()
        assert provenance is not None and provenance.validation_status == "ok"
        assert metrics["observed_opportunity_reconciled"] is True
        assert metrics["observed_confirmatory_eligible"] is False
        assert metrics["confirmatory_eligibility_basis"] == (
            "ineligible_until_authoritative_event_stream_reconciliation"
        )


def test_uploaded_manifest_without_runtime_evidence_cannot_upgrade_dprime(engine):
    _participant_with_visits(engine)
    scenario_sha256 = "a" * 64
    with Session(engine) as session:
        block = ingest_csv(
            session,
            content=_observed_opportunity_csv(scenario_sha256),
            filename="missing-runtime-evidence.csv",
            participant_id="P01",
            visit_ordinal=1,
            workload_level="LOW",
            manifest_content=_bound_manifest(scenario_sha256),
            manifest_filename="bound.txt.manifest.json",
        )
        provenance = session.exec(
            select(BlockProvenance).where(BlockProvenance.block_id == block.id)
        ).one()
        metrics = json.loads(block.metrics_json)["sysmon"]

        assert metrics["observed_confirmatory_eligible"] is False
        assert "missing_runtime_manifest_evidence" in {
            item["code"] for item in json.loads(provenance.validation_issues_json)
        }


def test_runtime_manifest_digest_mismatch_cannot_upgrade_dprime(engine):
    _participant_with_visits(engine)
    scenario_sha256 = "a" * 64
    manifest = _bound_manifest(scenario_sha256)
    content = _observed_opportunity_csv(
        scenario_sha256,
        manifest_content=manifest,
        evidence_updates={"scenario_manifest_sha256": "b" * 64},
    )
    with Session(engine) as session:
        block = ingest_csv(
            session,
            content=content,
            filename="wrong-runtime-digest.csv",
            participant_id="P01",
            visit_ordinal=1,
            workload_level="LOW",
            manifest_content=manifest,
            manifest_filename="bound.txt.manifest.json",
        )
        provenance = session.exec(
            select(BlockProvenance).where(BlockProvenance.block_id == block.id)
        ).one()
        metrics = json.loads(block.metrics_json)["sysmon"]

        assert metrics["observed_confirmatory_eligible"] is False
        assert "runtime_manifest_digest_mismatch" in {
            item["code"] for item in json.loads(provenance.validation_issues_json)
        }


def test_omitted_v3_questionnaire_plan_cannot_upgrade_complete_scale_metrics(engine):
    _participant_with_visits(engine)
    scenario_sha256 = "a" * 64
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(
        [
            [4, 4, "performance", "genericscales", "Mental demand", 6],
            [4, 4, "performance", "genericscales", "Physical demand", 6],
            [4, 4, "performance", "genericscales", "Temporal demand", 6],
            [4, 4, "performance", "genericscales", "Performance", 6],
            [4, 4, "performance", "genericscales", "Effort", 6],
            [4, 4, "performance", "genericscales", "Frustration", 6],
            [4, 4, "performance", "genericscales", "Bedford", 4],
        ]
    )
    content = _observed_opportunity_csv(scenario_sha256) + output.getvalue().encode()
    manifest = json.loads(_bound_manifest(scenario_sha256))
    manifest["questionnaires"] = {}
    manifest["expected"].pop("isa_probe_times_sec")
    manifest["expected"].pop("sagat_freezes")

    with Session(engine) as session:
        block = ingest_csv(
            session,
            content=content,
            filename="omitted-plan.csv",
            participant_id="P01",
            visit_ordinal=1,
            workload_level="LOW",
            manifest_content=json.dumps(manifest).encode(),
            manifest_filename="bound.txt.manifest.json",
        )
        provenance = session.exec(
            select(BlockProvenance).where(BlockProvenance.block_id == block.id)
        ).first()
        record = json.loads(block.metrics_json)

        assert provenance is not None and provenance.validation_status == "error"
        codes = {
            item["code"] for item in json.loads(provenance.validation_issues_json)
        }
        assert {"incomplete_questionnaire_plan", "incomplete_expected_plan"} <= codes
        assert record["nasatlx"]["rtlx_mean_0_100"] is not None
        assert record["bedford"]["value"] == 4
        assert metric_metadata(
            "nasatlx_rtlx_mean_0_100",
            record,
            provenance_validation_status=provenance.validation_status,
        )["confirmatory_eligible"] is False
        assert metric_metadata(
            "bedford",
            record,
            provenance_validation_status=provenance.validation_status,
        )["confirmatory_eligible"] is False


@pytest.mark.parametrize("metrics_schema_version", [None, "1.0", "3.0"])
def test_confirmatory_dprime_rejects_missing_or_unsupported_metrics_schema(
    engine,
    metrics_schema_version,
):
    _participant_with_visits(engine)
    scenario_sha256 = "a" * 64
    updates = {"metrics_schema_version": metrics_schema_version}
    manifest = json.loads(_bound_manifest(scenario_sha256))
    if metrics_schema_version is None:
        manifest.pop("metrics_schema_version")
    else:
        manifest.update(updates)

    with Session(engine) as session:
        block = ingest_csv(
            session,
            content=_observed_opportunity_csv(scenario_sha256),
            filename="unsupported-schema.csv",
            participant_id="P01",
            visit_ordinal=1,
            workload_level="LOW",
            manifest_content=json.dumps(manifest).encode("utf-8"),
            manifest_filename="bound.txt.manifest.json",
        )
        metrics = json.loads(block.metrics_json)["sysmon"]
        provenance = session.exec(
            select(BlockProvenance).where(BlockProvenance.block_id == block.id)
        ).first()

        assert provenance is not None and provenance.validation_status == "error"
        assert metrics["observed_confirmatory_eligible"] is False


@pytest.mark.parametrize(
    "manifest",
    [
        _bound_manifest("a" * 64, workload_level="HIGH"),
        _bound_manifest("b" * 64),
    ],
)
def test_forged_matching_counts_cannot_upgrade_dprime_eligibility(engine, manifest: bytes):
    _participant_with_visits(engine)
    with Session(engine) as s:
        block = ingest_csv(
            s,
            content=_observed_opportunity_csv("a" * 64),
            filename="forged.csv",
            participant_id="P01",
            visit_ordinal=1,
            workload_level="LOW",
            manifest_content=manifest,
            manifest_filename="forged.manifest.json",
        )
        metrics = json.loads(block.metrics_json)["sysmon"]
        assert metrics["observed_opportunity_reconciled"] is True
        assert metrics["observed_confirmatory_eligible"] is False


def test_mixed_runtime_scenario_hashes_cannot_bind_a_manifest(engine):
    _participant_with_visits(engine)
    content = _observed_opportunity_csv("a" * 64).replace(
        b"0,0,scenario_sha256,,," + b"a" * 64 + b"\n",
        b"0,0,scenario_sha256,,," + b"a" * 64 + b"\n"
        + b"0,0,scenario_sha256,,," + b"b" * 64 + b"\n",
    )
    with Session(engine) as s:
        block = ingest_csv(
            s,
            content=content,
            filename="mixed.csv",
            participant_id="P01",
            visit_ordinal=1,
            workload_level="LOW",
            manifest_content=_bound_manifest("a" * 64),
            manifest_filename="bound.manifest.json",
        )
        assert json.loads(block.metrics_json)["sysmon"]["observed_confirmatory_eligible"] is False
        provenance = s.exec(
            select(BlockProvenance).where(BlockProvenance.block_id == block.id)
        ).first()
        assert provenance is not None and provenance.validation_status == "error"
        assert "scenario_sha256_binding_ambiguous" in {
            issue["code"] for issue in json.loads(provenance.validation_issues_json)
        }


def test_nonfinite_manifest_json_is_stored_as_invalid_and_never_upgrades_metrics(
    engine, sample_csv_bytes
):
    _participant_with_visits(engine)
    manifest = _bound_manifest("a" * 64).replace(b'"block_duration_sec": 4', b'"block_duration_sec": NaN')
    with Session(engine) as s:
        block = ingest_csv(
            s,
            content=sample_csv_bytes(),
            filename="nonfinite.csv",
            participant_id="P01",
            visit_ordinal=1,
            workload_level="LOW",
            manifest_content=manifest,
            manifest_filename="nonfinite.manifest.json",
        )
        provenance = s.exec(
            select(BlockProvenance).where(BlockProvenance.block_id == block.id)
        ).first()

        assert provenance is not None
        assert provenance.validation_status == "invalid_manifest"
        assert json.loads(block.metrics_json)["sysmon"]["observed_confirmatory_eligible"] is False


def test_overwrite_commit_failure_rolls_back_block_and_provenance_atomically(
    engine, sample_csv_bytes, monkeypatch
):
    _participant_with_visits(engine)
    original_content = sample_csv_bytes(misses=(5.0,))
    replacement_content = sample_csv_bytes(misses=(7.0, 8.0))
    with Session(engine) as s:
        original = ingest_csv(
            s,
            content=original_content,
            filename="original.csv",
            participant_id="P01",
            visit_ordinal=1,
            workload_level="LOW",
        )
        original_id = original.id
        original_sha = original.source_csv_sha256

    with Session(engine) as s:
        def fail_commit() -> None:
            raise RuntimeError("simulated commit failure")

        monkeypatch.setattr(s, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="simulated commit failure"):
            ingest_csv(
                s,
                content=replacement_content,
                filename="replacement.csv",
                participant_id="P01",
                visit_ordinal=1,
                workload_level="LOW",
                overwrite=True,
            )

    with Session(engine) as s:
        blocks = s.exec(select(Block)).all()
        provenances = s.exec(select(BlockProvenance)).all()
        assert [(block.id, block.source_csv_sha256) for block in blocks] == [
            (original_id, original_sha)
        ]
        assert len(provenances) == 1
        assert provenances[0].block_id == original_id
