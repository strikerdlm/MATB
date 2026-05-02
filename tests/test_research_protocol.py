"""Tests for MATB-inspired research protocol execution."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from aircraft_monitor.research import (
    AutomationMode,
    ResearchExperimentRunner,
    ResearchModality,
    ResearchProtocol,
    WorkloadLevel,
)


def test_default_protocol_uses_ordered_workload_blocks() -> None:
    """Default protocol should provide a low/medium/high demand ladder."""
    protocol = ResearchProtocol.default(modality=ResearchModality.UAS, seed=123)

    assert [block.workload for block in protocol.blocks] == [
        WorkloadLevel.LOW,
        WorkloadLevel.MEDIUM,
        WorkloadLevel.HIGH,
    ]
    assert protocol.blocks[0].automation_mode == AutomationMode.MANUAL
    assert protocol.blocks[2].automation_mode == AutomationMode.FORCED_HANDOFF
    assert protocol.blocks[0].max_events < protocol.blocks[2].max_events


def test_research_runner_writes_jsonl_and_summary(tmp_path: Path) -> None:
    """A headless UAS experiment should produce machine-readable research files."""
    runner = ResearchExperimentRunner(
        event_delay=0.05,
        headless=True,
        output_dir=tmp_path,
        console=Console(record=True),
    )

    paths = runner.run_default_protocol(
        participant_id="pilot/test",
        session_id="session:001",
        modality=ResearchModality.UAS,
        seed=7,
    )

    assert paths.events_jsonl.exists()
    assert paths.summary_json.exists()
    assert "pilot-test" in paths.run_dir.name
    assert "session-001" in paths.run_dir.name

    lines = paths.events_jsonl.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    event_records = [record for record in records if record["record_type"] == "event"]
    probe_records = [
        record for record in event_records if record["title"] == "ISA WORKLOAD PROBE"
    ]

    assert len(event_records) > 0
    assert len(probe_records) > 0
    assert {record["workload"] for record in event_records} == {"low", "medium", "high"}

    summary = json.loads(paths.summary_json.read_text(encoding="utf-8"))
    assert summary["event_count"] == len(event_records)
    assert summary["modality"] == "uas"
