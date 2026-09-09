"""Recompute exported evidence offline; ZIP members are never extracted."""
import argparse
import hashlib
import json
import zipfile

from .contracts import MAX_STREAM_BYTES, strict_json
from .reconcile import reconcile


def verify_bundle(path: str) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > 12:
            raise ValueError("duplicate or excessive bundle members")
        if any(info.file_size > MAX_STREAM_BYTES for info in archive.infolist()):
            raise ValueError("bundle member too large")
        checksums = strict_json(archive.read("checksums.json"))
        if set(names) != {*checksums, "checksums.json"}:
            raise ValueError("bundle member inventory mismatch")
        files = {name: archive.read(name) for name in checksums}
        for name, content in files.items():
            if hashlib.sha256(content).hexdigest() != checksums[name]:
                raise ValueError(f"bundle checksum mismatch: {name}")
    sources = {}
    for role in ("capture_manifest", "scenario_manifest", "events", "timing", "legacy_csv", "runtime_envelope"):
        suffix = "jsonl" if role in {"events", "timing", "runtime_envelope"} else "csv" if role == "legacy_csv" else "json"
        name = f"sources/{role}.{suffix}"
        if name in files:
            sources[role] = files[name]
    result = reconcile(sources)
    original = strict_json(files["report.json"])
    previous = original.get("reconciliation")
    if previous is None or previous["fingerprint"] != result["fingerprint"]:
        raise ValueError("recomputed evidence fingerprint differs from export")
    for actual, expected in zip(sorted(result["metrics"], key=lambda m: m["metric"]), sorted(original["metrics"], key=lambda m: m["metric"])):
        for key in ("metric", "value", "descriptive_value", "status", "confirmatory_eligible", "exclusion_reasons", "metric_version", "definition", "timing_basis", "physical_timing_qualification", "human_calibration"):
            if actual[key] != expected[key]:
                raise ValueError(f"recomputed metric differs: {actual['metric']}.{key}")
        sources = [{"stream": stream, "record_id": rid}
                   for stream, key in (("events", "source_event_ids"), ("timing", "source_observation_ids"))
                   for rid in dict.fromkeys(actual[key])]
        if sources != expected.get("sources"):
            raise ValueError(f"recomputed metric source links differ: {actual['metric']}")
    if len(result["metrics"]) != len(original["metrics"]):
        raise ValueError("metric inventory differs")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle")
    args = parser.parse_args()
    result = verify_bundle(args.bundle)
    print(json.dumps({"verified": True, "fingerprint": result["fingerprint"],
                      "metrics": len(result["metrics"]), "status": result["status"]}))


if __name__ == "__main__":
    main()
