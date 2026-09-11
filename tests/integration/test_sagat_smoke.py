"""Integration smoke test for the SAGAT freeze-probe service.

Covers the pieces we can fully automate without a human-in-the-loop session:
  1. End-to-end scenario generation with include_sagat=True via build_block_scenario.
  2. Per-freeze probe files are emitted and parse cleanly via load_probes.
  3. The block manifest JSON is written with the expected schema.
  4. The scenario .txt contains the expected sagat;filename; / sagat;start pairs.

The bundled checkout has no SAGAT runtime plugin. Native CSV/replay timing is
verified with synthetic data; actual SAGAT UI execution remains a separate,
explicit missing-capability exclusion, not evidence of participant validation.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

REPO_ROOT = Path(__file__).resolve().parents[2]
QUESTIONNAIRE_DIR = REPO_ROOT / "matb_integration" / "questionnaires"
EN_BANK = QUESTIONNAIRE_DIR / "sagat_generic_en.txt"
ES_BANK = QUESTIONNAIRE_DIR / "sagat_generic_es.txt"


def _xvfb_available() -> bool:
    return shutil.which("xvfb-run") is not None


def test_scenario_emission_with_sagat_end_to_end(tmp_path: Path) -> None:
    """Generate a full LOW-workload scenario with SAGAT enabled. Verify the
    scenario .txt, all 3 probe files, and the manifest are all written and
    internally consistent."""
    from matb_integration.scenario_builder import build_block_scenario
    from matb_integration.sagat.probe_bank import load_probes
    from aircraft_monitor.research.protocol import WorkloadLevel

    text = build_block_scenario(
        level=WorkloadLevel.LOW,
        block_duration_sec=900,
        seed=42,
        include_sagat=True,
        sagat_bank=EN_BANK,
        sagat_output_dir=tmp_path,
        sagat_n_freezes=3,
        participant_id="SMOKE",
        block_num=1,
    )

    # Scenario .txt contains 3 sagat triggers
    assert text.count("sagat;filename;") == 3
    assert text.count("sagat;start") == 3

    # Manifest exists and has expected schema
    manifest_path = tmp_path / "SMOKE_block1_sagat_manifest.json"
    assert manifest_path.exists(), "Manifest JSON not written"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["participant_id"] == "SMOKE"
    assert manifest["block_num"] == 1
    assert manifest["bank"] == "sagat_generic_en.txt"
    assert len(manifest["freezes"]) == 3

    # All 3 probe files exist and parse, with 3 probes each (1 per SA level)
    import re as _re
    for freeze in manifest["freezes"]:
        probe_file = tmp_path / freeze["probe_file"]
        assert probe_file.exists(), f"Probe file missing: {probe_file}"
        probes = load_probes(probe_file)
        assert len(probes) == 3, f"{probe_file.name}: expected 3 probes, got {len(probes)}"
        levels = sorted(p.sa_level for p in probes)
        assert levels == [1, 2, 3], f"{probe_file.name}: levels {levels}, expected [1,2,3]"

        # Verify the manifest's freeze_id matches the convention the
        # Sagat plugin will derive from the probe filename. The plugin
        # reads "{participant}_block{N}_freeze{M}_(en|es).txt" and emits
        # freeze_id="{participant}_b{N}_f{M}".
        stem = probe_file.stem
        for lang in ("_en", "_es"):
            if stem.endswith(lang):
                stem = stem[:-len(lang)]
                break
        mm = _re.match(r"^(?P<pid>.+)_block(?P<bn>\d+)_freeze(?P<fn>\d+)$", stem)
        assert mm, f"probe filename doesn't match canonical pattern: {probe_file.name}"
        expected_freeze_id = f"{mm.group('pid')}_b{mm.group('bn')}_f{mm.group('fn')}"
        assert freeze["freeze_id"] == expected_freeze_id, (
            f"manifest freeze_id={freeze['freeze_id']!r} does not match "
            f"what the Sagat plugin would derive: {expected_freeze_id!r}"
        )


def test_scenario_emission_es_bank(tmp_path: Path) -> None:
    """Same as above but for Spanish bank — verify probe files inherit the
    `_es.txt` suffix and the No sé anchor is present after round-trip."""
    from matb_integration.scenario_builder import build_block_scenario
    from matb_integration.sagat.probe_bank import load_probes
    from aircraft_monitor.research.protocol import WorkloadLevel

    build_block_scenario(
        level=WorkloadLevel.LOW,
        block_duration_sec=900,
        seed=42,
        include_sagat=True,
        sagat_bank=ES_BANK,
        sagat_output_dir=tmp_path,
        sagat_n_freezes=3,
        participant_id="SMOKE",
        block_num=1,
    )

    manifest = json.loads((tmp_path / "SMOKE_block1_sagat_manifest.json").read_text(encoding="utf-8"))
    assert manifest["bank"] == "sagat_generic_es.txt"

    for freeze in manifest["freezes"]:
        probe_file = tmp_path / freeze["probe_file"]
        assert probe_file.name.endswith("_es.txt")
        probes = load_probes(probe_file)
        for p in probes:
            assert "No sé" in p.options
            assert "Unknown" not in p.options


@pytest.mark.skip(reason="SAGAT runtime plugin is not shipped in the bundled OpenMATB; scenario/probe generation and synthetic native replay are covered separately")
def test_sagat_native_plugin_execution():
    """Requires a separately supplied/qualified SAGAT native plugin, not a local CSV."""


def test_synthetic_freeze_csv_drives_native_replay_timing(tmp_path):
    """The actual LogReader/ReplayScheduler map a frozen segment without a GUI."""
    import subprocess
    csv = tmp_path / 'synthetic replay ñ.csv'
    csv.write_text('logtime,scenario_time,type,module,address,value\n'
                   '100,0,event,sysmon,start,\n'
                   '101,1,event,sysmon,stop,\n'
                   '102,1,input,keyboard,key,SPACE\n'
                   '104,1,input,keyboard,key,SPACE\n'
                   '105,2,event,sysmon,start,\n', encoding='utf-8')
    native = REPO_ROOT / 'openmatb'
    code = """import runpy, sys
from pathlib import Path
native=Path(sys.argv[1]);sys.path.insert(0,str(native))
runpy.run_path(str(native/'tests/conftest.py'))
from core.logreader import LogReader
from core.replayscheduler import ReplayScheduler
reader=LogReader(session_path=sys.argv[2])
assert len(reader.keyboard_inputs)==2
assert len(reader.contents)==2
assert reader.session_duration==5
replay=object.__new__(ReplayScheduler)
replay.logreader=reader
replay.replay_time=3
replay.update_timers(0.1)
assert replay.scenario_time==1
replay.replay_time=5
replay.update_timers(0.1)
assert replay.scenario_time==2
print('synthetic native replay timing passed; no SAGAT plugin or human capture')
"""
    result = subprocess.run([sys.executable, '-c', code, str(native), str(csv)],
                            cwd=native, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
