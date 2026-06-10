"""Integration smoke test for the SAGAT freeze-probe service.

Covers the pieces we can fully automate without a human-in-the-loop session:
  1. End-to-end scenario generation with include_sagat=True via build_block_scenario.
  2. Per-freeze probe files are emitted and parse cleanly via load_probes.
  3. The block manifest JSON is written with the expected schema.
  4. The scenario .txt contains the expected sagat;filename; / sagat;start pairs.

The actual OpenMATB-runtime portion (Xvfb headless + key-injection driving
the Sagat plugin through a full freeze) is marked skip until we have a
recorded fixture session to replay. OpenMATB's replay mode is session-replay
(load a CSV, replay it), not live-key-injection — so the runtime test needs
a previously-recorded participant CSV that doesn't yet exist.
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


@pytest.mark.skip(
    reason=(
        "Full Xvfb + OpenMATB replay run requires a recorded fixture session. "
        "OpenMATB replay mode is session-replay (loads a previous CSV), not "
        "live-key-injection. Record a real SAGAT session first, save it under "
        "tests/integration/fixtures/, then unskip this test and adapt it to "
        "drive ReplayScheduler against that fixture."
    )
)
def test_sagat_headless_runtime_smoke(tmp_path: Path) -> None:
    """Placeholder for the runtime SAGAT smoke test.

    TODO: when a recorded SAGAT session CSV exists at
    tests/integration/fixtures/sagat_session_smoke.csv:
      1. Invoke openmatb under xvfb-run with --replay <session_id>
      2. Wait for the run to complete
      3. Parse the resulting session.csv
      4. Assert at least 1 sagat;start and 1 sagat;is_correct row appear
      5. Run log_converter._sagat_metric on the parsed rows
      6. Assert n_freezes_executed >= 1 and overall_pct is computed
    """
