from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import sys

import pytest

from launch_contract import LaunchContractError, parse_launch_contract


def test_new_launch_contract_requires_all_synchronized_arguments(tmp_path: Path) -> None:
    scenario = tmp_path / "low.txt"
    scenario.write_text("0:00:00;system;pause\n", encoding="utf-8")

    contract = parse_launch_contract(
        [
            "--scenario",
            str(scenario),
            "--session-id",
            "de4ad40d-7cbb-4b2a-a4c6-9f839a086c4e",
            "--output-dir",
            str(tmp_path / "run"),
        ]
    )

    assert contract is not None
    assert contract.scenario == scenario.resolve()
    assert contract.output_csv == (tmp_path / "run" / "openmatb-session.csv").resolve()
    assert contract.events_jsonl == (tmp_path / "run" / "openmatb-events.jsonl").resolve()


def test_legacy_selector_and_replay_arguments_remain_untouched() -> None:
    assert parse_launch_contract([]) is None
    assert parse_launch_contract(["-r", "17"]) is None
    with pytest.raises(LaunchContractError, match="synchronized_arguments_required"):
        parse_launch_contract(["--scenario", "only-one.txt"])


def test_logger_keeps_six_column_csv_and_emits_synchronized_jsonl(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_csv = tmp_path / "openmatb-session.csv"
    events_jsonl = tmp_path / "openmatb-events.jsonl"
    monkeypatch.setenv("OPENMATB_OUTPUT_CSV", str(output_csv))
    monkeypatch.setenv("OPENMATB_EVENTS_JSONL", str(events_jsonl))
    monkeypatch.setenv(
        "OPENMATB_SESSION_ID",
        "de4ad40d-7cbb-4b2a-a4c6-9f839a086c4e",
    )
    fsynced_descriptors: list[int] = []
    monkeypatch.setattr(os, "fsync", fsynced_descriptors.append)
    from core.logger import Logger

    logger = Logger()
    logger.set_scenario_time(12.5)
    logger.record_boundary("scenario_started")
    logger.log_performance("sysmon", "miss", float("nan"))
    logger.record_input("keyboard", "F1", "press")
    logger.record_boundary("scenario_finished")
    logger.close()

    with output_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert list(rows[0]) == [
        "logtime",
        "scenario_time",
        "type",
        "module",
        "address",
        "value",
    ]
    raw_events = events_jsonl.read_text(encoding="utf-8")
    assert "NaN" not in raw_events
    events = [json.loads(line) for line in raw_events.splitlines()]
    assert [event["sequence"] for event in events] == [1, 2, 3, 4]
    assert all(
        event["schema_version"] == "openmatb-synchronized-event-v2"
        for event in events
    )
    assert events[0]["event"] == "scenario_started"
    assert events[0]["scenario_time"] == 12.5
    assert isinstance(events[0]["received_monotonic_ns"], str)
    assert events[0]["received_monotonic_ns"].isdigit()
    assert isinstance(events[0]["received_utc_ns"], str)
    assert events[1]["row"]["value"] is None
    assert events[2]["row"]["type"] == "input"
    assert events[3]["event"] == "scenario_finished"
    assert all(event["session_id"] == "de4ad40d-7cbb-4b2a-a4c6-9f839a086c4e" for event in events)
    assert fsynced_descriptors

    # Exercise the exact cross-repository contract: records written by the
    # native OpenMATB logger must be accepted by the backend's incremental
    # reader without a test-only translation layer.
    repository_root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(repository_root))
    from matb_integration.openmatb_events import OpenMATBEventTail

    parsed = OpenMATBEventTail(
        events_jsonl,
        session_id="de4ad40d-7cbb-4b2a-a4c6-9f839a086c4e",
    ).read_new()
    assert [event.get("event") for event in parsed if "event" in event] == [
        "scenario_started",
        "scenario_finished",
    ]


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory fsync contract")
def test_logger_fsyncs_directory_after_creating_each_capture_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_csv = tmp_path / "capture" / "openmatb-session.csv"
    events_jsonl = tmp_path / "capture" / "openmatb-events.jsonl"
    output_csv.parent.mkdir()
    monkeypatch.setenv("OPENMATB_OUTPUT_CSV", str(output_csv))
    monkeypatch.setenv("OPENMATB_EVENTS_JSONL", str(events_jsonl))

    import core.logger as logger_module

    synced: list[Path] = []
    monkeypatch.setattr(
        logger_module,
        "_sync_directory",
        lambda path: synced.append(Path(path)),
    )
    logger = logger_module.Logger()
    logger.close()

    assert synced.count(output_csv.parent) == 2
