from __future__ import annotations

import csv
import io
import json

from app.classic_exports import (
    visit_summary_csv,
    visit_summary_json,
    visit_summary_markdown,
)


def _summary() -> dict:
    return {
        "schema_version": "matb-classic-visit-summary-v1",
        "participant_id": "P01",
        "visit_ordinal": 1,
        "selection_audit": [
            {
                "workload_level": "LOW",
                "previous_attempt_id": "attempt-1",
                "new_attempt_id": "attempt-2",
                "reason_code": "researcher_qc_review",
                "actor": "researcher",
                "changed_at": "2026-08-23T12:00:00+00:00",
            }
        ],
        "workloads": {
            "LOW": {
                "selected_attempt_id": "attempt-2",
                "attempts": [
                    {
                        "session": {
                            "id": "attempt-1",
                            "attempt_number": 1,
                            "status": "INTERRUPTED",
                            "task_validity": "invalid",
                            "physiology_quality": "partial",
                            "failure_reason_code": "participant_requested_stop",
                        },
                        "matb_metrics": {"isa": {"probes": [2.0, 3.0]}},
                        "hrv": {"phases": {}},
                    },
                    {
                        "session": {
                            "id": "attempt-2",
                            "attempt_number": 2,
                            "status": "COMPLETE",
                            "task_validity": "valid",
                            "physiology_quality": "good",
                            "failure_reason_code": None,
                        },
                        "matb_metrics": {"tracking": {"samples": [0.1, 0.2]}},
                        "hrv": {"phases": {}},
                    },
                ],
            }
        },
    }


def test_visit_exports_preserve_all_attempt_metadata_sequences_and_selection_audit() -> None:
    summary = _summary()
    json_document = json.loads(visit_summary_json(summary))
    assert json_document["selection_audit"][0]["reason_code"] == "researcher_qc_review"

    rows = list(
        csv.DictReader(io.StringIO(visit_summary_csv(summary).decode("utf-8")))
    )
    assert any(
        row["attempt_id"] == "attempt-1"
        and row["scope"] == "session"
        and row["metric"] == "failure_reason_code"
        and row["value"] == "participant_requested_stop"
        for row in rows
    )
    assert any(
        row["attempt_id"] == "attempt-1"
        and row["scope"] == "matb_metrics"
        and row["metric"] == "probes.0"
        and row["value"] == "2.0"
        for row in rows
    )
    assert any(
        row["scope"] == "selection_audit"
        and row["metric"] == "reason_code"
        and row["value"] == "researcher_qc_review"
        for row in rows
    )

    markdown = visit_summary_markdown(summary).decode("utf-8")
    assert "Attempt 1" in markdown and "Attempt 2" in markdown
    assert "participant_requested_stop" in markdown
    assert "isa.probes.0" in markdown
    assert "researcher_qc_review" in markdown
