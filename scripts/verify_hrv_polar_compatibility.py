"""Compare MATB against an explicit local HRV checkout without loading either app."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from matb_integration.physiology.hrs import parse_heart_rate_measurement


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify(repo: Path) -> dict:
    folder = repo / "app/research_workspace/polar"
    package = types.ModuleType("hrv_reference")
    package.__path__ = [str(folder)]
    sys.modules["hrv_reference"] = package
    load_module("hrv_reference.models", folder / "models.py")
    reference = load_module("hrv_reference.hrs_parser", folder / "hrs_parser.py")
    count = 0
    # All flag combinations and the entire unsigned 16-bit RR range, including
    # exact fractional milliseconds. No real physiological samples are used.
    for flags in range(32):
        payload = bytes([flags]) + (struct.pack("<H", 300) if flags & 1 else bytes([60]))
        if flags & 8:
            payload += struct.pack("<H", 123)
        chunks = range(0, 65536, 128) if flags & 16 else [0]
        for start in chunks:
            frame = payload + (struct.pack("<128H", *range(start, start + 128)) if flags & 16 else b"")
            ours = parse_heart_rate_measurement(frame)
            theirs = reference.parse_heart_rate_measurement(frame)
            assert ours.heart_rate_bpm == theirs.heart_rate_bpm
            assert ours.rr_ticks_1024 == tuple(rr.ticks_1024 for rr in theirs.rr_values)
            assert ours.rr_ms == tuple(rr.milliseconds for rr in theirs.rr_values)
            assert ours.sensor_contact_supported == theirs.sensor_contact_supported
            assert ours.sensor_contact_detected == theirs.sensor_contact_detected
            assert ours.energy_expended_kj == theirs.energy_expended_kj
            count += 1
    reader_path = repo / "app/operational_clinical/polar_rr.py"
    reader = load_module("hrv_rr_text_reference", reader_path)
    samples = (1000.0, 1000.9765625, 999.0234375, 875.0)
    for content in ("\n".join(map(str, samples)), "beat_index,rr_ms\n" + "\n".join(f"{i},{rr}" for i, rr in enumerate(samples))):
        parsed = reader.parse_polar_rr_text(content,
            acquisition_start="2026-10-02T12:00:00Z", unit="milliseconds")
        assert parsed.rr_ms == samples
    revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    return dict(hrv_revision=revision, valid_packets_compared=count, all_rr_uint16_values=True,
                exact_rr_ms_match=True, txt_and_trace_csv_import_match=True,
                single_column_csv_with_header_supported=False,
                files_sha256={str(path.relative_to(repo)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in [folder / "hrs_parser.py", reader_path, folder / "backend.py"]},
                scope="software parser and text-import compatibility; physical acquisition and analysis equivalence not established",
                known_difference="MATB rejects trailing bytes without the RR flag; HRV protected parser ignores them. HRV text reader rejects single-column CSV with a header; use the headerless TXT per continuous segment. HRV importer rejects RR outside 200-3000 ms; MATB exports positive raw RR unchanged.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hrv-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify(args.hrv_repo.resolve())
    content = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    print(content)
