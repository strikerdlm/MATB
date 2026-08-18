from __future__ import annotations

from dataclasses import replace

from scripts.capture_liftoff_fixture import CapturedPacket, characterize_packets
from scripts.run_liftoff_acceptance import evaluate_acceptance
from tests.liftoff.test_protocol import valid_payload


def test_characterization_reports_stable_preliminary_profile():
    packets = [
        CapturedPacket(payload=valid_payload(replacement=(0, index / 60.0)), received_monotonic_ns=index * 16_666_667)
        for index in range(120)
    ]

    report = characterize_packets(packets)

    assert report["packet_count"] == 120
    assert report["single_packet_size"] is True
    assert report["packet_sizes"] == {"97": 120}
    assert report["finite_values"] is True
    assert report["simulator_time_monotonic"] is True
    assert report["motor_counts"] == {"4": 120}
    assert report["unresolved"]["coordinate_units"] is True


def test_acceptance_requires_every_hardware_evidence_gate():
    passing = {
        "median_loss_pct": 0.5,
        "schema_errors": 0,
        "unrecoverable_bundles": 0,
        "clock_step_detected": False,
        "udp_interruption_recovered": True,
        "second_machine_checksum_verified": True,
    }

    assert evaluate_acceptance(passing)["passed"] is True
    failing = {**passing, "second_machine_checksum_verified": False}
    result = evaluate_acceptance(failing)
    assert result["passed"] is False
    assert "second_machine_checksum" in result["failed_criteria"]
