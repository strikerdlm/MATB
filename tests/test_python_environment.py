"""Detect incompatible packages before a Windows launcher reports readiness."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts/check_python_environment.py"


def check(requirements):
    return subprocess.run([sys.executable, str(CHECKER), "--requirements", str(requirements)],
                          capture_output=True, text=True, check=False)


def test_rejects_installed_package_below_required_version(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("packaging>=999\n")
    result = check(requirements)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["ready"] is False
    assert report["issues"][0]["package"] == "packaging"
    assert report["issues"][0]["reason"] == "incompatible_version"


def test_resolves_nested_requirements_relative_to_their_file(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "deps.txt").write_text("packaging>=1\n")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("-r nested/deps.txt\n")
    result = check(requirements)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ready"] is True


def test_reports_missing_package_and_respects_platform_markers(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text('matb-nonexistent-test-package>=1\nother-missing; python_version < "1"\n')
    result = check(requirements)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert [issue["package"] for issue in report["issues"]] == ["matb-nonexistent-test-package"]


def test_rejects_unreadable_requirements(tmp_path):
    result = check(tmp_path / "absent.txt")
    assert result.returncode == 1
    assert json.loads(result.stdout)["ready"] is False
