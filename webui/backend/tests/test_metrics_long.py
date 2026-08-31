from __future__ import annotations

from app.metrics_long import METRIC_KEYS, extract_long_metrics, metric_metadata


def test_extract_covers_all_metrics_and_omits_nulls():
    record = {
        "metrics_schema_version": "2.0",
        "sysmon": {
            "d_prime": 2.5,
            "dprime_estimated_v1": 2.5,
            "dprime_observed_v2": 2.1,
            "observed_confirmatory_eligible": True,
            "hit_rate": 0.9,
            "mean_rt_ms": None,
            "n_misses": 1,
        },
        "comm": {"d_prime": 1.1},
        "nasatlx": {
            "raw_tlx": 55.0,
            "legacy_subscale_sum_0_60": 55.0,
            "rtlx_mean_0_100": 91.6667,
            "confirmatory_eligible": True,
        },
        "bedford": {"value": 4},
        "isa": {"mean": 2.5},
    }
    pairs = dict(extract_long_metrics(record))
    assert pairs["sysmon_d_prime"] == 2.5
    assert pairs["sysmon_dprime_observed_v2"] == 2.1
    assert pairs["sysmon_dprime_estimated_v1"] == 2.5
    assert pairs["sysmon_hit_rate"] == 0.9
    assert pairs["comm_d_prime"] == 1.1
    assert pairs["nasatlx_raw_tlx"] == 55.0
    assert pairs["nasatlx_rtlx_mean_0_100"] == 91.6667
    assert pairs["nasatlx_legacy_sum_0_60"] == 55.0
    assert pairs["bedford"] == 4.0
    assert pairs["isa_mean"] == 2.5
    assert "sysmon_mean_rt_ms" not in pairs  # null omitted
    assert set(pairs) <= set(METRIC_KEYS)


def test_extract_handles_missing_sections():
    assert extract_long_metrics({}) == []


def test_observed_dprime_metadata_requires_ok_block_provenance_even_if_record_claims_eligible():
    record = {
        "scientific_source_status": "authoritative_event_stream_reconciled",
        "sysmon": {"observed_confirmatory_eligible": True},
    }
    assert metric_metadata(
        "sysmon_dprime_observed_v2",
        record,
        provenance_validation_status="warning",
    )["confirmatory_eligible"] is False
    assert metric_metadata(
        "sysmon_dprime_observed_v2",
        record,
        provenance_validation_status="ok",
    )["confirmatory_eligible"] is True


def test_observed_hit_rate_metadata_requires_reconciled_opportunity_evidence():
    record = {
        "scientific_source_status": "authoritative_event_stream_reconciled",
        "sysmon": {"observed_confirmatory_eligible": False, "hit_rate": 0.5},
    }
    assert metric_metadata(
        "sysmon_hit_rate",
        record,
        provenance_validation_status="ok",
    )["confirmatory_eligible"] is False

    record["sysmon"]["observed_confirmatory_eligible"] = True
    assert metric_metadata(
        "sysmon_hit_rate",
        record,
        provenance_validation_status="ok",
    )["confirmatory_eligible"] is True


def test_sysmon_rt_metadata_requires_reconciled_human_opportunity_evidence():
    record = {
        "scientific_source_status": "authoritative_event_stream_reconciled",
        "sysmon": {"observed_confirmatory_eligible": False, "mean_rt_ms": 900},
    }
    assert metric_metadata(
        "sysmon_mean_rt_ms", record, provenance_validation_status="ok"
    )["confirmatory_eligible"] is False

    record["sysmon"]["observed_confirmatory_eligible"] = True
    assert metric_metadata(
        "sysmon_mean_rt_ms", record, provenance_validation_status="ok"
    )["confirmatory_eligible"] is True


def test_comm_dprime_is_v2_descriptive_even_with_valid_block_provenance():
    metadata = metric_metadata(
        "comm_d_prime",
        {"comm": {"observed_opportunity_reconciled": True}},
        provenance_validation_status="ok",
    )

    assert metadata["metric_version"] == "2"
    assert metadata["confirmatory_eligible"] is False


def test_legacy_csv_source_cannot_be_upgraded_to_confirmatory_by_a_manifest():
    metadata = metric_metadata(
        "sysmon_dprime_observed_v2",
        {
            "scientific_source_status": (
                "legacy_csv_derived_not_reconciled_to_authoritative_event_stream"
            ),
            "sysmon": {"observed_confirmatory_eligible": True},
        },
        provenance_validation_status="ok",
    )

    assert metadata["confirmatory_eligible"] is False
    assert metadata["scientific_source_status"] == (
        "legacy_csv_derived_not_reconciled_to_authoritative_event_stream"
    )


def _enroll_and_ingest(client, sample_csv_bytes):
    client.post("/participants", json={"id": "P01", "enrollment_date": "2026-06-01"})
    files = {"file": ("a.csv", sample_csv_bytes(misses=(5.0, 25.0), raw_tlx=60.0), "text/csv")}
    data = {"participant_id": "P01", "visit_ordinal": "1", "workload_level": "LOW"}
    assert client.post("/ingest", files=files, data=data).status_code == 201


def test_metrics_long_endpoint(client, sample_csv_bytes):
    _enroll_and_ingest(client, sample_csv_bytes)
    rows = client.get("/metrics/long").json()
    assert rows, "expected long rows"
    r0 = rows[0]
    assert set(r0) == {
        "participant_id", "visit_ordinal", "workload_level", "metric", "value",
        "metrics_schema_version", "metric_version", "scientific_source_status",
        "confirmatory_eligible",
    }
    tlx = [r for r in rows if r["metric"] == "nasatlx_raw_tlx"]
    assert tlx and tlx[0]["value"] == 36.0
    assert tlx[0]["confirmatory_eligible"] is False
    rtlx = [r for r in rows if r["metric"] == "nasatlx_rtlx_mean_0_100"]
    assert rtlx and rtlx[0]["value"] == 60.0
    assert rtlx[0]["confirmatory_eligible"] is False
    assert tlx[0]["participant_id"] == "P01" and tlx[0]["visit_ordinal"] == 1
    # filter works
    assert client.get("/metrics/long", params={"participant_id": "P99"}).json() == []
