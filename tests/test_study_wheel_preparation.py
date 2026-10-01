"""Installer readiness must not fetch dependencies on an offline restart."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_missing_offline_wheels_fail_without_creating_output(tmp_path):
    target = tmp_path / "absent wheels"
    result = subprocess.run([sys.executable, str(ROOT / "tools/prepare_study_wheels.py"),
                             str(target), "--check", "--instruments", "pvt"],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "missing" in result.stdout.lower()
    assert not target.exists()


def test_instrument_with_no_dependencies_needs_no_wheel_download(tmp_path):
    target = tmp_path / "absent wheels"
    result = subprocess.run([sys.executable, str(ROOT / "tools/prepare_study_wheels.py"),
                             str(target), "--check", "--instruments", "questionnaire"],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert not target.exists()
