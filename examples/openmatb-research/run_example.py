"""Run a deterministic, offline OpenMATB research-data tour."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from matb_integration.log_converter import convert_session, parse_csv
from matb_integration.scenario_builder import WorkloadLevel
from matb_integration.scenario_manifest import sha256_file
from matb_integration.suhir.pipeline import fit_participant


PARTICIPANT_ID = "SYNTH-P01"
SEED = 42
LEVELS = (
    ("LOW", WorkloadLevel.LOW, "low.csv"),
    ("MEDIUM", WorkloadLevel.MEDIUM, "medium.csv"),
    ("HIGH", WorkloadLevel.HIGH, "high.csv"),
)


def _validate_generated_manifests(scenarios_dir: Path) -> list[Path]:
    manifests = sorted(scenarios_dir.glob("*.txt.manifest.json"))
    if len(manifests) != len(LEVELS):
        raise RuntimeError("scenario generator did not produce three manifests")
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        scenario = manifest.get("scenario", {})
        scenario_path = manifest_path.parent / Path(str(scenario.get("filename", ""))).name
        if not scenario_path.is_file() or scenario.get("sha256") != sha256_file(scenario_path):
            raise RuntimeError(f"manifest checksum mismatch: {manifest_path.name}")
    return manifests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios_dir = output_dir / "scenarios"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "matb_integration.scenario_builder",
            "--output-dir",
            str(scenarios_dir),
            "--block-duration",
            "900",
            "--seed",
            str(SEED),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    scenario_manifests = _validate_generated_manifests(scenarios_dir)

    fixtures_dir = Path(__file__).parent / "fixtures"
    blocks: dict[str, tuple[dict[str, object], list[dict[str, str]]]] = {}
    metrics_path = output_dir / "metrics.jsonl"
    with metrics_path.open("w", encoding="utf-8") as metrics_file:
        for level_name, _level, fixture_name in LEVELS:
            fixture_path = fixtures_dir / fixture_name
            record = convert_session(
                fixture_path,
                participant_id=PARTICIPANT_ID,
                block_name=f"synthetic_{level_name.lower()}",
                workload_level=level_name,
            )
            rows = parse_csv(fixture_path)
            blocks[level_name] = (record, rows)
            metrics_file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    suhir_path = output_dir / "suhir.json"
    suhir_path.write_text(
        json.dumps(fit_participant(PARTICIPANT_ID, blocks), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )

    scenario_paths = sorted(scenarios_dir.glob("*.txt"))
    for path in [*scenario_paths, *scenario_manifests, metrics_path, suhir_path]:
        print(path.relative_to(output_dir))
    print("External OpenMATB was not started.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
