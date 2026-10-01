"""Installer readiness must not fetch dependencies on an offline restart."""
from pathlib import Path
import subprocess
import sys
import zipfile

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


def test_readiness_and_export_select_only_wheels_compatible_with_runtime(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / 'webui/backend'))
    from app import study_analysis_bundle as bundle
    from packaging.tags import sys_tags
    tag = next(sys_tags())
    incompatible = tmp_path / 'pydantic_core-1.0-cp999-cp999-win_amd64.whl'
    compatible = tmp_path / f'pydantic_core-1.0-{tag}.whl'
    for path in (incompatible, compatible):
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('placeholder', 'test inventory')
    assert bundle.compatible_wheels(tmp_path, 'pydantic_core', '1.0') == [compatible]
    monkeypatch.setattr(bundle, 'dependency_versions', lambda _: {'pydantic_core': '1.0'})
    monkeypatch.setenv('MATB_DESCRIPTIVE_WHEELHOUSE', str(tmp_path))
    files, _ = bundle.implementation_artifacts({'pvt'})
    assert [name for name in files if name.startswith('wheels/')] == ['wheels/' + compatible.name]
    compatible.unlink()
    assert bundle.compatible_wheels(tmp_path, 'pydantic_core', '1.0') == []


def test_check_rejects_matching_version_wheels_for_another_runtime(tmp_path):
    sys.path.insert(0, str(ROOT / 'webui/backend'))
    from app.study_analysis_bundle import dependency_versions
    for name, version in dependency_versions({'pvt'}).items():
        path = tmp_path / f"{name.replace('-', '_')}-{version}-cp999-cp999-win_amd64.whl"
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('placeholder', 'incompatible inventory')
    result = subprocess.run([sys.executable, str(ROOT / 'tools/prepare_study_wheels.py'),
                             str(tmp_path), '--check', '--instruments', 'pvt'],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert 'pydantic_core' in result.stdout
