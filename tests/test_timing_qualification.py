from __future__ import annotations

from matb_integration.qualification.timing import analyze_timing_records, distribution


def _rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for modality in ("visual", "audio", "input"):
        for index in range(200):
            row = {
                "event_id": f"{modality}-{index}",
                "modality": modality,
                "device_id": f"{modality}-device",
                "run_id": f"run-{index % 3}",
            }
            if modality == "input":
                row.update({"physical_input_s": "1.000", "response_s": "1.006"})
            else:
                row.update({"dispatch_s": "1.000", "physical_s": "1.008", "lsl_s": "1.009"})
            rows.append(row)
    return rows


def test_distribution_reports_signed_latency() -> None:
    summary = distribution([-2.0, 1.0, 4.0])
    assert summary["median"] == 1.0
    assert summary["min"] == -2.0
    assert summary["max"] == 4.0


def test_matched_timing_records_pass_explicit_limits() -> None:
    result = analyze_timing_records(
        _rows(),
        rig={
            "rig_id": "rig-a",
            "os": "Windows 11",
            "display": "display-a-144hz",
            "audio_device": "audio-a",
            "input_device": "joystick-a",
        },
        use_tier="block_plus_physiology",
        preregistered_limits={
            "visual": {"dispatch_to_physical_ms": {"max_p95_ms": 10}},
            "audio": {"dispatch_to_physical_ms": {"max_p95_ms": 10}},
            "input": {"physical_input_to_response_ms": {"max_p95_ms": 10}},
        },
        representative_full_block_recorded=True,
        source_commit="deadbeef",
    )
    assert result["status"] == "PASS"
    assert all(item["n"] == 200 for item in result["measurement_summaries"])


def test_missing_physical_event_fails_closed() -> None:
    rows = _rows()
    rows[0]["physical_s"] = ""
    result = analyze_timing_records(
        rows,
        rig={
            "rig_id": "rig-a",
            "os": "Windows 11",
            "display": "display-a",
            "audio_device": "audio-a",
            "input_device": "joystick-a",
        },
        use_tier="block_plus_physiology",
        preregistered_limits={
            "visual": {"dispatch_to_physical_ms": {"max_p95_ms": 10}},
            "audio": {"dispatch_to_physical_ms": {"max_p95_ms": 10}},
            "input": {"physical_input_to_response_ms": {"max_p95_ms": 10}},
        },
        representative_full_block_recorded=True,
        source_commit="deadbeef",
    )
    assert result["status"] == "FAIL"
    assert "unmatched_events:visual" in result["issues"]
