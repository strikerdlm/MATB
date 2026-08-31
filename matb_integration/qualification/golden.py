"""Executable deterministic golden cases for the frozen MATB candidate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from aircraft_monitor.research.protocol import WorkloadLevel
from matb_integration.scenario_builder import build_block_scenario

from .contracts import evaluate_conformance, load_profile, sha256_payload

GOLDEN_DIR = Path(__file__).with_name("golden")


def run_scenario_builder_golden(*, source_commit: str) -> dict[str, Any]:
    case = json.loads((GOLDEN_DIR / "scenario-builder-v2.json").read_text(encoding="utf-8"))
    checks: list[dict[str, Any]] = []
    for level in WorkloadLevel:
        expected = case["conditions"][level.name]
        text = build_block_scenario(
            level,
            block_duration_sec=int(expected["block_duration_sec"]),
            seed=int(expected["seed"]),
        )
        observed = {
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "line_count": len(text.splitlines()),
            "event_line_count": sum(
                1 for line in text.splitlines() if line and not line.startswith("#")
            ),
        }
        for field in ("sha256", "line_count", "event_line_count"):
            checks.append(
                {
                    "check_id": f"{case['case_id']}:{level.name}:{field}",
                    "expected": expected[field],
                    "observed": observed[field],
                    "evidence_class": "deterministic_software",
                }
            )
    report = evaluate_conformance(
        load_profile("matb-extended-2.0"), checks, source_commit=source_commit
    )
    report["golden_case_id"] = case["case_id"]
    report.pop("report_sha256", None)
    report["report_sha256"] = sha256_payload(report)
    return report
