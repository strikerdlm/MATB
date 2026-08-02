from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_cli_run_is_repeatable(tmp_path: Path) -> None:
    args = [sys.executable, "-m", "matb_integration.suas.cli", "run", "scenarios/suas/reference_area_search.yaml", "--block", "LOW", "--ticks", "100"]
    first = subprocess.run(args, check=True, capture_output=True, text=True)
    second = subprocess.run(args, check=True, capture_output=True, text=True)
    assert json.loads(first.stdout)["state_sha256"] == json.loads(second.stdout)["state_sha256"]


def test_cli_validate_prints_normalized_identity() -> None:
    result = subprocess.run([sys.executable, "-m", "matb_integration.suas.cli", "validate", "scenarios/suas/reference_area_search.yaml"], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout)["scenario_id"] == "reference_area_search"
