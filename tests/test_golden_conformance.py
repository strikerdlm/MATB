from __future__ import annotations

from matb_integration.qualification.golden import run_scenario_builder_golden


def test_frozen_scenario_builder_golden_suite_passes() -> None:
    report = run_scenario_builder_golden(source_commit="deadbeef")
    assert report["status"] == "PASS"
    assert len(report["checks"]) == 9
    assert all(check["evidence_class"] == "deterministic_software" for check in report["checks"])
    assert "human equivalence" in report["claim_boundary"]
