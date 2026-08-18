#!/usr/bin/env python3
"""Run and evaluate the workstation Liftoff telemetry acceptance soak."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import time

from matb_integration.liftoff.quality import assess_quality
from matb_integration.liftoff.receiver import LiftoffUdpReceiver
from matb_integration.recording.artifacts import write_json_artifact


def evaluate_acceptance(evidence: dict[str, object]) -> dict[str, object]:
    criteria = {
        "median_loss_below_1_pct": float(evidence.get("median_loss_pct", 100.0)) < 1.0,
        "zero_schema_errors": int(evidence.get("schema_errors", 1)) == 0,
        "zero_unrecoverable_bundles": int(evidence.get("unrecoverable_bundles", 1)) == 0,
        "no_clock_step": evidence.get("clock_step_detected") is False,
        "udp_interruption_recovered": evidence.get("udp_interruption_recovered") is True,
        "second_machine_checksum": evidence.get("second_machine_checksum_verified") is True,
    }
    failed = [name for name, passed in criteria.items() if not passed]
    return {"passed": not failed, "criteria": criteria, "failed_criteria": failed}


async def run_soak(*, port: int, duration_seconds: float, expected_rate_hz: float):
    receiver = LiftoffUdpReceiver(host="127.0.0.1", port=port)
    await receiver.start()
    packets = []
    deadline = time.monotonic() + duration_seconds
    try:
        while time.monotonic() < deadline:
            try:
                received = await asyncio.wait_for(receiver.next_packet(), timeout=1.0)
            except TimeoutError:
                continue
            packets.append(received.packet)
    finally:
        await receiver.stop()
    health = receiver.health()
    return assess_quality(packets, health, expected_rate_hz=expected_rate_hz), health


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default="astra-2026", choices=("astra-2026",))
    parser.add_argument("--duration-min", type=float, default=30.0)
    parser.add_argument("--port", type=int, default=9001)
    parser.add_argument("--expected-rate-hz", type=float, default=60.0)
    parser.add_argument("--unrecoverable-bundles", type=int, default=0)
    parser.add_argument("--udp-interruption-recovered", action="store_true")
    parser.add_argument("--second-machine-checksum-verified", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.duration_min <= 0:
        raise SystemExit("duration-min must be positive")
    quality, health = asyncio.run(run_soak(
        port=args.port,
        duration_seconds=args.duration_min * 60.0,
        expected_rate_hz=args.expected_rate_hz,
    ))
    evidence = {
        "report_version": "liftoff-acceptance-v1",
        "protocol_id": args.protocol,
        "executed_utc": datetime.now(timezone.utc).isoformat(),
        "duration_min": args.duration_min,
        "median_loss_pct": quality.loss_pct,
        "maximum_gap_s": quality.maximum_gap_s,
        "schema_errors": health.invalid_packet_count,
        "queue_overflows": health.overflow_count,
        "clock_step_detected": health.clock_step_detected,
        "unrecoverable_bundles": args.unrecoverable_bundles,
        "udp_interruption_recovered": args.udp_interruption_recovered,
        "second_machine_checksum_verified": args.second_machine_checksum_verified,
    }
    report = {**evidence, **evaluate_acceptance(evidence)}
    write_json_artifact(args.output, report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
