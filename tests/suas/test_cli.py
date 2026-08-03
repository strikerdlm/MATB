from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _record(tmp_path: Path, *, ticks: int = 3) -> Path:
    run_dir = tmp_path / "recorded"
    result = subprocess.run(
        [
            sys.executable, "-m", "matb_integration.suas.cli", "record",
            "scenarios/suas/reference_area_search.yaml", "--block", "LOW",
            "--ticks", str(ticks), "--output", str(run_dir), "--session-id", "cli-test",
        ], check=True, capture_output=True, text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["replay_status"] == "match"
    return run_dir


def test_cli_run_is_repeatable(tmp_path: Path) -> None:
    args = [sys.executable, "-m", "matb_integration.suas.cli", "run", "scenarios/suas/reference_area_search.yaml", "--block", "LOW", "--ticks", "100"]
    first = subprocess.run(args, check=True, capture_output=True, text=True)
    second = subprocess.run(args, check=True, capture_output=True, text=True)
    assert json.loads(first.stdout)["state_sha256"] == json.loads(second.stdout)["state_sha256"]


def test_cli_validate_prints_normalized_identity() -> None:
    result = subprocess.run([sys.executable, "-m", "matb_integration.suas.cli", "validate", "scenarios/suas/reference_area_search.yaml"], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout)["scenario_id"] == "reference_area_search"


def test_cli_record_and_verify_round_trip(tmp_path: Path) -> None:
    run_dir = _record(tmp_path)
    first = json.loads((run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert first["kind"] == "lifecycle"
    assert first["payload"]["event"] == "session_prepared"
    result = subprocess.run(
        [sys.executable, "-m", "matb_integration.suas.cli", "verify", str(run_dir)],
        check=True, capture_output=True, text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["status"] == "match"
    assert payload["checksums"]["status"] == "match"
    assert payload["replay"]["status"] == "match"
    assert (run_dir / "checksums.sha256").exists()


def test_cli_record_rejects_nonempty_output_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / "existing"
    run_dir.mkdir()
    (run_dir / "keep.txt").write_text("keep", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable, "-m", "matb_integration.suas.cli", "record",
            "scenarios/suas/reference_area_search.yaml", "--block", "LOW",
            "--ticks", "1", "--output", str(run_dir), "--session-id", "cli-test",
        ], capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert (run_dir / "keep.txt").read_text(encoding="utf-8") == "keep"
